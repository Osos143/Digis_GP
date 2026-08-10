"""
Command-line entry point for the RAN anomaly-detection service.

Runs run_pipeline.py (which stitches together the 19 stage services) as a
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
        prog="ran-anomaly",
        description=(
            "Run the LTE drive-test throughput anomaly-detection / RCA-handoff pipeline "
            "from the command line. Functionality and outputs are identical to the "
            "original monolithic script -- it has only been split into per-section stage "
            "files and given configurable input/output locations."
        ),
    )
    parser.add_argument(
        "-i", "--input",
        type=str,
        default=None,
        metavar="FILE",
        help=(
            "Path to the raw drive-test .pkl file (only used if the cleaned parquet/csv "
            "feature table isn't found). Defaults to Raw_Data/Network_Drive_Test.pkl."
        ),
    )
    parser.add_argument(
        "-d", "--data-dir",
        type=str,
        default=None,
        metavar="DIR",
        help="Directory holding the raw input data. Defaults to 'Raw_Data'.",
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=str,
        default=None,
        metavar="DIR",
        help=(
            "Root output directory. Must match the --output-dir used by the cleaning "
            "service (ran-clean), since this pipeline reads its "
            "01_preprocessing_cleaning/lte_dl_feature_table_clean_pre_anomaly.parquet "
            "output from there. Defaults to 'Throughput_Anomaly_Detection_Outputs'."
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
            "Open each plot in an interactive GUI window (blocks until closed), matching "
            "the original script's notebook-style behavior. Default is headless: every "
            "plot is saved as a PNG and execution never blocks."
        ),
    )
    parser.add_argument(
        "--mongo-uri",
        type=str,
        default=None,
        metavar="URI",
        help=(
            "MongoDB connection URI, e.g. mongodb://mongo:27017. If given (or if the "
            "MONGO_URI environment variable is already set), every JSON file this pipeline "
            "writes is also inserted into a same-named MongoDB collection. Optional -- "
            "omit to skip MongoDB entirely; file outputs are unaffected either way."
        ),
    )
    parser.add_argument(
        "--mongo-db",
        type=str,
        default=None,
        metavar="NAME",
        help="MongoDB database name to write into. Defaults to 'ran_telco'.",
    )
    return parser


def resolve_paths(args: argparse.Namespace) -> dict:
    data_dir = Path(args.data_dir) if args.data_dir else Path("Raw_Data")
    input_path = Path(args.input) if args.input else data_dir / "Network_Drive_Test.pkl"
    output_dir = Path(args.output_dir) if args.output_dir else Path("Throughput_Anomaly_Detection_Outputs")
    return {"data_dir": data_dir, "input_path": input_path, "output_dir": output_dir}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    resolved = resolve_paths(args)

    feature_table = resolved["output_dir"] / "01_preprocessing_cleaning" / "lte_dl_feature_table_clean_pre_anomaly.parquet"
    feature_table_csv_fallback = resolved["output_dir"] / "01_preprocessing_cleaning" / "lte_dl_feature_table_clean_pre_anomaly.csv.gz"

    print("RAN anomaly-detection service")
    print("------------------------------")
    print("Output dir           :", resolved["output_dir"])
    print("Expected feature table:", feature_table)
    mongo_uri_display = args.mongo_uri or os.environ.get("MONGO_URI")
    print("MongoDB              :", mongo_uri_display or "(disabled -- file outputs only)")
    print()

    if not feature_table.exists() and not feature_table_csv_fallback.exists():
        print(
            "WARNING: cleaned feature table not found yet at the path above.\n"
            "         Run the cleaning service first (ran-clean --output-dir "
            f"{resolved['output_dir']}) or point --output-dir at an existing run.",
            file=sys.stderr,
        )
        # Not a hard failure here: the pipeline itself also has its own fallback search
        # paths (see stage 02_utility_functions.py) and will raise its own clear error
        # if it truly can't find the table. We don't want to duplicate/diverge from that.

    if args.dry_run:
        print("Dry run requested -- pipeline was not executed.")
        return 0

    env = os.environ.copy()
    if args.input:
        env["RAN_ANOMALY_INPUT_FILE"] = str(Path(args.input).resolve())
    if args.data_dir:
        env["RAN_ANOMALY_DATA_DIR"] = str(Path(args.data_dir).resolve())
    if args.output_dir:
        env["RAN_ANOMALY_OUTPUT_DIR"] = str(Path(args.output_dir).resolve())
    if args.show_plots:
        env["RAN_ANOMALY_SHOW_PLOTS"] = "1"
    if args.mongo_uri:
        env["MONGO_URI"] = args.mongo_uri
    if args.mongo_db:
        env["MONGO_DB"] = args.mongo_db

    result = subprocess.run([sys.executable, str(RUN_PIPELINE_PATH)], env=env)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
