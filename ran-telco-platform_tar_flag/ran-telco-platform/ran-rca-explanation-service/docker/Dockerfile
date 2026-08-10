# Standalone service -- no dependency on the rest of ran-telco-platform.
# Talks to an Ollama server (default: local model, no API key) via
# OLLAMA_BASE_URL, and optionally Anthropic if --provider anthropic /
# LLM_PROVIDER=anthropic is set (needs the [cloud] extra, installed below).

FROM python:3.11-slim

WORKDIR /opt/ran-rca-explanation-service

ENV PIP_DEFAULT_TIMEOUT=100
RUN pip install --no-cache-dir --retries 5 --upgrade pip setuptools wheel

COPY . .
RUN pip install --no-cache-dir --retries 5 --no-build-isolation -e ".[cloud]"

EXPOSE 8010

# API by default. Override CMD for the CLI instead, e.g.:
#   docker run --rm -v $(pwd)/sample_input.json:/data/input.json <image> \
#     ran-rca-explain --input /data/input.json
CMD ["uvicorn", "ran_rca_explanation.api:app", "--host", "0.0.0.0", "--port", "8010"]
