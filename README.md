# Software Engineering Portfolio

Practical applications for inventory control, e-commerce data validation, shipment reporting, and browser automation. These projects illustrate translating operational problems into software workflows, validating data, and making results understandable to users.

## Start here

| Project | Problem addressed | Technologies and engineering evidence | Source | Download |
|---|---|---|---|---|
| Inventory Count Web App — v1.6.3 | Record physical counts, compare them with reference inventory, and preserve review/recount history | Python, SQLite, JavaScript, HTML/CSS; validation, session state, audit history, Excel import/export, automated test files | [Browse source](projects/inventory-count-web-app/v1.6.3/source/) | [Download ZIP](https://raw.githubusercontent.com/Fenrirn97/Work/main/projects/inventory-count-web-app/v1.6.3/Inventory_Count_Web_App_v1.6.3_Expected_Units_Source.zip) |
| Amazon Data Extractor — v0.6.3.1 | Compare public product listings with catalog reports and explain discrepancies | Python, Flask, Bright Data integration, openpyxl; ASIN matching, normalization, exception reporting, automated test files | [Browse source](projects/amazon-data-extractor/v0.6.3.1/source/) | [Download ZIP](https://raw.githubusercontent.com/Fenrirn97/Work/main/projects/amazon-data-extractor/v0.6.3.1/Amazon_Data_Extractor_v0.6.3.1.zip) |
| ShipStation Daily Shipment Check — v0.4.8 Auto API Key | Reconcile shipments within an inclusive Ship Date range with label-print status and displayed print time | Python, JavaScript, ShipStation API, CSV and normal-browser extension capture; package matching, Excel reports, automated tests | [Browse source](projects/shipstation-daily-shipment-check/v0.4.8/source/) | [Download ZIP](https://raw.githubusercontent.com/Fenrirn97/Work/main/projects/shipstation-daily-shipment-check/v0.4.8/ShipStation_Daily_Shipment_Check_v0.4.8_Auto_API_Key_Windows.zip) |
| ShipStation Print Time Capture Extension — v0.4.9 | Capture the correct label-print column when the page contains fragmented text and adjacent print fields | JavaScript, Chrome/Edge extension, DOM parsing, local application integration, diagnostic exports | [Browse source](projects/shipstation-print-time-capture-extension/v0.4.9/source/) | [Download ZIP](https://raw.githubusercontent.com/Fenrirn97/Work/main/projects/shipstation-print-time-capture-extension/v0.4.9/ShipStation_Print_Time_Capture_Extension_v0.4.9.zip) |
| ShipStation Excel Export — v1.2.0 | Turn shipment data into an organized local report | Python; archived combined source bundle | [Browse archive](projects/shipstation-excel-export/v1.2.0/) | [Download ZIP](https://raw.githubusercontent.com/Fenrirn97/Work/main/projects/shipstation-excel-export/v1.2.0/ShipStation_Excel_Export_Python_v1.2.0.zip) |

## Selected engineering decisions

### Inventory: preserve the evidence behind a count
The application freezes a reference snapshot and its SHA-256 fingerprint, records count attempts and reviewer decisions in SQLite, and locks finalized sessions. Recounts retain earlier captures. Spreadsheet organization creates a separate output rather than overwriting the input.

### Amazon: explain differences rather than return a single mismatch flag
The comparator distinguishes exact matches, formatting differences, changed text, missing bullets, and moved bullets. Unresolved identifiers and failed live results remain visible in the report. Offline comparison does not make marketplace network calls.

### ShipStation: separate missing information from a negative result
The v0.4.8 checker preserves raw print-cell text and distinguishes displayed print time from capture time. CSV observations require an exact unique tracking match. Browser observations also use exact tracking; a single shipment identifier can be used only when API tracking is missing. An order number alone cannot transfer another package's print status. Multiple-package item rows are marked for review, with individual observations in Tracking Records. The date filter uses Ship Date, and both selected dates are included. API files load automatically from the program folder or a user-supplied location; only the selected path is saved.

### Browser extension: use column boundaries to avoid false matches
The extension combines text fragments within the Label Printed column, using neighboring headers to prevent a packing-slip timestamp from being mistaken for a label timestamp. Diagnostic output supports manual verification.

## Run and review

Each source directory contains its own setup instructions and dependencies. The archive does not include a portable Python runtime; source users need to supply the runtime/dependencies described by the project.

Suggested review order:
1. Read the project README.
2. Inspect the main application and its data-processing modules.
3. Review the test files and run the documented test command.
4. Use synthetic data to try the workflow.

Test files are present in the inventory, Amazon extractor, and shipment checker source directories. This portfolio overview does not claim a fresh test run or a production deployment.

## Scope and limitations

- These are local workflow tools and source archives, not cloud-hosted production services.
- The Amazon version archived here is v0.6.3.1; features from later versions should not be assumed to exist in this source.
- Live extraction requires a separately configured Bright Data credential.
- ShipStation browser behavior needs live validation against the current page structure. Displayed print time is not proof of physical printer completion or first/last reprint time.
- The inventory app's local server should not be exposed publicly without authentication, HTTPS, backups, and production hosting controls.
- Do not use real customer, shipment, employee, inventory, or credential data in public demos or screenshots.

## Skills demonstrated by this archive

Python application development · JavaScript interfaces · Flask web workflows · SQLite persistence · API integration · Playwright automation · DOM parsing · Excel reporting · Data validation · Workflow testing · Diagnostics and documentation

These examples are relevant to backend, full-stack, integration, QA, data, and business-automation work. They do not imply experience with React, TypeScript, cloud architecture, distributed systems, or enterprise CI/CD.

[Complete project index](projects/README.md)



