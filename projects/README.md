# Project Archive

Public archive of the work software projects developed and tested in ChatGPT.

## Projects

### Amazon Data Extractor
- Archived source tree: **v0.6.3.3**
- Python / Flask / Bright Data / Excel
- Full browsable source is under `projects/amazon-data-extractor/v0.6.3.3/source/`.
- [Download Amazon Data Extractor v0.6.3.3 ZIP](https://raw.githubusercontent.com/Fenrirn97/Work/main/projects/amazon-data-extractor/v0.6.3.3/Amazon_Data_Extractor_v0.6.3.3.zip)
- Accepts .xlsx/.xlsm Category Listings Reports directly in Live Extraction, keeps the editable key TXT, and passes 51 offline tests. Earlier versions remain available for history.
- The ZIP's `brightdata_api_key.txt` contains only a placeholder for the user to replace. Populated credential files must remain local and are ignored by the source tree.

### ShipStation Excel Export
- Archived source: **v1.2.0**
- Python local web app
- Complete source bundle is under `projects/shipstation-excel-export/v1.2.0/`.
- [Download ShipStation Excel Export v1.2.0 ZIP](https://raw.githubusercontent.com/Fenrirn97/Work/main/projects/shipstation-excel-export/v1.2.0/ShipStation_Excel_Export_Python_v1.2.0.zip)
- API credentials are supplied at runtime and are not committed.

### ShipStation Daily Shipment Check
- Current variation: **v0.4.9 Voided Labels**, based on v0.4.8 Auto API Key.
- [Download the protected Windows ZIP](https://raw.githubusercontent.com/Fenrirn97/Work/main/projects/shipstation-daily-shipment-check/v0.4.9/ShipStation_v0.4.9_Voided_Labels_Protected.zip).
- [Release notes and setup](shipstation-daily-shipment-check/v0.4.9/README.md). The updated source is inside the encrypted archive; the ZIP password is shared separately.
- Adds Voided & Replacement Labels and Related Label History Excel sheets. Uses the selected range for Void Date and checks related labels across all dates.
- Reports replacement candidates conservatively and attaches only the candidate's own exact-tracking print observations. Missing or ambiguous evidence requires review.
- Preserves automatic local API-file selection, inclusive Ship Date ranges, API/CSV comparison, the normal-browser extension, and optional carrier checks.
- Passed 94 Python tests and the browser workflow with synthetic data. Live-account and native Windows validation remain pending.
- Earlier versions remain archived. See the [project guide](shipstation-daily-shipment-check/README.md).

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
