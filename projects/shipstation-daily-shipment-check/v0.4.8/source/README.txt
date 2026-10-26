SHIPSTATION DAILY SHIPMENT CHECK — VERSION 0.4.8 (AUTOMATIC API FILE + DATE RANGE)

QUICK START
1. Close any older copy of the program.
2. Extract this ZIP into a new folder. Put your existing API TXT file beside
   START.cmd and name it API key.txt, then double-click START.cmd.
3. Choose From date and Through date. Both dates are included.
4. Click Open ShipStation Shipped Page. In your normal ShipStation browser,
   apply the SAME Ship Date range to the Shipments view.
5. Export Shipments > Current View for the status CSV. For displayed print time,
   clear the previous capture and use the included extension on EACH page.
6. Check that the API area says Ready, then choose your optional status CSV.
   If your API file is elsewhere, open Use a different location or choose a file.
7. Click Create Compared Excel Report. Carrier checks are optional.

AUTOMATIC API KEY FILE
The default location is the folder containing START.cmd and app.py. The program
looks only in that folder for API key.txt or API key (without an extension).
Capitalization does not matter. It does not search the entire PC or subfolders.

To use a different location:
1. Open Use a different location or choose a file in the API area.
2. Paste the full file path, for example C:\Shipping\API key.txt, or its folder,
   for example C:\Shipping. A folder must contain API key.txt or API key.
3. Click Use this location. The location is remembered on this Windows account.
   Clicking Create Compared Excel Report also applies a newly typed path.

Use program folder resets the remembered location. The optional file chooser
still works and overrides automatic loading for that report only; it does not
change the remembered location. Empty or invalid chosen files produce an error
instead of silently switching to another file.

When both API key and API key.txt exist, enter the full path to the one you want.
A missing or invalid saved location must be corrected or reset explicitly.
The program reads the current file again for each report, so replacing the key
in the file does not require restarting the program. The Ready status checks
the file format; ShipStation validates the credentials when a report runs.

The file's credential format is unchanged. For V1, use API_KEY and API_SECRET
on separate lines. For V2, use V2_API_KEY alone. See the supplied placeholder
template. The template is deliberately not named API key.txt and is never
automatically selected. Files must be at most 16 KB. Automatic local reading
accepts UTF-8 and BOM-marked UTF-16 text from Notepad.

Only the selected path is saved, at %LOCALAPPDATA%\SSC\api_key_location.json.
The program does not copy the key into settings, Excel reports, or its source.
An automatically loaded key stays on the local server and is sent to ShipStation
for API authentication; it is not returned to the browser's status display.

WHAT THE RANGE MEANS
The range filters the Ship Date recorded by ShipStation. It does not filter by
Order Date, label creation date, or the displayed print time.

From 09/29/2026 through 10/02/2026 includes September 29 and October 2 in full.
For one day, select the same date in both fields. Reversed or invalid dates are
rejected before any API extraction starts.

The program requests the range in one run. It does not run the entire report
again for each day. V1 shipment and fulfillment queries use the requested range;
order history is read once where the existing reconciliation requires it. V2
completed labels are read once and filtered by Ship Date. Larger ranges can take
longer, particularly if there are many order records or carrier checks.

An order with several packages across dates appears once in the item report.
Ship Date(s) lists its dates within the selected range. Tracking Records keeps
individual shipment/package records. Order item quantity is not proof that every
unit shipped within the range.

OUTPUT
A range report is named, for example:
  Shipped_2026-09-29_to_2026-10-02_Checked.xlsx
A single-day report keeps the previous filename style:
  Shipped_2026-10-05_Checked.xlsx

The selected dates appear in the main sheet name, the on-screen summary, and
Read Me. The workbook contains:
- Main order/item report for the range
- Tracking Records
- Print Status CSV (supplied source records)
- ShipStation Print Capture (supplied source observations)
- Carrier Tracking
- Read Me

The workbook downloads through your browser to its configured download folder,
usually Windows Downloads. Press Ctrl+J in the browser to find the download.

The supporting CSV/capture sheets preserve the supplied source data. They can
contain observations outside the range if you supplied a broader input. Only
matching extracted shipments receive those print observations in the main report.

PRINTED STATUS AND DISPLAYED TIME
This release is based on v0.4.7 and retains the normal-browser workflow and its
bundled v0.4.9 extension. It does not use the experimental v0.5 browser reader.

The API/CSV workflow remains available. ShipStation's status CSV does not provide
the displayed print time in the exports inspected for this project. The extension
reads Shipments > Label Printed from the signed-in browser page, preserving the
raw cell text and the displayed timestamp separately from capture time.

The From / Through controls set the API extraction range. They do not change
ShipStation's browser filters or automatically move the extension through pages.
Apply the same Ship Date range in ShipStation and capture every page you need.
Do not assume that capturing one page covers the entire date range.

Print time is preserved as displayed. No account timezone conversion or claim
about first print versus latest reprint is made. ShipStation's Printed status is
a document record, not independent proof of physical paper output.

EXTENSION SETUP (ONCE)
If the extension is already working, keep using it.
Otherwise:
1. Click Open Extension Folder in the program.
2. In Edge open edge://extensions, or in Chrome open chrome://extensions.
3. Enable Developer mode, click Load unpacked, and choose the included
   ShipStation_Print_Time_Extension folder.
4. Pin its icon to the browser toolbar if useful.

FOR EACH RANGE
1. Keep the local program running on its default port 8787.
2. Click Clear Capture before a new capture session.
3. In ShipStation, apply the same Ship Date range.
4. Show Shipment #, Order #, Tracking #, and Label Printed in the grid.
5. Click the extension and Capture this Shipments page.
6. Repeat for each page in the filtered list.
7. Return to the program and Refresh Capture Status, then create the report.

MATCHING
CSV print observations require an exact unique tracking match. An order number
alone cannot transfer another package's print status. Browser observations also
use exact tracking; if API tracking is missing, a single matching shipment
identifier can be used. Missing tracking remains flagged.
Multiple-package item rows are marked for review instead of inheriting one
package's print time. See Tracking Records for the individual shipments.

INSTALLATION
Windows 10/11, Python 3.11 or newer, and an installed Edge/Chrome browser are
required for the respective browser operations. Internet is needed for first
setup and live ShipStation/carrier access.

START.cmd retains v0.4.6's short per-user runtime at %LOCALAPPDATA%\SSC\v043 to
avoid the earlier Windows long-path installation issue. This version does not
require a new runtime. If browser support fails, close the app and run
REPAIR_BROWSER_TRACKING.cmd while online.

Exit Program stops the local server. Credentials are read from your chosen TXT
file and used in memory. Reports contain shipment/customer information; no API
secret is written into the workbook.

VALIDATION
See TESTING.txt for automated checks and their limits. No live account records
or shipping settings were changed while building this release.
