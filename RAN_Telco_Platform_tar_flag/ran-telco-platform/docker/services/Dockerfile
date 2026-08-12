# Single image containing both ran-cleaning-service and ran-anomaly-service.
# Built from the repo root (see docker-compose.yml `context: .`), because it
# needs to COPY both service source trees, which live as siblings at the repo
# root, not inside docker/.

FROM python:3.11-slim

# Needed to build/import numpy, pandas, scikit-learn, pyarrow wheels cleanly,
# and matplotlib's Agg backend (already the default -- see each service's
# 01_imports_and_settings.py stage) has no extra system requirement beyond this.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/ran-telco

# Make pip resilient to a slow/flaky network (this is what was failing:
# "Installing build dependencies" -- pip re-downloading setuptools/wheel into
# an isolated build env for every package). Two things fix this:
#   1. Install setuptools/wheel/pip ourselves, once, as their own retryable step.
#   2. Use --no-build-isolation on the actual package installs so pip reuses
#      those instead of trying to fetch them again per-package.
ENV PIP_DEFAULT_TIMEOUT=100
RUN pip install --no-cache-dir --retries 5 --upgrade pip setuptools wheel

# Install both services in editable mode so their console_scripts entry
# points (ran-clean, ran-anomaly) land on PATH. Split into separate RUN/COPY
# layers so a retry after a network failure doesn't have to redo work Docker
# already cached successfully.
COPY ran-cleaning-service/ ./ran-cleaning-service/
RUN pip install --no-cache-dir --retries 5 --no-build-isolation -e ./ran-cleaning-service

COPY ran-anomaly-service/ ./ran-anomaly-service/
RUN pip install --no-cache-dir --retries 5 --no-build-isolation -e ./ran-anomaly-service

COPY docker/services/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Default locations inside the container; override via docker-compose env vars.
ENV RAN_CLEAN_INPUT_FILE=/data/raw/Network_Drive_Test.pkl \
    RAN_CLEAN_OUTPUT_DIR=/data/outputs \
    RAN_ANOMALY_OUTPUT_DIR=/data/outputs

VOLUME ["/data/raw", "/data/outputs"]

ENTRYPOINT ["entrypoint.sh"]
# Default mode: run cleaning then anomaly detection, in sequence, against the
# same output directory. Override at `docker run`/compose `command:` with
# "clean" or "anomaly" to run just one.
CMD ["both"]
