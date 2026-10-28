# Amazon Data Extractor v0.6.3.2

- [Download ZIP](https://raw.githubusercontent.com/Fenrirn97/Work/main/projects/amazon-data-extractor/v0.6.3.2/Amazon_Data_Extractor_v0.6.3.2.zip)
- [Browse source](source/)
- [Changelog](source/CHANGELOG.md)
- [SHA-256 checksum](SHA256SUMS.txt)

## Change requested

The program now comes with `brightdata_api_key.txt` beside `app.py`. Its only
line is:

```text
PASTE_YOUR_BRIGHTDATA_API_KEY_HERE
```

The user opens that TXT, replaces the whole line with their own account API
key, and saves. The web app and CLI read it again before each extraction.
There is no preset working credential or shared paid account.

## Behavior

- Empty/placeholder text is not a key and cannot start a provider request.
- The UI explains which file to edit; offline comparison needs no key.
- Existing files are never overwritten. Missing editable files are safely
  created by setup or the key loader.
- UTF-8/BOM and a Bearer prefix are supported; invalid multi-line content has
  a clear error without echoing its contents.
- `BRIGHTDATA_API_KEY` retains environment-variable priority.
- Public source tracks only the example file and ignores the editable file.
  The downloadable ZIP generates its TXT from that example, not a local key.
- All v0.6.3.1 startup fixes are retained; historical folders remain untouched.

## Verification and limits

All 32 offline tests passed on Linux/Python 3.12.14 with network calls blocked.
The final ZIP is separately checked for the exact placeholder, source/ZIP
integrity and fresh-extraction tests. No live Bright Data key was used. Native
Windows launcher execution remains unverified.

Extract into a new folder, edit the included TXT in Notepad, save, and run
`START.bat`. Python 3.11+ and internet for first-time setup are required. Keep
the populated TXT private; it is not encrypted.
