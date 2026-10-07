SHIPSTATION DAILY SHIPMENT CHECK — WINDOWS — VERSION 0.5.1

PURPOSE

The main purpose of this version is to capture the exact status shown by ShipStation
under Shipments -> Label Printed, including the displayed print date/time when
ShipStation exposes it in the grid or its tooltip.

The program does NOT substitute:
- label creation time,
- Ship Date,
- carrier pickup time, or
- Windows spooler time
for ShipStation's own Label Printed field.

WHAT VERSION 0.5.1 ADDS

- Fixes the dedicated Edge window opening at about:blank by explicitly navigating to the current ShipStation login page and verifying navigation succeeded.
- Enables the Chromium sandbox so Edge no longer launches with Playwright's --no-sandbox warning on supported Windows systems.

1. Opens ShipStation in a dedicated Microsoft Edge profile controlled by Playwright.
2. Keeps that dedicated ShipStation login session between runs.
3. Reads the current filtered Shipments grid.
4. Looks for the Shipment #, Tracking #, Order #, and Label Printed columns.
5. Preserves the original Label Printed cell text.
6. Separates:
   - ShipStation Label Printed status
   - ShipStation Displayed Print Date / Time
   - capture time (when this program read the page)
7. Attempts to read a visible tooltip when the cell says Printed but the date/time is
   not already in the cell text.
8. Scrolls virtualized grids and follows a visible Next Page control when available.
9. Treats an unreadable cell as "Could not read". It never converts missing data into
   "Not Printed".
10. Flags:
   - Printed but tracking number missing
   - Printed but displayed print date/time missing/unreadable
   - ambiguous package matches
11. Matches the ShipStation UI row to the API report by:
   a. Shipment # when the identifiers agree,
   b. Tracking #,
   c. Order # only when both sides prove there is exactly one shipment/package.
12. Keeps the existing Windows PrintService Event 307 check as SECONDARY evidence.

IMPORTANT SHIPSTATION BEHAVIOR

ShipStation Smart Document Tracking marks a label Printed when the label is downloaded
or printed through ShipStation Connect. ShipStation documentation says browser printing
does not update Smart Document Tracking.

Because the live account still needs to validate reprint behavior, this program calls
the value "ShipStation Displayed Print Time". It does not assume the time is the first
print, last print, or physical-printer completion time.

START ON WINDOWS

1. Extract the ZIP to a normal folder. A short folder such as C:\ShipStationCheck is
   recommended, but this version no longer places the Python virtual environment inside
   the extracted folder.
2. Double-click START.cmd.
3. The first run installs the Python packages if needed. Internet is required for that
   first setup.
4. The program uses Microsoft Edge already installed on Windows. It does NOT download a
   separate Playwright browser.
5. Your normal browser opens the local control page at http://127.0.0.1:8787.

WHY THE PLAYWRIGHT PATH IS DIFFERENT

Earlier Playwright installation failed with Windows WinError 206 because the project was
inside a deeply nested folder and the .venv was created inside that folder.

This version creates the virtual environment at:

%LOCALAPPDATA%\ShipStationDailyCheck\venv

and the dedicated Edge profile at:

%LOCALAPPDATA%\ShipStationDailyCheck\EdgeProfile

This keeps Playwright's files in a short path.

HOW TO READ LABEL PRINTED STATUS

1. In the local program click "Open ShipStation".
2. A dedicated Edge window opens.
3. Sign in to ShipStation if required.
4. In ShipStation go to Shipments -> Shipments.
5. Apply the exact date/filter you want the program to read.
6. Use ShipStation's Columns control and make sure these are visible:
   - Shipment #
   - Tracking #
   - Label Printed
   Order # is strongly recommended as an additional identity field.
7. Return to the local program.
8. Click "Read Shipments Grid".
9. Review the counts for:
   - Rows read
   - Printed
   - Printed / time missing
   - Printed / tracking missing
   - Unreadable cells
   - Pages read
10. Click "Download Print Status Excel" if you want the browser-capture-only workbook.

CREATE THE COMBINED DAILY REPORT

After reading the Shipments grid:

1. Select the ShipStation API TXT file.
2. Enter the Ship Date.
3. Click "Create Combined Excel Report".

The main worksheet adds these columns:
- ShipStation Label Printed
- ShipStation Displayed Print Time
- ShipStation Label Printed Raw
- ShipStation UI Match
- ShipStation Capture Time

The workbook also includes:
- Tracking Records
- ShipStation Print Status (when a capture exists)
- Print History (Windows Event 307 records)
- Read Me

API KEY TXT FILE

Version 1 credentials:

API_KEY=your_actual_v1_key
API_SECRET=your_actual_v1_secret

Version 2:

V2_API_KEY=your_actual_v2_key

Do not put real credentials into files you share publicly.

SAFETY / COMPLETENESS RULES

- The ShipStation UI reader is read-only. It does not click Print, create labels, void
  labels, change shipment data, or change filters.
- It only clicks a recognized Next Page pagination control while reading.
- It does not rely on Order # alone for split/multi-package orders.
- If the page structure cannot be recognized, the run stops and tells you which columns
  need to be visible. It does not create a false "Not Printed" result.
- The exact ShipStation page structure can change. The first live run against your
  account is required validation for this version.

FIRST LIVE VALIDATION

Use a small known set first, for example 5-10 shipments where you already know:
- which ones are Printed,
- the date/time ShipStation displays,
- the tracking number,
- at least one unprinted/created label if possible.

Compare the downloaded ShipStation Print Status workbook against the Shipments screen.
Do not rely on this version for the whole operation until those rows match correctly.

REPRINT VALIDATION

We still need to establish what ShipStation does to the displayed timestamp when a label
is reprinted. Test one known shipment by recording the displayed value, reprinting it in
the normal ShipStation workflow, then reading the grid again. Until that is confirmed,
the program deliberately preserves the displayed value without calling it first-print or
last-print time.

TESTS

Run:

python -m unittest discover -s tests -v

Version 0.5.1 passes 21 offline tests. These cover the existing API/export behavior plus
print-cell parsing and safe shipment/tracking matching. Offline tests cannot prove the
current live ShipStation DOM structure.

OFFICIAL REFERENCES USED FOR THIS FEATURE

ShipStation Shipment Records & Details / Smart Document Tracking:
https://help.shipstation.com/hc/en-us/articles/360026190952-Shipment-Records-Details

ShipStation Print Labels / Smart Document Tracking behavior:
https://help.shipstation.com/hc/en-us/articles/360026157671-Print-Labels

ShipStation V2 label API (creation time is documented; UI print timestamp is not used as
an API substitute by this program):
https://docs.shipstation.com/apis/openapi/labels/create_label
