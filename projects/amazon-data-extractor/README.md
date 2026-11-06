# Amazon Data Extractor

Current GitHub package: **v0.6.3.5 — Readable Excel Export**.

- [Download the password-protected ZIP](https://raw.githubusercontent.com/Fenrirn97/Work/main/projects/amazon-data-extractor/v0.6.3.5/Amazon_Data_Extractor_v0.6.3.5_Protected.zip)
- [Release notes and setup](v0.6.3.5/README.md)
- [SHA-256 checksum](v0.6.3.5/SHA256SUMS.txt)

The new program and source files are inside the AES-256 encrypted ZIP. The
archive password is supplied separately. No API key is included.

## Use

1. Extract the complete ZIP into a new folder with an AES-capable ZIP utility.
2. Open the supplied `brightdata_api_key.txt` beside `app.py`; replace the
   placeholder with your own Bright Data account key and save.
3. Run `START.bat`. Python 3.11+ is required; first setup needs internet.
4. In Live Extraction, upload a plain `.txt` list (one ASIN or Amazon.com
   product link per line), an ASIN workbook, or a Category Listings Report
   in `.xlsx` or `.xlsm` format.
5. Download `amazon_extraction.xlsx` and open **Summary**. Select a title
   or bullet-point check if you also want a focused workbook.

The program detects the workbook data sheet and header. It accepts an
ASIN/Child ASIN column or Product Id values explicitly marked ASIN, skips
Amazon's reserved rows, deduplicates ASINs and audits skipped inputs. It does
not guess ASINs from barcodes, modify input files or execute macros.

**Product Overview** puts common fields first. **All Fields** lists returned
fields and nested values by ASIN, and **Errors** explains missing, failed or
redirected results. The full workbook and raw JSON are saved even when a
focused check is selected. Offline Compare still reads the full workbook.

## Verification and history

The protected package passed all 70 offline tests after extraction. No live
Bright Data request or native Windows launch was tested. The archive contains
only the example key placeholder; keep your actual key local.

Earlier releases remain as published: [v0.6.3.3](v0.6.3.3/),
[v0.6.3.2](v0.6.3.2/), [v0.6.3.1](v0.6.3.1/) and [v0.6.3](v0.6.3/).
