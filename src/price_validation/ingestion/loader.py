"""
ingestion/loader.py — read pricing template and supplier shipment DataFrames
for a given FY and selected months.

Column name maps
----------------
FEATURE_COLS_PT   : canonical name  -> pricing-template column name
FEATURE_COLS_SHP  : canonical name  -> supplier-shipment column name
"""
from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Optional
import re

import pandas as pd

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

# canonical key -> column name in pricing template
FEATURE_COLS_PT: dict[str, str] = {
    "HP/ODM Part#":      "HP/ODM Part#",
    "Color":             "Color",
    "Product":           "Product",
    "Size":              "Size",
    "ODM & Site":        "ODM (Regional Site)",
    "GTK Suppliers":     "GTK Suppliers",
    "Platforms/Project": "Platforms/Project",
}

# canonical key -> column name in supplier shipment
FEATURE_COLS_SHP: dict[str, str] = {
    "HP/ODM Part#":      "HP/ODM Part#",
    "Color":             "Color",
    "Product":           "Product",
    "Size":              "Size",
    "ODM & Site":        "ODM",
    "GTK Suppliers":     "GTK Suppliers",
    "Platforms/Project": "Platforms",
}

# How many years ahead a month might be relative to FY start (Aug previous year)
# We just need to match "Rebate <Month> <Year>" with a 4-digit year derived from FY
_REBATE_PT_RE = re.compile(
    r"^Rebate\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}$",
    re.IGNORECASE,
)

_UNIT_REBATE_SHP_RE = re.compile(
    r"^Unit\s+Rebate\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)$",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _round_rebate(val) -> Optional[float]:
    """Convert a cell value to a rounded float (2 dp) or None."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        d = Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return float(d)
    except Exception:
        return None


def _strip_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Strip whitespace from all column names."""
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _build_index(row: pd.Series, index_keys: list[str], feature_map: dict[str, str]) -> str:
    parts = []
    for key in index_keys:
        col = feature_map[key]
        val = str(row.get(col, "")).strip()
        parts.append(val)
    return "-".join(parts).replace(" ", "").upper()


# --------------------------------------------------------------------------- #
# Pricing Template loader
# --------------------------------------------------------------------------- #

def load_pricing_template(
    file_path: Path,
    fy: str,
    months: list[str],
    index_keys: list[str],
    supplier_name: str = "",
) -> pd.DataFrame:
    """
    Read the pricing template. The file contains a single sheet named after
    the FY (e.g. 'FY25'). Falls back to 'InputDevice' for backwards compatibility.
    Returns a wide DataFrame with feature columns + Rebate columns for selected months,
    plus an '__index__' column.
    """
    import openpyxl as _opx
    _wb = _opx.load_workbook(file_path, read_only=True, data_only=True)
    _sheets = _wb.sheetnames
    _wb.close()
    # Prefer FY-named sheet, fall back to InputDevice
    if f"FY{fy}" in _sheets:
        sheet_name = f"FY{fy}"
    elif "InputDevice" in _sheets:
        sheet_name = "InputDevice"
    else:
        sheet_name = _sheets[0]
    df = pd.read_excel(file_path, sheet_name=sheet_name, header=0, dtype=str)
    df = _strip_cols(df)

    # Filter rows belonging to this supplier (GTK Suppliers column)
    gtk_col = FEATURE_COLS_PT["GTK Suppliers"]
    if gtk_col in df.columns and supplier_name:
        df = df[df[gtk_col].str.strip().str.upper() == supplier_name.strip().upper()]
    df = df.reset_index(drop=True)

    feature_cols_needed = [FEATURE_COLS_PT[k] for k in FEATURE_COLS_PT]

    # Find rebate columns matching selected months
    # Column header format: "Rebate Jan 2025", "Rebate Feb 2026", …
    rebate_month_map: dict[str, str] = {}  # month abbrev (title) -> actual column name
    for col in df.columns:
        m = _REBATE_PT_RE.match(col)
        if m:
            month_abbrev = m.group(1).title()
            if month_abbrev in months:
                rebate_month_map[month_abbrev] = col

    keep_cols = [c for c in feature_cols_needed if c in df.columns]
    rebate_cols = [rebate_month_map[mo] for mo in months if mo in rebate_month_map]

    df = df[keep_cols + rebate_cols].copy()

    # Rename rebate cols to canonical "Rebate_<Month>"
    rename_map = {v: f"Rebate_{k}" for k, v in rebate_month_map.items()}
    df.rename(columns=rename_map, inplace=True)

    # Round rebate values
    for mo in months:
        col = f"Rebate_{mo}"
        if col in df.columns:
            df[col] = df[col].apply(_round_rebate)

    df["__index__"] = df.apply(
        lambda row: _build_index(row, index_keys, FEATURE_COLS_PT), axis=1
    )
    return df


# --------------------------------------------------------------------------- #
# Supplier Shipment loader
# --------------------------------------------------------------------------- #

def load_supplier_shipment(
    file_path: Path,
    fy: str,
    months: list[str],
    index_keys: list[str],
) -> pd.DataFrame:
    """
    Read the FY<fy> sheet from a supplier shipment file.
    The header row is row 2 (0-indexed row 1).
    Returns a wide DataFrame with feature columns + Rebate columns for selected months,
    plus an '__index__' column.
    """
    sheet_name = f"FY{fy}"
    df = pd.read_excel(file_path, sheet_name=sheet_name, header=1, dtype=str)
    df = _strip_cols(df)

    feature_cols_needed = [FEATURE_COLS_SHP[k] for k in FEATURE_COLS_SHP]

    # Find "Unit Rebate <Month>" columns
    unit_rebate_map: dict[str, str] = {}  # month abbrev (title) -> actual column name
    for col in df.columns:
        m = _UNIT_REBATE_SHP_RE.match(col)
        if m:
            month_abbrev = m.group(1).title()
            if month_abbrev in months:
                unit_rebate_map[month_abbrev] = col

    keep_feat = [c for c in feature_cols_needed if c in df.columns]
    rebate_cols = [unit_rebate_map[mo] for mo in months if mo in unit_rebate_map]

    df = df[keep_feat + rebate_cols].copy()

    # Drop rows where Platforms/Project is blank
    platform_col = FEATURE_COLS_SHP["Platforms/Project"]
    if platform_col in df.columns:
        df = df[df[platform_col].notna() & (df[platform_col].str.strip() != "")]

    # Rename to canonical
    rename_map = {v: f"Rebate_{k}" for k, v in unit_rebate_map.items()}
    df.rename(columns=rename_map, inplace=True)

    # Round rebate values
    for mo in months:
        col = f"Rebate_{mo}"
        if col in df.columns:
            df[col] = df[col].apply(_round_rebate)

    df["__index__"] = df.apply(
        lambda row: _build_index(row, index_keys, FEATURE_COLS_SHP), axis=1
    )
    df.reset_index(drop=True, inplace=True)
    return df
