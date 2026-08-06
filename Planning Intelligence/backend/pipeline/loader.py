"""
loader.py - Stage 1 of the PCI + Mod4/Mod3 + RSI planning pipeline.

Reads the site/sector planning workbook, validates every row, and returns
a sorted list of sector dicts ready to feed into neighbor_graph.py.

A sector is a plain dict with these keys:
    site_sector_id, site_id, sector_id, sectors_count, requires_planning,
    azimuth, lat, lon, band, cell_radius, rsi, pci, mod4, plan_all

Use the helper functions below to answer "is this locked / does this need planning".
"""

from pathlib import Path

import openpyxl

# ---- 3GPP NR bounds used for validation --------------------------------
PCI_MIN, PCI_MAX = 0, 1007
RSI_MIN, RSI_MAX = 0, 830          
LAT_MIN, LAT_MAX = -90.0, 90.0
LON_MIN, LON_MAX = -180.0, 180.0

REQUIRED_COLUMNS = [
    "site_sector_ID", "siteID", "sectors_count", "sectorID",
    "Requires_Planning", "Azimuth", "Latitude", "Longitude",
    "Freq Band", "Cell Radius", "RSI", "PCI", "Mod4",
]

# --- Exceptions ------------------------------------------------------------
class LoaderError(Exception):
    """Raised when the input workbook fails validation."""


# --- Helper functions -------------------------------------------------------
def is_locked(sector: dict) -> bool:
    """True if this sector already carries a PCI the optimizer must preserve."""
    return sector["pci"] is not None    # checking for None is important because 0 is a valid PCI

def is_planning_target(sector: dict) -> bool:
    """True if this sector is one we must assign a PCI/RSI to."""
    if is_locked(sector):
        return False
    return sector["plan_all"] or sector["requires_planning"] # check plan_all first because it overrides the sheet's Requires_Planning flag

def _row_to_dict(header: list[str], row: tuple) -> dict:
    return {h: v for h, v in zip(header, row)}


# --- Validation -------------------------------------------------------------
def _validate_row(d: dict, row_num: int, errors: list[str]) -> None:
    def require(key):
        if d.get(key) is None:
            errors.append(f"row {row_num}: missing required field '{key}'")

    for key in ("site_sector_ID", "siteID", "sectorID", "Requires_Planning",
                "Azimuth", "Latitude", "Longitude", "Freq Band", "Cell Radius"):
        require(key)

    if d.get("Latitude") is not None and not (LAT_MIN <= d["Latitude"] <= LAT_MAX):
        errors.append(f"row {row_num}: Latitude {d['Latitude']} out of range")
    if d.get("Longitude") is not None and not (LON_MIN <= d["Longitude"] <= LON_MAX):
        errors.append(f"row {row_num}: Longitude {d['Longitude']} out of range")
    if d.get("Azimuth") is not None and not (0 <= d["Azimuth"] < 360):
        errors.append(f"row {row_num}: Azimuth {d['Azimuth']} out of [0, 360)")
    if d.get("Cell Radius") is not None and d["Cell Radius"] <= 0:
        errors.append(f"row {row_num}: Cell Radius must be > 0")

    pci = d.get("PCI")
    if pci is not None and not (PCI_MIN <= pci <= PCI_MAX):
        errors.append(f"row {row_num}: PCI {pci} out of [0, {PCI_MAX}]")
    rsi = d.get("RSI")
    if rsi is not None and not (RSI_MIN <= rsi <= RSI_MAX):
        errors.append(f"row {row_num}: RSI {rsi} out of [0, {RSI_MAX}]")
    mod4 = d.get("Mod4")
    if pci is not None and mod4 is not None and (pci % 4) != mod4:
        errors.append(f"row {row_num}: Mod4 {mod4} inconsistent with PCI {pci} (PCI % 4 = {pci % 4})")

# --- Main loader function ----------------------------------------------------
def load_sectors(path: str | Path, sheet_name: str = "Planning", plan_all: bool = False) -> list[dict]:
    """
    Read, validate, and sort site sectors from the planning workbook.

    Raises LoaderError with every problem found (not just the first).

    plan_all: if True, every unlocked sector is treated as a planning
        target regardless of Requires_Planning. Use this for a full reset
        (replan the whole network) rather than just the sheet-flagged rows.
    """
    #load the workbook and check for the expected sheet
    path = Path(path) 
    if not path.exists():
        raise LoaderError(f"file not found: {path}")
    
    wb = openpyxl.load_workbook(path, data_only=True) 
    if sheet_name not in wb.sheetnames:
        raise LoaderError(f"sheet '{sheet_name}' not found; available: {wb.sheetnames}")
    ws = wb[sheet_name]

    rows = list(ws.iter_rows(values_only=True)) # read all rows as tuples of cell values
    if not rows:
        raise LoaderError("sheet is empty")

    header = [str(h).strip() if h is not None else None for h in rows[0]]    #check for header row
    missing_cols = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing_cols:
        raise LoaderError(f"missing required columns: {missing_cols}")

    #--- Process each row --------------------------------------------------------
    errors: list[str] = []
    seen_ids: dict[str, int] = {}
    sectors: list[dict] = []

    for i, raw_row in enumerate(rows[1:], start=2): # skip header row, start counting at 2 for user-friendly error messages
        
        d = _row_to_dict(header, raw_row)
        
        if all(v is None for v in raw_row):
            continue  # skip fully blank trailing rows

        
        _validate_row(d, i, errors)

        # Check for duplicate site_sector_IDs
        sid = d.get("site_sector_ID")
        if sid is not None:
            if sid in seen_ids:
                errors.append(f"row {i}: duplicate site_sector_ID '{sid}' (first seen row {seen_ids[sid]})")
            else:
                seen_ids[sid] = i

        # skip further processing if there are already too many errors
        if len(errors) > 200:
            errors.append("... too many errors, stopping early")
            break

        sectors.append({
            "site_sector_id": str(sid),
            "site_id": str(d.get("siteID")),
            "sector_id": int(d.get("sectorID")),
            "sectors_count": int(d.get("sectors_count") or 0),
            "requires_planning": bool(d.get("Requires_Planning")),
            "azimuth": float(d.get("Azimuth")),
            "lat": float(d.get("Latitude")),
            "lon": float(d.get("Longitude")),
            "band": str(d.get("Freq Band")),
            "cell_radius": float(d.get("Cell Radius")),
            "rsi": d.get("RSI"),
            "pci": d.get("PCI"),
            "mod4": d.get("Mod4"),
            "plan_all": plan_all,
        })
    
    if errors:
        raise LoaderError(f"{len(errors)} validation error(s):\n" + "\n".join(errors))

    # Sort by site_id then sector_id for deterministic output
    sectors.sort(key=lambda s: (s["site_id"], s["sector_id"]))
    return sectors


def summarize(sectors: list[dict]) -> dict:
    """Quick sanity-check summary, useful when wiring this into the rest of the pipeline."""
    return {
        "total_sectors": len(sectors),
        "unique_sites": len({s["site_id"] for s in sectors}),
        "requires_planning": sum(s["requires_planning"] for s in sectors),
        "planning_targets": sum(is_planning_target(s) for s in sectors),
        "already_locked": sum(is_locked(s) for s in sectors),
        "bands": sorted({s["band"] for s in sectors}),
    }


if __name__ == "__main__":
    import sys
    import json

    src = sys.argv[1] if len(sys.argv) > 1 else "data/NR5G_PCI_RSI_Planning.xlsx"
    plan_all = "--plan-all" in sys.argv
    sectors = load_sectors(src, plan_all=plan_all)
    print(json.dumps(summarize(sectors), indent=2))
    print(f"\nFirst sector: {sectors[0]}")
