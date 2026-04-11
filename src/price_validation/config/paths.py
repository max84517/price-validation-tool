"""
config/paths.py — resolve base data folder (dev vs frozen exe)
"""
from __future__ import annotations
import sys
from pathlib import Path


def get_base_dir() -> Path:
    """Return the project root / base directory regardless of execution context."""
    if getattr(sys, "frozen", False):
        # PyInstaller onedir: exe lives next to _internal/
        return Path(sys.executable).parent
    # Running from source: go up from src/price_validation/config/
    return Path(__file__).resolve().parents[3]


BASE_DIR = get_base_dir()
DATA_DIR = BASE_DIR / "data"
PRICING_TEMPLATE_DIR = DATA_DIR / "pricing_template"
SUPPLIER_SHIPMENTS_DIR = DATA_DIR / "supplier_shipments"
REPORT_DIR = DATA_DIR / "report"
CONFIG_FILE = BASE_DIR / "config.json"
