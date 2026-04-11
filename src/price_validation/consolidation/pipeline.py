"""
consolidation/pipeline.py
=========================
Full pipeline: ingest raw → consolidate by segment → consolidate all
→ rebate only → write to Pricing_Template_InputDevices.xlsx InputDevice sheet.

Adapted from master-price-consolidate (github.com/max84517/master-price-consolidate).

Source folder structure expected from the user:
  nb_kb/
    Master price table_bNB/
      Master price table_bNB_<SUPPLIER>/   ← newest .xlsx is picked
      ...
    Master price table_cNB/
      Master price table_cNB_<SUPPLIER>/
      ...
  dt_kb/
    Master price table_DT/
      Master price table_DT_<SUPPLIER>/
      ...
  peripheral/
    Master price table_Peripheral/
      Master price table_Peripheral_<SUPPLIER>/
      ...
"""
from __future__ import annotations

import re
import tempfile
from datetime import date
from pathlib import Path
from typing import Callable, Optional

import openpyxl
from openpyxl import Workbook

from price_validation.config.paths import PRICING_TEMPLATE_DIR, MASTER_PRICE_SOURCE_DIR

# ── Constants ─────────────────────────────────────────────────────────────────

_FY_PATTERN = re.compile(r"^FY\d{2}$")
_REMOVE_PATTERNS = ("HP Cost", "ODM Cost")

# (segment_label, sub_path_under_source_root, folder_prefix)
_SEGMENT_DEFS: list[tuple[str, str, str, str]] = [
    ("bNB",         "nb_kb",        "Master price table_bNB",        "Master price table_bNB_"),
    ("cNB",         "nb_kb",        "Master price table_cNB",        "Master price table_cNB_"),
    ("DT",          "dt_kb",        "Master price table_DT",         "Master price table_DT_"),
    ("Peripheral",  "peripheral",   "Master price table_Peripheral", "Master price table_Peripheral_"),
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_fy_sheet(name: str) -> bool:
    return bool(_FY_PATTERN.match(name.strip()))


def _newest_xlsx(folder: Path) -> Optional[Path]:
    files = [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() == ".xlsx"]
    return max(files, key=lambda f: f.stat().st_mtime) if files else None


def _valid_col_indices(src_sheet) -> list[int]:
    """Header is on row 2; return indices of columns that have a non-None header."""
    rows = list(src_sheet.iter_rows(values_only=True, min_row=2, max_row=2))
    if not rows:
        return []
    return [i for i, h in enumerate(rows[0]) if h is not None]


def _copy_rows_segment(src_sheet, dest_sheet, first_supplier: bool, col_indices: list[int]) -> None:
    """
    Source layout: row 1 = title (skip), row 2 = headers (skip if not first), row 3+ = data.
    Normalise header cells: replace \\n with space.
    Only include columns in col_indices.
    """
    for row_idx, row in enumerate(src_sheet.iter_rows(values_only=True), start=1):
        if row_idx == 1:
            continue
        if row_idx == 2 and not first_supplier:
            continue
        extracted = [row[i] if i < len(row) else None for i in col_indices]
        if row_idx == 2:
            extracted = [v.replace("\n", " ") if isinstance(v, str) else v for v in extracted]
        if all(c is None for c in extracted):
            continue
        dest_sheet.append(extracted)


def _should_remove_col(header: object) -> bool:
    if not isinstance(header, str):
        return False
    h = header.replace("\n", " ")
    return any(pat.lower() in h.lower() for pat in _REMOVE_PATTERNS)


# ── Stage 1: Ingest ───────────────────────────────────────────────────────────

def _fix_gtk_suppliers(
    xlsx_path: Path,
    supplier_name: str,
    log: Callable[[str, str], None],
    seg_label: str,
) -> None:
    """
    Open *xlsx_path*, find the 'GTK Suppliers' column (header on row 2),
    and overwrite every data-row cell with *supplier_name*.
    This prevents mis-labelled or empty GTK Suppliers values from breaking
    the per-supplier split during validation.
    """
    # data_only=True: formula cells are loaded as their cached values (literals).
    # This prevents openpyxl from stripping cached values on save, which would
    # cause consolidation (also data_only=True) to read those cells as None.
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    for sheet_name in wb.sheetnames:
        if not _is_fy_sheet(sheet_name):
            continue
        ws = wb[sheet_name]
        # Header is on row 2; row 1 is a title row
        header_row = [c.value for c in ws[2]]
        gtk_col_idx = None
        for i, h in enumerate(header_row):
            if isinstance(h, str) and h.strip().lower() == "gtk suppliers":
                gtk_col_idx = i + 1  # openpyxl is 1-based
                break
        if gtk_col_idx is None:
            log(f"[{seg_label}] 'GTK Suppliers' column not found in {xlsx_path.name} sheet {sheet_name}", "WARN")
            continue
        for row in ws.iter_rows(min_row=3, max_row=ws.max_row):
            row[gtk_col_idx - 1].value = supplier_name
    wb.save(xlsx_path)
    wb.close()


def _ingest_to_dir(
    source_paths: dict[str, str],
    raw_dir: Path,
    log: Callable[[str, str], None],
) -> dict[str, list[Path]]:
    """
    Copy newest .xlsx from each supplier sub-folder into raw_dir/<segment>/.
    Returns {segment_label: [list of copied paths]}.
    """
    result: dict[str, list[Path]] = {}

    for seg_label, src_key, master_sub, prefix in _SEGMENT_DEFS:
        master_dir = Path(source_paths[src_key]) / master_sub
        if not master_dir.exists():
            log(f"[{seg_label}] Folder not found: {master_dir}", "WARN")
            result[seg_label] = []
            continue

        seg_raw_dir = raw_dir / seg_label
        seg_raw_dir.mkdir(parents=True, exist_ok=True)
        copied: list[Path] = []

        matched = sorted(d for d in master_dir.iterdir() if d.is_dir() and d.name.startswith(prefix))
        if not matched:
            log(f"[{seg_label}] No sub-folders matching '{prefix}*' in {master_dir}", "WARN")
            result[seg_label] = []
            continue

        for supplier_dir in matched:
            latest = _newest_xlsx(supplier_dir)
            if latest is None:
                log(f"[{seg_label}] No .xlsx in {supplier_dir.name}", "WARN")
                continue
            short = supplier_dir.name.replace("Master price table_", "", 1)
            dest = seg_raw_dir / f"{short}.xlsx"
            import shutil
            shutil.copy2(latest, dest)
            # ── Overwrite GTK Suppliers column with supplier name from filename ──
            # short is like "DT_CHICONY" or "bNB_LITEON"; supplier = part after first "_"
            supplier_name_from_file = short.split("_", 1)[1] if "_" in short else short
            _fix_gtk_suppliers(dest, supplier_name_from_file, log, seg_label)
            # ── Copy to master price source folder (keep original filename) ──
            master_src_seg_dir = MASTER_PRICE_SOURCE_DIR / seg_label
            shutil.copy2(dest, master_src_seg_dir / latest.name)
            copied.append(dest)
            log(f"[{seg_label}] Ingested: {supplier_dir.name}/{latest.name}", "INFO")

        result[seg_label] = copied

    return result


# ── Stage 2: Consolidate by segment ──────────────────────────────────────────

def _consolidate_segment(
    seg_label: str,
    raw_folder: Path,
    out_dir: Path,
    log: Callable[[str, str], None],
) -> Optional[Path]:
    xlsx_files = sorted(raw_folder.glob("*.xlsx"))
    if not xlsx_files:
        log(f"[{seg_label}] No raw files to consolidate", "WARN")
        return None

    today = date.today().strftime("%Y%m%d")
    out_path = out_dir / f"Consolidated_{seg_label}_{today}.xlsx"

    fy_order: list[str] = []
    fy_sources: dict[str, list[tuple[Path, str]]] = {}

    for xlsx_path in xlsx_files:
        wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
        for sheet_name in wb.sheetnames:
            if not _is_fy_sheet(sheet_name):
                continue
            fy = sheet_name.strip()
            if fy not in fy_sources:
                fy_order.append(fy)
                fy_sources[fy] = []
            fy_sources[fy].append((xlsx_path, sheet_name))
        wb.close()

    if not fy_order:
        log(f"[{seg_label}] No FY sheets found", "WARN")
        return None

    fy_order.sort()
    out_wb = Workbook()
    out_wb.remove(out_wb.active)

    for fy in fy_order:
        out_sheet = out_wb.create_sheet(title=fy)
        first = True
        col_indices: list[int] = []
        for xlsx_path, sheet_name in fy_sources[fy]:
            src_wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
            src_sheet = src_wb[sheet_name]
            if first:
                col_indices = _valid_col_indices(src_sheet)
            _copy_rows_segment(src_sheet, out_sheet, first_supplier=first, col_indices=col_indices)
            src_wb.close()
            first = False
        log(f"[{seg_label}] {fy}: {len(fy_sources[fy])} supplier(s), {out_sheet.max_row} rows", "INFO")

    out_wb.save(out_path)
    return out_path


# ── Stage 3: Consolidate all segments ────────────────────────────────────────

def _consolidate_all(
    segment_files: list[Path],
    out_dir: Path,
    log: Callable[[str, str], None],
) -> Path:
    """Stack segment files by FY sheet. Header is row 1 in segment output."""
    fy_order: list[str] = []
    fy_sources: dict[str, list[tuple[Path, str]]] = {}

    for src_path in segment_files:
        wb = openpyxl.load_workbook(src_path, read_only=True, data_only=True)
        for sheet_name in wb.sheetnames:
            if sheet_name not in fy_sources:
                fy_order.append(sheet_name)
                fy_sources[sheet_name] = []
            fy_sources[sheet_name].append((src_path, sheet_name))
        wb.close()

    fy_order.sort()
    out_wb = Workbook()
    out_wb.remove(out_wb.active)

    for fy in fy_order:
        out_sheet = out_wb.create_sheet(title=fy)
        first = True
        for src_path, sheet_name in fy_sources[fy]:
            src_wb = openpyxl.load_workbook(src_path, read_only=True, data_only=True)
            src_sheet = src_wb[sheet_name]
            for row_idx, row in enumerate(src_sheet.iter_rows(values_only=True), start=1):
                if row_idx == 1 and not first:
                    continue
                if all(c is None for c in row):
                    continue
                out_sheet.append(list(row))
            src_wb.close()
            first = False
        log(f"[All] {fy}: {len(fy_sources[fy])} segment(s), {out_sheet.max_row} rows", "INFO")

    today = date.today().strftime("%Y%m%d")
    out_path = out_dir / f"consolidate_all_{today}.xlsx"
    out_wb.save(out_path)
    return out_path


# ── Stage 4: Rebate only ─────────────────────────────────────────────────────

def _rebate_only(all_path: Path, out_dir: Path) -> Path:
    src_wb = openpyxl.load_workbook(all_path, read_only=True, data_only=True)
    out_wb = Workbook()
    out_wb.remove(out_wb.active)

    for sheet_name in src_wb.sheetnames:
        src_sheet = src_wb[sheet_name]
        out_sheet = out_wb.create_sheet(title=sheet_name)
        header_row = next(src_sheet.iter_rows(values_only=True), ())
        keep = [i for i, h in enumerate(header_row) if not _should_remove_col(h)]
        for row_idx, row in enumerate(src_sheet.iter_rows(values_only=True), start=1):
            extracted = [row[i] if i < len(row) else None for i in keep]
            if row_idx > 1 and all(c is None for c in extracted):
                continue
            out_sheet.append(extracted)

    src_wb.close()
    out_path = out_dir / "rebate_only.xlsx"
    out_wb.save(out_path)
    return out_path


# ── Stage 5: Write to Pricing Template ───────────────────────────────────────

def _write_pricing_template(rebate_path: Path, fy_sheet: str) -> Path:
    """
    Overwrite the InputDevice sheet in PRICING_TEMPLATE_DIR/Pricing_Template_InputDevices.xlsx.
    Creates the file if it doesn't exist yet.
    """
    PRICING_TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    template_file = PRICING_TEMPLATE_DIR / "Pricing_Template_InputDevices.xlsx"

    src_wb = openpyxl.load_workbook(rebate_path, read_only=True, data_only=True)
    if fy_sheet not in src_wb.sheetnames:
        src_wb.close()
        raise ValueError(f"Sheet '{fy_sheet}' not found in rebate workbook")
    src_sheet = src_wb[fy_sheet]

    if template_file.exists():
        tmpl_wb = openpyxl.load_workbook(template_file)
    else:
        tmpl_wb = Workbook()
        tmpl_wb.remove(tmpl_wb.active)

    if "InputDevice" not in tmpl_wb.sheetnames:
        dest_sheet = tmpl_wb.create_sheet("InputDevice")
    else:
        dest_sheet = tmpl_wb["InputDevice"]
        if dest_sheet.max_row:
            dest_sheet.delete_rows(1, dest_sheet.max_row)

    for row in src_sheet.iter_rows(values_only=True):
        if all(c is None for c in row):
            continue
        dest_sheet.append(list(row))

    src_wb.close()
    tmpl_wb.save(template_file)
    return template_file


# ── Public API ────────────────────────────────────────────────────────────────

def get_available_fy_sheets(source_paths: dict[str, str], log: Callable[[str, str], None]) -> list[str]:
    """
    Run ingest + segment consolidation + consolidate_all in a temp dir
    and return the list of available FY sheet names.
    Stores the temp dir path internally so run_full_pipeline can reuse it.
    """
    # We do a dry run to discover sheets; the results are cached in a module-level temp dir
    global _cached_rebate_path, _cached_tmpdir
    _cleanup_cache()
    _cached_tmpdir = tempfile.mkdtemp(prefix="pvtool_build_")
    tmp = Path(_cached_tmpdir)

    _cached_rebate_path = _run_stages(source_paths, tmp, log)
    if _cached_rebate_path is None:
        return []

    wb = openpyxl.load_workbook(_cached_rebate_path, read_only=True, data_only=True)
    sheets = list(wb.sheetnames)
    wb.close()
    return sheets


def run_full_pipeline(
    source_paths: dict[str, str],
    fy_sheet: str,
    log: Callable[[str, str], None],
) -> Path:
    """
    Run the full pipeline and write the chosen FY sheet to the pricing template.
    If get_available_fy_sheets was called first and the source paths are the same,
    reuses the cached rebate workbook. Otherwise re-runs from scratch.
    """
    global _cached_rebate_path, _cached_tmpdir
    if _cached_rebate_path is None or not _cached_rebate_path.exists():
        _cleanup_cache()
        _cached_tmpdir = tempfile.mkdtemp(prefix="pvtool_build_")
        tmp = Path(_cached_tmpdir)
        _cached_rebate_path = _run_stages(source_paths, tmp, log)

    if _cached_rebate_path is None:
        raise RuntimeError("Pipeline failed — check log for details.")

    out = _write_pricing_template(_cached_rebate_path, fy_sheet)
    log(f"Pricing Template written: {out}", "SUCCESS")
    _cleanup_cache()
    return out


def _run_stages(
    source_paths: dict[str, str],
    tmp: Path,
    log: Callable[[str, str], None],
) -> Optional[Path]:
    """Run ingest → segment → all → rebate_only; return rebate path or None on failure."""
    import shutil as _shutil

    # ── Clear master price source folders before each run ──
    _MASTER_SEGS = ("bNB", "cNB", "DT", "Peripheral")
    for seg in _MASTER_SEGS:
        seg_dir_ms = MASTER_PRICE_SOURCE_DIR / seg
        seg_dir_ms.mkdir(parents=True, exist_ok=True)
        for f in seg_dir_ms.glob("*.xlsx"):
            f.unlink(missing_ok=True)

    raw_dir = tmp / "raw"
    seg_dir = tmp / "segment"
    all_dir = tmp / "all"
    rebate_dir = tmp / "rebate"

    for d in (raw_dir, seg_dir, all_dir, rebate_dir):
        d.mkdir(parents=True, exist_ok=True)

    log("Ingesting raw files…", "INFO")
    raw_map = _ingest_to_dir(source_paths, raw_dir, log)

    segment_files: list[Path] = []
    for seg_label, src_key, _, _ in _SEGMENT_DEFS:
        seg_raw = raw_dir / seg_label
        if not seg_raw.exists() or not any(seg_raw.glob("*.xlsx")):
            log(f"[{seg_label}] Skipped (no raw files)", "WARN")
            continue
        log(f"Consolidating segment {seg_label}…", "INFO")
        seg_out = _consolidate_segment(seg_label, seg_raw, seg_dir, log)
        if seg_out:
            segment_files.append(seg_out)

    if not segment_files:
        log("No segment files produced — aborting.", "ERROR")
        return None

    log("Consolidating all segments…", "INFO")
    all_path = _consolidate_all(segment_files, all_dir, log)
    log("Building rebate-only workbook…", "INFO")
    rebate_path = _rebate_only(all_path, rebate_dir)
    return rebate_path


# ── Cache state ───────────────────────────────────────────────────────────────

_cached_rebate_path: Optional[Path] = None
_cached_tmpdir: Optional[str] = None


def _cleanup_cache() -> None:
    global _cached_rebate_path, _cached_tmpdir
    if _cached_tmpdir:
        import shutil
        try:
            shutil.rmtree(_cached_tmpdir, ignore_errors=True)
        except Exception:
            pass
    _cached_rebate_path = None
    _cached_tmpdir = None
