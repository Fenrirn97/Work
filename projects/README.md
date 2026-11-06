# Project Archive

Public archive of the work software projects developed and tested in ChatGPT.

## Projects

### Amazon Data Extractor
- Current download: **v0.6.3.5 — Readable Excel Export**
- Python / Flask / Bright Data / Excel
- [Download the password-protected ZIP](https://raw.githubusercontent.com/Fenrirn97/Work/main/projects/amazon-data-extractor/v0.6.3.5/Amazon_Data_Extractor_v0.6.3.5_Protected.zip)
- [Release notes and setup](amazon-data-extractor/v0.6.3.5/README.md). The new source is inside the protected archive; the password is supplied separately.
- Accepts plain TXT ASIN lists and Excel Category Listings Reports. Provides focused title/bullet checks and a full Excel export with a Summary and filterable All Fields.
- All 70 offline tests passed from the extracted archive. Live Bright Data and native Windows launchers were not tested.
- The ZIP's `brightdata_api_key.txt` is a placeholder. Keep populated credential files local.

### ShipStation Excel Export
- Archived source: **v1.2.0**
- Python local web app
- Complete source bundle is under `projects/shipstation-excel-export/v1.2.0/`.
- [Download ShipStation Excel Export v1.2.0 ZIP](https://raw.githubusercontent.com/Fenrirn97/Work/main/projects/shipstation-excel-export/v1.2.0/ShipStation_Excel_Export_Python_v1.2.0.zip)
- API credentials are supplied at runtime and are not committed.

### ShipStation Daily Shipment Check
- Current variation: **v0.4.9.1 Startup Fix**, based on v0.4.9 Voided Labels.
- [Download the protected Windows ZIP](https://raw.githubusercontent.com/Fenrirn97/Work/main/projects/shipstation-daily-shipment-check/v0.4.9.1/ShipStation_0491_Protected.zip).
- Extract the complete archive directly into Documents and open its short **SSC** folder, outside older version folders.
- Startup checks folder depth and required files before importing the app. Missing files produce recovery instructions.
- Preserves void/replacement audit, exact candidate print evidence, inclusive date ranges, automatic API-file selection and the normal-browser extension.
- [Release notes and setup](shipstation-daily-shipment-check/v0.4.9.1/README.md). Source is inside the protected archive. The same separately supplied v0.4.9 password applies.
- Passed 101 Python tests, fresh-archive import/startup checks, and the browser workflow with synthetic data. Live-account and native Windows validation remain pending.
- [Project guide and earlier versions](shipstation-daily-shipment-check/README.md).

### ShipStation Print Time Capture Extension
- Archived browsable source tree: **v0.4.9**
- Chrome/Edge extension source is under `projects/shipstation-print-time-capture-extension/v0.4.9/source/`.
- [Download ShipStation Print Time Capture Extension v0.4.9 ZIP](https://raw.githubusercontent.com/Fenrirn97/Work/main/projects/shipstation-print-time-capture-extension/v0.4.9/ShipStation_Print_Time_Capture_Extension_v0.4.9.zip)
- Captures ShipStation Shipment #, Order #, Tracking #, Label Printed status, and displayed print date/time.

### Inventory Count Web App
- Archived browsable source tree: **v1.6.3 — Expected Units**
- Source is under `projects/inventory-count-web-app/v1.6.3/source/`.
- A complete source-only `ALL_CODE` bundle is retained alongside the source tree.
- [Download Inventory Count Web App v1.6.3 source ZIP](https://raw.githubusercontent.com/Fenrirn97/Work/main/projects/inventory-count-web-app/v1.6.3/Inventory_Count_Web_App_v1.6.3_Expected_Units_Source.zip)
- The bundled portable Python runtime, DLLs, `__pycache__`, and local database/data files are intentionally not committed.

## Security

Do not commit live ShipStation, Bright Data, marketplace, carrier, or other API credentials. Local credential/key files should remain ignored. Test/example keys in the repository are non-production placeholders.
