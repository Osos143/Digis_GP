#!/usr/bin/env bash
# Entrypoint for the combined cleaning + anomaly detection image.
#
# Usage (as the container CMD / `docker run ... <mode> [extra args]`):
#   both     (default) run ran-clean, then ran-anomaly, against the same output dir
#   clean    run only ran-clean -- extra args are passed straight through to it
#   anomaly  run only ran-anomaly -- extra args are passed straight through to it
#   <anything else>   exec'd verbatim (e.g. "bash" to get a debug shell)
#
# Configuration is primarily via environment variables (set them in
# docker-compose.yml): RAN_CLEAN_INPUT_FILE, RAN_CLEAN_OUTPUT_DIR,
# RAN_ANOMALY_OUTPUT_DIR, MONGO_URI, MONGO_DB. These are read directly by
# each stage/CLI already, so this script only needs to invoke the commands --
# it does not need to translate env vars into CLI flags.

set -euo pipefail

MODE="${1:-both}"
if [ "$#" -gt 0 ]; then
  shift
fi

case "$MODE" in
  clean)
    exec ran-clean \
      --input "${RAN_CLEAN_INPUT_FILE:-/data/raw/Network_Drive_Test.pkl}" \
      --output-dir "${RAN_CLEAN_OUTPUT_DIR:-/data/outputs}" \
      "$@"
    ;;
  anomaly)
    exec ran-anomaly \
      --output-dir "${RAN_ANOMALY_OUTPUT_DIR:-/data/outputs}" \
      "$@"
    ;;
  both)
    echo "=================================================="
    echo " Stage 1/2: ran-clean"
    echo "=================================================="
    ran-clean \
      --input "${RAN_CLEAN_INPUT_FILE:-/data/raw/Network_Drive_Test.pkl}" \
      --output-dir "${RAN_CLEAN_OUTPUT_DIR:-/data/outputs}"

    echo "=================================================="
    echo " Stage 2/2: ran-anomaly"
    echo "=================================================="
    ran-anomaly \
      --output-dir "${RAN_ANOMALY_OUTPUT_DIR:-/data/outputs}"
    ;;
  *)
    # Anything else (e.g. "bash", "python3") is executed as-is -- useful for debugging.
    exec "$MODE" "$@"
    ;;
esac
