# Amazon Data Extractor

Current public package: **v0.6.3.1 — startup hotfix**.

This local Python/Flask program provides live Bright Data extraction and
offline catalog comparison, ASIN handling, bullet/image checks and Excel reports.

- [Download v0.6.3.1 ZIP](https://raw.githubusercontent.com/Fenrirn97/Work/main/projects/amazon-data-extractor/v0.6.3.1/Amazon_Data_Extractor_v0.6.3.1.zip)
- [Browse current source](v0.6.3.1/source/)
- [Patch notes and validation](v0.6.3.1/README.md)
- [SHA-256 checksum](v0.6.3.1/SHA256SUMS.txt)

## Install the corrected version

1. Stop the old app and extract the complete new ZIP into a new folder.
2. Double-click `START.bat`; Python 3.11 or newer is required.
3. Open `http://127.0.0.1:5050` if the browser does not open automatically.
4. For live extraction only, create `brightdata_api_key.txt` beside `app.py`
   or copy your private key file from the previous installation.

The patch fixes concatenated statements in `cli.py` and `offline_reader.py`
and adds a startup syntax check. All 17 offline tests passed on Linux/Python
3.12.14. Live Bright Data access and native Windows launchers remain unverified.

The [v0.6.3 archive](v0.6.3/) remains for project history, including its known
startup syntax errors. Use v0.6.3.1 for a new installation. Later versions from
other conversations are not part of this public patch.

Never commit `brightdata_api_key.txt`, private workbooks, output files or other
live marketplace/API credentials. The public ZIP does not contain a key file.
