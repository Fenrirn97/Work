"""Load user-owned API files from one explicit location; persist only that location."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import tempfile
import threading

from shipstation import ReportError, parse_credentials

MAX_KEY_BYTES = 16 * 1024
KEY_NAMES = {"api key", "api key.txt"}


def default_settings_path():
    local = os.environ.get("LOCALAPPDATA")
    parent = Path(local) / "SSC" if local else Path.home() / ".shipstation-daily-shipment-check"
    return parent / "api_key_location.json"


class CredentialSource:
    def __init__(self, app_folder, settings_path=None):
        self.app_folder = Path(app_folder).resolve()
        self.settings_path = Path(settings_path) if settings_path is not None else default_settings_path()
        self._lock = threading.RLock()
        self._location = ""
        self._settings_error = ""
        try:
            with self.settings_path.open("r", encoding="utf-8") as handle:
                raw = handle.read(65537)
            if len(raw) > 65536:
                raise ValueError("Settings too large")
            data = json.loads(raw)
            self._location = self._clean_location(data["location"])
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError, KeyError, ReportError):
            self._settings_error = "The saved API location could not be read. Choose a location again or click Use program folder."

    @staticmethod
    def _clean_location(value):
        if not isinstance(value, str) or len(value) > 32768 or any(c in value for c in "\x00\r\n"):
            raise ReportError("Enter a file or folder path, not the API key itself.")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1].strip()
        return value

    def _resolve(self, location):
        try:
            path = Path(os.path.expandvars(location)).expanduser() if location else self.app_folder
            if not path.is_absolute():
                path = self.app_folder / path
            if path.is_dir():
                # Deliberately shallow: no drive search or recursive folder scan.
                matches = [p for p in path.iterdir() if p.name.casefold() in KEY_NAMES and p.is_file()]
                if not matches:
                    raise ReportError("No API key file found. Put API key.txt beside START.cmd, enter its folder or full file path, or choose a file below.")
                if len(matches) != 1:
                    raise ReportError("More than one API key file was found in that folder. Enter the full path to the one you want.")
                path = matches[0]
            elif not path.exists():
                raise ReportError("The API key location was not found. Check the path or choose the file again.")
            if not stat.S_ISREG(path.stat().st_mode):
                raise ReportError("Choose a regular API text file or the folder that contains API key.txt.")
            return path.resolve()
        except (OSError, ValueError, RuntimeError):
            raise ReportError("The API key location could not be opened. Check the path and Windows permissions.") from None

    def _load(self, location):
        path = self._resolve(location)
        try:
            with path.open("rb") as handle:
                raw = handle.read(MAX_KEY_BYTES + 1)
            if len(raw) > MAX_KEY_BYTES:
                raise ReportError("Choose an API text file smaller than 16 KB.")
            encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
            text = raw.decode(encoding)
        except UnicodeError:
            raise ReportError("Save the API file as UTF-8 text in Notepad, then try again.") from None
        except OSError:
            raise ReportError("The API key file could not be read. Check Windows file permissions.") from None
        credentials = parse_credentials(text)
        version = credentials["version"].upper()
        credentials.clear()
        return text, {"ready": True, "location": location, "path": str(path), "apiVersion": version,
                      "source": "saved location" if location else "program folder"}

    def load(self):
        with self._lock:
            if self._settings_error:
                raise ReportError(self._settings_error)
            return self._load(self._location)

    def status(self):
        with self._lock:
            try:
                _, metadata = self.load()
                return metadata
            except ReportError as error:
                return {"ready": False, "location": self._location, "error": str(error)}

    def use_location(self, value):
        location = self._clean_location(value)
        with self._lock:
            # A bad custom selection must not silently switch credentials or overwrite
            # the previously selected location. Resetting to the program folder is
            # allowed even if its API file has not been placed there yet.
            if location:
                _, metadata = self._load(location)
                location = metadata["path"]  # Keep the chosen absolute file path.
            temporary = None
            try:
                self.settings_path.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.settings_path.parent,
                                                 prefix=".api-location-", suffix=".tmp", delete=False) as handle:
                    temporary = Path(handle.name)
                    json.dump({"location": location}, handle)
                    handle.write("\n")
                os.replace(temporary, self.settings_path)
            except OSError:
                raise ReportError("The API location could not be saved. Check Windows permissions, or choose the file for this report.") from None
            finally:
                if temporary is not None:
                    try:
                        temporary.unlink(missing_ok=True)
                    except OSError:
                        pass
            self._location = location
            self._settings_error = ""
            return self.status()
