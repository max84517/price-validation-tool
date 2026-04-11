"""
config/settings.py — load / save config.json
Schema:
{
    "pricing_template_path": "<absolute path to Pricing_Template_InputDevices.xlsx>",
    "suppliers": [
        {"name": "SupplierA", "shipment_folder": "<absolute path>"},
        ...
    ]
}
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any

from price_validation.config.paths import CONFIG_FILE


_DEFAULT: dict[str, Any] = {
    "suppliers": [],
    "nb_kb": "",
    "dt_kb": "",
    "peripheral": "",
}


def load() -> dict[str, Any]:
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            # back-fill missing keys
            for k, v in _DEFAULT.items():
                data.setdefault(k, v)
            return data
        except (json.JSONDecodeError, OSError):
            pass
    return dict(_DEFAULT)


def save(data: dict[str, Any]) -> None:
    CONFIG_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
