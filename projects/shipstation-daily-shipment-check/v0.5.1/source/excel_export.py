
"""Create Excel in memory with Python; no customer report is written by the server."""

from datetime import date, datetime
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from shipstation import ReportError

ITEM_COLUMNS = [
    ("Order Number", "orderNumber", 25),
    ("Item Name", "itemName", 45),
    ("SKU", "sku", 36),
    ("Quantity", "quantity", 12),
    ("Order Date", "orderDate", 15),
    ("Ship Date", "shipDate", 15),
    ("Tracking Number(s)", "tracking", 34),
    ("Carrier", "carrier", 21),
    ("Unit Price", "unitPrice", 14),
    ("Line Total", "lineTotal", 15),
    ("Quantity Basis", "quantityBasis", 26),
    ("Store / Source Code", "store", 24),
    ("Recipient", "recipient", 27),
    ("Service", "service", 23),
    ("Fulfillment Provider", "fulfillmentProvider", 26),
    ("Order ID", "orderId", 24),
    ("Item ID", "itemId", 24),
    ("Shipment IDs", "shipmentIds", 28),
    ("Record IDs", "recordIds", 28),
    ("Record Source", "source", 35),
    ("ShipStation Label Printed", "shipstationPrintStatus", 27),
    ("ShipStation Displayed Print Time", "shipstationDisplayedPrintTime", 29),
    ("ShipStation Label Printed Raw", "shipstationLabelPrintedRaw", 48),
    ("ShipStation UI Match", "shipstationPrintMatch", 22),
    ("ShipStation Capture Time", "shipstationPrintCapturedAt", 27),
    ("Review Notes", "warnings", 72),
    ("Windows Print Status", "printStatus", 34),
    ("Windows Printed Date / Time", "printedAt", 23),
    ("Printer", "printerName", 28),
    ("Print Computer", "printComputer", 28),
    ("Printed Document", "printDocument", 45),
    ("Print Match", "printMatch", 20),
    ("Print Count", "printCount", 12),
]
TRACKING_COLUMNS = [
    ("Order Number / Shipment Reference", "orderNumber", 32),
    ("Order ID / External Order ID", "orderId", 28),
    ("Ship Date", "shipDate", 15),
    ("Tracking Number(s)", "tracking", 34),
    ("Carrier", "carrier", 23),
    ("Shipment ID", "shipmentId", 28),
    ("Record ID", "recordId", 28),
    ("Record Source", "source", 35),
    ("Service", "service", 24),
    ("Fulfillment Provider", "provider", 26),
    ("Recipient", "recipient", 26),
]
SHIPSTATION_PRINT_COLUMNS = [
    ("Shipment #", "shipmentNumber", 28),
    ("Order #", "orderNumber", 28),
    ("Tracking #", "tracking", 35),
    ("Label Printed Status", "printStatus", 25),
    ("Displayed Print Date / Time", "displayedPrintTime", 30),
    ("Raw Label Printed Cell", "rawLabelPrinted", 55),
    ("Captured At", "capturedAt", 30),
]

PRINT_COLUMNS = [
    ("Matched Order Number(s)", "matchedOrderNumbers", 30),
    ("Match Type", "matchTypes", 18),
    ("Printed Date / Time", "printedAt", 23),
    ("Document Name", "documentName", 52),
    ("Printer", "printerName", 28),
    ("Computer", "computerName", 28),
    ("Windows User", "userName", 24),
    ("Pages", "pages", 10),
    ("Windows Event Record ID", "recordId", 24),
]


""" ----------- 1 - CREATE A FORMATTED EXCEL TABLE ----------- """


def table(sheet, columns, records):
    if len(records) > 1048575:
        raise ReportError("This report exceeds Excel's row limit. No partial workbook was created.")
    sheet.append([header for header, _, _ in columns])
    for index, (_, _, width) in enumerate(columns, 1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    for row_index, record in enumerate(records, 2):
        for column_index, (_, key, _) in enumerate(columns, 1):
            value = record.get(key)
            if key in ("orderDate", "shipDate"):
                value = date.fromisoformat(value) if value else None
            elif key == "printedAt" and value:
                value = datetime.fromisoformat(value).replace(tzinfo=None)
            if isinstance(value, str) and len(value) > 32767:
                raise ReportError(
                    "A field exceeds Excel's text limit. No truncated workbook was created."
                )
            cell = sheet.cell(row_index, column_index, value)
            if isinstance(value, str):
                # API text stays text, even when it starts with =, +, -, @ or #.
                cell.data_type = "s"
                cell.number_format = "@"
            elif key in ("orderDate", "shipDate"):
                cell.number_format = "mm/dd/yyyy"
            elif key == "printedAt":
                cell.number_format = "mm/dd/yyyy h:mm AM/PM"
            elif key in ("unitPrice", "lineTotal"):
                cell.number_format = "#,##0.00"
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            if key == "warnings" and value:
                cell.fill = PatternFill("solid", fgColor="FFF1CE")
        sheet.row_dimensions[row_index].height = 40
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    sheet.row_dimensions[1].height = 34
    for cell in sheet[1]:
        cell.fill = PatternFill("solid", fgColor="285F99")
        cell.font = Font(name="Calibri", bold=True, color="FFFFFF", size=11)
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.fitToWidth, sheet.page_setup.fitToHeight = 1, 0


""" ----------- 2 - CREATE THE FOUR WORKSHEETS ----------- """


def build_excel(report):
    workbook = Workbook()
    workbook.properties.creator = "ShipStation Excel Export"
    workbook.properties.created = datetime.fromisoformat(report["generatedAt"]).replace(tzinfo=None)
    items = workbook.active
    items.title = report["shipDate"]
    table(items, ITEM_COLUMNS, report["rows"])
    table(workbook.create_sheet("Tracking Records"), TRACKING_COLUMNS, report["events"])
    capture = report.get("shipstationPrintCapture")
    if capture:
        table(
            workbook.create_sheet("ShipStation Print Status"),
            SHIPSTATION_PRINT_COLUMNS,
            capture.get("rows") or [],
        )
    table(workbook.create_sheet("Print History"), PRINT_COLUMNS, report["printJobs"])
    match_summary = report.get("shipstationPrintMatchSummary") or {}
    notes = [
        ("Ship Date", report["displayDate"]),
        ("Generated at (UTC)", report["generatedAt"]),
        ("API mode", report["version"].upper()),
        ("Coverage", report["coverage"]),
        ("Order / shipment groups", report["recordCount"]),
        ("Item rows", report["rowCount"]),
        ("Groups missing tracking", report["missingTrackingCount"]),
        ("Quantity meaning", report["quantityNote"]),
        ("ShipStation Label Printed rows captured", (capture or {}).get("rowCount", 0)),
        ("ShipStation UI rows matched to report", match_summary.get("matched", 0)),
        ("ShipStation UI ambiguous matches", match_summary.get("ambiguous", 0)),
        ("ShipStation UI unmatched report rows", match_summary.get("missing", 0)),
        (
            "ShipStation print-time meaning",
            "The ShipStation Displayed Print Time is copied from Shipments > Label Printed. It is kept exactly as displayed and is not assumed to be the first print time. Label creation time is never substituted.",
        ),
        (
            "ShipStation print completeness",
            "Printed with a missing displayed print time is flagged for review. A missing/unreadable cell is reported as Could not read, not as Not Printed.",
        ),
        ("Matched Windows print jobs", report["printJobCount"]),
        ("Windows print-history result", report["printHistoryNote"]),
        (
            "Windows print status meaning",
            "Windows Printed means Event 307 was found and matched to an identifier in the document name. This is secondary evidence and is not the ShipStation Label Printed status.",
        ),
        (
            "No print match",
            "No matching print record is not proof that an item was never printed. The job may have been printed on another computer, before logging was enabled, or under a generic document name.",
        ),
        (
            "Prices",
            "Line Total is Quantity times Unit Price, before separate tax, shipping or discount. Currency is not inferred; do not sum across currencies.",
        ),
        (
            "Dates",
            "The selected date is the API Ship Date calendar component, not Order Date, label creation date or carrier pickup. V1 queries use ShipStation's documented Pacific time. V2 uses ISO bounds. Compare the first live export with your account's Ship Date display.",
        ),
        (
            "Missing values",
            "Blank means unavailable, never guessed. V2 does not document original Order Date on shipment details. Shipment creation date is not substituted.",
        ),
        (
            "Tracking",
            "Records are linked by API IDs, not SKU or customer name. Multiple tracking numbers on a row do not establish which item was in which package.",
        ),
        (
            "Unlinked records",
            "V1 daily events not linked to a currently Shipped order remain in Tracking Records for review.",
        ),
        (
            "Completeness",
            "All pages are checked; required request failures stop the export. Coverage is limited to records ShipStation exposes to this API account and retains.",
        ),
        (
            "Privacy",
            "Credentials and reports are handled in memory. The downloaded workbook contains customer/order data; store it securely.",
        ),
    ] + [(f"Review {i}", issue) for i, issue in enumerate(report["issues"], 1)]
    info = workbook.create_sheet("Read Me")
    table(
        info,
        [("Report detail", "detail", 30), ("Explanation", "value", 110)],
        [{"detail": name, "value": value} for name, value in notes],
    )
    for row in info.iter_rows(min_row=2):
        info.row_dimensions[row[0].row].height = 50
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()

def build_print_capture_excel(capture):
    """Create a standalone workbook from the latest ShipStation Shipments-grid capture."""
    workbook = Workbook()
    workbook.properties.creator = "ShipStation Daily Shipment Check"
    sheet = workbook.active
    sheet.title = "ShipStation Print Status"
    table(sheet, SHIPSTATION_PRINT_COLUMNS, capture.get("rows") or [])
    notes = workbook.create_sheet("Read Me")
    rows = [
        {"detail": "Captured at", "value": capture.get("capturedAt", "")},
        {"detail": "ShipStation page", "value": capture.get("url", "")},
        {"detail": "Rows captured", "value": capture.get("rowCount", 0)},
        {"detail": "Printed", "value": capture.get("printedCount", 0)},
        {"detail": "Printed but time unreadable", "value": capture.get("printedMissingTimeCount", 0)},
        {"detail": "Printed but tracking missing", "value": capture.get("printedMissingTrackingCount", 0)},
        {"detail": "Label Printed cell unreadable", "value": capture.get("unreadableCount", 0)},
        {"detail": "Meaning", "value": "Displayed Print Date / Time is copied from ShipStation's Shipments > Label Printed cell and preserved as displayed. It is not inferred from label creation or Windows printing."},
    ]
    table(notes, [("Report detail", "detail", 34), ("Explanation", "value", 110)], rows)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()

