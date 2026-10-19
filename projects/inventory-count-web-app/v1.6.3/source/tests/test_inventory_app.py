from __future__ import annotations

import io
import json
import sqlite3
import struct
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from inventory_app.comparison import compare_old_new, compare_reference
from inventory_app.database import (
    catalog_summary,
    connect,
    current_session,
    init_database,
    search_catalog_items,
    session_entries,
)
from inventory_app.rules import (
    InventoryError,
    comparison_key,
    count_make,
    group_entries,
    item_details,
    validate_entry,
)
from inventory_app.xlsxio import (
    DOC_REL_NS,
    MAIN_NS,
    PACKAGE_REL_NS,
    build_organized_workbook,
    build_organized_rows_workbook,
    build_inventory_workbook,
    _excel_datetime,
    extract_organized_rows,
    parse_count_workbook,
    parse_reference_workbook,
    read_xlsx_sheets,
    split_model_memory,
)
from server import InventoryHTTPServer


def sample_entry(**overrides):
    entry = {
        "id": "entry-1",
        "model": "Phone X",
        "ram": "8 GB",
        "storage": "256 GB",
        "color": "Black",
        "items_per_box": 10,
        "boxes": 2,
        "loose_items": 3,
        "amount": 23,
        "area": "Shelf A",
        "broken_box": False,
        "counted_at": "2026-08-24T12:00:00Z",
    }
    entry.update(overrides)
    return entry


def reference_workbook_bytes(
    sheet_name="Reference",
    date_header="Last Updated",
    date_value="2026-08-24",
):
    sheet = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="{MAIN_NS}"><sheetData>
<row r="1">
  <c r="A1" t="inlineStr"><is><t>MAKE</t></is></c>
  <c r="B1" t="inlineStr"><is><t>COLOR</t></is></c>
  <c r="C1" t="inlineStr"><is><t>START</t></is></c>
  <c r="D1" t="inlineStr"><is><t>END</t></is></c>
  <c r="E1" t="inlineStr"><is><t>{date_header}</t></is></c>
</row>
<row r="2">
  <c r="A2" t="inlineStr"><is><t>Phone X 8+256</t></is></c>
  <c r="B2" t="inlineStr"><is><t>Black</t></is></c>
  <c r="C2"><v>23</v></c><c r="D2"><v>20</v></c>
  <c r="E2" t="inlineStr"><is><t>{date_value}</t></is></c>
</row>
</sheetData></worksheet>'''
    workbook = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="{MAIN_NS}" xmlns:r="{DOC_REL_NS}"><sheets>
<sheet name="{sheet_name}" sheetId="1" r:id="rId1"/>
</sheets></workbook>'''
    relationships = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="{PACKAGE_REL_NS}">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>'''
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", relationships)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return output.getvalue()


def autocomplete_workbook_bytes():
    return build_organized_rows_workbook(
        [
            {
                "model": "X2425-3", "ram": "8 GB", "storage": "256 GB", "color": "Black",
                "start": "10", "end": "9", "date_counted": datetime(2026, 9, 8, 8, 0),
            },
            {
                "model": "X2425-3", "ram": "12 GB", "storage": "512 GB", "color": "Blue",
                "start": "7", "end": "7", "date_counted": datetime(2026, 9, 8, 8, 5),
            },
            {
                "model": "X2425-3", "ram": "8 GB", "storage": "256 GB", "color": "Black",
                "start": "10", "end": "9", "date_counted": datetime(2026, 9, 8, 8, 10),
            },
            {
                "model": "Cable", "ram": "", "storage": "", "color": "White",
                "start": "20", "end": "18", "date_counted": datetime(2026, 9, 8, 8, 15),
            },
        ]
    )


def unlabeled_date_column_workbook_bytes():
    sheet = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="{MAIN_NS}"><sheetData>
<row r="1">
  <c r="A1" t="inlineStr"><is><t>MAKE</t></is></c>
  <c r="B1" t="inlineStr"><is><t>COLOR</t></is></c>
  <c r="C1" t="inlineStr"><is><t>START</t></is></c>
  <c r="D1" t="inlineStr"><is><t>END</t></is></c>
  <c r="E1" t="inlineStr"><is><t> </t></is></c>
</row>
<row r="2"><c r="A2" t="inlineStr"><is><t>Item A</t></is></c><c r="B2" t="inlineStr"><is><t>Black</t></is></c><c r="C2"><v>1</v></c><c r="D2"><v>1</v></c><c r="E2"><v>46062</v></c></row>
<row r="3"><c r="A3" t="inlineStr"><is><t>Item B</t></is></c><c r="B3" t="inlineStr"><is><t>Blue</t></is></c><c r="C3"><v>2</v></c><c r="D3"><v>2</v></c><c r="E3" t="inlineStr"><is><t>11/13</t></is></c></row>
<row r="4"><c r="A4" t="inlineStr"><is><t>Item C</t></is></c><c r="B4" t="inlineStr"><is><t>White</t></is></c><c r="C4"><v>3</v></c><c r="D4"><v>3</v></c><c r="E4"><v>46274</v></c></row>
</sheetData></worksheet>'''
    workbook = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="{MAIN_NS}" xmlns:r="{DOC_REL_NS}"><sheets>
<sheet name="09092026" sheetId="1" r:id="rId1"/>
</sheets></workbook>'''
    relationships = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="{PACKAGE_REL_NS}">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>'''
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", relationships)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return output.getvalue()


class IdentityRuleTests(unittest.TestCase):
    def test_non_memory_item_omits_zero_zero(self):
        entry = sample_entry(model="Cable", ram="0", storage="0", color="White")
        self.assertEqual(count_make("Cable", "0", "0"), "Cable")
        self.assertEqual(item_details(entry), "Cable")
        self.assertEqual(comparison_key("Cable", "0", "0", "White"), "CABLE|WHITE")

    def test_broken_box_is_displayed_but_not_part_of_identity(self):
        normal = sample_entry()
        broken = sample_entry(id="entry-2", broken_box=True, amount=2, area="Shelf B")
        self.assertIn("Broken Box", item_details(broken))
        self.assertEqual(
            comparison_key(normal["model"], normal["ram"], normal["storage"], normal["color"]),
            comparison_key(broken["model"], broken["ram"], broken["storage"], broken["color"]),
        )
        group = group_entries([normal, broken])[0]
        self.assertEqual(group["amount"], 25)
        self.assertEqual(group["broken_amount"], 2)
        self.assertEqual(group["source_rows"], 2)

    def test_partial_zero_is_rejected(self):
        with self.assertRaises(InventoryError):
            validate_entry(
                {
                    "model": "Phone", "ram": "0", "storage": "256 GB", "color": "Black",
                    "items_per_box": 1, "boxes": 1, "loose_items": 0, "area": "A",
                }
            )

    def test_amount_formula(self):
        result = validate_entry(
            {
                "model": "Phone", "ram": "8 GB", "storage": "256 GB", "color": "black",
                "items_per_box": 10, "boxes": 4, "loose_items": 3, "area": "A",
            }
        )
        self.assertEqual(result["amount"], 43)
        self.assertEqual(result["color"], "Black")

    def test_organizer_splits_combined_memory_and_omits_zero_zero(self):
        self.assertEqual(
            split_model_memory("Phone X 8+256"),
            ("Phone X", "8 GB", "256 GB"),
        )
        self.assertEqual(split_model_memory("Cable 0+0"), ("Cable", "", ""))
        self.assertEqual(
            split_model_memory("Tablet Z", "12 GB", "512 GB"),
            ("Tablet Z", "12 GB", "512 GB"),
        )


class WorkbookAndComparisonTests(unittest.TestCase):
    def test_organized_copy_has_requested_columns_and_preserves_source(self):
        source = reference_workbook_bytes()
        original_bytes = bytes(source)
        extracted, sections = extract_organized_rows(source)
        workbook, row_count, packaged_sections = build_organized_workbook(source)

        self.assertEqual(source, original_bytes)
        self.assertEqual(sections, 1)
        self.assertEqual(packaged_sections, 1)
        self.assertEqual(row_count, 1)
        self.assertEqual(extracted[0]["model"], "Phone X")
        self.assertEqual(extracted[0]["ram"], "8 GB")
        self.assertEqual(extracted[0]["storage"], "256 GB")

        sheet = read_xlsx_sheets(workbook)[0]
        self.assertEqual(sheet["name"], "Organized Data")
        self.assertEqual(
            [sheet["rows"][0]["cells"][column] for column in range(7)],
            ["Model", "RAM", "Storage", "Color", "START", "END", "Date Counted"],
        )
        self.assertEqual(sheet["rows"][1]["cells"][0], "Phone X")
        self.assertEqual(sheet["rows"][1]["cells"][1], "8 GB")
        self.assertEqual(sheet["rows"][1]["cells"][2], "256 GB")
        self.assertEqual(sheet["rows"][1]["cells"][3], "Black")
        self.assertEqual(sheet["rows"][1]["cells"][4], "23")
        self.assertEqual(sheet["rows"][1]["cells"][5], "20")
        self.assertTrue(sheet["rows"][1]["cells"][6])

    def test_reference_parser_and_start_baseline(self):
        references, sections = parse_reference_workbook(reference_workbook_bytes())
        self.assertEqual(sections, 1)
        self.assertEqual(len(references), 1)
        results = compare_reference([sample_entry()], references)
        self.assertEqual(results[0]["result"], "MATCH")
        self.assertEqual(results[0]["baseline"], 23)
        self.assertIn("START", results[0]["explanation"])

    def test_sheet_name_is_never_used_as_product_date(self):
        source = reference_workbook_bytes(
            sheet_name="09092026",
            date_header=" ",
            date_value="46062",
        )
        organized, _ = extract_organized_rows(source)
        references, _ = parse_reference_workbook(source)
        self.assertEqual(organized[0]["date_counted"], "")
        self.assertEqual(references[0]["last_updated"], "(not provided)")

    def test_reliable_unlabeled_date_column_overrides_sheet_date_and_keeps_partial_dates(self):
        source = unlabeled_date_column_workbook_bytes()
        organized, _ = extract_organized_rows(source)
        references, _ = parse_reference_workbook(source)
        self.assertEqual(organized[0]["date_counted"], datetime(2026, 2, 9))
        self.assertEqual(organized[1]["date_counted"], "11/13")
        self.assertEqual(organized[2]["date_counted"], datetime(2026, 9, 9))
        self.assertEqual(
            [row["last_updated"] for row in references],
            ["02/09/2026", "11/13", "09/09/2026"],
        )

    def test_old_new_comparison(self):
        old = [sample_entry(amount=20)]
        new = [sample_entry(amount=23)]
        result = compare_old_new(old, new)[0]
        self.assertEqual(result["result"], "AMOUNT CHANGED")
        self.assertEqual(result["difference"], 3)

    def test_old_count_against_reference(self):
        old_count = [sample_entry(amount=20)]
        references, _ = parse_reference_workbook(reference_workbook_bytes())
        result = compare_reference(old_count, references)[0]
        self.assertEqual(result["result"], "MISSING ITEMS")
        self.assertEqual(result["baseline"], 23)
        self.assertEqual(result["counted"], 20)
        self.assertEqual(result["difference"], 3)

    def test_export_round_trip_and_hidden_detailed_data(self):
        session = {"id": "session-1", "name": "Test Count", "status": "DRAFT"}
        entries = [sample_entry(), sample_entry(id="entry-2", model="Cable", ram="0", storage="0", amount=5)]
        payload = build_inventory_workbook(session, entries, [], [])
        sheets = read_xlsx_sheets(payload)
        self.assertEqual(sheets[0]["name"], "Inventory Count")
        self.assertEqual(sheets[0]["rows"][0]["cells"][4], "Entered At")
        detailed = next(sheet for sheet in sheets if sheet["name"] == "Detailed Data")
        self.assertTrue(detailed["hidden"])
        self.assertEqual(detailed["rows"][0]["cells"][10], "Entered At")
        imported = parse_count_workbook(payload)
        self.assertEqual(len(imported), 2)
        self.assertEqual(count_make(imported[1]["model"], imported[1]["ram"], imported[1]["storage"]), "Cable")
        expected_local_time = _excel_datetime(sample_entry()["counted_at"])
        self.assertIsNotNone(expected_local_time)
        self.assertEqual(imported[0]["counted_at"], expected_local_time.isoformat())

    def test_organized_copy_preserves_partial_date_text(self):
        workbook = build_organized_rows_workbook([
            {
                "model": "Phone X", "ram": "8 GB", "storage": "256 GB", "color": "Black",
                "start": "10", "end": "9", "date_counted": "11/13",
            }
        ])
        rows, sections = extract_organized_rows(workbook)
        self.assertEqual(sections, 1)
        self.assertEqual(rows[0]["date_counted"], "11/13")

    def test_excel_entry_time_converts_to_local_time(self):
        eastern = timezone(timedelta(hours=-4))
        converted = _excel_datetime("2026-08-24T12:12:00Z", eastern)
        self.assertEqual(converted, datetime(2026, 8, 24, 8, 12))


class DatabaseAndHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / "inventory.db"
        init_database(self.database)

    def tearDown(self):
        # sqlite3.Connection context managers commit/rollback but do not close.
        # Force collection before removing the temporary database on Windows,
        # where open SQLite handles otherwise block directory deletion.
        import gc
        gc.collect()
        self.temp.cleanup()

    def test_database_creates_active_session(self):
        with connect(self.database) as connection:
            session = current_session(connection)
            self.assertEqual(session["status"], "DRAFT")
            self.assertEqual(session_entries(connection, session["id"]), [])

    def test_existing_version_14_database_migrates_without_replacement(self):
        legacy_database = Path(self.temp.name) / "legacy.db"
        with sqlite3.connect(legacy_database) as connection:
            connection.executescript(
                """
                CREATE TABLE sessions (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, status TEXT NOT NULL,
                    created_at TEXT NOT NULL, finalized_at TEXT
                );
                CREATE TABLE entries (
                    id TEXT PRIMARY KEY, session_id TEXT NOT NULL, model TEXT NOT NULL,
                    ram TEXT NOT NULL, storage TEXT NOT NULL, color TEXT NOT NULL,
                    items_per_box INTEGER NOT NULL, boxes INTEGER NOT NULL,
                    loose_items INTEGER NOT NULL, amount INTEGER NOT NULL, area TEXT NOT NULL,
                    broken_box INTEGER NOT NULL, counted_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE comparison_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, mode TEXT NOT NULL,
                    result TEXT NOT NULL, item TEXT NOT NULL, color TEXT NOT NULL, counted INTEGER NOT NULL,
                    baseline INTEGER, end_value INTEGER, difference INTEGER, broken_amount INTEGER NOT NULL,
                    source_rows INTEGER NOT NULL, last_updated TEXT NOT NULL, explanation TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                INSERT INTO sessions VALUES ('legacy-session', 'Legacy Count', 'DRAFT', '2026-08-01T00:00:00Z', NULL);
                INSERT INTO entries VALUES (
                    'legacy-entry', 'legacy-session', 'Cable', '0', '0', 'White',
                    0, 0, 4, 4, 'Shelf A', 0, '2026-08-01T01:00:00Z', '2026-08-01T01:00:00Z'
                );
                """
            )
        init_database(legacy_database)
        with connect(legacy_database) as connection:
            session = current_session(connection)
            entries = session_entries(connection, session["id"])
            session_columns = {row["name"] for row in connection.execute("PRAGMA table_info(sessions)")}
        self.assertEqual(session["name"], "Legacy Count")
        self.assertEqual(entries[0]["amount"], 4)
        self.assertEqual(entries[0]["attempt"], 1)
        self.assertIn("workflow_status", session_columns)
        self.assertTrue(session["session_number"].startswith("CC-"))

    def test_health_and_entry_api(self):
        server = InventoryHTTPServer(("127.0.0.1", 0), self.database)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with urllib.request.urlopen(f"{base}/api/health") as response:
                self.assertEqual(json.load(response)["status"], "ok")
            with urllib.request.urlopen(f"{base}/") as response:
                self.assertIn(b"Inventory Count Web App", response.read())
            payload = json.dumps(
                {
                    "model": "Phone X", "ram": "8 GB", "storage": "256 GB", "color": "Black",
                    "items_per_box": 10, "boxes": 2, "loose_items": 3, "area": "Bin 4",
                    "broken_box": True,
                }
            ).encode()
            request = urllib.request.Request(
                f"{base}/api/entries", data=payload, method="POST", headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(request) as response:
                self.assertEqual(response.status, 201)
            with urllib.request.urlopen(f"{base}/api/state") as response:
                state = json.load(response)
            self.assertEqual(state["summary"]["total_amount"], 23)
            self.assertEqual(state["entries"][0]["item_details"], "Phone X · 8 GB · 256 GB · Broken Box")
            entered_at = state["entries"][0]["counted_at"]
            self.assertRegex(entered_at, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

            edited_payload = json.dumps(
                {
                    "model": "Phone X", "ram": "8 GB", "storage": "256 GB", "color": "Black",
                    "items_per_box": 10, "boxes": 2, "loose_items": 3, "area": "Bin 5",
                    "broken_box": True,
                }
            ).encode()
            edit_request = urllib.request.Request(
                f"{base}/api/entries/{state['entries'][0]['id']}", data=edited_payload, method="PUT",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(edit_request) as response:
                self.assertEqual(response.status, 200)
            with urllib.request.urlopen(f"{base}/api/state") as response:
                edited_state = json.load(response)
            self.assertEqual(edited_state["entries"][0]["counted_at"], entered_at)
            self.assertEqual(edited_state["entries"][0]["area"], "Bin 5")

            duplicate_request = urllib.request.Request(
                f"{base}/api/entries", data=payload, method="POST", headers={"Content-Type": "application/json"}
            )
            with self.assertRaises(urllib.error.HTTPError) as duplicate_error:
                urllib.request.urlopen(duplicate_request)
            self.assertEqual(duplicate_error.exception.code, 409)

            compare_request = urllib.request.Request(
                f"{base}/api/compare/reference",
                data=reference_workbook_bytes(),
                method="POST",
                headers={"Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
            )
            with urllib.request.urlopen(compare_request) as response:
                self.assertEqual(json.load(response)["result_count"], 1)
            with urllib.request.urlopen(f"{base}/api/state") as response:
                compared_state = json.load(response)
            self.assertEqual(compared_state["comparisons"][0]["result"], "MATCH")

            with urllib.request.urlopen(f"{base}/api/export") as response:
                exported = response.read()
            self.assertEqual(read_xlsx_sheets(exported)[0]["name"], "Inventory Count")

            source = reference_workbook_bytes()
            organize_request = urllib.request.Request(
                f"{base}/api/organize?name={quote('Daily Count.xlsx')}",
                data=source,
                method="POST",
                headers={"Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
            )
            with urllib.request.urlopen(organize_request) as response:
                organized = response.read()
                self.assertEqual(response.headers["X-Original-Modified"], "false")
                self.assertEqual(response.headers["X-Organized-Rows"], "1")
                self.assertIn("Daily_Count_Organized.xlsx", response.headers["Content-Disposition"])
            self.assertEqual(source, reference_workbook_bytes())
            self.assertEqual(read_xlsx_sheets(organized)[0]["name"], "Organized Data")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_organized_workbook_loads_persistent_autocomplete_variants(self):
        server = InventoryHTTPServer(("127.0.0.1", 0), self.database)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        source = autocomplete_workbook_bytes()
        try:
            organize_request = urllib.request.Request(
                f"{base}/api/organize?name={quote('Warehouse Organized.xlsx')}",
                data=source,
                method="POST",
                headers={"Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
            )
            with urllib.request.urlopen(organize_request) as response:
                self.assertEqual(response.headers["X-Original-Modified"], "false")
                self.assertEqual(response.headers["X-Organized-Rows"], "4")
                self.assertEqual(response.headers["X-Catalog-Variants"], "3")
                response.read()

            with urllib.request.urlopen(f"{base}/api/catalog?q={quote('X2425-3')}") as response:
                result = json.load(response)
            self.assertEqual(len(result["items"]), 2)
            self.assertEqual(
                {(item["ram"], item["storage"], item["color"]) for item in result["items"]},
                {("8 GB", "256 GB", "Black"), ("12 GB", "512 GB", "Blue")},
            )
            self.assertEqual(result["catalog"]["variant_count"], 3)
            self.assertEqual(result["catalog"]["source_name"], "Warehouse Organized.xlsx")
            black_variant = next(item for item in result["items"] if item["color"] == "Black")
            self.assertEqual(black_variant["reference_quantity"], 10)
            self.assertEqual(black_variant["source_rows"], 2)
            self.assertIn("Organized Data!2", black_variant["source_locations"])
            self.assertIn("Organized Data!4", black_variant["source_locations"])

            with urllib.request.urlopen(f"{base}/api/catalog?q={quote('Cable')}") as response:
                non_memory = json.load(response)["items"][0]
            self.assertEqual(non_memory["ram"], "")
            self.assertEqual(non_memory["storage"], "")
            self.assertEqual(non_memory["reference_quantity"], 20)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

        init_database(self.database)
        with connect(self.database) as connection:
            self.assertEqual(catalog_summary(connection)["variant_count"], 3)
            self.assertEqual(len(search_catalog_items(connection, "X2425-3")), 2)

    def test_last_validated_workbook_can_be_downloaded_and_reused(self):
        server = InventoryHTTPServer(("127.0.0.1", 0), self.database)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            source = autocomplete_workbook_bytes()
            organize_request = urllib.request.Request(
                f"{base}/api/organize?name={quote('Daily Warehouse.xlsx')}",
                data=source, method="POST",
                headers={"Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
            )
            with urllib.request.urlopen(organize_request) as response:
                response.read()

            with urllib.request.urlopen(f"{base}/api/reference/last") as response:
                saved = json.load(response)["workbook"]
            self.assertEqual(saved["source_name"], "Daily Warehouse.xlsx")
            self.assertEqual(saved["validation"]["extracted_rows"], 4)
            self.assertEqual(saved["validation"]["duplicate_rows"], 1)

            with urllib.request.urlopen(f"{base}/api/reference/last/download") as response:
                organized = response.read()
            self.assertEqual(read_xlsx_sheets(organized)[0]["name"], "Organized Data")

            create_request = urllib.request.Request(
                f"{base}/api/sessions", data=json.dumps({"name": "Reuse Test"}).encode(), method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(create_request) as response:
                session = json.load(response)["session"]
            reuse_request = urllib.request.Request(
                f"{base}/api/sessions/{session['id']}/reference/reuse",
                data=b"{}", method="POST", headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(reuse_request) as response:
                reused = json.load(response)
            self.assertEqual(reused["source_name"], "Daily Warehouse.xlsx")
            self.assertEqual(reused["catalog_variants"], 3)
            with urllib.request.urlopen(f"{base}/api/state") as response:
                state = json.load(response)
            self.assertEqual(state["reference"]["source_name"], "Daily Warehouse.xlsx")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_old_reference_api_does_not_require_current_entries(self):
        server = InventoryHTTPServer(("127.0.0.1", 0), self.database)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            session = {"id": "old-session", "name": "Old Count", "status": "FINALIZED"}
            old_workbook = build_inventory_workbook(session, [sample_entry()], [], [])
            reference_workbook = reference_workbook_bytes()
            request_body = struct.pack(">I", len(old_workbook)) + old_workbook + reference_workbook
            compare_request = urllib.request.Request(
                f"{base}/api/compare/old-reference",
                data=request_body,
                method="POST",
                headers={"Content-Type": "application/vnd.inventory.old-reference"},
            )
            with urllib.request.urlopen(compare_request) as response:
                result = json.load(response)
            self.assertEqual(result["result_count"], 1)
            self.assertEqual(result["old_rows"], 1)
            self.assertEqual(result["reference_rows"], 1)

            with urllib.request.urlopen(f"{base}/api/state") as response:
                compared_state = json.load(response)
            self.assertEqual(compared_state["comparisons"][0]["mode"], "OLD_REFERENCE")
            self.assertEqual(compared_state["comparisons"][0]["result"], "MATCH")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_cycle_count_frozen_reference_review_movement_and_export(self):
        server = InventoryHTTPServer(("127.0.0.1", 0), self.database)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def post_json(path, payload):
            request = urllib.request.Request(
                f"{base}{path}", data=json.dumps(payload).encode(), method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request) as response:
                return json.load(response)

        try:
            created = post_json(
                "/api/sessions",
                {
                    "name": "Planned Cycle A", "count_type": "PLANNED", "warehouse": "Warehouse A",
                    "location": "Bin 4", "operator_name": "Counter A", "quantity_tolerance": 1,
                    "percentage_tolerance": 0,
                },
            )["session"]
            reference_request = urllib.request.Request(
                f"{base}/api/sessions/{created['id']}/reference?name=Reference.xlsx",
                data=reference_workbook_bytes(), method="POST",
                headers={"Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
            )
            with urllib.request.urlopen(reference_request) as response:
                self.assertEqual(response.headers["X-Original-Modified"], "false")
                self.assertEqual(len(response.headers["X-Reference-Hash"]), 64)
                response.read()

            post_json(
                "/api/movements",
                {
                    "movement_type": "SHIPMENT", "model": "Phone X", "ram": "8 GB",
                    "storage": "256 GB", "color": "Black", "quantity": 1,
                    "from_location": "Bin 4", "to_location": "Dispatch", "operator_name": "Operator B",
                    "note": "Recorded during count window",
                },
            )
            post_json(
                "/api/entries",
                {
                    "model": "Phone X", "ram": "8 GB", "storage": "256 GB", "color": "Black",
                    "items_per_box": 10, "boxes": 2, "loose_items": 2, "area": "Bin 4",
                    "broken_box": False,
                },
            )
            with urllib.request.urlopen(f"{base}/api/state") as response:
                counting_state = json.load(response)
            self.assertEqual(counting_state["session"]["workflow_status"], "COUNTING")
            self.assertEqual(len(counting_state["comparisons"]), 1)
            self.assertEqual(counting_state["comparisons"][0]["baseline"], 23)
            self.assertEqual(counting_state["comparisons"][0]["counted"], 22)
            self.assertEqual(counting_state["comparisons"][0]["difference"], 1)

            submitted = post_json(f"/api/sessions/{created['id']}/submit", {})
            self.assertEqual(submitted["workflow_status"], "PENDING_REVIEW")
            with urllib.request.urlopen(f"{base}/api/state") as response:
                review_state = json.load(response)
            self.assertEqual(review_state["comparisons"][0]["review_status"], "PENDING REVIEW")
            self.assertTrue(review_state["comparisons"][0]["within_tolerance"])
            self.assertIn("Shipment", review_state["comparisons"][0]["movement_warning"])

            reviewed = post_json(
                f"/api/sessions/{created['id']}/review",
                {"action": "APPROVE", "reviewer": "Supervisor A", "reason": "Verified movement record"},
            )
            self.assertEqual(reviewed["workflow_status"], "APPROVED")
            post_json(f"/api/sessions/{created['id']}/finalize", {})
            with urllib.request.urlopen(f"{base}/api/export") as response:
                sheets = read_xlsx_sheets(response.read())
            names = [sheet["name"] for sheet in sheets]
            self.assertIn("Summary", names)
            self.assertIn("Movement Log", names)
            self.assertIn("Count Attempts", names)
            self.assertTrue(next(sheet for sheet in sheets if sheet["name"] == "Detailed Data")["hidden"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_recount_keeps_prior_attempt_and_opens_empty_current_attempt(self):
        server = InventoryHTTPServer(("127.0.0.1", 0), self.database)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"

        def post_json(path, payload):
            request = urllib.request.Request(
                f"{base}{path}", data=json.dumps(payload).encode(), method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request) as response:
                return json.load(response)

        try:
            created = post_json("/api/sessions", {"name": "Recount Test"})["session"]
            reference_request = urllib.request.Request(
                f"{base}/api/sessions/{created['id']}/reference?name=Reference.xlsx",
                data=reference_workbook_bytes(), method="POST",
                headers={"Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
            )
            with urllib.request.urlopen(reference_request) as response:
                response.read()
            entry = {
                "model": "Phone X", "ram": "8 GB", "storage": "256 GB", "color": "Black",
                "items_per_box": 10, "boxes": 2, "loose_items": 0, "area": "Bin 4",
            }
            post_json("/api/entries", entry)
            self.assertEqual(
                post_json(f"/api/sessions/{created['id']}/submit", {})["workflow_status"],
                "RECOUNT_REQUIRED",
            )
            post_json(
                f"/api/sessions/{created['id']}/review",
                {"action": "RECOUNT", "reviewer": "Supervisor A", "reason": "Physical verification required"},
            )
            with urllib.request.urlopen(f"{base}/api/state") as response:
                recount_state = json.load(response)
            self.assertEqual(recount_state["session"]["recount_attempt"], 2)
            self.assertEqual(recount_state["entries"], [])
            self.assertEqual(recount_state["attempts"][0]["decision"], "RECOUNT")

            entry["loose_items"] = 3
            post_json("/api/entries", entry)
            second = post_json(f"/api/sessions/{created['id']}/submit", {})
            self.assertEqual(second["workflow_status"], "APPROVED")
            with connect(self.database) as connection:
                attempts = connection.execute(
                    "SELECT attempt, status FROM cycle_count_attempts WHERE session_id = ? ORDER BY attempt",
                    (created["id"],),
                ).fetchall()
                captured_rows = connection.execute(
                    "SELECT attempt, amount FROM entries WHERE session_id = ? ORDER BY attempt",
                    (created["id"],),
                ).fetchall()
            self.assertEqual([(row["attempt"], row["status"]) for row in attempts], [(1, "RECOUNT_REQUIRED"), (2, "APPROVED")])
            self.assertEqual([(row["attempt"], row["amount"]) for row in captured_rows], [(1, 20), (2, 23)])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_organizer_preview_does_not_change_catalog(self):
        server = InventoryHTTPServer(("127.0.0.1", 0), self.database)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            preview_request = urllib.request.Request(
                f"{base}/api/organize/preview", data=autocomplete_workbook_bytes(), method="POST",
                headers={"Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
            )
            with urllib.request.urlopen(preview_request) as response:
                preview = json.load(response)
            self.assertEqual(preview["row_count"], 4)
            self.assertEqual(preview["variant_count"], 3)
            self.assertEqual(preview["duplicate_rows"], 1)
            self.assertEqual(preview["dated_rows"], 4)
            self.assertEqual(preview["candidate_rows"], 4)
            self.assertEqual(preview["extracted_rows"], 4)
            self.assertEqual(preview["skipped_rows"], 0)
            self.assertEqual(preview["duplicate_group_count"], 1)
            self.assertEqual(preview["detected_dates"], ["2026-09-08"])
            with connect(self.database) as connection:
                self.assertEqual(catalog_summary(connection)["variant_count"], 0)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
