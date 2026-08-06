"""
cache.py - the API's one loading/caching layer, doing exactly what
core/state.py did under Streamlit (st.cache_resource) with a plain dict
instead: keyed on (path, file mtime) so an overwritten workbook is
re-read automatically instead of serving a stale cached copy.
"""

from __future__ import annotations

import os

_PIPELINE_STATE: dict[tuple, tuple] = {}
_NETWORK_JSON: dict[tuple, dict] = {}
_RAW_JSON: dict[tuple, dict] = {}


def _key(path: str) -> tuple:
    return (path, os.path.getmtime(path))


def get_pipeline_state(path: str):
    from loader import load_sectors
    from neighbor_graph import build_neighbor_graph

    k = _key(path)
    if k not in _PIPELINE_STATE:
        sectors = load_sectors(path)
        graph = build_neighbor_graph(sectors)
        assignments = {
            s["site_sector_id"]: {"pci": s["pci"], "rsi": s["rsi"], "mod4": s["mod4"]}
            for s in sectors
        }
        _PIPELINE_STATE[k] = (sectors, graph, assignments)
    return _PIPELINE_STATE[k]


def get_network_json(path: str) -> dict:
    from network_build import build_network_json

    k = _key(path)
    if k not in _NETWORK_JSON:
        _NETWORK_JSON[k] = build_network_json(path)
    return _NETWORK_JSON[k]


def get_raw_json(path: str) -> dict:
    from network_build import build_raw_json

    k = _key(path)
    if k not in _RAW_JSON:
        _RAW_JSON[k] = build_raw_json(path)
    return _RAW_JSON[k]


def invalidate(path: str) -> None:
    """Call after writing a new/overwritten workbook so the next request
    re-reads it instead of serving whatever was cached under an old mtime
    (harmless either way since mtime changes, but keeps memory bounded)."""
    prefix_matches = [k for k in {**_PIPELINE_STATE, **_NETWORK_JSON, **_RAW_JSON} if k[0] == path]
    for k in prefix_matches:
        _PIPELINE_STATE.pop(k, None)
        _NETWORK_JSON.pop(k, None)
        _RAW_JSON.pop(k, None)
