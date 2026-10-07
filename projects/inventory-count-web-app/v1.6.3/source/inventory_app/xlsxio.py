"""Dependency-free XLSX reader and writer used by the local Python web app."""

from __future__ import annotations

import io
import posixpath
import re
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Any
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape, quoteattr

from .rules import (
    InventoryError,
    clean_text,
    count_make,
    has_partial_zero_memory,
    item_details,
    normalize_color_key,
    normalize_header,
    normalize_make_key,
    parse_whole_number,
)


MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
DOC_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _tag(namespace: str, name: str) -> str:
    return f"{{{namespace}}}{name}"


def _column_number(reference: str) -> int:
    letters = re.match(r"^[A-Za-z]+", reference or "")
    number = 0
    for character in (letters.group(0).upper() if letters else ""):
        number = (number * 26) + (ord(character) - ord("A") + 1)
    return number - 1


def _column_name(index: int) -> str:
    number = index + 1
    result = ""
    while number > 0:
        number, remainder = divmod(number - 1, 26)
        result = chr(ord("A") + remainder) + result
    return result


def _cell_text(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t", "")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(f".//{_tag(MAIN_NS, 't')}"))
    value = cell.find(_tag(MAIN_NS, "v"))
    if value is None:
        return ""
    raw = value.text or ""
    if cell_type == "s":
        try:
            index = int(raw)
            return shared_strings[index] if 0 <= index < len(shared_strings) else ""
        except (ValueError, IndexError):
            return ""
    if cell_type == "b":
        return "TRUE" if raw == "1" else "FALSE"
    return raw


def read_xlsx_sheets(payload: bytes) -> list[dict[str, Any]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(payload), "r")
    except (zipfile.BadZipFile, OSError) as exc:
        raise InventoryError("The selected file is not a valid .xlsx workbook.") from exc

    with archive:
        names = set(archive.namelist())
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in names:
            try:
                root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
                for item in root.findall(_tag(MAIN_NS, "si")):
                    shared_strings.append(
                        "".join(node.text or "" for node in item.findall(f".//{_tag(MAIN_NS, 't')}"))
                    )
            except ET.ParseError as exc:
                raise InventoryError("The workbook shared-string table is damaged.") from exc

        sheet_entries: list[tuple[str, str, bool]] = []
        if "xl/workbook.xml" in names and "xl/_rels/workbook.xml.rels" in names:
            try:
                workbook = ET.fromstring(archive.read("xl/workbook.xml"))
                relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
                targets = {
                    rel.attrib.get("Id", ""): rel.attrib.get("Target", "")
                    for rel in relationships.findall(_tag(PACKAGE_REL_NS, "Relationship"))
                }
                for sheet in workbook.findall(f".//{_tag(MAIN_NS, 'sheet')}"):
                    rel_id = sheet.attrib.get(_tag(DOC_REL_NS, "id"), "")
                    target = targets.get(rel_id, "")
                    if not target:
                        continue
                    path = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl", target))
                    if path in names:
                        sheet_entries.append(
                            (sheet.attrib.get("name", "Worksheet"), path, sheet.attrib.get("state") == "hidden")
                        )
            except ET.ParseError as exc:
                raise InventoryError("The workbook structure is damaged.") from exc

        if not sheet_entries:
            fallback = sorted(
                name for name in names if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name)
            )
            sheet_entries = [(f"Sheet {index + 1}", name, False) for index, name in enumerate(fallback)]
        if not sheet_entries:
            raise InventoryError("The workbook does not contain any readable worksheets.")

        sheets: list[dict[str, Any]] = []
        for sheet_name, path, hidden in sheet_entries:
            try:
                root = ET.fromstring(archive.read(path))
            except (KeyError, ET.ParseError) as exc:
                raise InventoryError(f"Worksheet '{sheet_name}' could not be read.") from exc
            rows = []
            for row_index, row_node in enumerate(root.findall(f".//{_tag(MAIN_NS, 'sheetData')}/{_tag(MAIN_NS, 'row')}"), 1):
                row_number = int(row_node.attrib.get("r") or row_index)
                cells: dict[int, str] = {}
                for cell in row_node.findall(_tag(MAIN_NS, "c")):
                    column = _column_number(cell.attrib.get("r", ""))
                    if column >= 0:
                        cells[column] = _cell_text(cell, shared_strings)
                rows.append({"row_number": row_number, "cells": cells})
            sheets.append({"name": sheet_name, "path": path, "hidden": hidden, "rows": rows})
        return sheets


def _reference_date(value: Any) -> dict[str, Any]:
    text = clean_text(value)
    if not text:
        return {"valid": False, "value": None, "sort": float("-inf"), "display": "(not provided)"}
    try:
        serial = float(text)
        if 30_000 <= serial <= 80_000:
            date_value = datetime(1899, 12, 30) + timedelta(seconds=round(serial * 86_400))
            return {
                "valid": True,
                "value": date_value,
                "sort": date_value.timestamp(),
                "display": date_value.strftime("%m/%d/%Y"),
            }
    except ValueError:
        pass
    candidate = text.replace("Z", "+00:00")
    try:
        date_value = datetime.fromisoformat(candidate)
        if date_value.tzinfo:
            date_value = date_value.astimezone(timezone.utc).replace(tzinfo=None)
        return {
            "valid": True,
            "value": date_value,
            "sort": date_value.timestamp(),
            "display": date_value.strftime("%m/%d/%Y"),
        }
    except ValueError:
        pass
    for pattern in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y", "%B %d, %Y", "%b %d, %Y"):
        try:
            date_value = datetime.strptime(text, pattern)
            return {
                "valid": True,
                "value": date_value,
                "sort": date_value.timestamp(),
                "display": date_value.strftime("%m/%d/%Y"),
            }
        except ValueError:
            continue
    return {"valid": False, "value": None, "sort": float("-inf"), "display": text}


def _date_from_row(row: dict[str, Any], date_column: int | None, excluded: set[int]) -> dict[str, Any]:
    if date_column is not None:
        return _reference_date(row["cells"].get(date_column))
    for column in sorted(row["cells"], reverse=True):
        if column in excluded:
            continue
        candidate = _reference_date(row["cells"].get(column))
        if candidate["valid"]:
            return candidate
    return _reference_date(None)


def _looks_like_partial_date(value: Any) -> bool:
    match = re.fullmatch(r"(\d{1,2})/(\d{1,2})", clean_text(value))
    if not match:
        return False
    month, day = (int(part) for part in match.groups())
    return 1 <= month <= 12 and 1 <= day <= 31


def _infer_date_column(
    rows: list[dict[str, Any]],
    first_row: int,
    last_row: int | None,
    excluded: set[int],
) -> int | None:
    """Find an unlabeled column whose populated values consistently look like dates."""

    statistics: dict[int, dict[str, int]] = {}
    for row in rows:
        row_number = int(row["row_number"])
        if row_number <= first_row or (last_row is not None and row_number >= last_row):
            continue
        for column, value in row["cells"].items():
            text = clean_text(value)
            if column in excluded or not text:
                continue
            column_stats = statistics.setdefault(column, {"populated": 0, "date_like": 0})
            column_stats["populated"] += 1
            if _reference_date(text)["valid"] or _looks_like_partial_date(text):
                column_stats["date_like"] += 1

    candidates = [
        (stats["date_like"] / stats["populated"], stats["date_like"], column)
        for column, stats in statistics.items()
        if stats["date_like"] >= 3 and stats["date_like"] / stats["populated"] >= 0.60
    ]
    return max(candidates)[2] if candidates else None


def _effective_row_date(
    row: dict[str, Any],
    date_column: int | None,
    inferred_date_column: int | None,
    excluded: set[int],
) -> dict[str, Any]:
    """Return only a date stored on this product row."""

    for column in (date_column, inferred_date_column):
        if column is None:
            continue
        raw_value = clean_text(row["cells"].get(column))
        if raw_value:
            return _reference_date(raw_value)
    return _reference_date(None)


ORGANIZE_HEADER_ALIASES = {
    "make": "model",
    "model": "model",
    "itemmodel": "model",
    "productmodel": "model",
    "ram": "ram",
    "randomaccessmemory": "ram",
    "storage": "storage",
    "memory": "storage",
    "internalmemory": "storage",
    "internalstorage": "storage",
    "capacity": "storage",
    "rom": "storage",
    "color": "color",
    "colour": "color",
    "start": "start",
    "startcount": "start",
    "startingcount": "start",
    "openingcount": "start",
    "end": "end",
    "endt": "end",
    "endcount": "end",
    "endingcount": "end",
    "finalcount": "end",
    "startend": "start_end",
    "startendt": "start_end",
    "date": "date",
    "datecounted": "date",
    "counteddate": "date",
    "countedat": "date",
    "lastupdated": "date",
    "updated": "date",
    "updateddate": "date",
    "dateupdated": "date",
    "lastupdate": "date",
    "updatedon": "date",
    "lastupdateddate": "date",
}


def _display_memory(value: Any, default_unit: str = "GB") -> str:
    text = clean_text(value)
    if not text:
        return ""
    compact = re.sub(r"\s+", "", text).upper()
    if compact in {"0", "0GB", "0G", "0TB", "0T"}:
        return "0"
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(TB|GB|T|G)?", text, re.IGNORECASE)
    if not match:
        return text
    number, unit = match.groups()
    normalized_unit = {"T": "TB", "G": "GB"}.get((unit or default_unit).upper(), (unit or default_unit).upper())
    return f"{number} {normalized_unit}"


def split_model_memory(model_value: Any, ram_value: Any = "", storage_value: Any = "") -> tuple[str, str, str]:
    """Return separate model, RAM, and Storage values without inventing a 0+0 identity."""

    model = clean_text(model_value)    ram = _display_memory(ram_value)
    storage = _display_memory(storage_value)
    if ram or storage:
        if ram == "0" and storage == "0":
            return model, "", ""
        return model, ram, storage

    labeled = re.fullmatch(
        r"(?is)(?P<model>.+?)\s+(?:RAM\s*)?(?P<ram>\d+(?:\.\d+)?)\s*(?P<ram_unit>GB|G)?"
        r"\s*(?:\+|/|,|\s+)\s*(?:STORAGE|MEMORY|ROM)?\s*(?P<storage>\d+(?:\.\d+)?)"
        r"\s*(?P<storage_unit>TB|GB|T|G)?\s*",
        model,
    )
    compact = re.fullmatch(
        r"(?is)(?P<model>.+?)\s*(?:[-|]\s*)?\(?\s*(?P<ram>\d+(?:\.\d+)?)\s*(?P<ram_unit>GB|G)?"
        r"\s*(?:\+|/)\s*(?P<storage>\d+(?:\.\d+)?)\s*(?P<storage_unit>TB|GB|T|G)?\s*\)?\s*",
        model,
    )
    match = labeled or compact
    if not match:
        return model, "", ""

    separated_model = clean_text(match.group("model")).rstrip("-–—|,/").strip()
    ram_unit = match.group("ram_unit") or "GB"
    storage_unit = match.group("storage_unit") or "GB"
    ram = _display_memory(f"{match.group('ram')} {ram_unit}")
    storage = _display_memory(f"{match.group('storage')} {storage_unit}")
    if match.group("ram") == "0" and match.group("storage") == "0":
        return separated_model, "", ""
    return separated_model, ram, storage


def _split_start_end(value: Any) -> tuple[str, str]:
    text = clean_text(value)
    if not text:
        return "", ""
    parts = re.split(r"\s*(?:→|->|/|\||\bto\b)\s*", text, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) == 2:
        return clean_text(parts[0]), clean_text(parts[1])
    return text, ""


def analyze_organized_rows(payload: bytes) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
    """Extract rows and return a transparent import-validation report.

    The report counts every nonblank candidate row inside a recognized inventory
    section. Rows that cannot be imported are listed with the worksheet, row
    number, and reason so nothing disappears silently.
    """

    result: list[dict[str, Any]] = []
    section_count = 0
    sheets = read_xlsx_sheets(payload)
    skipped: list[dict[str, Any]] = []
    candidate_rows = 0
    section_details: list[dict[str, Any]] = []

    for sheet in sheets:
        headers: list[dict[str, Any]] = []
        for row in sheet["rows"]:
            found: dict[str, int] = {}
            for column, value in row["cells"].items():
                key = ORGANIZE_HEADER_ALIASES.get(normalize_header(value))
                if key and key not in found:
                    found[key] = column
            has_counts = "start" in found or "end" in found or "start_end" in found
            if "model" in found and "color" in found and has_counts:
                header = {"row_number": row["row_number"], **found}
                headers.append(header)
                section_count += 1
                section_details.append(
                    {
                        "sheet": sheet["name"],
                        "header_row": int(row["row_number"]),
                    }
                )
        if not headers:
            continue

        for index, header in enumerate(headers):
            next_header = headers[index + 1]["row_number"] if index + 1 < len(headers) else None
            excluded = {
                column for key, column in header.items()
                if key != "row_number"
            }
            header["inferred_date"] = _infer_date_column(
                sheet["rows"], header["row_number"], next_header, excluded
            )

        current: dict[str, Any] | None = None
        header_position = 0
        header_rows = {header["row_number"] for header in headers}
        for row in sheet["rows"]:
            while header_position < len(headers) and headers[header_position]["row_number"] < row["row_number"]:
                current = headers[header_position]
                header_position += 1
            if current is None or row["row_number"] in header_rows:
                continue

            relevant_columns = {
                column for key, column in current.items()
                if key in {"model", "ram", "storage", "color", "start", "end", "start_end", "date", "inferred_date"}
                and isinstance(column, int)
            }
            if not any(clean_text(row["cells"].get(column)) for column in relevant_columns):
                continue

            candidate_rows += 1
            raw_model = clean_text(row["cells"].get(current["model"]))
            raw_color = clean_text(row["cells"].get(current["color"]))
            raw_start = clean_text(row["cells"].get(current.get("start", -1)))
            raw_end = clean_text(row["cells"].get(current.get("end", -1)))
            if "start_end" in current:
                combined_start, combined_end = _split_start_end(row["cells"].get(current["start_end"]))
                raw_start = raw_start or combined_start
                raw_end = raw_end or combined_end

            if not raw_model:
                skipped.append(
                    {
                        "sheet": sheet["name"],
                        "row": int(row["row_number"]),
                        "reason": "Missing Model / MAKE",
                    }
                )
                continue
            if not raw_color and not raw_start and not raw_end:
                skipped.append(
                    {
                        "sheet": sheet["name"],
                        "row": int(row["row_number"]),
                        "reason": "Model exists, but Color and START/END are blank",
                        "model": raw_model,
                    }
                )
                continue

            model, ram, storage = split_model_memory(
                raw_model,
                row["cells"].get(current.get("ram", -1)),
                row["cells"].get(current.get("storage", -1)),
            )
            excluded = {
                column for key, column in current.items()
                if key in {"model", "ram", "storage", "color", "start", "end", "start_end"}
                and isinstance(column, int)
            }
            counted = _effective_row_date(
                row, current.get("date"), current.get("inferred_date"), excluded
            )
            counted_value = counted["value"] if counted["valid"] else (
                "" if counted["display"] == "(not provided)" else counted["display"]
            )
            result.append(
                {
                    "model": model,
                    "ram": ram,
                    "storage": storage,
                    "color": raw_color,
                    "start": raw_start,
                    "end": raw_end,
                    "date_counted": counted_value,
                    "source_sheet": sheet["name"],
                    "source_row": int(row["row_number"]),
                }
            )

    if section_count == 0:
        raise InventoryError(
            "No worksheet contains Model or MAKE, Color, and START, END, or START/END headers on the same row."
        )
    if not result:
        raise InventoryError("Organizing headers were found, but no inventory rows could be extracted.")

    duplicate_map: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for row in result:
        key = (
            str(row.get("model") or "").casefold(),
            str(row.get("ram") or "").casefold(),
            str(row.get("storage") or "").casefold(),
            str(row.get("color") or "").casefold(),
        )
        duplicate_map.setdefault(key, []).append(row)

    duplicate_groups: list[dict[str, Any]] = []
    for group in duplicate_map.values():
        if len(group) < 2:
            continue
        first = group[0]
        duplicate_groups.append(
            {
                "model": first["model"],
                "ram": first["ram"],
                "storage": first["storage"],
                "color": first["color"],
                "row_count": len(group),
                "source_rows": [f"{item['source_sheet']}!{item['source_row']}" for item in group[:20]],
            }
        )
    duplicate_groups.sort(key=lambda item: (-int(item["row_count"]), str(item["model"]).casefold()))

    date_counts: dict[str, int] = {}
    blank_date_rows = 0
    for row in result:
        value = row.get("date_counted")
        if not value:
            blank_date_rows += 1
            continue
        if hasattr(value, "strftime"):
            label = value.strftime("%m/%d/%Y")
        else:
            label = str(value)
        date_counts[label] = date_counts.get(label, 0) + 1

    report = {
        "worksheet_count": len(sheets),
        "section_count": section_count,
        "sections": section_details,
        "candidate_rows": candidate_rows,
        "extracted_rows": len(result),
        "skipped_rows": len(skipped),
        "skipped_examples": skipped[:50],
        "unique_variants": len(duplicate_map),
        "duplicate_rows": len(result) - len(duplicate_map),
        "duplicate_group_count": len(duplicate_groups),
        "duplicate_groups": duplicate_groups[:50],
        "non_memory_rows": sum(not row.get("ram") and not row.get("storage") for row in result),
        "dated_rows": len(result) - blank_date_rows,
        "blank_date_rows": blank_date_rows,
        "date_breakdown": [
            {"date": date, "rows": count}
            for date, count in sorted(date_counts.items(), key=lambda item: item[0])
        ],
    }
    return result, section_count, report


def extract_organized_rows(payload: bytes) -> tuple[list[dict[str, Any]], int]:
    """Read inventory-style sections without changing the uploaded workbook."""

    rows, section_count, _ = analyze_organized_rows(payload)
    return rows, section_count


def parse_reference_workbook(payload: bytes) -> tuple[list[dict[str, Any]], int]:
    result: list[dict[str, Any]] = []
    section_count = 0
    for sheet in read_xlsx_sheets(payload):
        headers: list[dict[str, Any]] = []
        for row in sheet["rows"]:
            found: dict[str, int] = {}
            for column, value in row["cells"].items():
                header = normalize_header(value)
                aliases = {"memory": "storage", "datecounted": "date"}
                header = aliases.get(header, header)
                if header in {"make", "model", "ram", "storage", "color", "start", "end"} and header not in found:
                    found[header] = column
                if header in {
                    "date", "lastupdated", "updated", "updateddate", "dateupdated",
                    "lastupdate", "updatedon", "lastupdateddate",
                } and "date" not in found:
                    found["date"] = column
            if ("make" in found or "model" in found) and "color" in found and ("start" in found or "end" in found):
                headers.append({"row_number": row["row_number"], **found})
                section_count += 1
        if not headers:
            continue

        for index, header in enumerate(headers):
            next_header = headers[index + 1]["row_number"] if index + 1 < len(headers) else None
            excluded = {
                column for key, column in header.items()
                if key != "row_number"
            }
            header["inferred_date"] = _infer_date_column(
                sheet["rows"], header["row_number"], next_header, excluded
            )

        current: dict[str, Any] | None = None
        header_position = 0
        header_rows = {header["row_number"] for header in headers}
        for row in sheet["rows"]:
            while header_position < len(headers) and headers[header_position]["row_number"] < row["row_number"]:
                current = headers[header_position]
                header_position += 1
            if current is None or row["row_number"] in header_rows:
                continue
            if "make" in current:
                make = clean_text(row["cells"].get(current["make"]))
            else:
                model = clean_text(row["cells"].get(current.get("model", -1)))
                ram = clean_text(row["cells"].get(current.get("ram", -1)))
                storage = clean_text(row["cells"].get(current.get("storage", -1)))
                make = count_make(model, ram, storage) if model else ""
            color = clean_text(row["cells"].get(current["color"]))
            start = clean_text(row["cells"].get(current.get("start", -1)))
            end = clean_text(row["cells"].get(current.get("end", -1)))
            if not make:
                continue
            if not color and not start and not end:
                continue
            excluded = {column for key, column in current.items() if key in {"make", "model", "ram", "storage", "color", "start", "end"}}
            updated = _effective_row_date(
                row, current.get("date"), current.get("inferred_date"), excluded
            )
            result.append(
                {
                    "reference_id": f"{sheet['name']}|{row['row_number']}",
                    "make": make,
                    "color": color,
                    "make_key": normalize_make_key(make),
                    "color_key": normalize_color_key(color),
                    "start_text": start,
                    "end_text": end,
                    "last_updated": updated["display"],
                    "last_updated_sort": updated["sort"],
                    "row_number": row["row_number"],
                }
            )
    if section_count == 0:
        raise InventoryError("No worksheet contains MAKE or Model, COLOR, and START or END headers on the same row.")
    if not result:
        raise InventoryError("Reference headers were found, but no valid item rows were found.")
    return result, section_count


def parse_count_workbook(payload: bytes) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    found_header = False
    for sheet in read_xlsx_sheets(payload):
        mapping: dict[str, int] | None = None
        header_row = 0
        for row in sheet["rows"]:
            candidate: dict[str, int] = {}
            for column, value in row["cells"].items():
                header = normalize_header(value)
                aliases = {
                    "memory": "storage",
                    "quantity": "amount",
                    "qty": "amount",
                    "enteredat": "date",
                    "entrydate": "date",
                    "entrytime": "date",
                    "dateentered": "date",
                    "countedat": "date",
                }
                header = aliases.get(header, header)
                if header in {"model", "ram", "storage", "color", "amount", "area", "brokenbox", "date"}:
                    candidate[header] = column
            if {"model", "ram", "storage", "color", "amount"}.issubset(candidate):
                mapping = candidate
                header_row = row["row_number"]
                found_header = True
                break
        if mapping is None:
            continue
        for row in sheet["rows"]:
            if row["row_number"] <= header_row:
                continue
            model = clean_text(row["cells"].get(mapping["model"]))
            ram = clean_text(row["cells"].get(mapping["ram"]))
            storage = clean_text(row["cells"].get(mapping["storage"]))
            color = clean_text(row["cells"].get(mapping["color"]))
            if not model and not ram and not storage:
                continue
            context = f"{sheet['name']}, row {row['row_number']}"
            if not model:
                raise InventoryError(f"Model is required in {context}.")
            if not ram and not storage:
                ram = storage = "0"
            if not ram or not storage:
                raise InventoryError(f"RAM and Storage must both contain values in {context}.")
            if has_partial_zero_memory(ram, storage):
                raise InventoryError(f"RAM and Storage must both be zero for a non-memory item in {context}.")
            if not color:
                raise InventoryError(f"Color is required in {context}.")
            amount = parse_whole_number(row["cells"].get(mapping["amount"]), f"Amount in {context}")
            broken_text = normalize_header(row["cells"].get(mapping.get("brokenbox", -1)))
            broken = broken_text in {"true", "yes", "1", "brokenbox", "broken"}
            area = clean_text(row["cells"].get(mapping.get("area", -1))) or "Imported"
            date_data = _reference_date(row["cells"].get(mapping.get("date", -1)))
            counted_at = date_data["value"] or datetime.now()
            result.append(
                {
                    "id": "",
                    "model": model,
                    "ram": ram,
                    "storage": storage,
                    "color": color,
                    "items_per_box": 0,
                    "boxes": 0,
                    "loose_items": amount,
                    "amount": amount,
                    "area": area,
                    "broken_box": broken,
                    "counted_at": counted_at.replace(microsecond=0).isoformat(),
                }
            )
    if not found_header:
        raise InventoryError("The workbook needs Model, RAM, Storage, Color, and Amount headers.")
    if not result:
        raise InventoryError("The workbook contains the required headers but no inventory rows.")
    return result


def _excel_datetime(value: Any, target_timezone: Any = None) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        result = value
    else:
        try:
            result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if result.tzinfo:
        result = (
            result.astimezone(target_timezone)
            if target_timezone is not None
            else result.astimezone()
        ).replace(tzinfo=None)
    return result


def _excel_serial(value: datetime) -> str:
    delta = value - datetime(1899, 12, 30)
    serial = delta.days + (delta.seconds + delta.microseconds / 1_000_000) / 86_400
    return format(serial, ".15g")


def _inline_cell(reference: str, value: Any, style: int = 2) -> str:
    text = "" if value is None else str(value)
    return f'<c r="{reference}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{escape(text)}</t></is></c>'


def _number_cell(reference: str, value: Any, style: int = 3) -> str:
    if value is None or value == "":
        return f'<c r="{reference}" s="{style}"/>'
    return f'<c r="{reference}" s="{style}"><v>{int(value)}</v></c>'


def _number_or_text_cell(reference: str, value: Any) -> str:
    text = clean_text(value)
    if re.fullmatch(r"[+-]?\d+", text):
        return _number_cell(reference, int(text))
    if re.fullmatch(r"[+-]?\d+\.0+", text):
        return _number_cell(reference, int(float(text)))
    return _inline_cell(reference, text)


def _date_cell(reference: str, value: Any, style: int = 4) -> str:
    date_value = _excel_datetime(value)
    if date_value is None:
        # Preserve partial or unusual date labels (for example "11/13") as
        # text instead of silently turning them into blank cells.
        text_value = clean_text(value)
        if text_value:
            return _inline_cell(reference, text_value, 5)
        return f'<c r="{reference}" s="{style}"/>'
    return f'<c r="{reference}" s="{style}"><v>{_excel_serial(date_value)}</v></c>'


def _result_style(result: str) -> int:
    if result == "MATCH":
        return 6
    if result in {"MISSING ITEMS", "EXTRA ITEMS", "AMOUNT CHANGED"}:
        return 7
    if result in {"NOT IN REFERENCE", "MISSING FROM COUNT", "MISSING IN NEW"}:
        return 8
    if result in {"ATTRIBUTE CONFLICT", "INVALID REFERENCE"}:
        return 9
    if result == "NEW ITEM":
        return 10
    return 2


def _worksheet_xml(
    headers: list[str],
    rows: list[list[Any]],
    types: list[str],
    widths: list[float],
    status_column: int = -1,
) -> str:
    header_cells = "".join(
        _inline_cell(f"{_column_name(column)}1", header, 1) for column, header in enumerate(headers)
    )
    sheet_rows = [f'<row r="1" ht="24" customHeight="1">{header_cells}</row>']
    for row_index, row in enumerate(rows, 2):
        cells = []
        for column, header in enumerate(headers):
            reference = f"{_column_name(column)}{row_index}"
            value = row[column] if column < len(row) else ""
            cell_type = types[column]
            if cell_type == "number":
                cells.append(_number_cell(reference, value))
            elif cell_type == "number_or_text":
                cells.append(_number_or_text_cell(reference, value))
            elif cell_type == "date":
                cells.append(_date_cell(reference, value))
            else:
                style = _result_style(str(value)) if column == status_column else 2
                cells.append(_inline_cell(reference, value, style))
        sheet_rows.append(f'<row r="{row_index}" ht="20" customHeight="1">{"".join(cells)}</row>')
    last_row = max(1, len(rows) + 1)
    last_column = _column_name(len(headers) - 1)
    columns = "".join(
        f'<col min="{index + 1}" max="{index + 1}" width="{width}" customWidth="1"/>'
        for index, width in enumerate(widths)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<worksheet xmlns="{MAIN_NS}">'
        f'<dimension ref="A1:{last_column}{last_row}"/>'
        '<sheetViews><sheetView showGridLines="0" workbookViewId="0">'
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        '</sheetView></sheetViews><sheetFormatPr defaultRowHeight="18"/>'
        f'<cols>{columns}</cols><sheetData>{"".join(sheet_rows)}</sheetData>'
        f'<autoFilter ref="A1:{last_column}{last_row}"/>'
        '<pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75" header="0.3" footer="0.3"/>'
        '</worksheet>'
    )


STYLES_XML = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="{MAIN_NS}">
  <numFmts count="1"><numFmt numFmtId="164" formatCode="m/d/yyyy h:mm AM/PM"/></numFmts>
  <fonts count="2">
    <font><sz val="11"/><color theme="1"/><name val="Calibri"/><family val="2"/></font>
    <font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/><family val="2"/></font>
  </fonts>
  <fills count="8">
    <fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF0F766E"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFDCFCE7"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFFEF3C7"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFFEE2E2"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFEDE9FE"/><bgColor indexed="64"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFDBEAFE"/><bgColor indexed="64"/></patternFill></fill>
  </fills>
  <borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border><border><left/><right/><top/><bottom style="thin"><color rgb="FFD9E2E8"/></bottom><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="11">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
    <xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment vertical="center"/></xf>
    <xf numFmtId="3" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1"><alignment horizontal="right" vertical="center"/></xf>
    <xf numFmtId="164" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
    <xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>
    <xf numFmtId="0" fontId="0" fillId="3" borderId="1" xfId="0" applyFill="1" applyBorder="1"/><xf numFmtId="0" fontId="0" fillId="4" borderId="1" xfId="0" applyFill="1" applyBorder="1"/>
    <xf numFmtId="0" fontId="0" fillId="5" borderId="1" xfId="0" applyFill="1" applyBorder="1"/><xf numFmtId="0" fontId="0" fillId="6" borderId="1" xfId="0" applyFill="1" applyBorder="1"/>
    <xf numFmtId="0" fontId="0" fillId="7" borderId="1" xfId="0" applyFill="1" applyBorder="1"/>
  </cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles><dxfs count="0"/><tableStyles count="0" defaultTableStyle="TableStyleMedium2" defaultPivotStyle="PivotStyleLight16"/>
</styleSheet>'''


def _package_workbook(sheets: list[dict[str, Any]], title: str) -> bytes:
    overrides = []
    workbook_sheets = []
    workbook_rels = []
    for index, sheet in enumerate(sheets, 1):
        overrides.append(
            f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
        state = ' state="hidden"' if sheet["hidden"] else ""
        workbook_sheets.append(
            f'<sheet name={quoteattr(sheet["name"])} sheetId="{index}"{state} r:id="rId{index}"/>'
        )
        workbook_rels.append(
            f'<Relationship Id="rId{index}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{index}.xml"/>'
        )
    style_rel_id = len(sheets) + 1
    workbook_rels.append(
        f'<Relationship Id="rId{style_rel_id}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        f'{"".join(overrides)}'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        '</Types>'
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{PACKAGE_REL_NS}">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
        '</Relationships>'
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<workbook xmlns="{MAIN_NS}" xmlns:r="{DOC_REL_NS}"><sheets>'
        f'{"".join(workbook_sheets)}</sheets></workbook>'
    )
    workbook_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{PACKAGE_REL_NS}">{"".join(workbook_rels)}</Relationships>'
    )
    created = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    core_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        f'<dc:title>{escape(title)}</dc:title><dc:creator>Inventory Count Web App</dc:creator>'
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created>'
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{created}</dcterms:modified></cp:coreProperties>'
    )
    app_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        '<Application>Inventory Count Web App</Application></Properties>'
    )

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("docProps/core.xml", core_xml)
        archive.writestr("docProps/app.xml", app_xml)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml)
        archive.writestr("xl/styles.xml", STYLES_XML)
        for index, sheet in enumerate(sheets, 1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", sheet["xml"])
    payload = output.getvalue()
    validate_xlsx_package(payload, len(sheets))
    return payload


def build_organized_rows_workbook(rows: list[dict[str, Any]]) -> bytes:
    organized_rows = [
        [
            row["model"], row["ram"], row["storage"], row["color"],
            row["start"], row["end"], row["date_counted"],
        ]
        for row in rows
    ]
    sheets = [
        {
            "name": "Organized Data",
            "hidden": False,
            "xml": _worksheet_xml(
                ["Model", "RAM", "Storage", "Color", "START", "END", "Date Counted"],
                organized_rows,
                ["text", "text", "text", "text", "number_or_text", "number_or_text", "date"],
                [28, 12, 14, 18, 12, 12, 18],
            ),
        }
    ]
    return _package_workbook(sheets, "Organized Inventory Copy")


def build_organized_workbook(source_payload: bytes) -> tuple[bytes, int, int]:
    rows, section_count = extract_organized_rows(source_payload)
    return build_organized_rows_workbook(rows), len(rows), section_count


def build_inventory_workbook(
    session: dict[str, Any],
    entries: list[dict[str, Any]],
    comparisons: list[dict[str, Any]],
    audit_events: list[dict[str, Any]],
    *,
    movements: list[dict[str, Any]] | None = None,
    attempts: list[dict[str, Any]] | None = None,
    all_entries: list[dict[str, Any]] | None = None,
) -> bytes:
    sheets: list[dict[str, Any]] = []
    movements = movements or []
    attempts = attempts or []
    all_entries = all_entries or entries
    count_rows = [
        [item_details(entry), entry["color"], entry["amount"], entry["area"], entry["counted_at"]]
        for entry in entries
    ]
    sheets.append(
        {
            "name": "Inventory Count",
            "hidden": False,
            "xml": _worksheet_xml(
                ["Item Details", "Color", "Amount", "Area", "Entered At"],
                count_rows,
                ["text", "text", "number", "text", "date"],
                [44, 16, 12, 22, 19],
            ),
        }
    )
    summary_rows = [
        ["Session Number", session.get("session_number", session.get("id", ""))],
        ["Session Name", session.get("name", "")],
        ["Count Type", session.get("count_type", "SPOT")],
        ["Workflow Status", session.get("workflow_status", session.get("status", ""))],
        ["Warehouse", session.get("warehouse", "")],
        ["Location", session.get("location", "")],
        ["Operator", session.get("operator_name", "")],
        ["Started", session.get("created_at", "")],
        ["Reference Workbook", session.get("reference_name", "")],
        ["Reference SHA256", session.get("reference_hash", "")],
        ["Reference Loaded", session.get("reference_loaded_at", "")],
        ["Quantity Tolerance", session.get("quantity_tolerance", 0)],
        ["Percentage Tolerance", session.get("percentage_tolerance", 0)],
        ["Current Attempt", session.get("recount_attempt", 1)],
        ["Submitted", session.get("submitted_at", "")],
        ["Approved", session.get("approved_at", "")],
        ["Approved By", session.get("approved_by", "")],
        ["Review Reason", session.get("review_reason", "")],
        ["Finalized", session.get("finalized_at", "")],
        ["Count Rows", len(entries)],
        ["Total Units", sum(int(row.get("amount") or 0) for row in entries)],
        ["Broken Box Units", sum(int(row.get("amount") or 0) for row in entries if row.get("broken_box"))],
        ["Exact Matches", sum(row.get("result") == "MATCH" for row in comparisons)],
        ["Items Needing Attention", sum(row.get("result") != "MATCH" for row in comparisons)],
    ]
    sheets.append(
        {
            "name": "Summary",
            "hidden": False,
            "xml": _worksheet_xml(
                ["Field", "Value"],
                summary_rows,
                ["text", "text"],
                [28, 72],
            ),
        }
    )
    detail_rows = [
        [
            entry["model"], entry["ram"], entry["storage"], entry["color"],
            entry["items_per_box"], entry["boxes"], entry["loose_items"], entry["amount"],
            entry["area"], "Broken Box" if entry["broken_box"] else "", entry["counted_at"],
            session["id"], entry["id"], session["status"],
            entry.get("operator_name", session.get("operator_name", "")), entry.get("attempt", 1),
        ]
        for entry in all_entries
    ]
    sheets.append(
        {
            "name": "Detailed Data",
            "hidden": True,
            "xml": _worksheet_xml(
                ["Model", "RAM", "Storage", "Color", "Items per Box", "Boxes", "Items Outside",
                 "Amount", "Area", "Broken Box", "Entered At", "Session ID", "Entry ID", "Session Status",
                 "Operator", "Attempt"],
                detail_rows,
                ["text", "text", "text", "text", "number", "number", "number", "number", "text",
                 "text", "date", "text", "text", "text", "text", "number"],
                [24, 12, 14, 16, 14, 10, 14, 12, 20, 15, 19, 38, 38, 16, 20, 10],
            ),
        }
    )
    if comparisons:
        comparison_rows = [
            [
                row["result"], row["item"], row["color"], row["counted"], row.get("baseline"),
                row.get("end_value"), row.get("difference"), row.get("broken_amount", 0),
                row.get("source_rows", 0), row.get("last_updated", ""), row.get("explanation", ""),
                row.get("difference_percent"),
                "Yes" if row.get("within_tolerance") else ("No" if row.get("within_tolerance") is not None else ""),
                row.get("review_status", ""), row.get("movement_warning", ""), row.get("attempt", 1),
            ]
            for row in comparisons
        ]
        sheets.append(
            {
                "name": "Comparison Results",
                "hidden": False,
                "xml": _worksheet_xml(
                    ["Result", "Item", "Color", "Counted", "Baseline or Old", "END or New", "Difference",
                     "Broken Quantity", "Source Rows", "Last Updated", "Explanation", "Difference %",
                     "Within Tolerance", "Review Status", "Movement Warning", "Attempt"],
                    comparison_rows,
                    ["text", "text", "text", "number", "number", "number", "number", "number", "number", "text", "text",
                     "number", "text", "text", "text", "number"],
                    [22, 40, 16, 12, 16, 14, 14, 16, 12, 15, 48, 14, 16, 20, 45, 10],
                    0,
                ),
            }
        )
        issue_rows = [
            [row["result"], row["item"], row["color"], row["counted"], row.get("baseline"),
             row.get("difference"), row.get("broken_amount", 0), row.get("explanation", "")]
            for row in comparisons if row["result"] != "MATCH"
        ]
        sheets.append(
            {
                "name": "Issues",
                "hidden": False,
                "xml": _worksheet_xml(
                    ["Issue", "Item", "Color", "Counted", "Baseline or Old", "Difference", "Broken Quantity", "Explanation"],
                    issue_rows,
                    ["text", "text", "text", "number", "number", "number", "number", "text"],
                    [22, 40, 16, 12, 16, 14, 16, 52],
                    0,
                ),
            }
        )
    audit_rows = [
        [event["created_at"], event["action"], event["entry_id"], event["previous_value"], event["new_value"]]
        for event in audit_events
    ]
    sheets.append(
        {
            "name": "Audit Log",
            "hidden": True,
            "xml": _worksheet_xml(
                ["Event Time", "Action", "Entry ID", "Previous Value", "New Value"],
                audit_rows,
                ["date", "text", "text", "text", "text"],
                [19, 18, 38, 48, 48],
            ),
        }
    )

    if movements:
        movement_rows = [
            [
                row.get("occurred_at", ""), row.get("movement_type", "").replace("_", " ").title(),
                row.get("model", ""), row.get("ram", ""), row.get("storage", ""), row.get("color", ""),
                row.get("quantity", 0), row.get("from_location", ""), row.get("to_location", ""),
                row.get("operator_name", ""), row.get("note", ""), row.get("id", ""),
            ]
            for row in movements
        ]
        sheets.append(
            {
                "name": "Movement Log",
                "hidden": False,
                "xml": _worksheet_xml(
                    ["Movement Time", "Type", "Model", "RAM", "Storage", "Color", "Quantity",
                     "From", "To", "Operator", "Note", "Movement ID"],
                    movement_rows,
                    ["date", "text", "text", "text", "text", "text", "number", "text", "text", "text", "text", "text"],
                    [19, 18, 24, 12, 14, 16, 12, 18, 18, 20, 40, 38],
                ),
            }
        )

    if attempts:
        attempt_rows = [
            [
                row.get("attempt", 1), row.get("submitted_at", ""), row.get("status", ""),
                row.get("decision", ""), row.get("decision_by", ""),
                row.get("decision_reason", ""), row.get("decided_at", ""),
            ]
            for row in attempts
        ]
        sheets.append(
            {
                "name": "Count Attempts",
                "hidden": False,
                "xml": _worksheet_xml(
                    ["Attempt", "Submitted", "Result", "Decision", "Decision By", "Decision Reason", "Decided At"],
                    attempt_rows,
                    ["number", "date", "text", "text", "text", "text", "date"],
                    [10, 19, 22, 15, 20, 48, 19],
                ),
            }
        )

    return _package_workbook(sheets, "Inventory Count and Comparison")


def validate_xlsx_package(payload: bytes, expected_sheets: int) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(payload), "r") as archive:
            required = ["[Content_Types].xml", "_rels/.rels", "xl/workbook.xml", "xl/styles.xml"]
            required.extend(f"xl/worksheets/sheet{index}.xml" for index in range(1, expected_sheets + 1))
            for name in required:
                content = archive.read(name)
                if not content:
                    raise InventoryError(f"Workbook validation failed: {name} is empty.")
                ET.fromstring(content)
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        raise InventoryError("The generated Excel workbook failed package validation.") from exc
