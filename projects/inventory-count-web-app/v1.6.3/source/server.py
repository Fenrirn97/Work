#!/usr/bin/env python3
"""Local, dependency-free Python web server for the Inventory Count Web App."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import mimetypes
import re
import struct
import sys
import threading
import traceback
import uuid
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from inventory_app.comparison import compare_old_new, compare_reference
from inventory_app.cycle import (
    add_movement,
    frozen_reference,
    list_attempts,
    list_movements,
    load_frozen_reference,
    review_cycle_count,
    save_frozen_reference,
    submit_cycle_count,
)
from inventory_app.database import (
    activate_session,
    add_audit,
    all_session_entries,
    catalog_summary,
    comparison_results,
    connect,
    create_session,
    current_session,
    finalize_session,
    init_database,
    last_workbook_summary,
    load_last_workbook,
    replace_catalog_items,
    replace_comparison_results,
    require_draft,
    session_entries,
    session_list,
    search_catalog_items,
    save_last_workbook,
    utc_now,
)
from inventory_app.rules import InventoryError, comparison_key, item_details, validate_entry
from inventory_app.xlsxio import (
    analyze_organized_rows,
    build_inventory_workbook,
    build_organized_rows_workbook,
    extract_organized_rows,
    parse_count_workbook,
    parse_reference_workbook,
)


ROOT = Path(__file__).resolve().parent
STATIC_ROOT = ROOT / "static"
DEFAULT_DATABASE = ROOT / "data" / "inventory.db"
DEFAULT_LOG = ROOT / "data" / "inventory.log"
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_WORKBOOK_BYTES = 25 * 1024 * 1024


class DuplicateEntryError(InventoryError):
    def __init__(self, count: int):
        super().__init__(
            f"This product identity already has {count} count row(s). The comparator totals them automatically."
        )
        self.count = count


def _display_entry(entry: dict[str, Any]) -> dict[str, Any]:
    row = dict(entry)
    row["broken_box"] = bool(row.get("broken_box"))
    row["item_details"] = item_details(row)
    row["calculation"] = (
        f"{row['items_per_box']:,} × {row['boxes']:,} + {row['loose_items']:,}"
        if row["items_per_box"] or row["boxes"]
        else "Loose/imported count"
    )
    return row


def _state(database_path: Path) -> dict[str, Any]:
    with connect(database_path) as connection:
        session = current_session(connection)        raw_entries = session_entries(connection, session["id"])
        identity_counts: dict[str, int] = {}
        for row in raw_entries:
            key = comparison_key(row["model"], row["ram"], row["storage"], row["color"])
            identity_counts[key] = identity_counts.get(key, 0) + 1
        entries = []
        for row in raw_entries:
            displayed = _display_entry(row)
            key = comparison_key(row["model"], row["ram"], row["storage"], row["color"])
            displayed["match_key"] = key
            displayed["identity_count"] = identity_counts.get(key, 1)
            entries.append(displayed)
        reference = frozen_reference(connection, session["id"])
        comparisons = comparison_results(connection, session["id"])
        if reference and session["workflow_status"] == "COUNTING" and raw_entries:
            comparisons = compare_reference(
                raw_entries,
                load_frozen_reference(connection, session["id"]),
                include_missing_reference=False,
            )
        total = sum(int(row["amount"]) for row in entries)
        broken = sum(int(row["amount"]) for row in entries if row["broken_box"])
        latest_values = [
            value
            for value in (
                session.get("approved_at"), session.get("submitted_at"), session.get("reference_loaded_at"),
                session.get("finalized_at"), session.get("created_at"),
                *[row.get("updated_at") for row in raw_entries[:10]],
            )
            if value
        ]
        return {
            "session": session,
            "entries": entries,
            "comparisons": comparisons,
            "sessions": session_list(connection),
            "catalog": catalog_summary(connection),
            "last_workbook": last_workbook_summary(connection),
            "reference": reference,
            "attempts": list_attempts(connection, session["id"]),
            "movements": list_movements(connection),
            "last_saved_at": max(latest_values) if latest_values else session.get("created_at", ""),
            "summary": {
                "rows": len(entries),
                "total_amount": total,
                "broken_amount": broken,
                "matches": sum(row["result"] == "MATCH" for row in comparisons),
                "issues": sum(row["result"] != "MATCH" for row in comparisons),
            },
        }


def _entry_summary(entry: dict[str, Any]) -> str:
    return f"{item_details(entry)} | {entry['color']} | {entry['amount']} | {entry['area']}"


class InventoryRequestHandler(BaseHTTPRequestHandler):
    server_version = "InventoryWebApp/1.6.3"

    @property
    def app_server(self) -> "InventoryHTTPServer":
        return self.server  # type: ignore[return-value]

    def log_message(self, format_string: str, *args: Any) -> None:
        message = f"[{self.log_date_time_string()}] {format_string % args}"
        sys.stdout.write(f"{message}\n")
        logging.getLogger("inventory.http").info(message)

    def _send_bytes(
        self,
        payload: bytes,
        content_type: str,
        status: int = HTTPStatus.OK,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _send_json(self, data: Any, status: int = HTTPStatus.OK) -> None:
        payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self._send_bytes(payload, "application/json; charset=utf-8", status)

    def _read_body(self, maximum: int) -> bytes:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise InventoryError("Invalid request length.") from None
        if length <= 0:
            raise InventoryError("The request did not contain any data.")
        if length > maximum:
            raise InventoryError(f"The uploaded data exceeds the {maximum // (1024 * 1024)} MB limit.")
        return self.rfile.read(length)

    def _read_json(self) -> dict[str, Any]:
        try:
            data = json.loads(self._read_body(MAX_JSON_BYTES).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise InventoryError("The request contains invalid JSON data.") from exc
        if not isinstance(data, dict):
            raise InventoryError("The request must contain a JSON object.")
        return data

    def _route_parts(self) -> list[str]:
        return [unquote(part) for part in urlparse(self.path).path.strip("/").split("/") if part]

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Allow", "GET, HEAD, POST, PUT, DELETE, OPTIONS")
        self.end_headers()

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_GET(self) -> None:  # noqa: N802
        try:
            path = urlparse(self.path).path
            if path == "/api/health":
                self._send_json({"status": "ok", "version": "1.6.3"})
                return
            if path == "/api/state":
                self._send_json(_state(self.app_server.database_path))
                return
            if path == "/api/catalog":
                query = str(parse_qs(urlparse(self.path).query).get("q", [""])[0])[:120]
                with connect(self.app_server.database_path) as connection:
                    items = search_catalog_items(connection, query)
                    summary = catalog_summary(connection)
                self._send_json({"items": items, "catalog": summary})
                return
            if path == "/api/reference/last":
                with connect(self.app_server.database_path) as connection:
                    summary = last_workbook_summary(connection)
                self._send_json({"workbook": summary})
                return
            if path == "/api/reference/last/download":
                with connect(self.app_server.database_path) as connection:
                    saved = load_last_workbook(connection)
                if not saved:
                    raise InventoryError("No previously validated workbook is saved yet.")
                safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(saved["source_name"]).stem).strip("_") or "Reference"
                self._send_bytes(
                    bytes(saved["organized_payload"]),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{safe_name}_Organized.xlsx"'},
                )
                return
            if path == "/api/export":
                self._export_workbook()
                return
            if path == "/api/movements":
                with connect(self.app_server.database_path) as connection:
                    movements = list_movements(connection)
                self._send_json({"movements": movements})
                return
            self._serve_static(path)
        except Exception as exc:  # pragma: no branch - central HTTP boundary
            self._handle_error(exc)

    def do_POST(self) -> None:  # noqa: N802
        try:
            parts = self._route_parts()
            if parts == ["api", "entries"]:
                self._add_entry()
            elif parts == ["api", "sessions"]:
                self._new_session()
            elif len(parts) == 4 and parts[:2] == ["api", "sessions"] and parts[3] == "activate":
                self._activate_session(parts[2])
            elif len(parts) == 4 and parts[:2] == ["api", "sessions"] and parts[3] == "finalize":
                self._finalize_session(parts[2])
            elif len(parts) == 4 and parts[:2] == ["api", "sessions"] and parts[3] == "reference":
                self._freeze_reference(parts[2])
            elif len(parts) == 5 and parts[:2] == ["api", "sessions"] and parts[3:] == ["reference", "reuse"]:
                self._reuse_last_reference(parts[2])
            elif len(parts) == 4 and parts[:2] == ["api", "sessions"] and parts[3] == "submit":
                self._submit_cycle(parts[2])
            elif len(parts) == 4 and parts[:2] == ["api", "sessions"] and parts[3] == "review":
                self._review_cycle(parts[2])
            elif parts == ["api", "compare", "reference"]:
                self._run_reference_comparison()
            elif parts == ["api", "compare", "old"]:
                self._run_old_comparison()
            elif parts == ["api", "compare", "old-reference"]:
                self._run_old_reference_comparison()
            elif parts == ["api", "organize"]:
                self._organize_workbook_copy()
            elif parts == ["api", "organize", "preview"]:
                self._preview_organized_workbook()
            elif parts == ["api", "movements"]:
                self._add_movement()
            else:
                self._send_json({"error": "API route not found."}, HTTPStatus.NOT_FOUND)
        except Exception as exc:  # pragma: no branch - central HTTP boundary
            self._handle_error(exc)

    def do_PUT(self) -> None:  # noqa: N802
        try:
            parts = self._route_parts()
            if len(parts) == 3 and parts[:2] == ["api", "entries"]:
                self._update_entry(parts[2])
            else:
                self._send_json({"error": "API route not found."}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self._handle_error(exc)

    def do_DELETE(self) -> None:  # noqa: N802
        try:
            parts = self._route_parts()
            if len(parts) == 3 and parts[:2] == ["api", "entries"]:
                self._delete_entry(parts[2])
            else:
                self._send_json({"error": "API route not found."}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            self._handle_error(exc)

    def _serve_static(self, request_path: str) -> None:
        file_name = "index.html" if request_path in {"", "/"} else request_path.lstrip("/")
        allowed = {"index.html", "styles.css", "app.js", "favicon.svg"}
        if file_name not in allowed:
            self._send_json({"error": "Page not found."}, HTTPStatus.NOT_FOUND)
            return
        path = STATIC_ROOT / file_name
        if not path.is_file():
            self._send_json({"error": "Static application file is missing."}, HTTPStatus.NOT_FOUND)
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript", "image/svg+xml"}:
            content_type += "; charset=utf-8"
        self._send_bytes(path.read_bytes(), content_type)

    def _duplicate_count(
        self,
        existing_rows: list[dict[str, Any]],
        entry: dict[str, Any],
        excluded_id: str = "",
    ) -> int:
        key = comparison_key(entry["model"], entry["ram"], entry["storage"], entry["color"])
        return sum(
            row["id"] != excluded_id
            and comparison_key(row["model"], row["ram"], row["storage"], row["color"]) == key
            for row in existing_rows
        )

    def _add_entry(self) -> None:
        payload = self._read_json()
        validated = validate_entry(payload)
        with connect(self.app_server.database_path) as connection:
            session = current_session(connection)
            require_draft(connection, session["id"])
            if session["workflow_status"] != "COUNTING":
                raise InventoryError("This cycle count is submitted. Approve it or start a recount before editing.")
            duplicate_count = self._duplicate_count(session_entries(connection, session["id"]), validated)
            if duplicate_count and not bool(payload.get("allow_duplicate")):
                raise DuplicateEntryError(duplicate_count)
            entry_id = str(uuid.uuid4())
            now = utc_now()
            connection.execute(
                """
                INSERT INTO entries
                (id, session_id, model, ram, storage, color, items_per_box, boxes, loose_items,
                amount, area, broken_box, counted_at, updated_at, operator_name, attempt)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_id, session["id"], validated["model"], validated["ram"], validated["storage"],
                    validated["color"], validated["items_per_box"], validated["boxes"],
                    validated["loose_items"], validated["amount"], validated["area"],
                    int(validated["broken_box"]), now, now, session["operator_name"],
                    int(session["recount_attempt"] or 1),
                ),
            )
            validated.update({"id": entry_id, "counted_at": now})
            add_audit(connection, session["id"], "ADD", entry_id, "", _entry_summary(validated))
            connection.execute("DELETE FROM comparison_results WHERE session_id = ?", (session["id"],))
        self._send_json({"ok": True, "entry_id": entry_id}, HTTPStatus.CREATED)

    def _update_entry(self, entry_id: str) -> None:
        payload = self._read_json()
        validated = validate_entry(payload)
        with connect(self.app_server.database_path) as connection:
            session = current_session(connection)
            require_draft(connection, session["id"])
            if session["workflow_status"] != "COUNTING":
                raise InventoryError("This cycle count is submitted. Approve it or start a recount before editing.")
            existing_row = connection.execute(
                "SELECT * FROM entries WHERE id = ? AND session_id = ?", (entry_id, session["id"])
            ).fetchone()
            if not existing_row:
                raise KeyError("Inventory entry not found in the active session.")
            existing = dict(existing_row)
            duplicate_count = self._duplicate_count(
                session_entries(connection, session["id"]), validated, excluded_id=entry_id
            )
            if duplicate_count and not bool(payload.get("allow_duplicate")):
                raise DuplicateEntryError(duplicate_count)
            connection.execute(
                """
                UPDATE entries SET model = ?, ram = ?, storage = ?, color = ?, items_per_box = ?,
                    boxes = ?, loose_items = ?, amount = ?, area = ?, broken_box = ?, updated_at = ?
                WHERE id = ? AND session_id = ?
                """,
                (
                    validated["model"], validated["ram"], validated["storage"], validated["color"],
                    validated["items_per_box"], validated["boxes"], validated["loose_items"],
                    validated["amount"], validated["area"], int(validated["broken_box"]),
                    utc_now(), entry_id, session["id"],
                ),
            )
            validated.update({"id": entry_id, "counted_at": existing["counted_at"]})
            add_audit(
                connection, session["id"], "EDIT", entry_id,
                _entry_summary(existing), _entry_summary(validated),
            )
            connection.execute("DELETE FROM comparison_results WHERE session_id = ?", (session["id"],))
        self._send_json({"ok": True})

    def _delete_entry(self, entry_id: str) -> None:
        with connect(self.app_server.database_path) as connection:
            session = current_session(connection)
            require_draft(connection, session["id"])
            if session["workflow_status"] != "COUNTING":
                raise InventoryError("This cycle count is submitted. Approve it or start a recount before editing.")
            row = connection.execute(
                "SELECT * FROM entries WHERE id = ? AND session_id = ?", (entry_id, session["id"])
            ).fetchone()
            if not row:
                raise KeyError("Inventory entry not found in the active session.")
            existing = dict(row)
            connection.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
            add_audit(connection, session["id"], "REMOVE", entry_id, _entry_summary(existing), "")
            connection.execute("DELETE FROM comparison_results WHERE session_id = ?", (session["id"],))
        self._send_json({"ok": True})

    def _new_session(self) -> None:
        payload = self._read_json()
        try:
            quantity_tolerance = int(payload.get("quantity_tolerance") or 0)
            percentage_tolerance = float(payload.get("percentage_tolerance") or 0)
        except (TypeError, ValueError):
            raise InventoryError("Tolerances must be valid non-negative numbers.") from None
        if quantity_tolerance < 0 or percentage_tolerance < 0:
            raise InventoryError("Tolerances cannot be negative.")
        with connect(self.app_server.database_path) as connection:
            session = create_session(
                connection,
                str(payload.get("name") or ""),
                count_type=str(payload.get("count_type") or "SPOT"),
                warehouse=str(payload.get("warehouse") or ""),
                location=str(payload.get("location") or ""),
                operator_name=str(payload.get("operator_name") or ""),
                quantity_tolerance=quantity_tolerance,
                percentage_tolerance=percentage_tolerance,
            )
        self._send_json({"ok": True, "session": session}, HTTPStatus.CREATED)

    def _activate_session(self, session_id: str) -> None:
        with connect(self.app_server.database_path) as connection:
            session = activate_session(connection, session_id)
        self._send_json({"ok": True, "session": session})

    def _finalize_session(self, session_id: str) -> None:
        with connect(self.app_server.database_path) as connection:
            active = current_session(connection)
            if active["id"] != session_id:
                raise InventoryError("Activate this session before finalizing it.")
            session = finalize_session(connection, session_id)
        self._send_json({"ok": True, "session": session})

    def _freeze_reference(self, session_id: str) -> None:
        source_payload = self._read_body(MAX_WORKBOOK_BYTES)
        references, reference_section_count = parse_reference_workbook(source_payload)
        rows, organize_section_count, validation = analyze_organized_rows(source_payload)
        workbook = build_organized_rows_workbook(rows)
        query = parse_qs(urlparse(self.path).query)
        source_name = str(query.get("name", ["Reference.xlsx"])[0])[:255]
        safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(source_name).stem).strip("_") or "Reference"
        validation["source_hash"] = hashlib.sha256(source_payload).hexdigest()
        with connect(self.app_server.database_path) as connection:
            active = current_session(connection)
            if active["id"] != session_id:
                raise InventoryError("Activate this session before loading its reference workbook.")
            reference = save_frozen_reference(
                connection, session_id, source_name, source_payload, references, reference_section_count
            )
            catalog_count = replace_catalog_items(connection, rows, source_name)
            save_last_workbook(
                connection, source_name, source_payload, workbook,
                json.dumps(validation, ensure_ascii=False, separators=(",", ":")),
            )
        self._send_bytes(
            workbook,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            HTTPStatus.OK,
            {
                "Content-Disposition": f'attachment; filename="{safe_name}_Organized.xlsx"',
                "X-Reference-Hash": reference["source_hash"],
                "X-Reference-Rows": str(reference["row_count"]),
                "X-Catalog-Variants": str(catalog_count),
                "X-Organized-Rows": str(len(rows)),
                "X-Organized-Sections": str(organize_section_count),
                "X-Original-Modified": "false",
            },
        )

    def _reuse_last_reference(self, session_id: str) -> None:
        self._read_json()
        with connect(self.app_server.database_path) as connection:
            active = current_session(connection)
            if active["id"] != session_id:
                raise InventoryError("Activate this session before loading its reference workbook.")
            saved = load_last_workbook(connection)
            if not saved:
                raise InventoryError("No previously validated workbook is saved yet.")
            source_payload = bytes(saved["source_payload"])
            source_name = str(saved["source_name"])
            references, reference_section_count = parse_reference_workbook(source_payload)
            rows, _, _ = analyze_organized_rows(source_payload)
            reference = save_frozen_reference(
                connection, session_id, source_name, source_payload, references, reference_section_count
            )
            catalog_count = replace_catalog_items(connection, rows, source_name)
        self._send_json({
            "ok": True,
            "reference": reference,
            "catalog_variants": catalog_count,
            "source_name": source_name,
        })

    def _submit_cycle(self, session_id: str) -> None:
        self._read_json()
        with connect(self.app_server.database_path) as connection:
            active = current_session(connection)
            if active["id"] != session_id:
                raise InventoryError("Activate this session before submitting it.")
            result = submit_cycle_count(connection, session_id)
        self._send_json({"ok": True, **result})

    def _review_cycle(self, session_id: str) -> None:
        payload = self._read_json()
        with connect(self.app_server.database_path) as connection:
            active = current_session(connection)
            if active["id"] != session_id:
                raise InventoryError("Activate this session before reviewing it.")
            result = review_cycle_count(
                connection,
                session_id,
                str(payload.get("action") or ""),
                str(payload.get("reviewer") or ""),
                str(payload.get("reason") or ""),
            )
        self._send_json({"ok": True, **result})

    def _run_reference_comparison(self) -> None:
        payload = self._read_body(MAX_WORKBOOK_BYTES)
        references, sections = parse_reference_workbook(payload)
        with connect(self.app_server.database_path) as connection:
            session = current_session(connection)
            entries = session_entries(connection, session["id"])
            if not entries:
                raise InventoryError("Add inventory entries before running a comparison.")
            results = compare_reference(entries, references)
            replace_comparison_results(connection, session["id"], "REFERENCE", results)
        self._send_json(
            {"ok": True, "result_count": len(results), "reference_rows": len(references), "sections": sections}
        )

    def _run_old_comparison(self) -> None:
        payload = self._read_body(MAX_WORKBOOK_BYTES)
        old_entries = parse_count_workbook(payload)
        with connect(self.app_server.database_path) as connection:
            session = current_session(connection)
            new_entries = session_entries(connection, session["id"])
            if not new_entries:
                raise InventoryError("Add inventory entries before running a comparison.")
            results = compare_old_new(old_entries, new_entries)
            replace_comparison_results(connection, session["id"], "OLD_NEW", results)
        self._send_json({"ok": True, "result_count": len(results), "old_rows": len(old_entries)})

    def _run_old_reference_comparison(self) -> None:
        payload = self._read_body((MAX_WORKBOOK_BYTES * 2) + 4)
        if len(payload) < 6:
            raise InventoryError("Select both an old count workbook and a reference workbook.")

        old_size = struct.unpack(">I", payload[:4])[0]
        reference_size = len(payload) - 4 - old_size
        if old_size <= 0 or old_size > MAX_WORKBOOK_BYTES:
            raise InventoryError("The old count workbook is missing or exceeds the 25 MB limit.")
        if reference_size <= 0 or reference_size > MAX_WORKBOOK_BYTES:
            raise InventoryError("The reference workbook is missing or exceeds the 25 MB limit.")

        old_payload = payload[4:4 + old_size]
        reference_payload = payload[4 + old_size:]
        old_entries = parse_count_workbook(old_payload)
        references, sections = parse_reference_workbook(reference_payload)

        with connect(self.app_server.database_path) as connection:
            session = current_session(connection)
            results = compare_reference(old_entries, references)
            replace_comparison_results(connection, session["id"], "OLD_REFERENCE", results)

        self._send_json(
            {
                "ok": True,
                "result_count": len(results),
                "old_rows": len(old_entries),
                "reference_rows": len(references),
                "sections": sections,
            }
        )

    def _organize_workbook_copy(self) -> None:
        source_payload = self._read_body(MAX_WORKBOOK_BYTES)
        rows, section_count, validation = analyze_organized_rows(source_payload)
        workbook = build_organized_rows_workbook(rows)
        row_count = len(rows)
        query = parse_qs(urlparse(self.path).query)
        source_name = str(query.get("name", ["Inventory"])[0])[:255]
        source_stem = Path(source_name).stem
        safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", source_stem).strip("_") or "Inventory"
        file_name = f"{safe_name}_Organized.xlsx"
        validation["source_hash"] = hashlib.sha256(source_payload).hexdigest()
        with connect(self.app_server.database_path) as connection:
            catalog_count = replace_catalog_items(connection, rows, source_name)
            save_last_workbook(
                connection, source_name, source_payload, workbook,
                json.dumps(validation, ensure_ascii=False, separators=(",", ":")),
            )
        self._send_bytes(
            workbook,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f'attachment; filename="{file_name}"',
                "X-Organized-Rows": str(row_count),
                "X-Organized-Sections": str(section_count),
                "X-Catalog-Variants": str(catalog_count),
                "X-Skipped-Rows": str(validation["skipped_rows"]),
                "X-Duplicate-Rows": str(validation["duplicate_rows"]),
                "X-Original-Modified": "false",
            },
        )

    def _preview_organized_workbook(self) -> None:
        source_payload = self._read_body(MAX_WORKBOOK_BYTES)
        rows, section_count, validation = analyze_organized_rows(source_payload)
        detected_dates = sorted(
            {
                value.date().isoformat() if hasattr(value, "date") else str(value)[:10]
                for value in (row.get("date_counted") for row in rows)
                if value
            }
        )
        self._send_json(
            {
                "ok": True,
                **validation,
                "row_count": len(rows),
                "variant_count": validation["unique_variants"],
                "detected_dates": detected_dates,
                "source_hash": hashlib.sha256(source_payload).hexdigest(),
            }
        )

    def _add_movement(self) -> None:
        payload = self._read_json()
        with connect(self.app_server.database_path) as connection:
            movement = add_movement(connection, payload)
        self._send_json({"ok": True, "movement": movement}, HTTPStatus.CREATED)

    def _export_workbook(self) -> None:
        with connect(self.app_server.database_path) as connection:
            session = current_session(connection)
            entries = session_entries(connection, session["id"])
            if not entries:
                raise InventoryError("Add at least one inventory count before exporting.")
            comparisons = comparison_results(connection, session["id"])
            all_entries = all_session_entries(connection, session["id"])
            movements = list_movements(connection, 2000)
            attempts = list_attempts(connection, session["id"])
            audit = [
                dict(row)
                for row in connection.execute(
                    "SELECT created_at, action, entry_id, previous_value, new_value "
                    "FROM audit_events WHERE session_id = ? ORDER BY id",
                    (session["id"],),
                ).fetchall()
            ]
        workbook = build_inventory_workbook(
            session, entries, comparisons, audit,
            movements=movements, attempts=attempts, all_entries=all_entries,
        )
        safe_name = re.sub(r"[^A-Za-z0-9_-]+", "_", session["name"]).strip("_") or "Inventory_Count"
        file_name = f"{safe_name}.xlsx"
        self._send_bytes(
            workbook,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
        )

    def _handle_error(self, exc: Exception) -> None:
        if isinstance(exc, DuplicateEntryError):
            self._send_json(
                {"error": str(exc), "code": "DUPLICATE", "duplicate_count": exc.count},
                HTTPStatus.CONFLICT,
            )
        elif isinstance(exc, InventoryError):
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        elif isinstance(exc, PermissionError):
            self._send_json({"error": str(exc)}, HTTPStatus.LOCKED)
        elif isinstance(exc, KeyError):
            self._send_json({"error": str(exc).strip("'\"")}, HTTPStatus.NOT_FOUND)
        elif isinstance(exc, ValueError):
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        else:
            traceback.print_exc()
            self._send_json(
                {"error": "The application encountered an unexpected error. Check the server window for details."},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )


class InventoryHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], database_path: Path):
        self.database_path = database_path
        super().__init__(address, InventoryRequestHandler)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inventory Count Web App")
    parser.add_argument("--host", default="127.0.0.1", help="Local bind address")
    parser.add_argument("--port", type=int, default=8765, help="Local port")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATABASE, help="SQLite database path")
    parser.add_argument("--open", action="store_true", help="Open the app in the default browser")
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    database_path = args.data.expanduser().resolve()
    init_database(database_path)
    log_path = database_path.parent / DEFAULT_LOG.name
    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    try:
        server = InventoryHTTPServer((args.host, args.port), database_path)
    except OSError as exc:
        print(f"Could not start the Inventory Web App on port {args.port}: {exc}", file=sys.stderr)
        return 1
    url = f"http://{args.host}:{server.server_address[1]}/"
    print("Inventory Count Web App")
    print(f"Open: {url}")
    print(f"Database: {database_path}")
    print("Press Ctrl+C to stop the app.")
    if args.open:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Inventory Count Web App...")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
