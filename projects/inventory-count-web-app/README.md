# Inventory Count Web App

**Latest version: v1.6.4 — Google Sheets Memory Extraction**

## Download the complete Windows program

- [Download portable Windows ZIP v1.6.4](https://github.com/Fenrirn97/Work/releases/download/inventory-v1.6.4/Inventory_Count_Web_App_v1.6.4_Google_Sheets_Memory.zip)
- [GitHub Release page v1.6.4](https://github.com/Fenrirn97/Work/releases/tag/inventory-v1.6.4)
- [ZIP SHA-256 checksum](https://github.com/Fenrirn97/Work/releases/download/inventory-v1.6.4/Inventory_Count_Web_App_v1.6.4_Google_Sheets_Memory.zip.sha256)

Extract the ZIP, open the extracted `Inventory_Count_Web_App` folder, and double-click `start_app.cmd`. Includes the portable Python runtime for Windows 10/11 x64, so a separate Python installation is not required.

**Important:** The green GitHub **Code → Download ZIP** button downloads repository sources, not the ready-to-run portable Windows release.

## New in v1.6.4

- Imports Google Sheets exported to **Excel (.xlsx)**.
- Recognizes RAM values throughout **3–12 GB** and storage values throughout **32–512 GB**.
- Handles combined fields, e.g. `3+32`, `6GB+128GB`, and `12GB RAM + 512GB Storage`, and separate RAM/Storage columns.
- Normalizes recognized memory values while retaining support for non-memory items (`0+0`). The stated ranges are examples, not limits that delete other capacities.
- Preserves the inventory count, expected units, comparisons, validation, session history, and exports from v1.6.3.

## Source and testing

- [v1.6.4 source](./v1.6.4/source/)
- [v1.6.4 change summary](./v1.6.4/README.md)
- [v1.6.3 source](./v1.6.3/source/) and [old release](https://github.com/Fenrirn97/Work/releases/tag/inventory-v1.6.3)

All 24 Python regression tests passed on Linux; targeted Windows tests and portable-runtime import checks also passed in the release workflow. The GitHub release file includes a separate SHA-256 checksum.

v1.6.4 ZIP SHA-256: `2a01d5927ab8ac1a46bda3748578bc527b81542d1d4d112aae2f8d58ad5a1add`.
