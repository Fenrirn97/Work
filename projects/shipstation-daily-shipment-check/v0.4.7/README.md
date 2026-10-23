# ShipStation Daily Shipment Check v0.4.7 — Date Range

[Download the Windows ZIP](https://raw.githubusercontent.com/Fenrirn97/Work/main/projects/shipstation-daily-shipment-check/v0.4.7/ShipStation_Daily_Shipment_Check_v0.4.7_Date_Range_Windows.zip)

This is the same date-range package delivered for v0.4.7. It adds inclusive From / Through Ship Date selection to the v0.4.6 normal-browser workflow and includes the v0.4.9 print-time capture extension.

- [Setup and usage](source/README.txt)
- [Changes](source/CHANGES_v0.4.7.txt)
- [Validation and limits](source/TESTING.txt)
- [Browsable source](source/)
- [Combined source bundle](ShipStation_Daily_Shipment_Check_v0.4.7_ALL_CODE.txt)
- [ZIP SHA-256](SHA256SUMS.txt)

Extract the ZIP, run `START.cmd`, and choose both dates. Select the same date twice for one day. Set the same Ship Date range in ShipStation when exporting the CSV or capturing print times, and capture every required page.

Excel reports download through the browser to its configured download folder. The ZIP does not include Python; Windows 10/11 and Python 3.11 or newer are required.

The `source/` files and combined source bundle are copied directly from the ZIP. The package passed 39 automated tests and a synthetic browser workflow test; live-account validation remains pending.
