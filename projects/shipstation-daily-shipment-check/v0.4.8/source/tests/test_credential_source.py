"""Filesystem selection, persistence, credential precedence, and HTTP isolation."""
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app import make_server
from credential_source import CredentialSource
from shipstation import ReportError, parse_ship_date_range

KEY_A = "API_KEY=synthetic-key-1111\nAPI_SECRET=synthetic-secret-1111"
KEY_B = "API_KEY=synthetic-key-2222\nAPI_SECRET=synthetic-secret-2222"


class CredentialFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.app = self.root / "Extracted Program"
        self.app.mkdir()
        self.settings = self.root / "settings" / "api_key_location.json"
        self.source = CredentialSource(self.app, self.settings)

    def key(self, name="API key.txt", text=KEY_A, parent=None, encoding="utf-8"):
        path = (parent or self.app) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding=encoding)
        return path

    def test_automatic_folder_is_program_folder_not_working_directory(self):
        expected = self.key()
        other = self.root / "Other Folder"
        self.key(text=KEY_B, parent=other)
        before = Path.cwd()
        try:
            os.chdir(other)
            text, metadata = self.source.load()
        finally:
            os.chdir(before)
        self.assertEqual(text, KEY_A)
        self.assertEqual(metadata["path"], str(expected))
        self.assertFalse(self.settings.exists())

    def test_extensionless_case_insensitive_name(self):
        self.key("aPi KeY")
        self.assertEqual(self.source.load()[0], KEY_A)

    def test_utf8_and_utf16_notepad_files(self):
        for encoding in ("utf-8-sig", "utf-16"):
            with self.subTest(encoding=encoding):
                self.key(encoding=encoding)
                self.assertEqual(self.source.load()[0], KEY_A)

    def test_no_recursive_search_or_template_selection(self):
        self.key(parent=self.app / "subfolder")
        self.key("ShipStation_API_KEY_TEMPLATE.txt")
        self.assertFalse(self.source.status()["ready"])

    def test_both_default_names_require_explicit_selection(self):
        path = self.key()
        self.key("API key", KEY_B)
        self.assertIn("More than one", self.source.status()["error"])
        self.source.use_location(str(path))
        self.assertEqual(self.source.load()[0], KEY_A)

    def test_explicit_folder_and_quoted_path_are_remembered(self):
        path = self.key(parent=self.root / "Credentials Folder")
        status = self.source.use_location('"' + str(path.parent) + '"')
        self.assertTrue(status["ready"])
        self.assertEqual(status["location"], str(path))
        fresh = CredentialSource(self.app, self.settings)
        self.assertEqual(fresh.load()[0], KEY_A)
        self.assertEqual(json.loads(self.settings.read_text()), {"location": str(path)})
        self.assertNotIn("synthetic", self.settings.read_text())

    def test_explicit_filename_relative_to_program_folder(self):
        path = self.key("custom-credentials.txt", KEY_B, self.app / "private")
        self.source.use_location("private/custom-credentials.txt")
        self.assertEqual(self.source.load()[1]["path"], str(path))
        self.assertEqual(self.source.load()[0], KEY_B)

    def test_environment_variable_in_supplied_path(self):
        path = self.key(parent=self.root / "Chosen")
        with patch.dict(os.environ, {"SSC_TEST_KEYS": str(path.parent)}):
            value = "%SSC_TEST_KEYS%" if os.name == "nt" else "$SSC_TEST_KEYS"
            self.assertTrue(self.source.use_location(value)["ready"])

    def test_changed_file_is_reread_for_next_report(self):
        path = self.key()
        self.assertEqual(self.source.load()[0], KEY_A)
        path.write_text(KEY_B)
        self.assertEqual(self.source.load()[0], KEY_B)

    def test_missing_saved_path_does_not_silently_use_other_credentials(self):
        self.key()
        chosen = self.key("chosen.txt", KEY_B)
        self.source.use_location(str(chosen))
        chosen.unlink()
        self.assertFalse(self.source.status()["ready"])
        self.source.use_location("")
        self.assertEqual(self.source.load()[0], KEY_A)

    def test_bad_selection_preserves_previous_location(self):
        chosen = self.key("chosen.txt", KEY_B)
        self.source.use_location(str(chosen))
        before = self.settings.read_bytes()
        with self.assertRaises(ReportError):
            self.source.use_location(str(self.root / "missing.txt"))
        self.assertEqual(self.settings.read_bytes(), before)
        self.assertEqual(self.source.load()[0], KEY_B)

    def test_corrupt_settings_can_be_reset_without_a_key_file(self):
        self.settings.parent.mkdir()
        self.settings.write_text("not-json")
        source = CredentialSource(self.app, self.settings)
        self.assertIn("saved API location", source.status()["error"])
        self.assertFalse(source.use_location("")["ready"])
        self.key()
        self.assertTrue(CredentialSource(self.app, self.settings).status()["ready"])

    def test_large_binary_and_placeholder_files_rejected(self):
        path = self.app / "API key.txt"
        for value in (b"x" * 16385, b"\x81\x82\x83", b"API_KEY=replace_with_your_key"):
            with self.subTest(value_type=len(value)):
                path.write_bytes(value)
                self.assertFalse(self.source.status()["ready"])

    def test_permission_error_is_actionable_and_never_echoes_secret(self):
        self.key()
        with patch.object(Path, "open", side_effect=PermissionError("private exception detail")):
            status = self.source.status()
        self.assertFalse(status["ready"])
        self.assertIn("permissions", status["error"])
        self.assertNotIn("private exception detail", json.dumps(status))

    def test_save_failure_preserves_existing_selection(self):
        self.key()
        chosen = self.key("chosen.txt", KEY_B)
        with patch("credential_source.os.replace", side_effect=PermissionError):
            with self.assertRaises(ReportError):
                self.source.use_location(str(chosen))
        self.assertEqual(self.source.load()[0], KEY_A)
        self.assertEqual(list(self.settings.parent.glob("*.tmp")), [])

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO is not available on Windows")
    def test_special_files_are_rejected_before_read(self):
        path = self.app / "pipe.txt"
        os.mkfifo(path)
        with self.assertRaises(ReportError):
            self.source.use_location(str(path))

    def test_status_contains_no_credentials(self):
        self.key()
        encoded = json.dumps(self.source.status())
        self.assertNotIn("synthetic", encoded)
        self.assertNotIn("API_SECRET", encoded)


class CredentialHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.settings = self.root / "settings.json"
        self.key_path = self.root / "API key.txt"
        self.key_path.write_text(KEY_A)
        self.received = []

        def extractor(credentials, start, progress, ship_date_end=None):
            self.received.append(credentials)
            selected = parse_ship_date_range(start, ship_date_end)
            return dict(version="v1", shipDate=selected["iso"], shipDateStart=selected["iso"],
                        shipDateEnd=selected["end"], displayDate=selected["display"],
                        rangeDays=selected["days"], fileRange=selected["fileRange"],
                        generatedAt="2026-10-26T12:00:00+00:00", rowCount=0, recordCount=0,
                        missingTrackingCount=0, coverage="Synthetic", quantityNote="Test",
                        rows=[], events=[], issues=[])

        self.server = make_server(port=0, extractor=extractor, app_folder=self.root, settings_path=self.settings)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def post(self, route, data=None, origin=None):
        request = Request(self.origin + route, data=json.dumps(data or {}).encode(),
                          headers={"Content-Type": "application/json", "Origin": origin or self.origin})
        return urlopen(request).read().decode()

    def report(self, **extra):
        return self.post("/api/report", dict(shipDateStart="2026-10-23", shipDateEnd="2026-10-26", **extra))

    def test_report_reads_local_credentials_without_sending_them_from_browser(self):
        body = self.report()
        self.assertIn('"type": "complete"', body)
        self.assertEqual(self.received, [KEY_A])
        self.assertNotIn("synthetic-secret", body)
        self.assertFalse(self.settings.exists())

    def test_upload_overrides_missing_or_invalid_automatic_file(self):
        self.key_path.write_text("invalid")
        self.report(credentialsText=KEY_B)
        self.assertEqual(self.received, [KEY_B])

    def test_empty_selected_file_does_not_fall_back_to_a_different_key(self):
        with self.assertRaises(HTTPError) as caught:
            self.report(credentialsText="")
        self.assertEqual(caught.exception.code, 400)
        self.assertEqual(self.received, [])

    def test_missing_key_fails_before_extraction(self):
        self.key_path.unlink()
        with self.assertRaises(HTTPError) as caught:
            self.report()
        self.assertEqual(caught.exception.code, 400)
        self.assertIn("API key.txt", caught.exception.read().decode())
        self.assertEqual(self.received, [])

    def test_custom_location_and_reset_affect_next_report(self):
        other = self.root / "Chosen" / "API key.txt"
        other.parent.mkdir()
        other.write_text(KEY_B)
        self.post("/api/credentials/location", {"location": str(other.parent)})
        status = self.post("/api/credentials/status")
        self.assertNotIn("synthetic", status)
        self.assertTrue(json.loads(status)["ready"])
        self.report()
        self.post("/api/credentials/location", {"location": ""})
        self.report()
        self.assertEqual(self.received, [KEY_B, KEY_A])

    def test_other_websites_cannot_read_or_change_local_credential_selection(self):
        for route in ("/api/credentials/status", "/api/credentials/location", "/api/report"):
            with self.subTest(route=route):
                with self.assertRaises(HTTPError) as caught:
                    self.post(route, {"location": str(self.root)}, origin="https://unrelated.example")
                self.assertEqual(caught.exception.code, 403)
        self.assertFalse(self.settings.exists())
        self.assertEqual(self.received, [])

    def test_credentials_cannot_be_downloaded_from_static_server(self):
        for path in ("/API%20key.txt", "/../API%20key.txt", "/%2e%2e/API%20key.txt"):
            with self.subTest(path=path):
                with self.assertRaises(HTTPError) as caught:
                    urlopen(self.origin + path)
                self.assertEqual(caught.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
