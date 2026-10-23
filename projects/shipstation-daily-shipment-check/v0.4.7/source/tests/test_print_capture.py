import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from print_capture import (
    merge_capture_store,
    merge_shipstation_print_capture,
    normalize_capture_rows,
    parse_label_print_cell,
)


class PrintCellTests(unittest.TestCase):
    def test_printed_time_mmddyyyy(self):
        parsed = parse_label_print_cell("Printed | 09/29/2026 10:31 AM")
        self.assertEqual(parsed["printStatus"], "Printed")
        self.assertEqual(parsed["displayedPrintTime"], "09/29/2026 10:31 AM")

    def test_printed_time_month_name(self):
        parsed = parse_label_print_cell("Printed Sep 29, 2026 at 10:31 AM")
        self.assertEqual(parsed["printStatus"], "Printed")
        self.assertEqual(parsed["displayedPrintTime"], "Sep 29, 2026 10:31 AM")

    def test_printed_time_shipstation_colon_format(self):
        parsed = parse_label_print_cell("Printed 09/17/2026:11:36")
        self.assertEqual(parsed["printStatus"], "Printed")
        self.assertEqual(parsed["displayedPrintTime"], "09/17/2026:11:36")

    def test_printed_time_shipstation_bullet_format(self):
        parsed = parse_label_print_cell("Printed 09/25/2026•14:40")
        self.assertEqual(parsed["printStatus"], "Printed")
        self.assertEqual(parsed["displayedPrintTime"], "09/25/2026 14:40")

    def test_proven_v049_extension_payload(self):
        rows = normalize_capture_rows([{
            "shipmentNumber": "322379570",
            "orderNumber": "23-15149-06110",
            "tracking": "1ZE664G50331777850",
            "labelPrintedRaw": "Printed 09/25/2026•14:40",
        }], "2026-09-29T20:03:52.116Z")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["printStatus"], "Printed")
        self.assertEqual(rows[0]["displayedPrintTime"], "09/25/2026 14:40")

    def test_created_is_not_printed(self):
        parsed = parse_label_print_cell("Created")
        self.assertEqual(parsed["printStatus"], "Created - not printed")

    def test_unreadable_is_not_called_unprinted(self):
        parsed = parse_label_print_cell("some icon text")
        self.assertEqual(parsed["printStatus"], "Could not read")


class CaptureMergeTests(unittest.TestCase):
    def _base_report(self):
        return {
            "rows": [{
                "orderNumber": "ORDER-1",
                "orderId": "9001",
                "tracking": "1Z1234567890123456",
                "shipmentIds": "7001",
                "source": "ShipStation label",
                "warnings": "",
                "printCheck": "PRINTED",
                "labelPrinted": "Printed",
            }],
            "events": [{
                "orderNumber": "ORDER-1",
                "orderId": "9001",
                "tracking": "1Z1234567890123456",
                "shipmentId": "7001",
                "shipmentIds": "7001",
                "source": "ShipStation label",
            }],
        }

    def test_tracking_match_carries_status_and_time(self):
        report = self._base_report()
        capture = normalize_capture_rows([{
            "shipmentNumber": "7001",
            "orderNumber": "ORDER-1",
            "tracking": "1Z1234567890123456",
            "labelPrintedRaw": "Printed | 09/29/2026 10:31 AM",
        }], "2026-09-29T10:35:00-04:00")
        merge_shipstation_print_capture(report, capture)
        row = report["rows"][0]
        self.assertEqual(row["shipstationUiPrintStatus"], "Printed")
        self.assertEqual(row["shipstationDisplayedPrintTime"], "09/29/2026 10:31 AM")
        self.assertEqual(row["shipstationUiPrintMatch"], "Tracking #")
        self.assertEqual(report["uiPrintMatchedRows"], 1)

    def test_printed_without_tracking_is_critical(self):
        report = self._base_report()
        report["rows"][0]["tracking"] = ""
        report["events"][0]["tracking"] = ""
        capture = normalize_capture_rows([{
            "shipmentNumber": "7001",
            "orderNumber": "ORDER-1",
            "tracking": "",
            "labelPrintedRaw": "Printed | 09/29/2026 10:31 AM",
        }])
        merge_shipstation_print_capture(report, capture)
        row = report["rows"][0]
        self.assertEqual(row["shipstationUiPrintStatus"], "Printed")
        self.assertIn("CRITICAL: ShipStation says Printed but tracking number is missing", row["warnings"])
        self.assertEqual(report["printedMissingTrackingCount"], 1)

    def test_printed_missing_displayed_time_is_flagged(self):
        report = self._base_report()
        capture = normalize_capture_rows([{
            "shipmentNumber": "7001",
            "orderNumber": "ORDER-1",
            "tracking": "1Z1234567890123456",
            "labelPrintedRaw": "Printed",
        }])
        merge_shipstation_print_capture(report, capture)
        self.assertEqual(report["uiPrintedMissingTimeCount"], 1)
        self.assertIn("displayed print date/time could not be read", report["rows"][0]["warnings"])

    def test_multi_package_order_does_not_use_order_number(self):
        report = {
            "rows": [
                {"orderNumber": "ORDER-X", "orderId": "1", "tracking": "", "shipmentIds": "A", "source": "ShipStation label", "warnings": "", "printCheck": "", "labelPrinted": ""},
                {"orderNumber": "ORDER-X", "orderId": "1", "tracking": "", "shipmentIds": "B", "source": "ShipStation label", "warnings": "", "printCheck": "", "labelPrinted": ""},
            ],
            "events": [],
        }
        capture = normalize_capture_rows([
            {"shipmentNumber": "UI-A", "orderNumber": "ORDER-X", "tracking": "", "labelPrintedRaw": "Printed | 09/29/2026 9:00 AM"},
            {"shipmentNumber": "UI-B", "orderNumber": "ORDER-X", "tracking": "", "labelPrintedRaw": "Printed | 09/29/2026 9:05 AM"},
        ])
        merge_shipstation_print_capture(report, capture)
        self.assertTrue(all(row["shipstationUiPrintStatus"] == "" for row in report["rows"]))
        self.assertEqual(report["uiPrintAmbiguousRows"], 2)

    def test_capture_store_accumulates_unique_pages(self):
        first = normalize_capture_rows([{"orderNumber": "A", "tracking": "T1", "labelPrintedRaw": "Printed"}])
        second = normalize_capture_rows([
            {"orderNumber": "A", "tracking": "T1", "labelPrintedRaw": "Printed"},
            {"orderNumber": "B", "tracking": "T2", "labelPrintedRaw": "Created"},
        ])
        merged = merge_capture_store(first, second)
        self.assertEqual(len(merged), 2)

    def test_later_readable_capture_replaces_old_unreadable_capture(self):
        first = normalize_capture_rows([{
            "shipmentNumber": "7001",
            "orderNumber": "ORDER-1",
            "tracking": "1Z1234567890123456",
            "labelPrintedRaw": "",
        }])
        second = normalize_capture_rows([{
            "shipmentNumber": "7001",
            "orderNumber": "ORDER-1",
            "tracking": "1Z1234567890123456",
            "labelPrintedRaw": "Printed 09/17/2026:11:36",
        }])
        merged = merge_capture_store(first, second)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["printStatus"], "Printed")
        self.assertEqual(merged[0]["displayedPrintTime"], "09/17/2026:11:36")


if __name__ == "__main__":
    unittest.main()
