# Changelog

## v0.6.3.3 — Category Listings Reports as live-extraction input

- Live Extraction and the CLI now accept `.xlsx` and `.xlsm` Category Listings
  Reports directly, as well as ordinary ASIN workbooks.
- Automatically detect the data sheet and header row; skip Amazon's field-name
  and reserved example rows without scraping sample data.
- Read explicit ASIN columns or Product Id values whose Product Id Type is
  ASIN. Reject barcodes, flag conflicting/missing identifiers, exclude explicit
  parent rows and deduplicate submissions.
- Preserve SKU, identifier type, source field and original row in Input Audit;
  show skipped rows in the browser and record layout details in run metadata.
- Keep explicit CLI sheet/header/column overrides. Input reports are read-only;
  macros are not executed and source workbook bytes remain unchanged.
- Added 19 synthetic reader and workflow tests. All 51 offline tests passed,
  including both upload formats, template/example handling, barcode rejection,
  no-ASIN blocking, simple-list compatibility and a 25-ASIN async simulation.

The previously supplied report was also checked locally without network calls.
No private report, its rows or its identifiers are bundled in the public source
or tests. The v0.6.3.2 editable-key template and earlier startup fixes remain.
Live Bright Data access and native Windows launchers remain unverified.

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
