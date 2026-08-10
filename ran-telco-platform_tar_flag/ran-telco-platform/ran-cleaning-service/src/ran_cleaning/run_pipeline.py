"""
Pipeline orchestrator for the RAN cleaning service.

The original script was one 2,268-line monolithic file. It has been split into 11
stage files under `stages/`, one per the original author's own numbered sections
(e.g. "8. Canonical throughput and LTE KPI column detection"). Each stage file's
code is copied verbatim -- nothing was rewritten, reordered, or renamed inside them.

Because later stages depend on module-level variables/dataframes created by earlier
stages (this is a single pipeline, not independent programs), this runner executes
each stage's source with Python's `exec()` against one shared namespace, in file
order. That reproduces the exact same variable state and execution flow as running
the original single file -- the split is purely an on-disk organizational change,
not a behavioral one.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

STAGES_DIR = Path(__file__).resolve().parent / "stages"


def discover_stages() -> list[Path]:
    """Stage files are named NN_description.py; sorting by name gives execution order."""
    return sorted(STAGES_DIR.glob("*.py"))


def run() -> int:
    stages = discover_stages()
    if not stages:
        print(f"No stage files found in {STAGES_DIR}", file=sys.stderr)
        return 1

    shared_globals: dict = {"__name__": "__main__", "__file__": str(STAGES_DIR)}

    for stage_path in stages:
        print(f"\n{'=' * 70}")
        print(f"Running stage: {stage_path.name}")
        print(f"{'=' * 70}")
        source = stage_path.read_text()
        try:
            code = compile(source, str(stage_path), "exec")
            exec(code, shared_globals)
        except Exception:
            print(f"\nPipeline failed during stage: {stage_path.name}", file=sys.stderr)
            traceback.print_exc()
            return 1

    print("\nAll stages completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
