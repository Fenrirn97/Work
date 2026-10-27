# Amazon Data Extractor v0.6.3.1

Startup hotfix for the public v0.6.3 package. The historical version remains
unchanged in its own folder.

- [Download the complete ZIP](https://raw.githubusercontent.com/Fenrirn97/Work/main/projects/amazon-data-extractor/v0.6.3.1/Amazon_Data_Extractor_v0.6.3.1.zip)
- [Browse source](source/)
- [Full patch notes](source/CHANGELOG.md)
- [SHA-256 checksum](SHA256SUMS.txt)

## Changes

- Split the joined CLI `print()` statements that caused the reported startup
  `SyntaxError`.
- Corrected a second joined statement in `offline_reader.py`; its header
  parser returns after indexing all columns.
- Added a syntax preflight to `START.bat` and five regression tests.
- Updated the web, package, version file and HTTP user-agent to v0.6.3.1.

Extraction and comparison rules remain those of v0.6.3.

## Verification

All 17 offline tests passed on Linux/Python 3.12.14 with network access blocked
during testing. Python sources compile, the local homepage returns HTTP 200,
and the CLI version agrees. The ZIP is checked for CRC integrity, expected
files, source syntax and exclusion of keys, virtual environments and output.
No live Bright Data request or native Windows launcher execution was performed.

## Use

Extract into a **new folder**, not over the old installation, then double-click
`START.bat`. Python 3.11+ and an internet connection for first-time dependency
installation are required. For live extraction, create the private key TXT
file beside `app.py`; it is not included in the public ZIP. Offline Compare
does not require a key.
