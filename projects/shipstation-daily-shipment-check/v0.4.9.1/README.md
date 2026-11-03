# ShipStation Daily Shipment Check v0.4.9.1 — Startup Fix

[Download the protected Windows ZIP](https://raw.githubusercontent.com/Fenrirn97/Work/main/projects/shipstation-daily-shipment-check/v0.4.9.1/ShipStation_0491_Protected.zip) · [SHA-256 checksum](SHA256SUMS.txt)

## Fix

The previous archive used a long versioned folder name. Extracting it inside older version folders can push local module paths past Windows path limits. The v0.4.9 archive includes carrier_tracking.py, but the reported missing-module error was consistent with this deeply nested path problem; the user's Windows settings and extracted files were not directly inspected.

This package uses a short **SSC** root folder. START.cmd checks the folder depth before loading Python files, then check_setup.py checks that required modules and browser assets exist, are nonempty and readable. Failure produces instructions to extract the whole program to a short path.

## Install

1. Close older copies of the program.
2. Use 7-Zip and the **same separately supplied v0.4.9 password** to extract the complete ZIP directly into **Documents**.
3. Open the **SSC** folder, outside all older ShipStation folders. If that folder already exists, choose another short location; do not merge versions.
4. Put **API key.txt** beside **START.cmd**, or select its existing location through the program.
5. Double-click **START.cmd**. Keep all the files together; do not run from inside the ZIP.

The folder-depth guard uses 180 characters to leave room for module, asset and cache file names. No Windows registry edit is required. The existing short Local AppData Python environment is retained. Windows 10/11 and Python 3.11 or newer remain required.

## Retained behavior

The main report uses the selected Ship Date range. The void audit uses the same range for Void Date and searches related label history across all dates. Replacement relationships remain candidates, with ambiguous/incomplete results requiring review. A candidate's printed status/time still requires its own exact-tracking observation; no old-label print time is transferred.

All v0.4.9 API-file selection, CSV/extension matching and optional carrier checks remain. The normal-browser extension remains version 0.4.9. The program does not modify ShipStation labels or orders.

## Validation

- **101 automated Python tests passed**, including seven new setup-file/path checks.
- **Fresh encrypted archive checked:** every decrypted file matched the build; all app modules imported from its SSC folder; local app served the v0.4.9.1 interface.
- **Browser workflow passed** with synthetic data, including automatic credentials, date ranges, Excel downloads and candidate print capture.
- **AES-256 archive protection verified**, including rejection of an incorrect password.
- Windows CMD execution and a live-account run remain unverified in this Linux environment. The user's original path-length diagnosis is evidence-based but not confirmed on their PC.

Public GitHub contains the encrypted package and documentation. Its password and unencrypted new source are not published. Full source, tests and instructions are inside the archive.

[Microsoft: Windows path-length limits](https://learn.microsoft.com/en-us/windows/win32/fileio/maximum-file-path-limitation) · [Project guide](../README.md)
