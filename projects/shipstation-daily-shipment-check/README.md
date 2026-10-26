# ShipStation Daily Shipment Check

The current variation is **v0.4.8 Auto API Key**, based on v0.4.7 Date Range. It combines ShipStation API records, an optional Shipments status CSV, displayed print-time capture, and optional public UPS/FedEx/USPS tracking checks in an Excel report.

[Download v0.4.8 for Windows](https://raw.githubusercontent.com/Fenrirn97/Work/main/projects/shipstation-daily-shipment-check/v0.4.8/ShipStation_Daily_Shipment_Check_v0.4.8_Auto_API_Key_Windows.zip) · [Browse source](v0.4.8/source/) · [Full instructions](v0.4.8/source/README.txt) · [Checksums](v0.4.8/SHA256SUMS.txt)

## Run the program

1. Close any older copy and extract the ZIP into a new folder.
2. Put your existing API text file beside `START.cmd` and name it **API key.txt**. A file named **API key** without an extension also works.
3. Run `START.cmd`. The API area shows **Ready** when the file is found and its format is valid.
4. Choose **From date** and **Through date**. Both dates are included, using **Ship Date**. Select the same date twice for one day.
5. Apply the same Ship Date range in ShipStation. Export the status CSV if needed. For displayed print time, clear the previous capture and use the included extension on every required page.
6. Click **Create Compared Excel Report**.

If the API file is elsewhere, open **Use a different location or choose a file**, paste the file or folder path, and click **Use this location**. The program remembers the location on this Windows account. Only the path is saved. **Use program folder** resets this choice.

A file selected with the file chooser overrides automatic loading for that report. Folder lookup is limited to that folder, without searching the PC or subfolders. Ambiguous or invalid selections produce a message instead of silently switching keys. Readiness checks the file format; ShipStation validates the credentials when a report runs.

The Excel file downloads through the browser to its configured download folder, usually Downloads. Range filenames look like `Shipped_2026-09-29_to_2026-10-02_Checked.xlsx`.

## Requirements and limits

Windows 10/11 and Python 3.11 or newer are required. The ZIP contains source and launchers; the launcher installs dependencies on first run. See the [full instructions](v0.4.8/source/README.txt) for key-file format, extension setup and carrier support.

The date controls do not change ShipStation's filters or move the extension through pages. Displayed print time remains separate from capture time and is not independent proof of physical printer completion.

The package passed **63 Python automated tests and a browser workflow test** with synthetic data. Live ShipStation account validation remains pending. Windows CMD launchers were not executed natively in the Linux build environment. See [TESTING.txt](v0.4.8/source/TESTING.txt) for commands and limits.

## Version archive

| Version | Workflow | Files |
|---|---|---|
| **v0.4.8 Auto API Key** | Automatic local API file selection and remembered location, plus Ship Date ranges and the v0.4.9 extension | [ZIP and source](v0.4.8/) |
| v0.4.7 Date Range | Previous normal-browser variation with inclusive Ship Date ranges | [Archive](v0.4.7/) |
| v0.5.1 | Historical experimental separate-browser reader | [Archive](v0.5.1/) |
| v0.4.0 | Earlier combined-source baseline | [Archive](v0.4.0/) |

Credentials remain local to the user's PC. This public package contains only credential placeholders and synthetic test data.


