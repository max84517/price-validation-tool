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


def _match_shp_to_pt(
    pt_rows: list[pd.Series],
    shp_rows: list[pd.Series],
    months: list[str],
) -> tuple[list[tuple[pd.Series, pd.Series]], list[pd.Series], list[pd.Series]]:
    """
    Greedily match each SHP row to the best-matching PT row (fewest price
    differences across all selected months).  Each PT row is consumed at most
    once, so a PT duplicate is only paired with one SHP row.

    Returns:
        matched   – list of (pt_row, shp_row) pairs
        extra_pt  – PT rows not consumed by any SHP row  (→ PT-only)
        extra_shp – SHP rows left over when PT rows run out (→ SHP-only)
    """
    available: list[int] = list(range(len(pt_rows)))
    matched: list[tuple[pd.Series, pd.Series]] = []
    extra_shp: list[pd.Series] = []

    for s_row in shp_rows:
        best_pi: int | None = None
        best_diffs: int = len(months) + 1  # worse than any real score

        for pi in available:
            p_row = pt_rows[pi]
            diffs = 0
            for month in months:
                col = f"Rebate_{month}"
                pv = p_row.get(col)
                sv = s_row.get(col)
                pc = 0.0 if (pv is None or (isinstance(pv, float) and pd.isna(pv))) else float(pv)
                sc = 0.0 if (sv is None or (isinstance(sv, float) and pd.isna(sv))) else float(sv)
                if pc != sc:
                    diffs += 1
            if diffs < best_diffs:
                best_diffs = diffs
                best_pi = pi
            if best_diffs == 0:
                break  # perfect match – no need to check further

        if best_pi is not None:
            available.remove(best_pi)
            matched.append((pt_rows[best_pi], s_row))
        else:
            extra_shp.append(s_row)  # all PT rows already consumed

    extra_pt = [pt_rows[i] for i in available]
    return matched, extra_pt, extra_shp


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

    When multiple PT or SHP rows share the same index key (duplicates), the
    function uses a best-match greedy algorithm: each SHP row is paired with
    the PT row that has the fewest price differences across all selected months.
    This avoids false mismatches caused by picking an arbitrary duplicate.

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

        # Normalise to list[Series] so duplicates are handled uniformly
        if in_pt:
            raw = pt_indexed.loc[idx]
            pt_rows = [raw] if isinstance(raw, pd.Series) else [raw.iloc[i] for i in range(len(raw))]
        else:
            pt_rows = []

        if in_shp:
            raw = shp_indexed.loc[idx]
            shp_rows = [raw] if isinstance(raw, pd.Series) else [raw.iloc[i] for i in range(len(raw))]
        else:
            shp_rows = []

        # ── SHP-only: index not in PT at all ─────────────────────────────────
        if not in_pt:
            feat = _feature_from_row(shp_rows[0], "shp")
            for month in months:
                rebate_col = f"Rebate_{month}"
                records.append(MismatchRecord(
                    month=month, index_value=idx,
                    exists_in_pt=False, exists_in_shp=True,
                    shp_rebate=_rebate_val(shp_rows[0], rebate_col),
                    comment="Exists in Supplier Shipment only (not in Master Table)",
                    **feat,
                ))
            continue

        # ── PT-only: index not in SHP at all ─────────────────────────────────
        if not in_shp:
            if allow_pt_only:
                continue
            feat = _feature_from_row(pt_rows[0], "pt")
            for month in months:
                rebate_col = f"Rebate_{month}"
                records.append(MismatchRecord(
                    month=month, index_value=idx,
                    exists_in_pt=True, exists_in_shp=False,
                    pt_rebate=_rebate_val(pt_rows[0], rebate_col),
                    comment="Exists in Master Table only (not in Supplier Shipment)",
                    **feat,
                ))
            continue

        # ── Both exist: pair SHP rows to best-matching PT rows ───────────────
        matched, extra_pt, extra_shp = _match_shp_to_pt(pt_rows, shp_rows, months)

        # Compare each matched pair month by month
        for p_row, s_row in matched:
            feat = _feature_from_row(p_row, "pt")
            for month in months:
                rebate_col = f"Rebate_{month}"
                pt_val  = _rebate_val(p_row, rebate_col)
                shp_val = _rebate_val(s_row, rebate_col)

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
                            f"Price mismatch — Master Table: {pt_cmp}, "
                            f"Supplier Shipment: {shp_cmp}{blank_suffix}"
                        ),
                        **feat,
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
                            "Values match — please verify and fill in the correct rebate if applicable."
                        ),
                        is_blank_warning=True,
                        **feat,
                    ))

        # Extra SHP rows (more SHP rows than PT rows for this index) → SHP-only
        for s_row in extra_shp:
            feat = _feature_from_row(s_row, "shp")
            for month in months:
                rebate_col = f"Rebate_{month}"
                records.append(MismatchRecord(
                    month=month, index_value=idx,
                    exists_in_pt=False, exists_in_shp=True,
                    shp_rebate=_rebate_val(s_row, rebate_col),
                    comment="Exists in Supplier Shipment only (all Master Table entries for this index already matched)",
                    **feat,
                ))

        # Extra PT rows (more PT rows than SHP rows for this index) → PT-only
        if not allow_pt_only:
            for p_row in extra_pt:
                feat = _feature_from_row(p_row, "pt")
                for month in months:
                    rebate_col = f"Rebate_{month}"
                    records.append(MismatchRecord(
                        month=month, index_value=idx,
                        exists_in_pt=True, exists_in_shp=False,
                        pt_rebate=_rebate_val(p_row, rebate_col),
                        comment="Exists in Master Table only (not matched to any Supplier Shipment entry)",
                        **feat,
                    ))

    if suppress_blank_warnings:
        records = [r for r in records if not r.is_blank_warning]
    return records
