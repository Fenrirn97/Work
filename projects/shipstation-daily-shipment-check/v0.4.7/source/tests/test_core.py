
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from carrier_tracking import (
    build_tracking_url,
    extract_browser_status,
    normalize_carrier,
    valid_tracking_identifier,
)
from excel_export import build_excel
from print_status import merge_print_status, parse_print_status_csv


class PrintStatusTests(unittest.TestCase):
    def test_csv_keeps_tracking_as_text_and_marks_scientific_unsafe(self):
        text = (
            "Shipment #,Order #,Tracking #,Service,Recipient,Ship Date,Packing Slip Printed,"
            "Label Created,Label Printed,Marketplace Notified,Shipment Notification,Delivery Notification\n"
            "322564113,13-15170-13871,1ZE664G50323432871,UPS Ground,T J,09/17/2026,,Created,,Notified,Not Sent,Failed\n"
            "111,ORDER2,9.40015020621792E+021,USPS Ground Advantage,A B,09/17/2026,,Created,Printed,Notified,Not Sent,Failed\n"
        )
        rows = parse_print_status_csv(text)
        self.assertEqual(rows[0]["tracking"], "1ZE664G50323432871")
        self.assertEqual(rows[1]["tracking"], "")
        self.assertEqual(rows[1]["trackingRaw"], "9.40015020621792E+021")

    def test_merge_matches_real_world_tracking(self):
        csv_text = (
            "Shipment #,Order #,Tracking #,Service,Recipient,Ship Date,Packing Slip Printed,"
            "Label Created,Label Printed,Marketplace Notified,Shipment Notification,Delivery Notification\n"
            "322564113,13-15170-13871,1ZE664G50323432871,UPS Ground,T J,09/17/2026,,Created,,Notified,Not Sent,Failed\n"
        )
        report = {
            "rows": [{
                "orderNumber": "13-15170-13871",
                "orderId": "322564113",
                "tracking": "1ZE664G50323432871",
                "source": "ShipStation label",
            }],
            "events": [],
        }
        merge_print_status(report, parse_print_status_csv(csv_text))
        self.assertEqual(report["rows"][0]["printCheck"], "NOT PRINTED")
        self.assertEqual(report["rows"][0]["printMatch"], "Tracking #")
        self.assertEqual(report["notPrintedRowCount"], 1)

    def test_fulfillment_is_not_false_not_printed(self):
        report = {
            "rows": [{
                "orderNumber": "A",
                "orderId": "1",
                "tracking": "383710885977",
                "source": "Fulfillment / marked shipped",
            }],
            "events": [],
        }
        merge_print_status(report, [])
        self.assertTrue(report["rows"][0]["printCheck"].startswith("N/A"))


class CarrierTests(unittest.TestCase):
    def test_supported_carrier_detection(self):
        self.assertEqual(normalize_carrier("ups_walleted", "ups_ground", "", "1Z123"), "UPS")
        self.assertEqual(normalize_carrier("fedex", "fedex_2day", "", "383710885977"), "FedEx")
        self.assertEqual(normalize_carrier("stamps_com", "usps_ground_advantage", "", "940011"), "USPS")
        self.assertEqual(normalize_carrier("", "", "", "1Z9999999999999999"), "UPS")

    def test_tracking_identifier_rejects_scientific_notation(self):
        self.assertFalse(valid_tracking_identifier("9.40015020621792E+021"))
        self.assertTrue(valid_tracking_identifier("9400150206217922772301"))

    def test_public_tracking_urls(self):
        self.assertIn("tracknum=1ZE664G50323432871", build_tracking_url("UPS", "1ZE664G50323432871"))
        self.assertIn("trknbr=383710885977", build_tracking_url("FedEx", "383710885977"))
        self.assertIn("tLabels=9400150206217922772301", build_tracking_url("USPS", "9400150206217922772301"))

    def test_ups_label_created_is_not_shipped(self):
        body = """
        Tracking Number 1ZE664G50323432871
        Label Created
        Estimated delivery date will be available when UPS receives the package.
        """
        result = extract_browser_status("UPS", "1ZE664G50323432871", body)
        self.assertEqual(result["status"], "LABEL CREATED")
        self.assertEqual(result["carrierAccepted"], "No")

    def test_fedex_label_created_is_not_shipped(self):
        body = """
        383710885977
        Label created
        We'll add a delivery date as soon as we get your package.
        """
        result = extract_browser_status("FedEx", "383710885977", body)
        self.assertEqual(result["status"], "LABEL CREATED")
        self.assertEqual(result["carrierAccepted"], "No")

    def test_usps_pre_shipment_is_not_shipped(self):
        body = """
        9400150206217922772301
        Pre-Shipment
        Shipping Label Created, USPS Awaiting Item
        """
        result = extract_browser_status("USPS", "9400150206217922772301", body)
        self.assertEqual(result["status"], "LABEL CREATED")
        self.assertEqual(result["carrierAccepted"], "No")

    def test_physical_carrier_statuses(self):
        ups = extract_browser_status("UPS", "1Z999999999999999999", "1Z999999999999999999\nWe Have Your Package")
        fedex = extract_browser_status("FedEx", "383710885977", "383710885977\nOn the way")
        usps = extract_browser_status("USPS", "9400150206217922772301", "9400150206217922772301\nUSPS in possession of item")
        self.assertEqual(ups["carrierAccepted"], "Yes")
        self.assertEqual(fedex["status"], "IN TRANSIT")
        self.assertEqual(usps["status"], "CARRIER ACCEPTED")

    def test_human_verification_is_not_bypassed(self):
        body = "Tracking 383710885977\nPlease verify you are human to continue."
        result = extract_browser_status("FedEx", "383710885977", body)
        self.assertEqual(result["status"], "MANUAL CHECK REQUIRED")
        self.assertEqual(result["carrierAccepted"], "Unknown")


class ExcelSmokeTests(unittest.TestCase):
    def test_workbook_builds(self):
        report = {
            "generatedAt": "2026-09-24T18:00:00+00:00",
            "shipDate": "2026-09-17",
            "displayDate": "09/17/2026",
            "version": "v1",
            "coverage": "test",
            "recordCount": 1,
            "rowCount": 1,
            "missingTrackingCount": 0,
            "quantityNote": "test",
            "issues": [],
            "printCsvProvided": True,
            "printCsvRecordCount": 1,
            "printCsvMatchedRows": 1,
            "notPrintedRowCount": 1,
            "unmatchedPrintCsvCount": 0,
            "carrierCheckEnabled": True,
            "carrierCheckCount": 1,
            "carrierAcceptedCount": 0,
            "carrierNotAcceptedCount": 1,
            "carrierManualCount": 0,
            "carrierErrorCount": 0,
            "events": [],
            "printStatusRecords": [],
            "carrierTracking": [{
                "tracking": "1ZE664G50323432871",
                "carrier": "UPS",
                "trackingUrl": build_tracking_url("UPS", "1ZE664G50323432871"),
                "status": "LABEL CREATED",
                "carrierAccepted": "No",
                "statusDescription": "Label Created",
                "firstCarrierScan": "",
                "latestScan": "",
                "latestLocation": "",
                "estimatedDelivery": "",
                "actualDelivery": "",
                "checkedAt": "2026-09-24T14:00:00-04:00",
                "error": "",
            }],
            "rows": [{
                "orderNumber": "13-15170-13871",
                "itemName": "Test",
                "sku": "TEST",
                "quantity": 1,
                "orderDate": "2026-09-16",
                "shipDate": "2026-09-17",
                "tracking": "1ZE664G50323432871",
                "carrier": "ups_walleted",
                "service": "ups_ground",
                "source": "ShipStation label",
                "labelCreated": "Created",
                "labelPrinted": "",
                "printCheck": "NOT PRINTED",
                "printMatch": "Tracking #",
                "marketplaceNotified": "Notified",
                "shipmentNotification": "Not Sent",
                "deliveryNotification": "Failed",
                "normalizedCarrier": "UPS",
                "trackingUrl": build_tracking_url("UPS", "1ZE664G50323432871"),
                "carrierStatus": "LABEL CREATED",
                "carrierAccepted": "No",
                "carrierStatusDescription": "Label Created",
                "firstCarrierScan": "",
                "latestCarrierScan": "",
                "latestCarrierLocation": "",
                "estimatedDelivery": "",
                "actualDelivery": "",
                "shippingWarning": "CRITICAL - NOT PRINTED AND NO CARRIER ACCEPTANCE",
                "carrierCheckError": "",
                "store": "Omega eBay",
                "recipient": "T J",
                "unitPrice": 35,
                "lineTotal": 35,
                "fulfillmentProvider": "",
                "orderId": "322564113",
                "itemId": "616592577",
                "shipmentIds": "171703764",
                "recordIds": "171703764",
                "warnings": "",
            }],
        }
        data = build_excel(report)
        self.assertGreater(len(data), 5000)
        self.assertEqual(data[:2], b"PK")


if __name__ == "__main__":
    unittest.main()
