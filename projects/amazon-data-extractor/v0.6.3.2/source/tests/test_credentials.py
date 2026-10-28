"""Offline checks for the editable key template and both program entry points."""

from __future__ import annotations

import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from openpyxl import Workbook

from app import create_app
from amazon_data_extractor import cli
from amazon_data_extractor.credentials import (
    API_KEY_PLACEHOLDER, API_KEY_TEMPLATE, KeyConfigurationError,
    ensure_api_key_file, load_api_key, normalize_api_key,
)

TEST_KEY = "synthetic-key-for-offline-tests-only"
ASIN = "B000000001"


def input_workbook() -> bytes:
    workbook = Workbook()
    workbook.active.append(["ASIN"])
    workbook.active.append([ASIN])
    output = io.BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


class CredentialTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.file = self.root / "brightdata_api_key.txt"
        environment = patch.dict(os.environ, {"BRIGHTDATA_API_KEY": ""})
        environment.start()
        self.addCleanup(environment.stop)

    def test_shipped_example_is_only_the_safe_placeholder(self):
        self.assertEqual((ROOT / "brightdata_api_key.example.txt").read_text(), API_KEY_TEMPLATE)
        self.assertEqual(normalize_api_key(API_KEY_TEMPLATE), "")

    def test_missing_file_is_created_and_is_not_configured(self):
        self.assertEqual(load_api_key(self.root), "")
        self.assertEqual(self.file.read_text(), API_KEY_TEMPLATE)

    def test_existing_file_is_never_overwritten_even_if_empty(self):
        for value in ("", API_KEY_TEMPLATE, TEST_KEY + "\n"):
            self.file.write_text(value, encoding="utf-8")
            original = self.file.read_bytes()
            ensure_api_key_file(self.root)
            self.assertEqual(self.file.read_bytes(), original)

    def test_file_edits_are_reloaded_with_bom_and_bearer_support(self):
        self.file.write_text("\ufeff bearer " + TEST_KEY + "\n", encoding="utf-8")
        self.assertEqual(load_api_key(self.root), TEST_KEY)
        self.file.write_text("edited-synthetic-key", encoding="utf-8")
        self.assertEqual(load_api_key(self.root), "edited-synthetic-key")

    def test_environment_takes_priority_but_a_placeholder_is_not_a_key(self):
        self.file.write_text(TEST_KEY, encoding="utf-8")
        with patch.dict(os.environ, {"BRIGHTDATA_API_KEY": "environment-test-key"}):
            self.assertEqual(load_api_key(self.root), "environment-test-key")
        with patch.dict(os.environ, {"BRIGHTDATA_API_KEY": API_KEY_PLACEHOLDER}):
            self.assertEqual(load_api_key(self.root), TEST_KEY)

    def test_blank_and_common_placeholder_values_are_rejected(self):
        for value in ("", "  ", API_KEY_PLACEHOLDER, "your_api_key", "Bearer " + API_KEY_PLACEHOLDER):
            with self.subTest(value=value):
                self.assertEqual(normalize_api_key(value), "")

    def test_invalid_content_errors_do_not_echo_the_key(self):
        for value in (TEST_KEY + "\nextra instructions", "not a one-line key", "x" * 4100):
            with self.subTest(length=len(value)), self.assertRaises(KeyConfigurationError) as error:
                normalize_api_key(value)
            self.assertNotIn(TEST_KEY, str(error.exception))

    def test_file_location_is_independent_of_the_terminal_directory(self):
        self.file.write_text(TEST_KEY, encoding="utf-8")
        previous = Path.cwd()
        elsewhere = self.root / "other-folder"
        elsewhere.mkdir()
        try:
            os.chdir(elsewhere)
            self.assertEqual(load_api_key(self.root), TEST_KEY)
            self.assertFalse((elsewhere / "brightdata_api_key.txt").exists())
        finally:
            os.chdir(previous)

    def test_custom_key_file_path_is_supported(self):
        custom = self.root / "private-key.txt"
        custom.write_text(TEST_KEY, encoding="utf-8")
        self.assertEqual(load_api_key(self.root, key_file=Path("private-key.txt")), TEST_KEY)
        self.assertFalse(self.file.exists())

    def test_oversized_or_unreadable_files_have_safe_errors(self):
        self.file.write_text("x" * 8200, encoding="utf-8")
        with self.assertRaises(KeyConfigurationError):
            load_api_key(self.root)
        with patch.object(Path, "open", side_effect=PermissionError("synthetic denied")):
            with self.assertRaises(KeyConfigurationError):
                ensure_api_key_file(self.root)


class CredentialWorkflowTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.file = ensure_api_key_file(self.root)
        environment = patch.dict(os.environ, {"BRIGHTDATA_API_KEY": ""})
        environment.start()
        self.addCleanup(environment.stop)
        self.app = create_app({"TESTING": True, "PROJECT_DIR": self.root})
        self.client = self.app.test_client()

    def upload(self):
        return self.client.post("/extract", data={
            "workbook": (io.BytesIO(input_workbook()), "synthetic.xlsx"), "mode": "Automatic",
        }, follow_redirects=True)

    def test_placeholder_cannot_start_a_live_request(self):
        with patch("app.BrightDataClient") as provider:
            response = self.upload()
            provider.assert_not_called()
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"replace the placeholder", response.data)
        self.assertIn(b"Not configured", response.data)

    def test_edited_txt_key_is_used_by_the_web_app_without_exposing_it(self):
        self.file.write_text(TEST_KEY, encoding="utf-8")
        api = Mock()
        api.collect_sync.return_value = [{"asin": ASIN, "title": "Synthetic product", "features": ["Demo bullet"]}]
        with patch("app.BrightDataClient", return_value=api) as provider:
            response = self.upload()
            provider.assert_called_once_with(TEST_KEY)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(TEST_KEY.encode(), response.data)
        self.assertEqual(len(list(self.root.glob("output/*/amazon_extraction.xlsx"))), 1)
        self.assertNotIn(TEST_KEY, next(self.root.glob("output/*/run_metadata.json")).read_text())
        self.assertEqual(self.file.read_text(), TEST_KEY)

    def test_invalid_key_file_does_not_break_the_homepage_or_expose_contents(self):
        self.file.write_text(TEST_KEY + "\nextra line", encoding="utf-8")
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"one line", response.data)
        self.assertNotIn(TEST_KEY.encode(), response.data)

    def test_cli_placeholder_stops_before_constructing_the_api_client(self):
        input_path = self.root / "input.xlsx"
        input_path.write_bytes(input_workbook())
        with patch.object(cli, "BrightDataClient") as provider, \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()) as stderr:
            result = cli.main([str(input_path), "--yes", "--api-key-file", str(self.file)])
        self.assertEqual(result, 2)
        self.assertIn("Bright Data was not called", stderr.getvalue())
        provider.assert_not_called()

    def test_cli_reads_the_edited_txt_file_instead_of_asking_for_a_key(self):
        input_path = self.root / "input.xlsx"
        input_path.write_bytes(input_workbook())
        self.file.write_text(TEST_KEY, encoding="utf-8")
        api = Mock()
        api.collect_sync.return_value = [{"asin": ASIN, "title": "Synthetic product"}]
        api.dataset_id = "gd_synthetic_offline_test"
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(cli, "BrightDataClient", return_value=api) as provider, \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = cli.main([str(input_path), "--yes", "--sync", "--api-key-file", str(self.file),
                               "--output-dir", str(self.root / "cli-output")])
        self.assertEqual(result, 0)
        provider.assert_called_once_with(TEST_KEY)
        self.assertNotIn(TEST_KEY, stdout.getvalue() + stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
