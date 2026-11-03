# ShipStation Daily Shipment Check

The current variation is **v0.4.9.1 Startup Fix**, based on v0.4.9 Voided Labels. It combines shipment records, optional CSV and browser print observations, optional carrier checks, and a read-only void/replacement-label audit in one Excel workbook.

[Download v0.4.9.1 protected ZIP](https://raw.githubusercontent.com/Fenrirn97/Work/main/projects/shipstation-daily-shipment-check/v0.4.9.1/ShipStation_0491_Protected.zip) · [Setup and release notes](v0.4.9.1/README.md) · [Checksum](v0.4.9.1/SHA256SUMS.txt)

The updated source and tests are inside the password-protected archive. Obtain the password separately from the project owner.

## Run the program

1. Close any older copy. Extract the complete ZIP directly into **Documents** with 7-Zip, then open its short **SSC** folder. Keep it outside all older ShipStation version folders. If SSC already exists, use another short location rather than merging different versions.
2. Put your existing API text file beside **START.cmd** and name it **API key.txt**. A file named **API key** without an extension also works.
3. Run **START.cmd**. The launcher first checks folder depth and required files. The API area shows **Ready** when the file is found and its format is valid.
4. Choose **From date** and **Through date**. Both dates are included. The main shipment report uses Ship Date; the new void sheet uses Void Date.
5. Apply the desired Ship Date filter in ShipStation. Export the status CSV if needed. For displayed print time, use the included extension on every required page, including candidate replacement labels outside the selected dates.
6. Click **Create Compared Excel Report**. Review **Voided & Replacement Labels**, **Related Label History**, and their coverage notices.

If the API file is elsewhere, open **Use a different location or choose a file**, enter its file or folder path, and click **Use this location**. Only the selected path is saved. A manually selected file overrides automatic loading for that report. The program does not search the entire PC or subfolders.

The workbook downloads through the browser to its configured download folder, usually Downloads.

## Replacement and print evidence

Related labels are read across all dates and linked through internal IDs. A compatible single label is reported as a **candidate**, not a confirmed replacement relationship. Multiple packages, missing links, reused tracking and incomplete lookups require review. A voided label does not mean its order was canceled.

Only the candidate's own exact tracking observation can supply its printed status/time. Blank, unreadable, conflicting or missing evidence remains **Unknown**. Capture time and displayed print time remain distinct; neither independently proves physical printer completion.

## Requirements and validation

Windows 10/11 and Python 3.11 or newer are required. The ZIP contains source and launchers; dependencies are installed on first run.

The v0.4.9.1 package passed **101 automated Python tests, fresh-archive module imports and local startup, and the browser workflow with synthetic data**. Live-account validation and native Windows launcher testing remain pending. See the release notes and the archive's README.txt and TESTING.txt for commands, date interpretation and coverage limits.

## Version archive

| Version | Workflow | Files |
|---|---|---|
| **v0.4.9.1 Startup Fix** | Short SSC folder, early long-path detection and incomplete-extraction checks; retains v0.4.9 features | [Protected ZIP and release notes](v0.4.9.1/) |
| v0.4.9 Voided Labels | Void Date audit, related history, replacement tracking candidates and exact candidate print evidence | [Protected ZIP and release notes](v0.4.9/) |
| v0.4.8 Auto API Key | Automatic local API-file selection, remembered location and Ship Date ranges | [Archive](v0.4.8/) |
| v0.4.7 Date Range | Normal-browser variation with inclusive Ship Date ranges | [Archive](v0.4.7/) |
| v0.5.1 | Historical experimental separate-browser reader | [Archive](v0.5.1/) |
| v0.4.0 | Earlier combined-source baseline | [Archive](v0.4.0/) |

Credentials remain local. This update publishes the protected v0.4.9.1 package, without its password or unencrypted new source. Older repository history has not been rewritten.
