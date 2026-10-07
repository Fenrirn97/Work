# Inventory Count Web App

A local Python web application for recording boxed and loose inventory, running controlled cycle counts, keeping count-session history in SQLite, comparing Excel workbooks, and exporting organized `.xlsx` reports.

## Run it on Windows without installing Python

1. Extract the ZIP file to a normal folder.
2. Double-click `start_app.cmd`.
3. Your default browser opens the app at `http://127.0.0.1:8765/`.
4. Keep the black server window open while using the app. Press `Ctrl+C` in that window when finished.

The portable Windows x64 package includes the official CPython 3.14.7 embedded runtime in the `runtime` folder. Python does not need to be installed on the PC. Keep the entire extracted folder together; do not run the launcher from inside the ZIP.

The launcher uses the bundled runtime first and falls back to an installed Python 3.10 or newer only when the `runtime` folder is missing. The app does not require Flask, Excel, Microsoft Office, or a separate database installation.

This portable build supports 64-bit Windows 10 and Windows 11. The bundled runtime is the official Python Software Foundation release from `https://www.python.org/downloads/release/python-3147/`; its license is included at `runtime/LICENSE.txt`.

## Version 1.6.3 patch

- Renamed the selected-product quantity to **Expected Units** so the reference count is explicit.
- The counting screen now shows **Expected Units**, **Current Count**, and a live **Difference**.
- Current Count and Difference update immediately as Items per Box, Number of Boxes, or Loose Items change.
- Autocomplete suggestions now label the reference number as **Expected Units**.

## Version 1.6.2 patch

- Inventory quantity is now visible directly in product autocomplete.
- Selecting an inventory item shows a large **Inventory Qty** value on the counting screen.
- The displayed quantity uses the same baseline rule as comparison: START first, then END when START is unavailable.
- The quantity display clears if the user manually changes Model, RAM, Storage, or Color so an old quantity is never shown for a different product.
- Existing databases are upgraded in place with the new nullable catalog quantity field.

## Version 1.6.1 patch

- Removed Blind Count mode completely.
- Frozen reference quantities are no longer intentionally hidden while counting.
- The Compare & Review screen can show a live comparison for products already counted without marking every not-yet-counted reference item as missing.
- Manual reference comparison is allowed while the session is still in Counting status.
- Final submission still performs the complete comparison and preserves the existing approval/recount history.

## Version 1.6 usability improvements

Version 1.6 keeps the existing SQLite database and cycle-count workflow, while making daily counting faster and easier for non-technical users:

- Quick actions for **Start New Count**, **Continue Count**, **Review Problems**, and **Export Count**.
- Automatic draft recovery for unfinished form values and the last open work area in each session.
- A visible autosave indicator.
- Keyboard-first entry: press Enter to move through the count fields; the final Enter submits the count.
- Improved model autocomplete that searches Model, RAM, Storage, and Color and shows when one variant came from multiple spreadsheet rows.
- Recently counted product shortcuts that refill the product identity with one click.
- Clear **Counted**, **Needs Review**, and **Locked** row statuses plus labeled Edit/Remove buttons.
- A **Problems** shortcut and a comparison filter that hides matching rows when the user only needs to review issues.
- A transparent **Import Check** before an organized workbook is created. It reports source rows found, imported rows, skipped rows with exact worksheet/row/reason, duplicate source rows, unique variants, sections, and detected dates.
- The last successfully validated source workbook and its organized copy are stored locally in SQLite. A new session can reuse the last validated workbook without browsing for it again, and the organized copy can be downloaded again.
- Organized workbooks with separate Model/RAM/Storage columns can be used as frozen references in addition to legacy combined MAKE references.
- Partial date labels such as `11/13` are preserved in the organized copy instead of becoming blank.

All of these additions are local to the PC running the app. No cloud account is required.

## Inventory fields

- Model
- RAM
- Storage / Memory
- Color
- Items per Box
- Number of Boxes
- Loose Items
- Area / Location
- Broken Box

The saved amount is calculated as:

```text
(Items per Box × Number of Boxes) + Loose Items
```

Every new product row automatically records its original entry date and time. The web table and Excel export display that timestamp in the computer's local time. Editing a row does not replace its original entry timestamp.

## Cycle-count workflow

1. Create a **Planned** or **Spot** session and enter the warehouse, location, operator, and optional tolerances.
2. Open **Session History**, select the reference workbook, and choose **Freeze Reference & Download Organized Copy**.
3. The app validates the workbook before saving anything. It stores a SHA-256 fingerprint and parsed snapshot in SQLite, loads the autocomplete variants, and downloads a separate organized copy. The original workbook is never changed.
4. Enter the physical count. The **Compare & Review** screen shows the frozen reference quantity and current difference for products already counted.
5. When the count is ready for final review, choose **Submit Count for Review**. The app performs the complete comparison against the frozen snapshot, including reference items not yet counted.
6. Exact matches are accepted automatically. Differences inside a configured tolerance wait for supervisor review. Differences outside tolerance request a recount. A supervisor can approve or start a new recount and must record a name and reason.
7. After approval, finalize the session to lock it.

Recounts never delete prior captures. Each attempt keeps its count rows, submitted results, reviewer decision, name, reason, and timestamps.

## Inventory movement log

The **Movement Log** records receiving, shipments, transfers, temporary removals, returns to stock, and adjustments. Each movement keeps the product identity, quantity, locations, operator, note, and time. Movements during a count window produce review warnings; they never change physical-count quantities automatically.

## Organize an existing Excel workbook without changing it

Open the **Organize Excel** tab, select an `.xlsx` or `.xlsm` workbook, and choose **Create Organized Copy**. The uploaded workbook is read-only input: the app never edits, renames, moves, or overwrites it. The app first displays a validation preview and asks for confirmation. A separate macro-free download named `OriginalName_Organized.xlsx` is created with these columns:

- Model
- RAM
- Storage
- Color
- START
- END
- Date Counted

The organizer recognizes `Model` or `MAKE`, `Color` or `Colour`, separate or combined `START`/`END` headings, common date headings, and optional separate RAM and Storage columns. For Date Counted, it uses a labeled date column first. It can also recognize a consistently date-formatted unlabeled column and preserves partial values such as `11/13` without inventing a year. Worksheet names are never treated as product dates; when a product row has no date, Date Counted stays blank. A combined item such as `Phone X 8+256` is split into Model `Phone X`, RAM `8 GB`, and Storage `256 GB`. A `0+0` suffix is removed and leaves RAM and Storage blank for non-memory items.

### Model autocomplete

Creating the organized copy also replaces the app's local autocomplete catalog with the unique product variants extracted from that workbook. The catalog is stored in `data/inventory.db`, so it remains available after closing and reopening the app.

When a user types at least two characters in the Model field, the app searches the catalog and displays every matching variant. Each option shows Model, RAM, Storage, and Color. Selecting an option fills all four identity fields. For non-memory items, selecting the option fills RAM and Storage with `0` so the existing validation rule remains valid. Manual entry is always available when no option matches.

## Product identity rules

- Normal comparison identity: Model + RAM + Storage + Color.
- Area does not change product identity.
- Broken Box does not change product identity; its quantity is reported separately.
- When RAM and Storage are both `0`, the item is treated as a non-memory product. RAM and Storage are omitted from its displayed name and the comparison identity becomes Model + Color.
- A partial zero such as RAM `0` with Storage `256 GB` is rejected.
- Repeated rows with the same product identity are permitted after a warning and are totaled during comparison.

## Excel comparison

### Current Count vs Reference Sheet

The reference workbook must contain either a combined `MAKE` column or separate `Model`/optional `RAM`/`Storage` columns, plus `COLOR` and either `START` or `END` on the same header row. `START` is the preferred baseline; `END` is used when START is unavailable.

### Old Count vs Current Count

Use a workbook previously exported by this app or the desktop version. The importer reads the separate fields from its `Detailed Data` worksheet.

### Old Count vs Reference Sheet

Select both an older exported count workbook and the reference workbook. The app applies the same identity and totaling rules to the old count, then checks it against the reference baseline. This mode does not require entries in the active session.

## Data and backups

All sessions are stored in:

```text
data/inventory.db
```

Copy that file while the application is stopped to make a complete database backup. Excel exports provide an additional human-readable record.

Cycle-count exports can include `Inventory Count`, `Summary`, hidden `Detailed Data`, `Comparison Results`, `Issues`, hidden `Audit Log`, `Movement Log`, and `Count Attempts` worksheets. The application also writes operational messages to `data/inventory.log`.

The app binds only to `127.0.0.1`, so it is available only on the computer running it. Do not expose this development server directly to the public internet. A publicly hosted version should add user authentication, HTTPS, managed backups, and a production web server.

## Run tests

From the project folder:

```text
python -m unittest discover -s tests -v
```
