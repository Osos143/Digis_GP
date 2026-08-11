# netfix-backend needs ran-clean/ran-anomaly on PATH (it invokes them as
# subprocesses -- see services/cleaning_service.py and detection_service.py
# for why) AND needs ran_kpi_labeling / ran_reason_matching importable as
# libraries (see services/threshold_evaluation_service.py,
# cause_matching_service.py, llm_explanation_service.py) -- so, unlike the
# rest of this platform's services, this is the one image that needs all
# four packages installed together, plus netfix-backend itself.
#
# Built from the repo root (see docker-compose.yml `context: .`), same
# reason as docker/services/Dockerfile: it needs to COPY sibling source
# trees that live at the repo root, not inside docker/.

FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/ran-telco

ENV PIP_DEFAULT_TIMEOUT=100
RUN pip install --no-cache-dir --retries 5 --upgrade pip setuptools wheel

# Same layering strategy as docker/services/Dockerfile: one COPY+RUN pair per
# package, so a retry after a network hiccup doesn't redo already-cached work.
COPY ran-cleaning-service/ ./ran-cleaning-service/
RUN pip install --no-cache-dir --retries 5 --no-build-isolation -e ./ran-cleaning-service

COPY ran-anomaly-service/ ./ran-anomaly-service/
RUN pip install --no-cache-dir --retries 5 --no-build-isolation -e ./ran-anomaly-service

COPY RCA_Demo/ ./RCA_Demo/

COPY netfix-backend/ ./netfix-backend/
RUN pip install --no-cache-dir --retries 5 --no-build-isolation -e ./netfix-backend

# Working directories for uploaded datasets and Phase 1 outputs, one per
# session (see UploadService / Phase1Orchestrator). Mounted as a volume so
# they survive container restarts.
ENV NETFIX_DATA_DIR=/data/netfix
VOLUME ["/data/netfix"]

EXPOSE 8000

# API by default. Override CMD to run the CLI instead, e.g.:
#   docker compose run --rm netfix-backend netfix-backend status
ENTRYPOINT []
CMD ["uvicorn", "netfix_backend.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
