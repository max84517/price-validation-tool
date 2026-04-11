# Price Validation Tool

A desktop application for validating rebate prices between the **Master Pricing Template** (InputDevice sheet) and **Supplier Shipment** files.

Built with Python, Tkinter dark-mode UI, pandas, and openpyxl.

---

## Download (No Python Required)

Download the latest release from the [Releases page](https://github.com/max84517/price-validation-tool/releases/latest).

1. Download `PriceValidation-v1.1.6.zip`
2. Extract the zip to any folder (keep all files together)
3. Run **`PriceValidation.exe`**

> The `_internal/` folder next to the exe must stay in the same directory.

---

## Features

- **Supplier management**  Add / remove suppliers with name and shipment folder path. Configuration is persisted to `config.json` and reloaded automatically on next launch.
- **Fetch Data**  Finds the newest Excel file in each supplier's shipment folder, copies it into `data/supplier_shipments/<supplier>/`, and shows the filename in the UI.
- **Selective processing**  Per-supplier checkboxes + Select All toggle. Only checked suppliers are fetched or validated.
- **Validate**  Compares the Master Pricing Template against each supplier's shipment for a chosen FY and set of months.
- **Mismatch report**  Generates a colour-coded Excel workbook per supplier (one sheet per month) saved under `data/report/<timestamp>/`.
- **Clear Files**  One-click removal of cached shipment files for selected suppliers to keep the project folder clean.
- **Build Pricing Template**  Consolidate raw master price table files (NB KB / DT KB / Peripheral) into a single `Pricing_Template_InputDevices.xlsx` saved in `data/pricing_template/`. Select the FY sheet to write into the `InputDevice` sheet.
- **Open Report**  Opens the most recent report folder (`data/report/<latest timestamp>/`) directly in Windows Explorer.
- **Log panel**  Timestamped, colour-coded live log (INFO / SUCCESS / WARN / ERROR) directly in the UI.

---

## Project Structure

```
price-validation-tool/
 data/
    pricing_template/         place Pricing_Template_InputDevices.xlsx here
    supplier_shipments/       auto-populated by Fetch Data
       <SupplierName>/
    master price source/      source Excel files from last Build PT run
       bNB/
       cNB/
       DT/
       Peripheral/
    report/                   validation reports saved here
        <YYYY-MM-DD HH-MM>/
            Report_<Supplier>_FY<YY>.xlsx
 src/
    price_validation/
        main.py               entry point
        config/
           paths.py          BASE_DIR / DATA_DIR paths (dev + frozen)
           settings.py       load / save config.json
        ingestion/
           fetch.py          copy newest Excel from supplier folder
           loader.py         read pricing template & shipment into DataFrames
        validation/
           compare.py        produce MismatchRecord list
        report/
           writer.py         write Excel report workbook
        consolidation/
           pipeline.py       Build PT consolidation pipeline
        ui/
            app.py            Tkinter dark-mode application
 config.json                   auto-generated; stores suppliers & folder paths
 pyproject.toml
 README.md
```

---

## Installation

### Option A  Pre-built exe (recommended)

See **[Download](#download-no-python-required)** above. No Python needed.

### Option B  Run from source

**Requirements:** Python 3.12+, [Poetry](https://python-poetry.org/) 1.8+

```bash
git clone https://github.com/max84517/price-validation-tool.git
cd price-validation-tool
poetry install
poetry run price-validation
```

### Option C  Build exe yourself

```bash
poetry install
build_exe.bat        # Windows only; output: dist\PriceValidation\PriceValidation.exe
```

---

## Usage Guide

### 1. Build / Update the Pricing Template *(optional  skip if you already have one)*

Set the three source folders in the **Build Pricing Template** panel:

| Field | Source folder contains |
|---|---|
| **NB KB** | `Master price table_bNB_*/` and `Master price table_cNB_*/` sub-folders |
| **DT KB** | `Master price table_DT_*/` sub-folders |
| **Peripheral** | `Master price table_Peripheral_*/` sub-folders |

Click **Build PT**. The tool will:
1. Copy the newest `.xlsx` from each supplier sub-folder and fix the `GTK Suppliers` column from the filename.
2. Consolidate by segment, then merge all segments.
3. Remove `HP Cost` / `ODM Cost` columns.
4. Ask which FY sheet to write, then overwrite the `InputDevice` sheet in `data/pricing_template/Pricing_Template_InputDevices.xlsx` (created automatically if it doesn't exist).

Folder settings are saved to `config.json` and reloaded on next launch.

### 2. Set the Pricing Template *(already handled by Build PT)*

The tool always reads from **`data/pricing_template/Pricing_Template_InputDevices.xlsx`**, sheet **`InputDevice`**. No manual file selection needed.

### 3. Add Suppliers

Click **Add Supplier**, enter:
- **Supplier Name**  must match the value in the `GTK Suppliers` column of the pricing template exactly (case-insensitive).
- **Shipment Folder**  folder that contains the supplier's shipment Excel files.

The supplier is saved to `config.json` immediately.

### 4. Fetch Data

Check the suppliers you want, then click **Fetch Data**.
The tool picks the **most recently modified** Excel file from each shipment folder and copies it to `data/supplier_shipments/<name>/`.
The filename appears in the *Latest File* column.

### 5. Validate

Click **Validate** to open the configuration dialog:

| Field | Description |
|---|---|
| **Fiscal Year** | Exactly 2 digits (e.g. `25`). Used to find the `FY25` sheet in the shipment file. |
| **Months** | Select one or more months (Jan  Nov). |
| **Cross-check Index** | Select  2 fields to build a composite key used for matching rows between both files. Fields are joined with `-`, spaces removed, uppercased. |
| **Allow: Master Table has entry but Supplier Shipment doesn't** | Tick to suppress reporting of items that exist in the master table but are absent from the shipment. |

The tool then:
1. Loads and filters the `InputDevice` sheet to rows where `GTK Suppliers` matches the supplier name.
2. Loads the `FY<YY>` sheet from the supplier's shipment file (header on row 2).
3. Drops shipment rows with a blank `Platforms` column.
4. Builds the composite index on both sides.
5. Compares rebate values for each selected month. Blank cells are treated as `0`  a warning record is emitted if both sides resolve to the same value via this substitution.
6. Generates a report workbook.

### 6. Report Format

Each report workbook contains one sheet per selected month.

| Condition | Row colour | Comment |
|---|---|---|
| Blank cell(s), values match after treating as 0 | Blue | "Master Table and/or Supplier Shipment cell(s) are blank (treated as 0). Values match  please verify..." |
| Only in Master Table | Orange | "Exists in Master Table only (not in Supplier Shipment)" |
| Only in Supplier Shipment | Orange | "Exists in Supplier Shipment only (not in Master Table)" |
| Price mismatch | Red | "Price mismatch  Master Table: X, Supplier Shipment: Y" |
| No mismatches | Green | "No mismatches found for this month." |

Columns: `HP/ODM Part#`, `Color`, `Product`, `Size`, `ODM & Site`, `GTK Suppliers`, `Platforms/Project`, `Master Table Rebate`, `Supplier Rebate`, `Comment`.

---

## Data Format Notes

### Pricing Template (`InputDevice` sheet)

- Header on **row 1**.
- Rebate columns follow the pattern `Rebate <Month> <Year>` (e.g. `Rebate Jan 2025`).
- The tool reads all 12 rebate columns but only processes the months you select.

### Supplier Shipment (`FY<YY>` sheet)

- Header on **row 2** (row 1 is ignored).
- Rebate columns follow the pattern `Unit Rebate <Month>` (e.g. `Unit Rebate Jan`).
- Rows with a blank `Platforms` column are dropped automatically.

### Cross-check Index field mapping

| Label | Pricing Template column | Shipment column |
|---|---|---|
| HP/ODM Part# | HP/ODM Part# | HP/ODM Part# |
| Color | Color | Color |
| Product | Product | Product |
| Size | Size | Size |
| ODM & Site | ODM (Regional Site) | ODM |
| GTK Suppliers | GTK Suppliers | GTK Suppliers |
| Platforms/Project | Platforms/Project | Platforms |

---

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| pandas | ^2.2 | DataFrame manipulation |
| openpyxl | ^3.1.5 | Excel read / write |
| tkinter | stdlib | UI (included with Python) |

---

## Changelog

### v1.1.6
- Fixed: When validating multiple suppliers, all reports are now saved into the same timestamped folder even if the run spans across a minute boundary.

### v1.1.5
- UI: Supplier list rebuilt with a shared grid layout — Supplier Name, Shipment Folder, and Latest File columns are now pixel-aligned under their headers.
- UI: Shipment Folder column is now a scrollable text field (left/right drag to see full path).
- UI: Latest File column now uses a plain label (same style as Shipment Folder), no more text-box appearance.
- UI: Added **Open Report** button in the toolbar — opens the most recent report folder in Windows Explorer.

### v1.1.4
- Fixed: Rebate cells with formula values in source Excel were appearing blank after Build PT consolidation. Root cause: openpyxl was stripping formula cached values when saving during GTK Suppliers fix step. Now loads with `data_only=True` to preserve all cell values.

### v1.1.3
- Fixed: Master price source folder now preserves the original Excel filename instead of the renamed copy.

### v1.1.2
- Added `data/master price source/` folder (bNB / cNB / DT / Peripheral). Each Build PT run clears and repopulates these folders with the ingested source files.

### v1.1.1
- Fixed: `None` values in Rebate cells are now treated as `0` during comparison.
- Fixed: Blank cells that resolve to the same value after `None→0` treatment are now reported as blue warning rows.
- Fixed: GTK Suppliers column is now correctly populated from the supplier filename during Build PT.
