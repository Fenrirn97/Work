# Amazon Data Extractor v0.6.3.3

- [Download ZIP](https://raw.githubusercontent.com/Fenrirn97/Work/main/projects/amazon-data-extractor/v0.6.3.3/Amazon_Data_Extractor_v0.6.3.3.zip)
- [Browse source](source/)
- [Changelog](source/CHANGELOG.md)
- [SHA-256 checksum](SHA256SUMS.txt)

## New input support

Live Extraction now accepts Amazon Category Listings Reports directly, in
`.xlsx` or `.xlsm` format. There is no need to manually create an ASIN-only
workbook. Ordinary ASIN lists remain supported.

- Auto-detect the data sheet and header row, including Amazon's Template layout.
- Skip machine-field and reserved example rows; do not submit example ASINs.
- Read explicit ASIN/Child ASIN fields or Product Id values with type ASIN.
- Reject barcodes and conflicting identifiers instead of guessing ASINs.
- Submit each unique usable ASIN once; skip explicit parent rows.
- Preserve source SKU, identifier type, field and row in the full Input Audit;
  show the first 100 skipped/duplicate rows in the browser.
- Record detected worksheet/header/start row in run metadata.
- Keep CLI overrides, the editable key TXT, startup fixes and offline comparison.

Auto-detection reads one eligible data sheet and scans its first 50 rows and
2,048 columns for headers. Rows with only UPC/EAN/GTIN identifiers still need
their actual ASINs supplied; this patch does not perform barcode lookup.
Workbooks are opened read-only and macros are not run.

## Verification

All 51 offline tests passed on Linux/Python 3.12.14 with network calls blocked.
Coverage includes both file formats, simple lists, machine/reserved-example
rows, identifiers/parents/duplicates, manual overrides, source-byte preservation,
no-ASIN request blocking and a simulated 25-ASIN asynchronous run. A previously
supplied real report was also read locally to verify the layout. No private
report, data rows or identifiers are included in the public package.

The complete ZIP is checked for file integrity, syntax, the placeholder key TXT
and tests from a fresh extraction. Live Bright Data access and native Windows
launcher execution remain unverified.

Extract the ZIP into a new folder, edit its `brightdata_api_key.txt`, then run
`START.bat` and upload the Category Listings Report in Live Extraction. Python
3.11+ and internet for first setup are required. The key stays private locally.
