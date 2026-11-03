# ShipStation Daily Shipment Check v0.4.9 — Voided Labels

[Download the password-protected Windows ZIP](https://raw.githubusercontent.com/Fenrirn97/Work/main/projects/shipstation-daily-shipment-check/v0.4.9/ShipStation_v0.4.9_Voided_Labels_Protected.zip) · [SHA-256](SHA256SUMS.txt)

## What changed

The Excel workbook adds **Voided & Replacement Labels** and **Related Label History**. They show old tracking, void timestamps, active replacement candidates, and the candidate label's own captured printed status and displayed print time.

The existing main report still uses Ship Date. The new audit uses the same From/Through range for **Void Date**, then reads related label history without a date filter. A replacement created after the selected dates can therefore be included.

A different tracking number on the same marketplace order number is not sufficient. V1 reads history by internal Order ID; V2 uses Shipment ID and linked sales-order IDs when available. Multiple packages, missing IDs, reused tracking, incompatible chronology and incomplete history are marked for review. Replacement candidates are inferences, not an explicit replacement relationship supplied by ShipStation.

## Run

1. Obtain the ZIP password separately from the project owner. It is not stored in this repository.
2. Extract the archive with an AES-compatible ZIP tool such as [7-Zip](https://www.7-zip.org/) into a new folder.
3. Put your existing **API key.txt** beside **START.cmd**, or enter its location in the program.
4. Double-click **START.cmd**, select From/Through dates, and create the Excel report.
5. For a candidate's displayed print time, capture its Shipments row with the included extension, including rows outside the chosen dates, then rerun. Keep existing captures while adding candidate labels for the same report.

Windows 10/11 and Python 3.11 or newer are required. The package contains Python source and Windows launchers; it is not a standalone compiled executable. The launcher installs the required dependencies on first run. API credentials remain local.

The Excel workbook downloads to the browser's configured download folder, usually Downloads.

## Reading the results

- **Replacement candidate found:** one compatible active label with different tracking was found through internal IDs. Verify the inferred relationship before acting.
- **No active replacement found:** no active ShipStation-created outbound label was found in the successfully checked linked history. This is not proof that the order is canceled or the package is missing.
- **Needs review:** multiple possible packages, incomplete metadata, unknown chronology or other uncertainty.
- **Unknown printed status:** no usable exact-tracking print observation was supplied. The old label's print timestamp is never transferred to the candidate.

Check the report's **Complete / Limited / Incomplete** coverage notice. Failed lookups do not become a successful zero-result check. V2 history can be limited when sales-order links are unavailable. Returns, external/carrier-only replacements and recreated orders under unrelated internal IDs are outside this audit.

API timestamps are preserved as returned, and Void Date filtering uses their calendar-date component without account-timezone conversion. Near-midnight UTC timestamps can differ from the local date shown in ShipStation.

## Validation

- **94 automated Python tests passed.**
- **Browser workflow passed:** credential-file selection, date-range validation, Excel downloads, both audit sheets, and candidate print capture through the local HTTP endpoint.
- AES-256 encryption checked, incorrect password rejected, and every decrypted archive file compared with its source.
- Development and validation used synthetic data. Live ShipStation account and native Windows launcher testing remain pending.
- All ShipStation API operations are reads. The program does not void, create, print or modify labels.

Full source, setup notes, tests and the combined source reference are included inside the encrypted archive. The bundled normal-browser print-time extension remains version 0.4.9.

## Distribution

This publishes the exact protected archive initially delivered privately. Public GitHub holds the encrypted package and these release notes; the password and unencrypted v0.4.9 source are not included. Encryption protects the locked download, not source after an authorized recipient extracts it.

[Project guide and version archive](../README.md)
