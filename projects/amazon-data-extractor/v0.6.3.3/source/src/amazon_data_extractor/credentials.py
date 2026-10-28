"""Load a user's local key without mistaking the shipped template for a secret."""

from __future__ import annotations

import os
from pathlib import Path
import re


DEFAULT_API_KEY_FILENAME = "brightdata_api_key.txt"
API_KEY_PLACEHOLDER = "PASTE_YOUR_BRIGHTDATA_API_KEY_HERE"
API_KEY_TEMPLATE = API_KEY_PLACEHOLDER + "\n"
PLACEHOLDERS = {
    API_KEY_PLACEHOLDER, "YOUR_API_KEY", "YOUR_BRIGHTDATA_API_KEY",
    "YOUR_BRIGHTDATA_API_KEY_HERE", "PASTE_YOUR_API_KEY_HERE", "PASTE_YOUR_KEY_HERE",
}


class KeyConfigurationError(ValueError):
    """A local key setting needs correction before any provider request."""


def normalize_api_key(value: str) -> str:
    key = value.strip().lstrip("\ufeff").strip()
    key = re.sub(r"^authorization\s*:\s*", "", key, flags=re.I)
    key = re.sub(r"^bearer\s+", "", key, flags=re.I).strip()
    if not key or key.upper() in PLACEHOLDERS:
        return ""
    if len(key) > 4096 or not key.isascii() or any(char.isspace() for char in key):
        raise KeyConfigurationError(
            "The API key must be one line with no spaces. Replace the entire "
            "placeholder in brightdata_api_key.txt with only your key, then save."
        )
    return key


def ensure_api_key_file(project_dir: Path) -> Path:
    """Create a template only if missing; never replace an existing key file."""
    path = Path(project_dir) / DEFAULT_API_KEY_FILENAME
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(API_KEY_TEMPLATE)
    except FileExistsError:
        pass
    except OSError as exc:
        raise KeyConfigurationError(
            "Cannot create brightdata_api_key.txt beside app.py. Check the "
            "folder permissions or create the TXT file there yourself."
        ) from exc
    return path


def load_api_key(project_dir: Path, *, key_file: Path | None = None) -> str:
    """Reload on every use. A configured environment variable takes priority."""
    environment = os.getenv("BRIGHTDATA_API_KEY", "").strip()
    if environment:
        key = normalize_api_key(environment)
        if key:
            return key
    project_dir = Path(project_dir)
    if key_file is None or Path(key_file) == Path(DEFAULT_API_KEY_FILENAME):
        path = ensure_api_key_file(project_dir)
    else:
        path = Path(key_file)
        if not path.is_absolute():
            path = project_dir / path
    try:
        if path.stat().st_size > 8192:
            raise KeyConfigurationError("The API key TXT file is too large; it should contain only one key.")
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return ""
    except (OSError, UnicodeError) as exc:
        raise KeyConfigurationError(
            "Cannot read the API key TXT file. Check its permissions and save it as UTF-8 text."
        ) from exc
    return normalize_api_key(text)
