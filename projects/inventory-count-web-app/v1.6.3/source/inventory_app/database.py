"""SQLite persistence for inventory sessions, entries, comparisons, and audit events."""

from __future__ import annotations

import sqlite3
import uuid
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('DRAFT', 'FINALIZED')),
    created_at TEXT NOT NULL,
    finalized_at TEXT
);

CREATE TABLE IF NOT EXISTS entries (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    model TEXT NOT NULL,
    ram TEXT NOT NULL,
    storage TEXT NOT NULL,
    color TEXT NOT NULL,
    items_per_box INTEGER NOT NULL CHECK (items_per_box >= 0),
    boxes INTEGER NOT NULL CHECK (boxes >= 0),
    loose_items INTEGER NOT NULL CHECK (loose_items >= 0),
    amount INTEGER NOT NULL CHECK (amount > 0),
    area TEXT NOT NULL,
    broken_box INTEGER NOT NULL CHECK (broken_box IN (0, 1)),
    counted_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS entries_session_idx ON entries(session_id, counted_at);

CREATE TABLE IF NOT EXISTS comparison_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    mode TEXT NOT NULL,
    result TEXT NOT NULL,
    item TEXT NOT NULL,
    color TEXT NOT NULL,
    counted INTEGER NOT NULL,
    baseline INTEGER,
    end_value INTEGER,
    difference INTEGER,
    broken_amount INTEGER NOT NULL,
    source_rows INTEGER NOT NULL,
    last_updated TEXT NOT NULL,
    explanation TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS comparison_session_idx ON comparison_results(session_id, id);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    entry_id TEXT NOT NULL,
    previous_value TEXT NOT NULL,
    new_value TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS audit_session_idx ON audit_events(session_id, id);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS catalog_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model TEXT NOT NULL,
    ram TEXT NOT NULL,
    storage TEXT NOT NULL,
    color TEXT NOT NULL,
    source_name TEXT NOT NULL,
    loaded_at TEXT NOT NULL,
    source_rows INTEGER NOT NULL DEFAULT 1,
    source_locations TEXT NOT NULL DEFAULT '',
    reference_quantity INTEGER,
    UNIQUE(model, ram, storage, color)
);

CREATE INDEX IF NOT EXISTS catalog_model_idx ON catalog_items(model COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS saved_workbooks (
    key TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    source_payload BLOB NOT NULL,
    organized_payload BLOB NOT NULL,
    validation_json TEXT NOT NULL,
    saved_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cycle_references (
    session_id TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
    source_name TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    section_count INTEGER NOT NULL,
    references_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cycle_count_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    attempt INTEGER NOT NULL,
    submitted_at TEXT NOT NULL,
    status TEXT NOT NULL,
    results_json TEXT NOT NULL,
    decision TEXT NOT NULL DEFAULT '',
    decision_by TEXT NOT NULL DEFAULT '',
    decision_reason TEXT NOT NULL DEFAULT '',
    decided_at TEXT,
    UNIQUE(session_id, attempt)
);

CREATE TABLE IF NOT EXISTS inventory_movements (
    id TEXT PRIMARY KEY,
    movement_type TEXT NOT NULL,
    model TEXT NOT NULL,
    ram TEXT NOT NULL,
    storage TEXT NOT NULL,
    color TEXT NOT NULL,
    item_key TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    from_location TEXT NOT NULL,
    to_location TEXT NOT NULL,
    operator_name TEXT NOT NULL,
    note TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS movement_time_idx ON inventory_movements(occurred_at, item_key);
"""


SESSION_COLUMNS = {
    "session_number": "TEXT NOT NULL DEFAULT ''",
    "count_type": "TEXT NOT NULL DEFAULT 'SPOT'",
    "warehouse": "TEXT NOT NULL DEFAULT ''",
    "location": "TEXT NOT NULL DEFAULT ''",
    "operator_name": "TEXT NOT NULL DEFAULT ''",
    "quantity_tolerance": "INTEGER NOT NULL DEFAULT 0",
    "percentage_tolerance": "REAL NOT NULL DEFAULT 0",
    "workflow_status": "TEXT NOT NULL DEFAULT 'COUNTING'",
    "reference_name": "TEXT NOT NULL DEFAULT ''",
    "reference_hash": "TEXT NOT NULL DEFAULT ''",
    "reference_loaded_at": "TEXT",
    "submitted_at": "TEXT",
    "approved_at": "TEXT",
    "approved_by": "TEXT NOT NULL DEFAULT ''",
    "review_reason": "TEXT NOT NULL DEFAULT ''",
    "recount_attempt": "INTEGER NOT NULL DEFAULT 1",
}

ENTRY_COLUMNS = {
    "operator_name": "TEXT NOT NULL DEFAULT ''",
    "attempt": "INTEGER NOT NULL DEFAULT 1",
}

COMPARISON_COLUMNS = {
    "match_key": "TEXT NOT NULL DEFAULT ''",
    "difference_percent": "REAL",
    "within_tolerance": "INTEGER",
    "review_status": "TEXT NOT NULL DEFAULT ''",
    "movement_warning": "TEXT NOT NULL DEFAULT ''",
    "attempt": "INTEGER NOT NULL DEFAULT 1",
}

CATALOG_COLUMNS = {
    "source_rows": "INTEGER NOT NULL DEFAULT 1",
    "source_locations": "TEXT NOT NULL DEFAULT ''",
    "reference_quantity": "INTEGER",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def connect(path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(str(path), timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


def init_database(path: str | Path) -> None:
    database_path = Path(path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(database_path) as connection:
        connection.executescript(SCHEMA)
        _ensure_columns(connection, "sessions", SESSION_COLUMNS)
        _ensure_columns(connection, "entries", ENTRY_COLUMNS)
        _ensure_columns(connection, "comparison_results", COMPARISON_COLUMNS)
        _ensure_columns(connection, "catalog_items", CATALOG_COLUMNS)
        connection.execute(
            "UPDATE sessions SET session_number = 'CC-' || substr(replace(id, '-', ''), 1, 8) "
            "WHERE session_number = ''"
        )
        ensure_active_session(connection)


def _ensure_columns(
    connection: sqlite3.Connection,
    table: str,
    definitions: dict[str, str],
) -> None:
    """Add backwards-compatible columns without replacing the user's database."""

    existing = {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}
    for column, definition in definitions.items():
        if column not in existing:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def create_session(
    connection: sqlite3.Connection,
    name: str | None = None,
    *,
    count_type: str = "SPOT",
    warehouse: str = "",
    location: str = "",
    operator_name: str = "",
    quantity_tolerance: int = 0,
    percentage_tolerance: float = 0,
) -> dict[str, Any]:
    session_id = str(uuid.uuid4())
    created_at = utc_now()
    session_name = (name or "").strip() or datetime.now().strftime("Inventory Count %Y-%m-%d %H:%M")
    count_kind = str(count_type or "SPOT").strip().upper()
    if count_kind not in {"PLANNED", "SPOT"}:
        raise ValueError("Count Type must be Planned or Spot.")
    session_number = f"CC-{datetime.now():%Y%m%d}-{session_id[:6].upper()}"
    connection.execute(
        """
        INSERT INTO sessions
        (id, name, status, created_at, session_number, count_type, warehouse, location,
         operator_name, quantity_tolerance, percentage_tolerance, workflow_status)
        VALUES (?, ?, 'DRAFT', ?, ?, ?, ?, ?, ?, ?, ?, 'COUNTING')
        """,
        (
            session_id, session_name, created_at, session_number, count_kind,
            str(warehouse).strip(), str(location).strip(), str(operator_name).strip(),
            max(0, int(quantity_tolerance)), max(0, float(percentage_tolerance)),
        ),
    )
    connection.execute(
        "INSERT INTO app_settings (key, value) VALUES ('active_session_id', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (session_id,),
    )
    add_audit(connection, session_id, "NEW SESSION", "", "", session_name)
    return dict(connection.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone())


def ensure_active_session(connection: sqlite3.Connection) -> dict[str, Any]:
    setting = connection.execute(
        "SELECT value FROM app_settings WHERE key = 'active_session_id'"
    ).fetchone()
    if setting:
        row = connection.execute("SELECT * FROM sessions WHERE id = ?", (setting["value"],)).fetchone()
        if row:
            return dict(row)
    latest = connection.execute("SELECT * FROM sessions ORDER BY created_at DESC LIMIT 1").fetchone()
    if latest:
        connection.execute(
            "INSERT INTO app_settings (key, value) VALUES ('active_session_id', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (latest["id"],),
        )
        return dict(latest)
    return create_session(connection)


def activate_session(connection: sqlite3.Connection, session_id: str) -> dict[str, Any]:
    row = connection.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if not row:
        raise KeyError("Inventory session not found.")
    connection.execute(
        "INSERT INTO app_settings (key, value) VALUES ('active_session_id', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (session_id,),
    )
    return dict(row)


def current_session(connection: sqlite3.Connection) -> dict[str, Any]:
    return ensure_active_session(connection)


def require_draft(connection: sqlite3.Connection, session_id: str) -> None:
    row = connection.execute("SELECT status FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if not row:
        raise KeyError("Inventory session not found.")
    if row["status"] != "DRAFT":
        raise PermissionError("This inventory session is finalized and locked.")


def finalize_session(connection: sqlite3.Connection, session_id: str) -> dict[str, Any]:
    require_draft(connection, session_id)
    count = connection.execute(
        """
        SELECT COUNT(*) AS count FROM entries e JOIN sessions s ON s.id = e.session_id
        WHERE e.session_id = ? AND e.attempt = s.recount_attempt
        """,
        (session_id,),
    ).fetchone()["count"]
    if count == 0:
        raise ValueError("Add at least one inventory count before finalizing.")
    session = connection.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
    if session["reference_name"] and session["workflow_status"] != "APPROVED":
        raise ValueError("Approve the submitted cycle count before finalizing it.")
    finalized_at = utc_now()
    connection.execute(
        "UPDATE sessions SET status = 'FINALIZED', workflow_status = 'FINALIZED', finalized_at = ? WHERE id = ?",
        (finalized_at, session_id),
    )
    add_audit(connection, session_id, "FINALIZE", "", "DRAFT", "FINALIZED")
    return dict(connection.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone())


def add_audit(
    connection: sqlite3.Connection,
    session_id: str,
    action: str,
    entry_id: str,
    previous_value: str,
    new_value: str,
) -> None:
    connection.execute(
        "INSERT INTO audit_events "
        "(session_id, action, entry_id, previous_value, new_value, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (session_id, action, entry_id, previous_value, new_value, utc_now()),
    )


def rows_as_dicts(rows: list[sqlite3.Row] | tuple[sqlite3.Row, ...]) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        item = dict(row)
        if "broken_box" in item:
            item["broken_box"] = bool(item["broken_box"])
        if "within_tolerance" in item and item["within_tolerance"] is not None:
            item["within_tolerance"] = bool(item["within_tolerance"])
        result.append(item)
    return result


def session_entries(connection: sqlite3.Connection, session_id: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT e.* FROM entries e
        JOIN sessions s ON s.id = e.session_id
        WHERE e.session_id = ? AND e.attempt = s.recount_attempt
        ORDER BY e.counted_at DESC, e.rowid DESC
        """,
        (session_id,),
    ).fetchall()
    return rows_as_dicts(rows)


def all_session_entries(connection: sqlite3.Connection, session_id: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT * FROM entries WHERE session_id = ? ORDER BY attempt, counted_at, rowid",
        (session_id,),
    ).fetchall()
    return rows_as_dicts(rows)


def comparison_results(connection: sqlite3.Connection, session_id: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT result, item, color, counted, baseline, end_value, difference, "
        "broken_amount, source_rows, last_updated, explanation, mode, created_at, match_key, "
        "difference_percent, within_tolerance, review_status, movement_warning, attempt "
        "FROM comparison_results WHERE session_id = ? ORDER BY id",
        (session_id,),
    ).fetchall()
    return rows_as_dicts(rows)


def _catalog_reference_quantity(item: dict[str, Any]) -> int | None:
    """Return the quantity the count workflow uses as the inventory baseline.

    START is preferred to match reference comparison behavior. END is used only
    when START is unavailable. Invalid, negative, or fractional values are ignored.
    """

    for key in ("start", "end"):
        text = str(item.get(key) or "").strip().replace(",", "")
        if not text:
            continue
        try:
            number = Decimal(text)
        except InvalidOperation:
            continue
        if not number.is_finite() or number < 0 or number != number.to_integral_value():
            continue
        return int(number)
    return None


def replace_catalog_items(
    connection: sqlite3.Connection,
    items: list[dict[str, Any]],
    source_name: str,
) -> int:
    """Replace the local autocomplete catalog with unique product variants.

    Duplicate source rows are intentionally retained as metadata so the UI can
    explain when several spreadsheet rows represent the same product identity.
    """

    loaded_at = utc_now()
    unique: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for item in items:
        model = str(item.get("model") or "").strip()
        ram = str(item.get("ram") or "").strip()
        storage = str(item.get("storage") or "").strip()
        color = str(item.get("color") or "").strip()
        if not model or not color:
            continue
        key = (model.casefold(), ram.casefold(), storage.casefold(), color.casefold())
        group = unique.setdefault(
            key,
            {"values": (model, ram, storage, color), "locations": [], "reference_quantity": None},
        )
        location = ""
        if item.get("source_sheet") and item.get("source_row"):
            location = f"{item['source_sheet']}!{item['source_row']}"
        if location and location not in group["locations"]:
            group["locations"].append(location)
        quantity = _catalog_reference_quantity(item)
        if quantity is not None:
            group["reference_quantity"] = quantity

    connection.execute("DELETE FROM catalog_items")
    connection.executemany(
        "INSERT INTO catalog_items "
        "(model, ram, storage, color, source_name, loaded_at, source_rows, source_locations, reference_quantity) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                *group["values"],
                source_name,
                loaded_at,
                max(1, len(group["locations"])),
                "; ".join(group["locations"][:20]),
                group["reference_quantity"],
            )
            for group in unique.values()
        ],
    )
    settings = {
        "catalog_source_name": source_name,
        "catalog_loaded_at": loaded_at,
        "catalog_variant_count": str(len(unique)),
    }
    connection.executemany(
        "INSERT INTO app_settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        settings.items(),
    )
    return len(unique)


def catalog_summary(connection: sqlite3.Connection) -> dict[str, Any]:
    rows = connection.execute(
        "SELECT key, value FROM app_settings WHERE key IN "
        "('catalog_source_name', 'catalog_loaded_at', 'catalog_variant_count')"
    ).fetchall()
    settings = {row["key"]: row["value"] for row in rows}
    actual_count = connection.execute("SELECT COUNT(*) AS count FROM catalog_items").fetchone()["count"]
    return {
        "variant_count": int(actual_count),
        "source_name": settings.get("catalog_source_name", ""),
        "loaded_at": settings.get("catalog_loaded_at", ""),
    }


def search_catalog_items(
    connection: sqlite3.Connection,
    query: str,
    limit: int = 30,
) -> list[dict[str, Any]]:
    text = query.strip()
    if not text:
        return []
    rows = connection.execute(
        """
        SELECT id, model, ram, storage, color, source_rows, source_locations, reference_quantity
        FROM catalog_items
        WHERE instr(lower(model || ' ' || ram || ' ' || storage || ' ' || color), lower(?)) > 0
        ORDER BY
            CASE
                WHEN lower(model) = lower(?) THEN 0
                WHEN lower(model) LIKE lower(?) || '%' THEN 1
                ELSE 2
            END,
            model COLLATE NOCASE,
            ram COLLATE NOCASE,
            storage COLLATE NOCASE,
            color COLLATE NOCASE
        LIMIT ?
        """,
        (text, text, text, max(1, min(int(limit), 100))),
    ).fetchall()
    return [dict(row) for row in rows]



def save_last_workbook(
    connection: sqlite3.Connection,
    source_name: str,
    source_payload: bytes,
    organized_payload: bytes,
    validation_json: str,
) -> dict[str, Any]:
    """Persist the last successfully validated workbook for one-click reuse."""

    import hashlib

    saved_at = utc_now()
    source_hash = hashlib.sha256(source_payload).hexdigest()
    connection.execute(
        """
        INSERT INTO saved_workbooks
        (key, source_name, source_hash, source_payload, organized_payload, validation_json, saved_at)
        VALUES ('last_reference', ?, ?, ?, ?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET
            source_name = excluded.source_name,
            source_hash = excluded.source_hash,
            source_payload = excluded.source_payload,
            organized_payload = excluded.organized_payload,
            validation_json = excluded.validation_json,
            saved_at = excluded.saved_at
        """,
        (source_name[:255] or "Reference.xlsx", source_hash, source_payload, organized_payload, validation_json, saved_at),
    )
    return {
        "source_name": source_name[:255] or "Reference.xlsx",
        "source_hash": source_hash,
        "saved_at": saved_at,
    }


def last_workbook_summary(connection: sqlite3.Connection) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT source_name, source_hash, validation_json, saved_at FROM saved_workbooks WHERE key = 'last_reference'"
    ).fetchone()
    if not row:
        return None
    import json

    result = dict(row)
    try:
        result["validation"] = json.loads(result.pop("validation_json") or "{}")
    except json.JSONDecodeError:
        result["validation"] = {}
    return result


def load_last_workbook(connection: sqlite3.Connection) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT source_name, source_hash, source_payload, organized_payload, validation_json, saved_at "
        "FROM saved_workbooks WHERE key = 'last_reference'"
    ).fetchone()
    return dict(row) if row else None

def session_list(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    active = ensure_active_session(connection)["id"]
    rows = connection.execute(
        """
        SELECT s.*,
               COUNT(e.id) AS entry_count,
               COALESCE(SUM(e.amount), 0) AS total_amount,
               COALESCE(SUM(CASE WHEN e.broken_box = 1 THEN e.amount ELSE 0 END), 0) AS broken_amount
        FROM sessions s
        LEFT JOIN entries e ON e.session_id = s.id AND e.attempt = s.recount_attempt
        GROUP BY s.id
        ORDER BY s.created_at DESC
        """
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["active"] = item["id"] == active
        result.append(item)
    return result


def replace_comparison_results(
    connection: sqlite3.Connection,
    session_id: str,
    mode: str,
    results: list[dict[str, Any]],
) -> None:
    connection.execute("DELETE FROM comparison_results WHERE session_id = ?", (session_id,))
    created_at = utc_now()
    for result in results:
        connection.execute(
            """
            INSERT INTO comparison_results
            (session_id, mode, result, item, color, counted, baseline, end_value,
             difference, broken_amount, source_rows, last_updated, explanation, created_at,
             match_key, difference_percent, within_tolerance, review_status, movement_warning, attempt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                mode,
                result["result"],
                result["item"],
                result["color"],
                result["counted"],
                result.get("baseline"),
                result.get("end_value"),
                result.get("difference"),
                result.get("broken_amount", 0),
                result.get("source_rows", 0),
                result.get("last_updated", ""),
                result.get("explanation", ""),
                created_at,
                result.get("match_key", ""),
                result.get("difference_percent"),
                None if result.get("within_tolerance") is None else int(bool(result["within_tolerance"])),
                result.get("review_status", ""),
                result.get("movement_warning", ""),
                int(result.get("attempt", 1)),
            ),
        )
    add_audit(connection, session_id, "COMPARE", "", "", f"{mode}: {len(results)} results")
