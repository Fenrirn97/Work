
"""Parse a user-exported ShipStation shipment-status CSV and merge it into API rows."""

from __future__ import annotations

import csv
import io
import re
from collections import defaultdict

from shipstation import ReportError

EXPECTED_HEADERS = {
    "Shipment #",
    "Order #",
    "Tracking #",
    "Service",
    "Recipient",
    "Ship Date",
    "Packing Slip Printed",
    "Label Created",
    "Label Printed",
    "Marketplace Notified",
    "Shipment Notification",
    "Delivery Notification",
}


def clean(value):
    return "" if value is None else str(value).strip()


def normalize_tracking(value):
    """Return a safe exact identifier or blank when Excel-style scientific notation destroyed it."""
    value = clean(value).replace(" ", "")
    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?[Ee][+-]?\d+", value):
        return ""
    return value.upper()


def split_tracking(value):
    parts = re.split(r"[;,\n\r]+", clean(value))
    return [p.strip().upper() for p in parts if p.strip()]


def parse_print_status_csv(csv_text):
    if not csv_text or not str(csv_text).strip():
        return []
    if len(csv_text.encode("utf-8", errors="ignore")) > 25 * 1024 * 1024:
        raise ReportError("The ShipStation CSV is larger than 25 MB.")

    stream = io.StringIO(csv_text.lstrip("\ufeff"), newline="")
    reader = csv.DictReader(stream)
    if not reader.fieldnames:
        raise ReportError("The ShipStation CSV has no header row.")
    fieldnames = [clean(name).lstrip("\ufeff") for name in reader.fieldnames]
    reader.fieldnames = fieldnames

    minimum = {"Order #", "Tracking #", "Label Created", "Label Printed"}
    missing = sorted(minimum - set(fieldnames))
    if missing:
        raise ReportError(
            "This does not look like the ShipStation Print Status export. Missing column(s): "
            + ", ".join(missing)
        )

    records = []
    for raw in reader:
        if not raw or not any(clean(value) for value in raw.values()):
            continue
        row = {clean(key): clean(value) for key, value in raw.items() if key is not None}
        records.append(
            {
                "shipmentNumber": row.get("Shipment #", ""),
                "orderNumber": row.get("Order #", ""),
                "trackingRaw": row.get("Tracking #", ""),
                "tracking": normalize_tracking(row.get("Tracking #", "")),
                "service": row.get("Service", ""),
                "recipient": row.get("Recipient", ""),
                "shipDate": row.get("Ship Date", ""),
                "packingSlipPrinted": row.get("Packing Slip Printed", ""),
                "labelCreated": row.get("Label Created", ""),
                "labelPrinted": row.get("Label Printed", ""),
                "marketplaceNotified": row.get("Marketplace Notified", ""),
                "shipmentNotification": row.get("Shipment Notification", ""),
                "deliveryNotification": row.get("Delivery Notification", ""),
            }
        )
    return records


def _is_shipstation_label(row):
    return "shipstation label" in clean(row.get("source")).lower()


def _pick_candidate(api_row, by_tracking, by_order, by_order_id):
    # A wider date range can contain several packages for one order.
    tracking_numbers = {normalize_tracking(t) for t in split_tracking(api_row.get("tracking"))}
    tracking_numbers.discard("")
    if len(tracking_numbers) > 1:
        return None, "Ambiguous tracking: multiple packages; see Tracking Records"
    if not tracking_numbers:
        return None, "No exact tracking number"
    candidates = by_tracking.get(next(iter(tracking_numbers)), [])
    unique = {id(item): item for item in candidates}
    if len(unique) > 1:
        return None, "Ambiguous tracking match"
    if len(unique) == 1:
        item = next(iter(unique.values()))
        order = clean(api_row.get("orderNumber"))
        if order and item["orderNumber"] and order != item["orderNumber"]:
            return None, "Ambiguous tracking: order numbers conflict"
        return item, "Tracking #"
    return None, "No exact tracking match"


def merge_print_status(report, records):
    """Attach ShipStation Smart Document Tracking/export fields to report rows/events."""
    by_tracking = defaultdict(list)
    by_order = defaultdict(list)
    by_order_id = defaultdict(list)
    for item in records:
        if item["tracking"]:
            by_tracking[item["tracking"]].append(item)
        if item["orderNumber"]:
            by_order[item["orderNumber"]].append(item)
        if item["shipmentNumber"]:
            by_order_id[item["shipmentNumber"]].append(item)

    matched_record_ids = set()
    matched_rows = 0
    not_printed_rows = 0

    for row in report.get("rows", []):
        row.update(
            labelCreated="",
            labelPrinted="",
            packingSlipPrinted="",
            marketplaceNotified="",
            shipmentNotification="",
            deliveryNotification="",
            printMatch="",
            printCheck="",
            printCsvTracking="",
        )

        if not _is_shipstation_label(row):
            row["printCheck"] = "N/A - Fulfillment / marked shipped"
            continue

        match, match_type = _pick_candidate(row, by_tracking, by_order, by_order_id)
        row["printMatch"] = match_type
        if not match:
            row["printCheck"] = (
                "REVIEW - ambiguous CSV match"
                if "Ambiguous" in match_type
                else "NOT IN SELECTED PRINT STATUS CSV"
            )
            continue

        matched_rows += 1
        matched_record_ids.add(id(match))
        row["labelCreated"] = match["labelCreated"]
        row["labelPrinted"] = match["labelPrinted"]
        row["packingSlipPrinted"] = match["packingSlipPrinted"]
        row["marketplaceNotified"] = match["marketplaceNotified"]
        row["shipmentNotification"] = match["shipmentNotification"]
        row["deliveryNotification"] = match["deliveryNotification"]
        row["printCsvTracking"] = match["trackingRaw"]

        if match["labelPrinted"].strip().lower() == "printed":
            row["printCheck"] = "PRINTED"
        else:
            row["printCheck"] = "NOT PRINTED"
            not_printed_rows += 1

    # Attach print status to raw tracking records too, so the workbook can be audited at shipment level.
    for event in report.get("events", []):
        temp = {
            "tracking": event.get("tracking", ""),
            "orderNumber": event.get("orderNumber", ""),
            "orderId": event.get("orderId", ""),
        }
        match, match_type = _pick_candidate(temp, by_tracking, by_order, by_order_id)
        event["labelCreated"] = match["labelCreated"] if match else ""
        event["labelPrinted"] = match["labelPrinted"] if match else ""
        event["marketplaceNotified"] = match["marketplaceNotified"] if match else ""
        event["printMatch"] = match_type

    report["printStatusRecords"] = records
    report["printCsvProvided"] = True
    report["printCsvRecordCount"] = len(records)
    report["printCsvMatchedRows"] = matched_rows
    report["notPrintedRowCount"] = not_printed_rows
    report["unmatchedPrintCsvCount"] = len(records) - len(matched_record_ids)
    return report


def mark_no_print_csv(report):
    for row in report.get("rows", []):
        row.update(
            labelCreated="",
            labelPrinted="",
            packingSlipPrinted="",
            marketplaceNotified="",
            shipmentNotification="",
            deliveryNotification="",
            printMatch="",
            printCsvTracking="",
            printCheck=(
                "NOT CHECKED - no ShipStation CSV selected"
                if _is_shipstation_label(row)
                else "N/A - Fulfillment / marked shipped"
            ),
        )
    for event in report.get("events", []):
        event.update(labelCreated="", labelPrinted="", marketplaceNotified="", printMatch="")
    report.update(
        printStatusRecords=[],
        printCsvProvided=False,
        printCsvRecordCount=0,
        printCsvMatchedRows=0,
        notPrintedRowCount=0,
        unmatchedPrintCsvCount=0,
    )
    return report
