"""Merge ShipStation Shipments-grid Label Printed data captured by the browser extension.

This module never guesses a ShipStation print time from label creation, Ship Date,
or the Windows print spooler. The displayed text from Shipments -> Label Printed is
preserved exactly and parsed only when the status/time is actually present.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

PRINTED_RE = re.compile(r"\bprinted(?=\s|\d|[|·•:]|$)", re.I)
NOT_PRINTED_RE = re.compile(r"\b(?:not\s+printed|unprinted)\b", re.I)
CREATED_RE = re.compile(r"\bcreated\b", re.I)

DATE_TIME_PATTERNS = [
    re.compile(
        r"(?<!\d)\d{1,2}/\d{1,2}/\d{2,4}(?:,)?(?:(?:\s+at)?\s+|:|•|·)\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?\b",
        re.I,
    ),
    re.compile(
        r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s+\d{4}(?:,)?(?:\s+at)?\s+\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?\b",
        re.I,
    ),
    re.compile(
        r"\b\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{4}(?:,)?(?:\s+at)?\s+\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?\b",
        re.I,
    ),
]


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_identifier(value: Any) -> str:
    return re.sub(r"\s+", "", clean_text(value).upper())


def split_values(value: Any) -> list[str]:
    text = clean_text(value)
    if not text:
        return []
    return [part.strip() for part in re.split(r"\s*;\s*|\s*,\s*|[\r\n]+", text) if part.strip()]


def parse_label_print_cell(raw_text: Any) -> dict[str, str]:
    """Interpret only the text/attributes ShipStation exposed in Label Printed."""
    raw = clean_text(raw_text)
    lower = raw.lower()
    if not raw:
        status = "Could not read"
    elif NOT_PRINTED_RE.search(raw):
        status = "Not Printed"
    elif PRINTED_RE.search(raw):
        status = "Printed"
    elif CREATED_RE.search(raw):
        status = "Created - not printed"
    elif lower in {"yes", "true"}:
        status = "Printed"
    elif lower in {"no", "false"}:
        status = "Not Printed"
    else:
        status = "Could not read"

    displayed_time = ""
    for pattern in DATE_TIME_PATTERNS:
        match = pattern.search(raw)
        if match:
            displayed_time = clean_text(match.group(0)).replace(" at ", " ").replace("•", " ").replace("·", " ")
            break

    return {
        "printStatus": status,
        "displayedPrintTime": displayed_time,
        "rawLabelPrinted": raw,
    }


def normalize_capture_rows(rows: Any, captured_at: str | None = None) -> list[dict[str, str]]:
    if not isinstance(rows, list):
        return []
    captured_at = clean_text(captured_at) or datetime.now(timezone.utc).isoformat()
    result = []
    seen = set()
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        shipment = clean_text(raw.get("shipmentNumber"))
        tracking = clean_text(raw.get("tracking"))
        order = clean_text(raw.get("orderNumber"))
        raw_print = clean_text(raw.get("labelPrintedRaw") or raw.get("rawLabelPrinted"))
        if not any((shipment, tracking, order, raw_print)):
            continue
        parsed = parse_label_print_cell(raw_print)
        row = {
            "shipmentNumber": shipment,
            "tracking": tracking,
            "orderNumber": order,
            **parsed,
            "capturedAt": clean_text(raw.get("capturedAt")) or captured_at,
        }
        key = (
            normalize_identifier(shipment),
            normalize_identifier(tracking),
            normalize_identifier(order),
            row["rawLabelPrinted"],
        )
        if key not in seen:
            seen.add(key)
            result.append(row)
    return result


def capture_key(row: dict) -> tuple[str, str, str, str]:
    return (
        normalize_identifier(row.get("shipmentNumber")),
        normalize_identifier(row.get("tracking")),
        normalize_identifier(row.get("orderNumber")),
        clean_text(row.get("rawLabelPrinted")),
    )


def _stable_capture_identity(row: dict) -> tuple[str, str, str]:
    """Package identity that does not change when a later capture reads more cell text."""
    return (
        normalize_identifier(row.get("shipmentNumber")),
        normalize_identifier(row.get("tracking")),
        normalize_identifier(row.get("orderNumber")),
    )


def _capture_quality(row: dict) -> tuple[int, int]:
    raw = clean_text(row.get("rawLabelPrinted"))
    status = clean_text(row.get("printStatus"))
    useful = int(bool(raw)) * 2 + int(status not in {"", "Could not read"}) * 3
    return useful, len(raw)


def merge_capture_store(existing: list[dict], incoming: list[dict]) -> list[dict]:
    """Accumulate pages, replacing an older unreadable capture with a better later read."""
    combined: dict[tuple[str, str, str], dict] = {}
    for row in [*existing, *incoming]:
        if not isinstance(row, dict):
            continue
        identity = _stable_capture_identity(row)
        old = combined.get(identity)
        if old is None or _capture_quality(row) >= _capture_quality(old):
            combined[identity] = dict(row)
    return list(combined.values())


def _unique_candidates(candidates: list[dict]) -> list[dict]:
    seen = set()
    result = []
    for item in candidates:
        key = capture_key(item)
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _package_identity(row: dict) -> tuple[str, str]:
    return (normalize_identifier(row.get("shipmentIds")), normalize_identifier(row.get("tracking")))


def _choose_match(report_row: dict, capture_rows: list[dict], report_rows: list[dict]):
    by_tracking: dict[str, list[dict]] = {}
    by_shipment: dict[str, list[dict]] = {}
    by_order: dict[str, list[dict]] = {}
    for item in capture_rows:
        tracking = normalize_identifier(item.get("tracking"))
        shipment = normalize_identifier(item.get("shipmentNumber"))
        order = normalize_identifier(item.get("orderNumber"))
        if tracking:
            by_tracking.setdefault(tracking, []).append(item)
        if shipment:
            by_shipment.setdefault(shipment, []).append(item)
        if order:
            by_order.setdefault(order, []).append(item)

    # Only one package can inherit one captured print observation.
    report_tracking = {normalize_identifier(v) for v in split_values(report_row.get("tracking"))}
    report_tracking.discard("")
    if len(report_tracking) > 1:
        return None, "Ambiguous tracking match: multiple packages; see Tracking Records"
    if report_tracking:
        unique = _unique_candidates(by_tracking.get(next(iter(report_tracking)), []))
        if len(unique) > 1:
            return None, "Ambiguous tracking match"
        if len(unique) == 1:
            match = unique[0]
            order = normalize_identifier(report_row.get("orderNumber"))
            captured_order = normalize_identifier(match.get("orderNumber"))
            if order and captured_order and order != captured_order:
                return None, "Ambiguous tracking match: order numbers conflict"
            return match, "Tracking #"
        # Never transfer another package's print status based only on the same order.
        return None, "No exact tracking match"

    report_ids = {normalize_identifier(v) for v in split_values(
        report_row.get("shipmentIds") or report_row.get("shipmentId"))}
    report_ids.discard("")
    if len(report_ids) > 1:
        return None, "Ambiguous shipment match"
    candidates = [item for value in report_ids for item in by_shipment.get(value, [])]
    unique = _unique_candidates(candidates)
    if len(unique) == 1:
        match = unique[0]
        order = normalize_identifier(report_row.get("orderNumber"))
        other = normalize_identifier(match.get("orderNumber"))
        if order and other and order != other:
            return None, "Ambiguous shipment match: order numbers conflict"
        return match, "Shipment # (exact)"
    if len(unique) > 1:
        return None, "Ambiguous shipment match"
    order = normalize_identifier(report_row.get("orderNumber"))
    if order and len(_unique_candidates(by_order.get(order, []))) > 1:
        return None, "Ambiguous order match"
    return None, "No exact package match"


def _append_warning(row: dict, message: str) -> None:
    current = [x.strip() for x in str(row.get("warnings") or "").split(";") if x.strip()]
    if message and message not in current:
        current.append(message)
    row["warnings"] = "; ".join(current)


def merge_shipstation_print_capture(report: dict, capture_rows: list[dict]) -> dict:
    """Add ShipStation UI Label Printed state/time without disturbing the old workflow."""
    rows = report.get("rows", [])
    matched = ambiguous = missing = printed_missing_time = printed_missing_tracking = 0
    ui_not_printed = 0

    for row in rows:
        row.update(
            shipstationUiPrintStatus="",
            shipstationDisplayedPrintTime="",
            shipstationLabelPrintedRaw="",
            shipstationUiPrintMatch="",
            shipstationUiCapturedAt="",
        )

        if "shipstation label" not in clean_text(row.get("source")).lower():
            continue

        match, match_type = _choose_match(row, capture_rows, rows)
        row["shipstationUiPrintMatch"] = match_type
        if match is None:
            if "Ambiguous" in match_type:
                ambiguous += 1
                _append_warning(row, "Multiple ShipStation UI rows matched this shipment; print status was not guessed")
            else:
                missing += 1
            continue

        matched += 1
        status = clean_text(match.get("printStatus")) or "Could not read"
        displayed = clean_text(match.get("displayedPrintTime"))
        raw = clean_text(match.get("rawLabelPrinted"))
        row["shipstationUiPrintStatus"] = status
        row["shipstationDisplayedPrintTime"] = displayed
        row["shipstationLabelPrintedRaw"] = raw
        row["shipstationUiCapturedAt"] = clean_text(match.get("capturedAt"))

        # UI capture is the main print check when it is readable. The old CSV remains in the workbook.
        if status == "Printed":
            row["printCheck"] = "PRINTED"
            if not clean_text(row.get("tracking")):
                printed_missing_tracking += 1
                _append_warning(row, "CRITICAL: ShipStation says Printed but tracking number is missing")
            if not displayed:
                printed_missing_time += 1
                _append_warning(row, "ShipStation says Printed but displayed print date/time could not be read")
        elif status in {"Not Printed", "Created - not printed"}:
            row["printCheck"] = "NOT PRINTED"
            ui_not_printed += 1
        else:
            row["printCheck"] = "REVIEW - UI print status unreadable"
            _append_warning(row, "ShipStation Label Printed cell was captured but could not be interpreted")

        csv_status = clean_text(row.get("labelPrinted")).lower()
        if csv_status:
            csv_printed = csv_status == "printed"
            ui_printed = status == "Printed"
            if status != "Could not read" and csv_printed != ui_printed:
                _append_warning(row, "ShipStation CSV and Shipments-grid Label Printed status disagree")

    # Raw shipment/event sheet gets the same package-level capture when possible.
    for event in report.get("events", []):
        event.update(
            shipstationUiPrintStatus="",
            shipstationDisplayedPrintTime="",
            shipstationLabelPrintedRaw="",
            shipstationUiPrintMatch="",
            shipstationUiCapturedAt="",
        )
        match, match_type = _choose_match(event, capture_rows, report.get("events", []))
        event["shipstationUiPrintMatch"] = match_type
        if match:
            event["shipstationUiPrintStatus"] = clean_text(match.get("printStatus")) or "Could not read"
            event["shipstationDisplayedPrintTime"] = clean_text(match.get("displayedPrintTime"))
            event["shipstationLabelPrintedRaw"] = clean_text(match.get("rawLabelPrinted"))
            event["shipstationUiCapturedAt"] = clean_text(match.get("capturedAt"))

    report.update(
        shipstationPrintCapture=list(capture_rows),
        uiPrintCaptureProvided=bool(capture_rows),
        uiPrintCaptureCount=len(capture_rows),
        uiPrintMatchedRows=matched,
        uiPrintAmbiguousRows=ambiguous,
        uiPrintMissingRows=missing,
        uiPrintedMissingTimeCount=printed_missing_time,
        printedMissingTrackingCount=printed_missing_tracking,
        uiNotPrintedRowCount=ui_not_printed,
    )
    return report


def mark_no_shipstation_print_capture(report: dict) -> dict:
    for row in report.get("rows", []):
        row.update(
            shipstationUiPrintStatus="",
            shipstationDisplayedPrintTime="",
            shipstationLabelPrintedRaw="",
            shipstationUiPrintMatch="",
            shipstationUiCapturedAt="",
        )
    for event in report.get("events", []):
        event.update(
            shipstationUiPrintStatus="",
            shipstationDisplayedPrintTime="",
            shipstationLabelPrintedRaw="",
            shipstationUiPrintMatch="",
            shipstationUiCapturedAt="",
        )
    report.update(
        shipstationPrintCapture=[],
        uiPrintCaptureProvided=False,
        uiPrintCaptureCount=0,
        uiPrintMatchedRows=0,
        uiPrintAmbiguousRows=0,
        uiPrintMissingRows=0,
        uiPrintedMissingTimeCount=0,
        printedMissingTrackingCount=0,
        uiNotPrintedRowCount=0,
    )
    return report
