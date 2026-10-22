# Project Archive

Private archive of the software projects developed and tested in ChatGPT.

## Projects

### Amazon Data Extractor
- Archived source tree: **v0.6.3**
- Python / Flask / Bright Data / Excel
- Full browsable source is under `projects/amazon-data-extractor/v0.6.3/source/`.
- The complete GitHub upload bundle is also retained alongside the source tree.
- Downloadable archive: `projects/amazon-data-extractor/v0.6.3/Amazon_Data_Extractor_v0.6.3.zip`\n- Credential files such as `brightdata_api_key.txt` are intentionally excluded.

### ShipStation Excel Export
- Archived source: **v1.2.0**
- Python local web app
- Complete source bundle is under `projects/shipstation-excel-export/v1.2.0/`.
- Downloadable archive: `projects/shipstation-excel-export/v1.2.0/ShipStation_Excel_Export_Python_v1.2.0.zip`\n- API credentials are supplied at runtime and are not committed.

### ShipStation Daily Shipment Check
- Archived browsable source tree: **v0.5.1**
- Earlier source baseline: **v0.4.0**
- Full v0.5.1 source is under `projects/shipstation-daily-shipment-check/v0.5.1/source/`.
- The original v0.5.1 `ALL_CODE` bundle is retained alongside the source tree.
- Downloadable archive: `projects/shipstation-daily-shipment-check/v0.5.1/ShipStation_Daily_Shipment_Check_v0.5.1_Windows.zip`\n- Combines ShipStation shipment data, print-status comparison, extension capture integration, and shipment checking.

### ShipStation Print Time Capture Extension
- Archived browsable source tree: **v0.4.9**
- Chrome/Edge extension source is under `projects/shipstation-print-time-capture-extension/v0.4.9/source/`.
- Downloadable archive: `projects/shipstation-print-time-capture-extension/v0.4.9/ShipStation_Print_Time_Capture_Extension_v0.4.9.zip`\n- Captures ShipStation Shipment #, Order #, Tracking #, Label Printed status, and displayed print date/time.

### Inventory Count Web App
- Archived browsable source tree: **v1.6.3 — Expected Units**
- Source is under `projects/inventory-count-web-app/v1.6.3/source/`.
- A complete source-only `ALL_CODE` bundle is retained alongside the source tree.
- Downloadable source archive: `projects/inventory-count-web-app/v1.6.3/Inventory_Count_Web_App_v1.6.3_Expected_Units_Source.zip`\n- The bundled portable Python runtime, DLLs, `__pycache__`, and local database/data files are intentionally not committed.

## Security

Do not commit live ShipStation, Bright Data, marketplace, carrier, or other API credentials. Local credential/key files should remain ignored. Test/example keys in the repository are non-production placeholders.
