"""
workbooks.py - tracks which .xlsx files the API is allowed to serve, and
gives each one a short id the React client can pass around instead of a
raw filesystem path (mirrors what st.session_state["active_xlsx"] did in
the Streamlit app, just made explicit/statelesss instead of hidden in a
session).

RAW_ID / FINAL_ID are always available (the two files shipped in data/).
Anything produced by a replan or a commit gets registered here too, so
the client can immediately request it back by id.
"""

from __future__ import annotations

import os
import uuid

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(BASE_DIR, "data")
STREAMLIT_DATA_DIR = os.path.join(ROOT_DIR, "network_pulse_streamlit", "data")
OUTPUT_DIR = os.path.join(ROOT_DIR, "output")

RAW_ID = "raw"
FINAL_ID = "final"


def _pick_existing_path(*candidates: str) -> str:
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return candidates[0]


_REGISTRY: dict[str, dict] = {
    RAW_ID: {
        "path": _pick_existing_path(
            os.path.join(DATA_DIR, "NR5G_PCI_RSI_Planning_raw.xlsx"),
            os.path.join(STREAMLIT_DATA_DIR, "NR5G_PCI_RSI_Planning_raw.xlsx"),
        ),
        "label": "Raw (unplanned)",
        "selectable": True,
    },
    FINAL_ID: {
        "path": _pick_existing_path(
            os.path.join(DATA_DIR, "NR5G_PCI_RSI_Planning_Final.xlsx"),
            os.path.join(OUTPUT_DIR, "NR5G_PCI_RSI_Planning_Final.xlsx"),
            os.path.join(STREAMLIT_DATA_DIR, "NR5G_PCI_RSI_Planning_final(mod_final).xlsx"),
        ),
        "label": "Planned (shipped)",
        "selectable": True,
    },
}


def resolve_workbook(workbook_id: str) -> str:
    entry = _REGISTRY.get(workbook_id)
    if entry is None:
        raise ValueError(f"unknown workbook id '{workbook_id}'")
    return entry["path"]


def register_live_workbook(path: str, label: str, selectable: bool = True) -> str:
    workbook_id = f"live:{uuid.uuid4().hex[:8]}"
    _REGISTRY[workbook_id] = {"path": path, "label": label, "selectable": selectable}
    return workbook_id


def list_workbooks() -> list[dict]:
    return [
        {"id": wid, "label": e["label"]}
        for wid, e in _REGISTRY.items()
        if e["selectable"]
    ]
