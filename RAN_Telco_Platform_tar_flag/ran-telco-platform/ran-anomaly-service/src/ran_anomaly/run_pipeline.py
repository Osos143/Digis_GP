"""
Pipeline orchestrator for the RAN anomaly-detection service.

The original script was one 6,121-line monolithic file. It has been split into 19
stage files under `stages/`, one per the original author's own numbered sections
(e.g. "12. Simple and robust statistical anomaly scores"). Each stage file's code
is copied verbatim -- nothing was rewritten, reordered, or renamed inside them.

Because later stages depend on module-level variables/dataframes/models created by
earlier stages (this is a single, tightly-coupled analytical pipeline, not a set of
independent programs), this runner executes each stage's source with Python's
`exec()` against one shared namespace, in file order. That reproduces the exact
same variable state and execution flow as running the original single file --
the split is purely an on-disk organizational change, not a behavioral one.
"""

from __future__ import annotations

import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

STAGES_DIR = Path(__file__).resolve().parent / "stages"


def discover_stages() -> list[Path]:
    """Stage files are named NN_description.py; sorting by name gives execution order.
    Files starting with '_' are auxiliary (e.g. inference_only.py) and are excluded."""
    return sorted(p for p in STAGES_DIR.glob("*.py") if not p.name.startswith("_"))


def run() -> int:
    stages = discover_stages()
    if not stages:
        print(f"No stage files found in {STAGES_DIR}", file=sys.stderr)
        return 1

    if "RAN_RUN_ID" not in os.environ:
        os.environ["RAN_RUN_ID"] = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    print(f"Run ID: {os.environ['RAN_RUN_ID']}")

    # Shared namespace all stages execute against -- equivalent to one file's module globals.
    shared_globals: dict = {"__name__": "__main__", "__file__": str(STAGES_DIR)}

    for stage_path in stages:
        stage_name = stage_path.name
        is_inference = shared_globals.get("ML_SKIP_TRAINING")

        if is_inference and stage_name.startswith("11_"):
            inference_path = STAGES_DIR / "_inference_only.py"
            print(f"\n{'=' * 70}")
            print(f"Running inference stage: {inference_path.name} (replaces stages 11-13)")
            print(f"{'=' * 70}")
            inf_source = inference_path.read_text()
            try:
                code = compile(inf_source, str(inference_path), "exec")
                exec(code, shared_globals)
            except Exception:
                print(f"\nPipeline failed during inference stage", file=sys.stderr)
                traceback.print_exc()
                return 1
            continue

        if is_inference and stage_name.startswith(("12_", "13_")):
            print(f"\n{'=' * 70}")
            print(f"Skipping stage: {stage_name} (inference mode)")
            print(f"{'=' * 70}")
            continue

        print(f"\n{'=' * 70}")
        print(f"Running stage: {stage_name}")
        print(f"{'=' * 70}")
        sys.stdout.flush()
        source = stage_path.read_text()
        try:
            code = compile(source, str(stage_path), "exec")
            exec(code, shared_globals)
        except Exception:
            print(f"\nPipeline failed during stage: {stage_name}", file=sys.stderr)
            traceback.print_exc()
            return 1

    print("\nAll stages completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
