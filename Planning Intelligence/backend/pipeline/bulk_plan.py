
"""
bulk_plan.py - Plans the entire network by processing one region at a time
using the shared assignment_engine.
 
The planning data is divided into four regions based on the existing site
ID prefixes:
 
    - ALX : Alexandria
    - DEL : Delta
    - SIN : Sinai
    - UPP : Upper Egypt
 
Analysis of the real network confirmed that 0% of tier-1 (7 km) and tier-2 (14 km) neighbor relationships cross a region boundary,
so coloring each region's subgraph independently gives EXACTLY the same result as one global coloring
"""
 
import time
from collections import defaultdict
 
from loader import load_sectors
from neighbor_graph import build_neighbor_graph
from assignment_engine import assign_all
 
# --- Region handling / Public API -------------------------------------------------------------------
def region_of(site_id: str) -> str:
    return site_id[:3] # The first three characters of the site ID indicate the region (e.g., "ALX", "DEL", "SIN", "UPP")
 
# --- Bulk planning -------------------------------------------------------------------
def bulk_plan(xlsx_path: str) -> tuple[list[dict], dict, dict[str, dict]]:
    sectors = load_sectors(xlsx_path, plan_all=True)
    graph = build_neighbor_graph(sectors)
 
    # Group sectors by region based on their site ID prefixes
    regions: dict[str, list[dict]] = defaultdict(list) 
    for s in sectors:
        regions[region_of(s["site_id"])].append(s)
 
    # Plan each region independently and collect the assignments
    all_assignments: dict[str, dict] = {}
    for region_name, region_sectors in sorted(regions.items(), key=lambda kv: -len(kv[1])): # Sort regions by the number of sectors in descending order
        t0 = time.time()
        result = assign_all(region_sectors, graph, all_sectors_for_site_grouping=region_sectors) 
        all_assignments.update(result)
        n_sites = len({s["site_id"] for s in region_sectors})
        print(f"  {region_name}: {len(region_sectors)} sectors / {n_sites} sites "
              f"planned in {time.time() - t0:.2f}s")
 
    return sectors, graph, all_assignments
 
# --- Example usage -------------------------------------------------------------------
if __name__ == "__main__":
    import sys
 
    src = sys.argv[1] if len(sys.argv) > 1 else "data/NR5G_PCI_RSI_Planning.xlsx"
    print("Bulk planning by region...")
    sectors, graph, assignments = bulk_plan(src)
    print(f"\nTotal sectors planned: {len(assignments)} / {len(sectors)}")