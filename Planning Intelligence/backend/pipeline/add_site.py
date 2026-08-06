"""
add_site.py - plan a single new site's sectors against a region that has already been planned, without touching anything else.

Same assignment_engine as bulk_plan.py - the only difference is what's in
`existing_assignments` (everyone else in the region, locked) vs. what's in
`sectors_to_plan` (just the new site).
"""

from loader import load_sectors
from neighbor_graph import build_neighbor_graph
from assignment_engine import assign_all
from bulk_plan import region_of

# --- Add a new site to an existing plan -------------------------------------------------------------------
def add_site(xlsx_path: str, existing_assignments: dict[str, dict], target_site_id: str ) -> dict[str, dict]:
    """
    existing_assignments: {site_sector_id: {"pci":, "rsi":, "mod4":}} for every already-planned sector EXCEPT the target site.
    target_site_id: the new site to plan (e.g. "ALX9999").
    Returns {site_sector_id: {"pci":, "rsi":, "mod4":}} for the new site only.
    """
    sectors = load_sectors(xlsx_path, plan_all=True)
    graph = build_neighbor_graph(sectors)

    # Find the sectors belonging to the target site
    site_sectors = [s for s in sectors if s["site_id"] == target_site_id]
    if not site_sectors:
        raise ValueError(f"site '{target_site_id}' not found")

    # Determine the region of the target site and filter sectors to only those in the same region
    region = region_of(target_site_id)
    region_sectors = [s for s in sectors if region_of(s["site_id"]) == region]

    # Lock the existing assignments for sectors not belonging to the target site
    site_sector_ids = {s["site_sector_id"] for s in site_sectors}
    locked = {sid: a for sid, a in existing_assignments.items() if sid not in site_sector_ids}

    return assign_all( site_sectors ,graph ,all_sectors_for_site_grouping=region_sectors ,existing_assignments=locked )

# --- Example usage -------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    from bulk_plan import bulk_plan

    src = sys.argv[1] if len(sys.argv) > 1 else "data/NR5G_PCI_RSI_Planning.xlsx"
    target = sys.argv[2] if len(sys.argv) > 2 else None

    print("Planning the whole network first, to have something 'existing' to add on to...")
    sectors, graph, assignments = bulk_plan(src)

    if target is None:
        target = sectors[0]["site_id"]

    print(f"\nNow pretending '{target}' is a brand-new site (dropping its assignment)...")
    result = add_site(src, assignments, target)
    for sid, a in sorted(result.items()):
        print(f"  {sid}: PCI={a['pci']} Mod4={a['mod4']} RSI={a['rsi']}")
