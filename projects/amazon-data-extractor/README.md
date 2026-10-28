# Amazon Data Extractor

Current public package: **v0.6.3.2 — editable API-key TXT included**.

- [Download the complete ZIP](https://raw.githubusercontent.com/Fenrirn97/Work/main/projects/amazon-data-extractor/v0.6.3.2/Amazon_Data_Extractor_v0.6.3.2.zip)
- [Browse current source](v0.6.3.2/source/)
- [Release notes](v0.6.3.2/README.md)
- [SHA-256 checksum](v0.6.3.2/SHA256SUMS.txt)

## Use

1. Extract the entire ZIP into a new folder.
2. Open the supplied `brightdata_api_key.txt` beside `app.py` in Notepad.
3. Replace `PASTE_YOUR_BRIGHTDATA_API_KEY_HERE` with only your Bright Data
   account API key, on one line, and save.
4. Double-click `START.bat`. Python 3.11+ is required; first setup needs internet.
5. Open `http://127.0.0.1:5050` if the browser does not open automatically.

The user supplies the real key privately; no shared account key is included.
The program reloads the TXT file before each live extraction and does not
overwrite an existing file. An unchanged placeholder blocks live requests.
Offline Compare works without a key. An existing `BRIGHTDATA_API_KEY`
environment variable takes priority over the TXT file.

The app retains live extraction, catalog/offline comparison, ASIN handling,
bullet/image checks and Excel reporting from the archived baseline. The
v0.6.3.1 startup fixes are included. All 32 offline tests passed on Linux/Python
3.12.14; live Bright Data access and native Windows launchers remain unverified.

## Source and security

The ZIP includes the editable `brightdata_api_key.txt` with a placeholder.
Public source contains only `brightdata_api_key.example.txt`; setup or the
first page load creates the ignored editable file if it is missing. Packaging
always generates the ZIP's key TXT from the safe example, never from a local
credential file. The real key is plain text on the user's computer: do not
commit or share the populated file, private workbooks or output folders.

[v0.6.3.1](v0.6.3.1/) and [v0.6.3](v0.6.3/) remain unchanged for history.
Use the current ZIP for a fresh installation.
