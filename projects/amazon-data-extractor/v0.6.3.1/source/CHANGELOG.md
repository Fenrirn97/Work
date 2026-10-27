# Changelog

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
