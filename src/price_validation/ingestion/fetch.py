"""
ingestion/fetch.py — find the newest Excel in a supplier folder and copy it
into data/supplier_shipments/<supplier_name>/.
"""
from __future__ import annotations
import shutil
from pathlib import Path
from typing import Optional

from price_validation.config.paths import SUPPLIER_SHIPMENTS_DIR


_EXCEL_SUFFIXES = {".xlsx", ".xlsm", ".xls"}


def _newest_excel(folder: Path) -> Optional[Path]:
    """Return the most recently modified Excel file in *folder* (non-recursive)."""
    candidates = [
        f for f in folder.iterdir()
        if f.is_file() and f.suffix.lower() in _EXCEL_SUFFIXES
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda f: f.stat().st_mtime)


def fetch_supplier(supplier_name: str, shipment_folder: str) -> Optional[Path]:
    """
    Find the newest Excel in *shipment_folder*, copy it to
    data/supplier_shipments/<supplier_name>/ and return the destination path.
    Returns None if no Excel is found.
    """
    src_folder = Path(shipment_folder)
    newest = _newest_excel(src_folder)
    if newest is None:
        return None

    dest_dir = SUPPLIER_SHIPMENTS_DIR / supplier_name
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / newest.name
    shutil.copy2(newest, dest)
    return dest
