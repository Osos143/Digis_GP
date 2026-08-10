FROM python:3.12-slim

# Create app directory
WORKDIR /app

# Install system deps for Mongo and Redis clients (if any)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy only needed files
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app

# Default entrypoint runs the CLI; override with command args
ENTRYPOINT ["python", "classify_incident_cli.py"]
CMD ["--help"]
