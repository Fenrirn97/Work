SHIPSTATION PRINT TIME CAPTURE EXTENSION — v0.4.9
=================================================

THIS PACKAGE IS ONLY THE BROWSER EXTENSION.
The main ShipStation Daily Shipment Check program is not included and was not changed.

WHAT v0.4.9 FIXES
-----------------
The v0.4.7 diagnostic proved that ShipStation can render the Label Printed cell as
multiple nested text fragments. Trying to choose one "best" DOM element caused the
actual print value to disappear during organization.

v0.4.9 now:
- captures the row first, before normalizing it;
- finds Packing Slip Printed and Marketplace Notified as the neighboring headers;
- uses those neighbors to define the exact Label Printed column boundaries;
- combines the status/date/time fragments inside that one column;
- accepts ShipStation's bullet separator, for example:
      Printed09/17/2026•13:52
- keeps the horizontal-scroll reader only as a fallback;
- keeps detailed TXT diagnostics, including the fragments found for each row.

This prevents a Packing Slip Printed time from being mistaken for the Label Printed
time when both columns contain print information.

BUTTONS
-------
1. Capture this Shipments page
   Reads Shipment #, Order #, Tracking # and Label Printed and sends the rows to the
   local ShipStation checker at 127.0.0.1:8787.

2. Download Diagnostic TXT
   Does not require the local checker to be running. It downloads a plain TXT file
   showing what the extension detected and how each Label Printed value was rebuilt.

INSTALL / UPDATE
----------------
1. Extract this ZIP to a normal folder.
2. Open edge://extensions or chrome://extensions.
3. Turn on Developer mode.
4. Remove/reload the previous ShipStation Print Time Capture extension.
5. Click Load unpacked.
6. Select the extracted ShipStation_Print_Time_Capture_Extension_v0.4.9 folder.

TEST FIRST
----------
1. Open ShipStation -> Shipments -> Shipped / Recent.
2. Keep Shipment #, Order #, Tracking #, Packing Slip Printed, Label Printed, and
   Marketplace Notified enabled under Columns when possible.
3. Click the extension icon.
4. Click Download Diagnostic TXT first.
5. Confirm rows show short values like:
      Raw Label Printed: Printed 09/17/2026•13:52
      Parsed status: Printed
      Parsed displayed print time: 09/17/2026 13:52
6. Only after that use Capture this Shipments page.

SECURITY
--------
The diagnostic does not include your ShipStation password or API key. The capture
sends only shipment identifiers and Label Printed text to the local checker.
