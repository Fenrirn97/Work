# Project Archive

Public archive of the work software projects developed and tested in ChatGPT.

## Projects

### Amazon Data Extractor
- Archived source tree: **v0.6.3.1**
- Python / Flask / Bright Data / Excel
- Full browsable source is under `projects/amazon-data-extractor/v0.6.3.1/source/`.
- [Download Amazon Data Extractor v0.6.3.1 ZIP](https://raw.githubusercontent.com/Fenrirn97/Work/main/projects/amazon-data-extractor/v0.6.3.1/Amazon_Data_Extractor_v0.6.3.1.zip)
- Startup patch: fixes two joined Python statements; 17 offline tests passed. The earlier v0.6.3 folder remains available for history.
- Credential files such as `brightdata_api_key.txt` are intentionally excluded.

### ShipStation Excel Export
- Archived source: **v1.2.0**
- Python local web app
- Complete source bundle is under `projects/shipstation-excel-export/v1.2.0/`.
- [Download ShipStation Excel Export v1.2.0 ZIP](https://raw.githubusercontent.com/Fenrirn97/Work/main/projects/shipstation-excel-export/v1.2.0/ShipStation_Excel_Export_Python_v1.2.0.zip)
- API credentials are supplied at runtime and are not committed.

### ShipStation Daily Shipment Check
- Current variation: **v0.4.8 Auto API Key**, based on v0.4.7 Date Range.
- [Browse v0.4.8 source](shipstation-daily-shipment-check/v0.4.8/source/).
- [Download ShipStation Daily Shipment Check v0.4.8 ZIP](https://raw.githubusercontent.com/Fenrirn97/Work/main/projects/shipstation-daily-shipment-check/v0.4.8/ShipStation_Daily_Shipment_Check_v0.4.8_Auto_API_Key_Windows.zip).
- Automatically loads `API key.txt` or `API key` beside `START.cmd`, or uses a file/folder path entered by the user. The location is remembered; credentials are not copied into settings.
- Includes inclusive From / Through Ship Date selection, API/CSV comparison and the v0.4.9 normal-browser extension for displayed print time.
- The earlier v0.4.7 date-range package, historical v0.5.1 separate-browser variation and v0.4.0 baseline remain archived. See the [project guide](shipstation-daily-shipment-check/README.md).

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



