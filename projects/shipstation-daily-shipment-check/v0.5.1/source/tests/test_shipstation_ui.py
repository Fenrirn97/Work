import unittest

from shipstation_ui import ShipStationBrowserManager, merge_shipstation_capture, parse_label_print_cell


class ShipStationUIParserTests(unittest.TestCase):
    def test_printed_time_is_preserved_from_cell(self):
        parsed = parse_label_print_cell("Label: Printed  09/28/2026 3:14 PM")
        self.assertEqual(parsed["printStatus"], "Printed")
        self.assertEqual(parsed["displayedPrintTime"], "09/28/2026 3:14 PM")
        self.assertIn("Printed", parsed["rawLabelPrinted"])

    def test_created_is_not_printed(self):
        parsed = parse_label_print_cell("Label: Created")
        self.assertEqual(parsed["printStatus"], "Created - not printed")
        self.assertEqual(parsed["displayedPrintTime"], "")

    def test_blank_is_unreadable_not_unprinted(self):
        parsed = parse_label_print_cell("")
        self.assertEqual(parsed["printStatus"], "Could not read")

    def test_merge_prefers_tracking(self):
        rows = [{
            "orderNumber": "1001",
            "shipmentIds": "internal-55",
            "tracking": "1Z999",
            "warnings": "",
        }]
        capture = [{
            "orderNumber": "1001",
            "shipmentNumber": "visible-88",
            "tracking": "1Z999",
            "printStatus": "Printed",
            "displayedPrintTime": "09/28/2026 4:20 PM",
            "rawLabelPrinted": "Printed 09/28/2026 4:20 PM",
            "capturedAt": "2026-09-29T10:00:00-04:00",
        }]
        summary = merge_shipstation_capture(rows, capture)
        self.assertEqual(summary["matched"], 1)
        self.assertEqual(rows[0]["shipstationPrintMatch"], "Tracking #")
        self.assertEqual(rows[0]["shipstationDisplayedPrintTime"], "09/28/2026 4:20 PM")

    def test_unique_order_fallback_can_flag_printed_missing_tracking(self):
        rows = [{
            "orderNumber": "1002",
            "shipmentIds": "shipment-a",
            "tracking": "",
            "warnings": "Tracking unavailable",
        }]
        capture = [{
            "orderNumber": "1002",
            "shipmentNumber": "shipment-visible-a",
            "tracking": "",
            "printStatus": "Printed",
            "displayedPrintTime": "09/28/2026 5:00 PM",
            "rawLabelPrinted": "Printed 09/28/2026 5:00 PM",
            "capturedAt": "2026-09-29T10:00:00-04:00",
        }]
        summary = merge_shipstation_capture(rows, capture)
        self.assertEqual(summary["matched"], 1)
        self.assertIn("unique shipment only", rows[0]["shipstationPrintMatch"])
        self.assertIn("CRITICAL", rows[0]["warnings"])

    def test_order_fallback_refuses_multiple_shipments(self):
        rows = [
            {"orderNumber": "1003", "shipmentIds": "a", "tracking": "", "warnings": ""},
            {"orderNumber": "1003", "shipmentIds": "b", "tracking": "", "warnings": ""},
        ]
        capture = [
            {"orderNumber": "1003", "shipmentNumber": "visible-a", "tracking": "", "printStatus": "Printed", "displayedPrintTime": "", "rawLabelPrinted": "Printed", "capturedAt": "x"},
            {"orderNumber": "1003", "shipmentNumber": "visible-b", "tracking": "", "printStatus": "Printed", "displayedPrintTime": "", "rawLabelPrinted": "Printed", "capturedAt": "x"},
        ]
        summary = merge_shipstation_capture(rows, capture)
        self.assertEqual(summary["matched"], 0)
        self.assertEqual(summary["missing"], 2)


class NavigationTests(unittest.TestCase):
    def test_about_blank_is_navigated_to_shipstation(self):
        class FakePage:
            def __init__(self):
                self.url = "about:blank"
                self.targets = []
            def goto(self, target, **kwargs):
                self.targets.append(target)
                self.url = target
            def wait_for_timeout(self, ms):
                pass
        page = FakePage()
        ShipStationBrowserManager._navigate_to_shipstation(page)
        self.assertTrue(page.targets)
        self.assertIn("shipstation.com", page.url)

    def test_existing_shipstation_page_is_not_reloaded(self):
        class FakePage:
            url = "https://ss6.shipstation.com/shipments"
            def goto(self, target, **kwargs):
                raise AssertionError("should not navigate")
        ShipStationBrowserManager._navigate_to_shipstation(FakePage())


if __name__ == "__main__":
    unittest.main()
