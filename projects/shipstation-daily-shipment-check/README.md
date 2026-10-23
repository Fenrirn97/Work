# ShipStation Daily Shipment Check

The current date-range variation is **v0.4.7**, based on the v0.4.6 normal-browser workflow. It combines ShipStation API records, an optional Shipments status CSV, displayed print-time capture, and optional public UPS/FedEx/USPS tracking checks in an Excel report.

[Download v0.4.7 Date Range for Windows](https://raw.githubusercontent.com/Fenrirn97/Work/main/projects/shipstation-daily-shipment-check/v0.4.7/ShipStation_Daily_Shipment_Check_v0.4.7_Date_Range_Windows.zip) · [Browse source](v0.4.7/source/) · [Setup and usage](v0.4.7/source/README.txt) · [Checksums](v0.4.7/SHA256SUMS.txt)

## Run the date-range variation

1. Close any older copy, extract the ZIP into a new folder, and run `START.cmd`.
2. Choose **From date** and **Through date**. Both dates are included, using **Ship Date**. Select the same date twice for a single-day report.
3. Apply the same Ship Date range in ShipStation. Export the Shipments status CSV if needed. For displayed print time, clear the previous capture and use the included v0.4.9 extension on each required page.
4. Choose the API credential TXT file and optional CSV, then click **Create Compared Excel Report**.

The Excel file downloads through the browser to its configured download folder, usually Downloads. Range filenames look like `Shipped_2026-09-29_to_2026-10-02_Checked.xlsx`.

The program's date controls set the API extraction range; they do not change ShipStation's filters or move the extension through pages. Displayed print time remains separate from capture time and is not independent proof of physical printer completion.

Windows 10/11 and Python 3.11 or newer are required. The ZIP contains source and launchers; the launcher installs dependencies on first run. Use the [full instructions](v0.4.7/source/README.txt) for extension setup and carrier support.

## Validation

The delivered v0.4.7 package passed 39 Python automated tests and a browser workflow test with synthetic data before publication. The ZIP is the same package delivered for this variation; its SHA-256 is recorded in `v0.4.7/SHA256SUMS.txt`.

Live ShipStation account validation is still pending. Windows CMD launchers were not executed natively in the Linux build environment. See [TESTING.txt](v0.4.7/source/TESTING.txt) for commands and limits.

## Version archive

| Version | Workflow | Files |
|---|---|---|
| **v0.4.7 Date Range** | Current normal-browser variation; inclusive Ship Date range, CSV/API comparison, bundled v0.4.9 extension | [ZIP and source](v0.4.7/) |
| v0.5.1 | Historical experimental separate-browser reader; retained as an archive, not the workflow used by v0.4.7 | [Archive](v0.5.1/) |
| v0.4.0 | Earlier combined-source baseline | [Archive](v0.4.0/) |

Credentials are supplied locally at runtime. The public package contains only credential placeholders and synthetic test data.

