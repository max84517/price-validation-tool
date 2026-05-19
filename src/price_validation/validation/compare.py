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


def _best_pt_row(
    pt_rows: list[pd.Series],
    shp_row: pd.Series,
    months: list[str],
) -> pd.Series:
    """
    Return the PT row with the fewest price differences against shp_row.
    When there is only one PT row this is identical to returning it directly
    (same behaviour as the old iloc[0] approach).
    Falls back to the first PT row on a tie so results are deterministic.
    """
    best_row = pt_rows[0]
    best_diffs = len(months) + 1

    for p_row in pt_rows:
        diffs = 0
        for month in months:
            col = f"Rebate_{month}"
            pv = p_row.get(col)
            sv = shp_row.get(col)
            pc = 0.0 if (pv is None or (isinstance(pv, float) and pd.isna(pv))) else float(pv)
            sc = 0.0 if (sv is None or (isinstance(sv, float) and pd.isna(sv))) else float(sv)
            if pc != sc:
                diffs += 1
        if diffs < best_diffs:
            best_diffs = diffs
            best_row = p_row
        if best_diffs == 0:
            break  # perfect match -- no need to look further

    return best_row


def _rebate_val(row: pd.Series, rebate_col: str) -> Optional[float]:
    """Return the rebate value or None if missing/NaN."""
    v = row.get(rebate_col)
    return None if (v is None or (isinstance(v, float) and pd.isna(v))) else v  # type: ignore[return-value]


def compare(
    df_pt: pd.DataFrame,
    df_shp: pd.DataFrame,
    months: list[str],
    supplier_name: str,
    allow_pt_only: bool = False,
    suppress_blank_warnings: bool = False,
) -> list[MismatchRecord]:
    """
    Compare df_pt (pricing template) and df_shp (supplier shipment) for the
    given months.  Both DataFrames must have '__index__' and 'Rebate_<Month>' columns.

    When the PT has multiple rows sharing the same index key (duplicates), the
    function picks the PT row whose prices best match the SHP row rather than
    blindly taking the first one.  The SHP side still uses its first row when
    duplicates exist (conservative -- avoids introducing spurious SHP-only
    mismatches from duplicate SHP entries).

    allow_pt_only: if True, skip records that exist only in the master table.
    Returns a list of MismatchRecord (only discrepancies).
    """
    records: list[MismatchRecord] = []

    pt_indexed  = df_pt.set_index("__index__")
    shp_indexed = df_shp.set_index("__index__")

    all_indices = set(pt_indexed.index) | set(shp_indexed.index)

    for idx in sorted(all_indices):
        in_pt  = idx in pt_indexed.index
        in_shp = idx in shp_indexed.index

        # Normalise PT to list[Series]; SHP always takes first row (iloc[0])
        if in_pt:
            raw = pt_indexed.loc[idx]
            pt_rows = [raw] if isinstance(raw, pd.Series) else [raw.iloc[i] for i in range(len(raw))]
        else:
            pt_rows = []

        if in_shp:
            raw = shp_indexed.loc[idx]
            shp_row = raw if isinstance(raw, pd.Series) else raw.iloc[0]
        else:
            shp_row = None  # type: ignore[assignment]

        feat = _feature_from_row(pt_rows[0], "pt") if pt_rows else _feature_from_row(shp_row, "shp")

        for month in months:
            rebate_col = f"Rebate_{month}"

            pt_val: Optional[float] = None
            shp_val: Optional[float] = None

            if not in_pt:
                # SHP-only
                shp_val = _rebate_val(shp_row, rebate_col)
                records.append(MismatchRecord(
                    month=month, index_value=idx,
                    exists_in_pt=False, exists_in_shp=True,
                    shp_rebate=shp_val,
                    comment="Exists in Supplier Shipment only (not in Master Table)",
                    **feat,
                ))
                continue

            if not in_shp:
                # PT-only
                if allow_pt_only:
                    continue
                pt_val = _rebate_val(pt_rows[0], rebate_col)
                records.append(MismatchRecord(
                    month=month, index_value=idx,
                    exists_in_pt=True, exists_in_shp=False,
                    pt_rebate=pt_val,
                    comment="Exists in Master Table only (not in Supplier Shipment)",
                    **feat,
                ))
                continue

            # Both exist -- pick the best-matching PT row for this SHP row
            p_row = _best_pt_row(pt_rows, shp_row, months)
            matched_feat = _feature_from_row(p_row, "pt")

            pt_val  = _rebate_val(p_row,   rebate_col)
            shp_val = _rebate_val(shp_row, rebate_col)

            pt_cmp  = 0.0 if pt_val  is None else float(pt_val)
            shp_cmp = 0.0 if shp_val is None else float(shp_val)
            pt_blank  = pt_val  is None
            shp_blank = shp_val is None

            if pt_cmp != shp_cmp:
                blank_notes = []
                if pt_blank:  blank_notes.append("Master Table cell is blank (treated as 0)")
                if shp_blank: blank_notes.append("Supplier Shipment cell is blank (treated as 0)")
                blank_suffix = " | " + "; ".join(blank_notes) if blank_notes else ""
                records.append(MismatchRecord(
                    month=month, index_value=idx,
                    exists_in_pt=True, exists_in_shp=True,
                    pt_rebate=pt_val, shp_rebate=shp_val,
                    comment=(
                        f"Price mismatch -- Master Table: {pt_cmp}, "
                        f"Supplier Shipment: {shp_cmp}{blank_suffix}"
                    ),
                    **matched_feat,
                ))
            elif pt_blank or shp_blank:
                blank_sides = []
                if pt_blank:  blank_sides.append("Master Table")
                if shp_blank: blank_sides.append("Supplier Shipment")
                records.append(MismatchRecord(
                    month=month, index_value=idx,
                    exists_in_pt=True, exists_in_shp=True,
                    pt_rebate=pt_val, shp_rebate=shp_val,
                    comment=(
                        f"{' and '.join(blank_sides)} cell(s) are blank (treated as 0). "
                        "Values match -- please verify and fill in the correct rebate if applicable."
                    ),
                    is_blank_warning=True,
                    **matched_feat,
                ))

    if suppress_blank_warnings:
        records = [r for r in records if not r.is_blank_warning]
    return records