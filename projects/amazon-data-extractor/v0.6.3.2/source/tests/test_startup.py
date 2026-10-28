"""Offline regression checks for the public archive's startup failures."""

from __future__ import annotations

import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from openpyxl import Workbook

from app import APP_VERSION, create_app
from amazon_data_extractor import __version__, cli
from amazon_data_extractor.brightdata_client import BrightDataClient, BrightDataError
from amazon_data_extractor.offline_reader import _headers


class StartupTests(unittest.TestCase):
    def test_every_python_source_compiles(self):
        paths = [ROOT / "app.py", ROOT / "run_extractor.py"]
        paths.extend((ROOT / "src" / "amazon_data_extractor").rglob("*.py"))
        paths.extend((ROOT / "tests").rglob("*.py"))
        for path in paths:
            with self.subTest(file=str(path.relative_to(ROOT))):
                compile(path.read_bytes(), str(path), "exec")

    def test_version_labels_agree(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(__version__, "0.6.3.2")
        self.assertEqual(APP_VERSION, __version__)
        self.assertEqual(project["project"]["version"], __version__)
        self.assertEqual((ROOT / "VERSION.txt").read_text().strip(), __version__)
        self.assertEqual(BrightDataClient("synthetic-test-key")._headers["User-Agent"],
                         f"amazon-data-extractor/{__version__}")

    def test_cli_error_writes_both_messages_and_one_log_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workbook = Workbook()
            workbook.active.append(["ASIN"])
            workbook.active.append(["B000000001"])
            input_path = root / "input.xlsx"
            workbook.save(input_path)
            workbook.close()
            api = Mock()
            api.trigger_collection.side_effect = BrightDataError("Synthetic HTTP 400")
            stderr, stdout = io.StringIO(), io.StringIO()
            with patch.dict(os.environ, {"BRIGHTDATA_API_KEY": "synthetic-test-key"}), \
                    patch.object(cli, "BrightDataClient", return_value=api), \
                    contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(stdout):
                result = cli.main([str(input_path), "--yes", "--output-dir", str(root / "output")])
            self.assertEqual(result, 1)
            self.assertEqual(stderr.getvalue().count("Bright Data error:"), 1)
            self.assertEqual(stderr.getvalue().count("Error log:"), 1)
            log = (root / "output" / "errors.txt").read_text(encoding="utf-8")
            self.assertEqual(log.count("Error: Synthetic HTTP 400"), 1)
            self.assertIn("] UTC", log)
            api.trigger_collection.assert_called_once()

    def test_header_parser_returns_after_all_columns_are_indexed(self):
        workbook = Workbook()
        try:
            workbook.active.append(["Source Row", "Normalized ASIN", "Status", "Status"])
            headers, indexes = _headers(workbook.active)
            self.assertEqual(len(headers), 4)
            self.assertEqual(indexes, {"source row": 0, "normalized asin": 1, "status": 2})
        finally:
            workbook.close()

    def test_homepage_starts_offline_and_displays_patch_version(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict(os.environ, {"BRIGHTDATA_API_KEY": ""}), \
                patch("amazon_data_extractor.brightdata_client.urlopen",
                      side_effect=AssertionError("Live requests are forbidden in this test")):
            app = create_app({"TESTING": True, "PROJECT_DIR": Path(directory)})
            response = app.test_client().get("/")
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"0.6.3.2", response.data)
            self.assertIn(b"Live Extraction", response.data)
            self.assertIn(b"Offline Compare", response.data)


if __name__ == "__main__":
    unittest.main()
