"""
Command-line entry point for the RAN cleaning service.

Runs run_pipeline.py (which stitches together the 11 stage services) as a
subprocess of the same Python interpreter, passing the input file / output
directory / plot-display choice through environment variables that the stage
files already read. This guarantees output identical to running the original
single-file script directly.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

RUN_PIPELINE_PATH = Path(__file__).resolve().parent / "run_pipeline.py"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ran-clean",
        description=(
            "Run the LTE drive-test throughput cleaning / preprocessing pipeline "
            "from the command line. Functionality and outputs are identical to the "
            "original monolithic script -- it has only been split into per-section "
            "stage files and given configurable input/output locations."
        ),
    )
    parser.add_argument(
        "-i", "--input",
        type=str,
        default=None,
        metavar="FILE",
        help=(
            "Path to the raw drive-test .pkl file. "
            "Defaults to Raw_Data/Network_Drive_Test.pkl (same default as the original script)."
        ),
    )
    parser.add_argument(
        "-d", "--data-dir",
        type=str,
        default=None,
        metavar="DIR",
        help=(
            "Directory that holds the raw input data. Only used to build the default "
            "input path when --input is not given. Defaults to 'Raw_Data'."
        ),
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=str,
        default=None,
        metavar="DIR",
        help=(
            "Root directory for all pipeline outputs (preprocessing, plots, RCA "
            "handoff). Defaults to 'Throughput_Anomaly_Detection_Outputs'."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resolved configuration and exit without running the pipeline.",
    )
    parser.add_argument(
        "--show-plots",
        action="store_true",
        help=(
            "Open each plot in an interactive GUI window (blocks until you close it), "
            "matching the original notebook script's behavior. Default is headless: "
            "every plot is saved as a PNG and execution never blocks."
        ),
    )
    return parser


def resolve_paths(args: argparse.Namespace) -> dict:
    data_dir = Path(args.data_dir) if args.data_dir else Path("Raw_Data")
    if args.input:
        input_path = Path(args.input)
    elif os.environ.get("RAN_CLEAN_INPUT_FILE"):
        input_path = Path(os.environ["RAN_CLEAN_INPUT_FILE"])
    else:
        input_path = data_dir / "Network_Drive_Test.pkl"
    output_dir = Path(args.output_dir) if args.output_dir else Path("Throughput_Anomaly_Detection_Outputs")
    return {"data_dir": data_dir, "input_path": input_path, "output_dir": output_dir}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    resolved = resolve_paths(args)

    print("RAN throughput cleaning service")
    print("--------------------------------")
    print("Input file :", resolved["input_path"])
    print("Data dir   :", resolved["data_dir"])
    print("Output dir :", resolved["output_dir"])
    print()

    if not resolved["input_path"].exists():
        print(f"ERROR: input file not found: {resolved['input_path']}", file=sys.stderr)
        print("Use --input /path/to/Network_Drive_Test.pkl (or --data-dir) to point at your file.", file=sys.stderr)
        return 2

    if args.dry_run:
        print("Dry run requested -- pipeline was not executed.")
        return 0

    env = os.environ.copy()
    if args.input:
        env["RAN_CLEAN_INPUT_FILE"] = str(Path(args.input).resolve())
    if args.data_dir:
        env["RAN_CLEAN_DATA_DIR"] = str(Path(args.data_dir).resolve())
    if args.output_dir:
        env["RAN_CLEAN_OUTPUT_DIR"] = str(Path(args.output_dir).resolve())
    if args.show_plots:
        env["RAN_CLEAN_SHOW_PLOTS"] = "1"

    result = subprocess.run([sys.executable, str(RUN_PIPELINE_PATH)], env=env)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
