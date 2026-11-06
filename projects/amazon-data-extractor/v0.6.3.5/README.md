# Amazon Data Extractor v0.6.3.5

[Download the password-protected Windows ZIP](https://raw.githubusercontent.com/Fenrirn97/Work/main/projects/amazon-data-extractor/v0.6.3.5/Amazon_Data_Extractor_v0.6.3.5_Protected.zip) ·
[SHA-256 checksum](SHA256SUMS.txt)

## What's new

- Use a TXT list with one ASIN or Amazon.com product link per line, as well as
  Excel ASIN workbooks and Category Listings Reports.
- Run focused title, bullet-point or title-and-bullet checks. These create
  `asin_check.xlsx` alongside the complete `amazon_extraction.xlsx`.
- Open the full workbook on **Summary** for status counts and links to the
  other sheets. **Product Overview** brings the title, price, availability,
  seller, ratings and listing link forward.
- Filter **All Fields** by ASIN or field. Nested details have separate rows;
  long text is saved in numbered parts. **Errors** identifies missing, failed,
  redirected and warning results.
- The existing **Amazon Data** and **Input Audit** sheets still support
  Offline Compare. The complete provider response is also saved in JSON.

## Run on Windows

Extract the full ZIP into a new folder using an AES-capable ZIP utility and
the separately supplied archive password. With Python 3.11+ installed, add
your Bright Data key to `brightdata_api_key.txt` beside `app.py` and open
`START.bat`. The key file in the download contains only a placeholder.

The update's source is inside the AES-256 encrypted ZIP. The archive rejected
missing and incorrect passwords, and all 45 decrypted files matched the
tested build. All 70 offline tests passed on Python 3.12 after extraction.
No live account or native Windows launcher was used for testing.
