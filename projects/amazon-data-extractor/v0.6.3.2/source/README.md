# Amazon Data Extractor v0.6.3.2

## Edit the supplied API key TXT file

The downloaded ZIP includes `brightdata_api_key.txt` beside `app.py`.
Open it in Notepad and replace this entire line with your own Bright Data
account API key:

```text
PASTE_YOUR_BRIGHTDATA_API_KEY_HERE
```

Save the file, then start the program or refresh its page. Paste only the key,
on one line. The program reads the file again before each live extraction;
you do not need to edit Python code. An unchanged placeholder is not a key and
never starts an API request. Offline Compare still works without a key.

The file is plain text, not encrypted. Keep it private and never commit it to
GitHub. Public source contains only `brightdata_api_key.example.txt`; setup or
the first page load creates the editable file if it is missing. Existing files
are never overwritten. The ZIP gets its preset TXT from the example template,
never from a developer's local credential file. `BRIGHTDATA_API_KEY`, if set in
the environment, takes priority over the TXT file.

## Startup hotfix

This patch repairs two joined Python statements in the public v0.6.3 source:
the CLI error-message prints and the offline workbook header parser's return.
The Windows launcher now checks Python syntax before opening the browser.
Extraction and comparison rules are unchanged. See `CHANGELOG.md`.

Extract this ZIP into a **new folder** and use its `START.bat`. Do not overwrite
or mix it with the old installation. Copy only your private
`brightdata_api_key.txt` into the new folder if you need live extraction; keep
that file off GitHub. The offline tab does not need a key.

This local Windows program has two separate tabs.

## 1. Live Extraction

1. Upload an `.xlsx` workbook containing an ASIN column.
2. The program validates and deduplicates the ASINs.
3. Bright Data reads the public Amazon product pages.
4. Download `amazon_extraction.xlsx`.

The Bright Data key is read from `brightdata_api_key.txt` or the
`BRIGHTDATA_API_KEY` environment variable. The ZIP includes the editable TXT
with a placeholder, not an actual account key.

## 2. Offline Compare

1. Upload `amazon_extraction.xlsx` from the Live Extraction tab.
2. Upload the Amazon Category Listings Report (`.xlsx` or `.xlsm`).
3. Optionally add the All Listings Report (`.txt` or `.tsv`) for SKU fallback.
4. If catalog rows still have no ASIN, the program pauses and asks you. Each row
   shows its identifier type and number, SKU, and product name.
5. Enter the known ASINs or leave them blank, then download
   `comparison_report.xlsx`.

The offline tab makes no Bright Data or Amazon network call. It recovers the
original requested ASINs from the extraction workbook's `Input Audit` sheet.

Product matching is attempted in this order:

1. Requested ASIN.
2. Returned ASIN.
3. SKU through the optional All Listings Report.
4. Unique normalized product name.
5. ASIN entered by the user on the confirmation screen.

An ASIN already present in the Category Listings Report is never overwritten.
Rows left unresolved are preserved on the `ASIN Needed` sheet with their
original identifier number.

## Bullet classifications

- **Exact Match** — identical text in the same position.
- **Formatting Only** — normalized content is the same, but capitalization,
  punctuation, spacing, HTML, quotes, or similar presentation differs.
- **Text Changed** — both positions contain different content.
- **Missing Live** — the catalog has a bullet and the live result does not.
- **Missing Catalog** — the live result has a bullet and the catalog does not.
- **Bullet Moved** — the same normalized bullet is present at another position.

Redirected, missing, and failed live products are reported but never compared.

## Comparison report

- `ASIN Issues` is the short product-level review list.
- `Bullet Results` includes every classification, including exact matches.
- `Difference Details` contains review-only rows. Its first two columns are
  `ASIN` and `Product Name`, directly beside each other.
- `ASIN Needed` preserves unresolved identifier type/number, SKU, product name,
  and source catalog row.
- `Not Found in Catalog` and `Live Extraction Problems` explain unmatched or
  unusable live results.
- `Read Me` defines the classifications and product-matching order.

## Start on Windows

1. Install Python 3.11 or newer.
2. Extract the entire ZIP; do not run it from inside the ZIP.
3. Double-click `START.bat`.
4. The first start creates `.venv` and installs Flask and openpyxl.
5. Use `http://127.0.0.1:5050` if the browser does not open automatically.
6. Press **Exit Program** when finished. Python stops and the command window
   closes naturally.

The original uploaded workbooks are never modified.

## Verify this patch without using API credits

From this folder, after setup:

```cmd
.venv\Scripts\python.exe -m compileall -q app.py src tests
.venv\Scripts\python.exe -m unittest discover -s tests -v
set PYTHONPATH=src
.venv\Scripts\python.exe -m amazon_data_extractor --version
```

The 32 automated tests use synthetic workbooks and mocked provider responses.
They passed on Linux/Python 3.12.14 during patch verification. A live Bright Data
account and native Windows launcher execution were not tested.
