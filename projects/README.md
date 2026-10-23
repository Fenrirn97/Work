# Project Archive

Public archive of the work software projects developed and tested in ChatGPT.

## Projects

### Amazon Data Extractor
- Archived source tree: **v0.6.3**
- Python / Flask / Bright Data / Excel
- Full browsable source is under `projects/amazon-data-extractor/v0.6.3/source/`.
- [Download Amazon Data Extractor v0.6.3 ZIP](https://raw.githubusercontent.com/Fenrirn97/Work/main/projects/amazon-data-extractor/v0.6.3/Amazon_Data_Extractor_v0.6.3.zip)
- Credential files such as `brightdata_api_key.txt` are intentionally excluded.

### ShipStation Excel Export
- Archived source: **v1.2.0**
- Python local web app
- Complete source bundle is under `projects/shipstation-excel-export/v1.2.0/`.
- [Download ShipStation Excel Export v1.2.0 ZIP](https://raw.githubusercontent.com/Fenrirn97/Work/main/projects/shipstation-excel-export/v1.2.0/ShipStation_Excel_Export_Python_v1.2.0.zip)
- API credentials are supplied at runtime and are not committed.

### ShipStation Daily Shipment Check
- Current date-range variation: **v0.4.7 Date Range**, based on the v0.4.6 normal-browser workflow.
- [Browse v0.4.7 source](shipstation-daily-shipment-check/v0.4.7/source/).
- [Download ShipStation Daily Shipment Check v0.4.7 Date Range ZIP](https://raw.githubusercontent.com/Fenrirn97/Work/main/projects/shipstation-daily-shipment-check/v0.4.7/ShipStation_Daily_Shipment_Check_v0.4.7_Date_Range_Windows.zip).
- Choose From and Through dates; both dates are included, using Ship Date. The same date in both fields produces a single-day report.
- Includes API/CSV comparison and the v0.4.9 normal-browser extension for displayed print time. Apply the same Ship Date filter in ShipStation and capture each required page.
- The historical v0.5.1 separate-browser variation and v0.4.0 baseline remain archived. Version numbering reflects separate variations; see the [project guide](shipstation-daily-shipment-check/README.md).

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

