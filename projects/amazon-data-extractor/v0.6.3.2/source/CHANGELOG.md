# Changelog

## v0.6.3.2 — Editable API key TXT supplied in the ZIP

- Added `brightdata_api_key.txt` to the downloadable program with the single
  line `PASTE_YOUR_BRIGHTDATA_API_KEY_HERE` for the user to replace.
- Added a shared web/CLI key loader with placeholder rejection, UTF-8/BOM and
  Bearer-prefix handling, per-request reloads and environment-variable priority.
- Missing editable files are created exclusively; existing files, including
  edited keys, are never overwritten. Setup also creates a missing template.
- Empty/placeholder keys block live extraction before the API client is
  constructed. The interface tells users which file to edit and remains usable
  for offline comparisons.
- Public source contains only the example template and ignores the populated
  key filename. Packaging generates the ZIP's preset TXT from that safe example
  rather than reading any local credential file.
- Added 15 credential and workflow regression tests. All 32 offline tests passed
  on Linux/Python 3.12.14 with network requests blocked. The final ZIP is checked
  separately for its preset contents, source syntax and fresh-install tests.

No live Bright Data key or account was used. Native Windows launcher execution
still requires a Windows check. The v0.6.3.1 startup fixes are retained, and
earlier public versions remain unchanged.

## v0.6.3.1 — Public-package startup hotfix

- Fixed two concatenated `print()` calls in `cli.py` that prevented the app
  from importing its error-log helper.
- Fixed a second concatenated statement in `offline_reader.py`. The header
  parser now returns after indexing all columns, not inside its loop.
- Added a Python syntax preflight to `START.bat` before opening the browser.
- Synchronized the web, package, version-file and HTTP user-agent labels.
- Added offline regression tests for source compilation, version consistency,
  CLI error logging, complete header parsing and the homepage.

This is a maintenance patch to the public v0.6.3 archive. Live extraction and
offline comparison rules are unchanged. Automated verification uses synthetic
workbooks and a simulated provider error; it does not verify a live Bright Data
account. Native Windows launcher execution still requires a Windows check.

Validation: all 17 tests passed on Linux/Python 3.12.14 with network requests
blocked. All Python files compile, the homepage returns HTTP 200, and the CLI
reports v0.6.3.1. The downloadable ZIP is checked separately for integrity,
syntax, expected files and absence of local credential/output files.

The historical v0.6.3 archive remains available for traceability. Use the new
v0.6.3.1 ZIP for a fresh installation rather than merging old and new files.
