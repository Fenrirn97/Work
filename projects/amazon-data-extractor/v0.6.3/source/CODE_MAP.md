# Code map — v0.6.3

## Web workflow

`app.py`

- Serves the two-tab local interface.
- Runs live extraction.
- Runs offline comparison.
- Serves generated downloads.
- Schedules the local process exit.

## Input readers

- `asin_reader.py` validates and deduplicates the ASIN upload.
- `offline_reader.py` reads `Amazon Data` and recovers accepted ASINs from
  `Input Audit`.
- `catalog_reader.py` locates ASIN, SKU, Product Name, and Bullet Point 1–5 in
  Amazon Category Listings reports. It discovers the worksheet instead of
  assuming a sheet named `Products`.
- `all_listings.py` reads the optional All Listings TXT as an ASIN/SKU bridge.

## Live collection

- `brightdata_client.py` makes Bright Data requests.
- `live_records.py` classifies each requested ASIN as Found, Redirected,
  Not Found, or Extraction Failed.
- `exporter.py` writes the raw response and `amazon_extraction.xlsx`.

## Comparison

- `comparator.py` performs one-to-one bullet matching and assigns the six
  v0.6.3 classifications. It also resolves blank ASINs by SKU, unique product
  name, and user-entered ASIN.
- `comparison_report.py` creates `comparison_report.xlsx`.

## Rule that protects comparisons

Only a `Found` result for the requested ASIN reaches bullet comparison.
Redirected, missing, and failed live results go to `Live Extraction Problems`.
An existing catalog ASIN is never replaced by a fallback identifier.