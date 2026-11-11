"""Cycle-count workflow, review decisions, frozen references, and movement records."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import uuid
from datetime import datetime
from typing import Any

from .comparison import compare_reference
from .database import add_audit, replace_comparison_results, session_entries, utc_now
from .rules import InventoryError, clean_text, comparison_key, parse_whole_number


MOVEMENT_TYPES = {
    "RECEIVE",
    "SHIPMENT",
    "TRANSFER",
    "TEMPORARY_OUT",
    "RETURN_TO_STOCK",
    "ADJUSTMENT",
}


def _safe_reference_rows(references: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return JSON-safe parsed rows while preserving every comparison field."""

    safe: list[dict[str, Any]] = []
    for reference in references:
        row = dict(reference)
        sort_value = row.get("last_updated_sort")
        if isinstance(sort_value, float) and not math.isfinite(sort_value):
            row["last_updated_sort"] = -1.0
        safe.append(row)
    return safe


def frozen_reference(connection: sqlite3.Connection, session_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT source_name, source_hash, row_count, section_count, created_at "
        "FROM cycle_references WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    return dict(row) if row else None


def save_frozen_reference(
    connection: sqlite3.Connection,
    session_id: str,
    source_name: str,
    source_payload: bytes,
    references: list[dict[str, Any]],
    section_count: int,
) -> dict[str, Any]:
    session = connection.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if not session:
        raise KeyError("Inventory session not found.")
    if session["status"] != "DRAFT":
        raise PermissionError("This inventory session is finalized and locked.")
    if connection.execute(
        "SELECT COUNT(*) AS count FROM entries WHERE session_id = ?", (session_id,)
    ).fetchone()["count"]:
        raise InventoryError("Load the frozen reference before entering counts for this session.")

    now = utc_now()
    digest = hashlib.sha256(source_payload).hexdigest()
    safe_rows = _safe_reference_rows(references)
    connection.execute(
        """
        INSERT INTO cycle_references
        (session_id, source_name, source_hash, row_count, section_count, references_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(session_id) DO UPDATE SET
            source_name = excluded.source_name,
            source_hash = excluded.source_hash,
            row_count = excluded.row_count,
            section_count = excluded.section_count,
            references_json = excluded.references_json,
            created_at = excluded.created_at
        """,
        (
            session_id,
            clean_text(source_name)[:255] or "Reference.xlsx",
            digest,
            len(safe_rows),
            section_count,
            json.dumps(safe_rows, ensure_ascii=False, separators=(",", ":"), allow_nan=False),
            now,
        ),
    )
    connection.execute(
        """
        UPDATE sessions SET reference_name = ?, reference_hash = ?, reference_loaded_at = ?,
            workflow_status = 'COUNTING', submitted_at = NULL, approved_at = NULL,
            approved_by = '', review_reason = ''
        WHERE id = ?
        """,
        (clean_text(source_name)[:255] or "Reference.xlsx", digest, now, session_id),
    )
    add_audit(
        connection,
        session_id,
        "FREEZE REFERENCE",
        "",
        "",
        f"{clean_text(source_name)} | SHA256 {digest} | {len(safe_rows)} rows",
    )
    return {
        "source_name": clean_text(source_name)[:255] or "Reference.xlsx",
        "source_hash": digest,
        "row_count": len(safe_rows),
        "section_count": section_count,
        "created_at": now,
    }


def load_frozen_reference(connection: sqlite3.Connection, session_id: str) -> list[dict[str, Any]]:
    row = connection.execute(
        "SELECT references_json FROM cycle_references WHERE session_id = ?", (session_id,)
    ).fetchone()
    if not row:
        raise InventoryError("Load and freeze a reference workbook before submitting the cycle count.")
    references = json.loads(row["references_json"])
    if not isinstance(references, list) or not references:
        raise InventoryError("The saved reference snapshot is empty or invalid.")
    return references


def list_attempts(connection: sqlite3.Connection, session_id: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT attempt, submitted_at, status, decision, decision_by, decision_reason, decided_at
        FROM cycle_count_attempts WHERE session_id = ? ORDER BY attempt
        """,
        (session_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def list_movements(connection: sqlite3.Connection, limit: int = 500) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT * FROM inventory_movements ORDER BY occurred_at DESC, rowid DESC LIMIT ?",
        (max(1, min(int(limit), 2000)),),
    ).fetchall()
    return [dict(row) for row in rows]


def validate_movement(payload: dict[str, Any]) -> dict[str, Any]:
    movement_type = clean_text(payload.get("movement_type")).upper().replace(" ", "_")
    if movement_type not in MOVEMENT_TYPES:
        raise InventoryError("Select a valid movement type.")
    model = clean_text(payload.get("model"))
    ram = clean_text(payload.get("ram"))
    storage = clean_text(payload.get("storage"))
    color = clean_text(payload.get("color"))
    operator_name = clean_text(payload.get("operator_name"))
    if not model or not ram or not storage or not color:
        raise InventoryError("Enter Model, RAM, Storage, and Color for the movement.")
    if not operator_name:
        raise InventoryError("Enter the operator who recorded the movement.")
    quantity = parse_whole_number(payload.get("quantity"), "Movement Quantity", allow_zero=False)
    occurred_at = clean_text(payload.get("occurred_at")) or utc_now()
    try:
        datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
    except ValueError:
        raise InventoryError("Movement Time must be a valid date and time.") from None
    return {
        "movement_type": movement_type,
        "model": model,
        "ram": ram,
        "storage": storage,
        "color": color.title(),
        "item_key": comparison_key(model, ram, storage, color),
        "quantity": quantity,
        "from_location": clean_text(payload.get("from_location")),
        "to_location": clean_text(payload.get("to_location")),
        "operator_name": operator_name,
        "note": clean_text(payload.get("note")),
        "occurred_at": occurred_at,
    }


def add_movement(connection: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    movement = validate_movement(payload)
    movement["id"] = str(uuid.uuid4())
    connection.execute(
        """
        INSERT INTO inventory_movements
        (id, movement_type, model, ram, storage, color, item_key, quantity, from_location,
         to_location, operator_name, note, occurred_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        tuple(movement[key] for key in (
            "id", "movement_type", "model", "ram", "storage", "color", "item_key",
            "quantity", "from_location", "to_location", "operator_name", "note", "occurred_at",
        )),
    )
    return movement


def _movement_warnings(
    connection: sqlite3.Connection,
    session: sqlite3.Row,
) -> dict[str, str]:
    location = clean_text(session["location"]).casefold()
    rows = connection.execute(
        "SELECT * FROM inventory_movements WHERE occurred_at >= ? ORDER BY occurred_at",
        (session["created_at"],),
    ).fetchall()
    warnings: dict[str, list[str]] = {}
    for row in rows:
        if location and location not in {
            clean_text(row["from_location"]).casefold(),
            clean_text(row["to_location"]).casefold(),
        }:
            continue
        route = " → ".join(part for part in (row["from_location"], row["to_location"]) if part)
        message = f"{row['movement_type'].replace('_', ' ').title()} {row['quantity']}"
        if route:
            message += f" ({route})"
        message += f" at {row['occurred_at']}"
        warnings.setdefault(row["item_key"], []).append(message)
    return {key: "; ".join(values) for key, values in warnings.items()}


def submit_cycle_count(connection: sqlite3.Connection, session_id: str) -> dict[str, Any]:
    session = connection.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if not session:
        raise KeyError("Inventory session not found.")
    if session["status"] != "DRAFT":
        raise PermissionError("This inventory session is finalized and locked.")
    if session["workflow_status"] != "COUNTING":
        raise InventoryError("This count is already submitted. Approve it or start a recount.")
    entries = session_entries(connection, session_id)
    if not entries:
        raise InventoryError("Add at least one inventory count before submitting.")

    references = load_frozen_reference(connection, session_id)
    results = compare_reference(entries, references)
    movement_warnings = _movement_warnings(connection, session)
    quantity_tolerance = max(0, int(session["quantity_tolerance"] or 0))
    percentage_tolerance = max(0.0, float(session["percentage_tolerance"] or 0))
    attempt = max(1, int(session["recount_attempt"] or 1))
    has_review = False
    has_recount = False

    for result in results:
        difference = result.get("difference")
        baseline = result.get("baseline")
        exact = result["result"] == "MATCH"
        percent = None
        if difference is not None and baseline not in (None, 0):
            percent = round(abs(float(difference)) / abs(float(baseline)) * 100, 2)
        quantity_ok = difference is not None and quantity_tolerance > 0 and abs(int(difference)) <= quantity_tolerance
        percentage_ok = percent is not None and percentage_tolerance > 0 and percent <= percentage_tolerance
        within = exact or quantity_ok or percentage_ok
        if exact:
            review_status = "ACCEPTED"
        elif within:
            review_status = "PENDING REVIEW"
            has_review = True
        else:
            review_status = "RECOUNT REQUIRED"
            has_recount = True
        result.update(
            {
                "difference_percent": percent,
                "within_tolerance": within,
                "review_status": review_status,
                "movement_warning": movement_warnings.get(result.get("match_key", ""), ""),
                "attempt": attempt,
            }
        )

    workflow_status = "RECOUNT_REQUIRED" if has_recount else ("PENDING_REVIEW" if has_review else "APPROVED")
    submitted_at = utc_now()
    replace_comparison_results(connection, session_id, "CYCLE_REFERENCE", results)
    connection.execute(
        """
        INSERT INTO cycle_count_attempts
        (session_id, attempt, submitted_at, status, results_json)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(session_id, attempt) DO UPDATE SET
            submitted_at = excluded.submitted_at,
            status = excluded.status,
            results_json = excluded.results_json
        """,
        (
            session_id,
            attempt,
            submitted_at,
            workflow_status,
            json.dumps(results, ensure_ascii=False, separators=(",", ":"), allow_nan=False),
        ),
    )
    approved_at = submitted_at if workflow_status == "APPROVED" else None
    approved_by = "Automatic exact match" if workflow_status == "APPROVED" else ""
    connection.execute(
        """
        UPDATE sessions SET workflow_status = ?, submitted_at = ?, approved_at = ?,
            approved_by = ?, review_reason = '' WHERE id = ?
        """,
        (workflow_status, submitted_at, approved_at, approved_by, session_id),
    )
    add_audit(
        connection,
        session_id,
        "SUBMIT COUNT",
        "",
        "COUNTING",
        f"{workflow_status} | attempt {attempt} | {len(results)} identities",
    )
    return {
        "workflow_status": workflow_status,
        "attempt": attempt,
        "result_count": len(results),
        "submitted_at": submitted_at,
    }


def review_cycle_count(
    connection: sqlite3.Connection,
    session_id: str,
    action: str,
    reviewer: str,
    reason: str,
) -> dict[str, Any]:
    session = connection.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if not session:
        raise KeyError("Inventory session not found.")
    if session["status"] != "DRAFT":
        raise PermissionError("This inventory session is finalized and locked.")
    decision = clean_text(action).upper()
    reviewer_name = clean_text(reviewer)
    reason_text = clean_text(reason)
    if decision not in {"APPROVE", "RECOUNT"}:
        raise InventoryError("Review action must be Approve or Recount.")
    if not reviewer_name:
        raise InventoryError("Enter the supervisor or reviewer name.")
    if not reason_text:
        raise InventoryError("Enter a reason for the review decision.")
    if session["workflow_status"] not in {"PENDING_REVIEW", "RECOUNT_REQUIRED"}:
        raise InventoryError("Submit the count before recording a review decision.")

    now = utc_now()
    attempt = max(1, int(session["recount_attempt"] or 1))
    if decision == "APPROVE":
        connection.execute(
            """
            UPDATE sessions SET workflow_status = 'APPROVED', approved_at = ?, approved_by = ?,
                review_reason = ? WHERE id = ?
            """,
            (now, reviewer_name, reason_text, session_id),
        )
        next_status = "APPROVED"
    else:
        connection.execute(
            """
            UPDATE sessions SET workflow_status = 'COUNTING', recount_attempt = recount_attempt + 1,
                submitted_at = NULL, approved_at = NULL, approved_by = '', review_reason = ?
            WHERE id = ?
            """,
            (reason_text, session_id),
        )
        connection.execute("DELETE FROM comparison_results WHERE session_id = ?", (session_id,))
        next_status = "COUNTING"
    connection.execute(
        """
        UPDATE cycle_count_attempts SET decision = ?, decision_by = ?, decision_reason = ?,
            decided_at = ? WHERE session_id = ? AND attempt = ?
        """,
        (decision, reviewer_name, reason_text, now, session_id, attempt),
    )
    add_audit(
        connection,
        session_id,
        f"REVIEW {decision}",
        "",
        session["workflow_status"],
        f"{next_status} | {reviewer_name} | {reason_text}",
    )
    return {"workflow_status": next_status, "attempt": attempt + (decision == "RECOUNT")}
