"""
validation/compare.py — compare pricing template vs supplier shipment DataFrames.

Returns per-month mismatch records used by the report generator.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from price_validation.ingestion.loader import FEATURE_COLS_PT, FEATURE_COLS_SHP


@dataclass
class MismatchRecord:
    """One row of discrepancy for a single month."""
    month: str
    index_value: str

    # Feature values (from PT side if available, else SHP side)
    hp_odm_part: str = ""
    color: str = ""
    product: str = ""
    size: str = ""
    odm_site: str = ""
    gtk_suppliers: str = ""
    platforms: str = ""

    exists_in_pt: bool = True
    exists_in_shp: bool = True
    pt_rebate: Optional[float] = None
    shp_rebate: Optional[float] = None
    comment: str = ""
    is_blank_warning: bool = False  # True when values match (both 0) but one cell was blank


def _feature_from_row(row: pd.Series, source: str) -> dict:
    """Extract the 7 feature values from a DataFrame row."""
    if source == "pt":
        m = FEATURE_COLS_PT
    else:
        m = FEATURE_COLS_SHP

    def _get(key: str) -> str:
        col = m.get(key, key)
        val = row.get(col, "")
        return "" if pd.isna(val) else str(val).strip()

    return {
        "hp_odm_part": _get("HP/ODM Part#"),
        "color":        _get("Color"),
        "product":      _get("Product"),
        "size":         _get("Size"),
        "odm_site":     _get("ODM & Site"),
        "gtk_suppliers":_get("GTK Suppliers"),
        "platforms":    _get("Platforms/Project"),
    }


def compare(
    df_pt: pd.DataFrame,
    df_shp: pd.DataFrame,
    months: list[str],
    supplier_name: str,
    allow_pt_only: bool = False,
) -> list[MismatchRecord]:
    """
    Compare df_pt (pricing template) and df_shp (supplier shipment) for the
    given months.  Both DataFrames must have '__index__' and 'Rebate_<Month>' columns.

    allow_pt_only: if True, skip records that exist only in the master table.
    Returns a list of MismatchRecord (only discrepancies).
    """
    records: list[MismatchRecord] = []

    pt_indexed = df_pt.set_index("__index__")
    shp_indexed = df_shp.set_index("__index__")

    all_indices = set(pt_indexed.index) | set(shp_indexed.index)

    for idx in sorted(all_indices):
        in_pt = idx in pt_indexed.index
        in_shp = idx in shp_indexed.index

        pt_row = pt_indexed.loc[idx] if in_pt else None
        shp_row = shp_indexed.loc[idx] if in_shp else None

        # Get the first occurrence if there are duplicates
        if isinstance(pt_row, pd.DataFrame):
            pt_row = pt_row.iloc[0]
        if isinstance(shp_row, pd.DataFrame):
            shp_row = shp_row.iloc[0]

        feat = _feature_from_row(pt_row, "pt") if in_pt else _feature_from_row(shp_row, "shp")

        for month in months:
            rebate_col = f"Rebate_{month}"

            pt_val: Optional[float] = None
            shp_val: Optional[float] = None

            if in_pt and rebate_col in pt_indexed.columns:
                v = pt_row.get(rebate_col)
                pt_val = None if (v is None or (isinstance(v, float) and pd.isna(v))) else v  # type: ignore[arg-type]

            if in_shp and rebate_col in shp_indexed.columns:
                v = shp_row.get(rebate_col)
                shp_val = None if (v is None or (isinstance(v, float) and pd.isna(v))) else v  # type: ignore[arg-type]

            # Treat None as 0 for comparison
            pt_cmp  = 0.0 if pt_val  is None else pt_val
            shp_cmp = 0.0 if shp_val is None else shp_val
            pt_blank  = (pt_val  is None) and in_pt
            shp_blank = (shp_val is None) and in_shp

            if not in_pt:
                comment = "Exists in Supplier Shipment only (not in Master Table)"
                rec = MismatchRecord(
                    month=month, index_value=idx,
                    exists_in_pt=False, exists_in_shp=True,
                    shp_rebate=shp_val, comment=comment, **feat
                )
                records.append(rec)
            elif not in_shp:
                if allow_pt_only:
                    continue
                comment = "Exists in Master Table only (not in Supplier Shipment)"
                rec = MismatchRecord(
                    month=month, index_value=idx,
                    exists_in_pt=True, exists_in_shp=False,
                    pt_rebate=pt_val, comment=comment, **feat
                )
                records.append(rec)
            elif pt_cmp != shp_cmp:
                # Build blank-cell notes for mismatch comment
                blank_notes = []
                if pt_blank:
                    blank_notes.append("Master Table cell is blank (treated as 0)")
                if shp_blank:
                    blank_notes.append("Supplier Shipment cell is blank (treated as 0)")
                blank_suffix = " | " + "; ".join(blank_notes) if blank_notes else ""
                comment = (
                    f"Price mismatch — Master Table: {pt_cmp}, "
                    f"Supplier Shipment: {shp_cmp}{blank_suffix}"
                )
                rec = MismatchRecord(
                    month=month, index_value=idx,
                    exists_in_pt=True, exists_in_shp=True,
                    pt_rebate=pt_val, shp_rebate=shp_val,
                    comment=comment, **feat
                )
                records.append(rec)
            elif pt_blank or shp_blank:
                # Values match (both 0) but at least one cell is blank — emit a warning
                blank_sides = []
                if pt_blank:
                    blank_sides.append("Master Table")
                if shp_blank:
                    blank_sides.append("Supplier Shipment")
                comment = (
                    f"{' and '.join(blank_sides)} cell(s) are blank (treated as 0). "
                    "Values match — please verify and fill in the correct rebate if applicable."
                )
                rec = MismatchRecord(
                    month=month, index_value=idx,
                    exists_in_pt=True, exists_in_shp=True,
                    pt_rebate=pt_val, shp_rebate=shp_val,
                    comment=comment, is_blank_warning=True, **feat
                )
                records.append(rec)

    return records
