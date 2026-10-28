# Amazon Data Extractor

Current public package: **v0.6.3.3 — Category Listings input**.

- [Download ZIP](https://raw.githubusercontent.com/Fenrirn97/Work/main/projects/amazon-data-extractor/v0.6.3.3/Amazon_Data_Extractor_v0.6.3.3.zip)
- [Browse source](v0.6.3.3/source/)
- [Release notes](v0.6.3.3/README.md)
- [SHA-256 checksum](v0.6.3.3/SHA256SUMS.txt)

## Use

1. Extract the complete ZIP into a new folder.
2. Open the supplied `brightdata_api_key.txt` beside `app.py`; replace its
   placeholder with your own Bright Data account key and save.
3. Run `START.bat`. Python 3.11+ is required; first setup needs internet.
4. In Live Extraction, upload an ordinary ASIN list or Amazon Category Listings
   Report in `.xlsx` or `.xlsm` format.

The program detects the data sheet/header, reads an ASIN/Child ASIN column or
Product Id values marked ASIN, skips Amazon's reserved template/example rows,
deduplicates requests and excludes explicit parent listings. UPC/EAN/GTIN-only
or conflicting identifiers are not guessed. Skipped rows retain their SKU,
identifier type, source field and row in Input Audit and the result preview.
One detected data sheet is read, not every helper/validation sheet. The first
50 rows and 2,048 columns are scanned for headers; CLI overrides remain.

Source workbooks are not modified and macros are not executed. Automatic mode
uses sync for up to 20 unique ASINs and async for larger input. No usable ASINs
means no provider request. Offline Compare remains unchanged.

## Key file and safety

The ZIP contains an editable placeholder TXT, not a shared working key. Public
source tracks only `brightdata_api_key.example.txt`; setup or the loader safely
creates a missing editable file. Existing key files are never overwritten by
the app. An environment `BRIGHTDATA_API_KEY` takes priority. Keep populated TXT
files, private reports and output local; the TXT is not encrypted.

All 51 offline tests passed, including both report formats, reserved-example
skipping, barcode rejection and a 25-ASIN async simulation. Live Bright Data
account access and native Windows launchers remain unverified.

The [v0.6.3.2 key-template patch](v0.6.3.2/), [v0.6.3.1 startup fix](v0.6.3.1/)
and [v0.6.3 baseline](v0.6.3/) remain available without changes.
