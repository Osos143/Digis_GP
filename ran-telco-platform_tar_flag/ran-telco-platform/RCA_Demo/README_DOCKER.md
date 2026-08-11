# RCA Classifier Docker Service

This folder contains a Dockerfile and docker-compose configuration to run the RCA classifier alongside MongoDB and Redis.

Prerequisites
- Docker and docker-compose installed on your host.

Build and start services

```bash
# Build the app image and start MongoDB + Redis
docker-compose up -d --build
```

Run the classifier for a single anomaly

```bash
# Run the CLI inside the app container for incident INC-000001 and bootstrap local JSONs into Mongo
docker-compose run --rm app INC-000001 --bootstrap

# If you prefer to avoid writing to Redis (for example if it's not running yet):
docker-compose run --rm app INC-000001 --bootstrap --skip-cache
```

Notes
- The `app` service sets `MONGO_URI` to `mongodb://mongo:27017` and `REDIS_URL` to `redis://redis:6379/0` so it connects to the compose-managed Mongo and Redis.
- The `app` service is configured as a CLI: you normally run it with `docker-compose run app <anomaly>` so it executes once and exits. If you want a long-running worker, we can add a supervisor script.
- Local JSON files are mounted into the container at `/app` (read-only) so `--bootstrap` will find them.

If you want, I can also:
- Add a small systemd unit or Kubernetes manifest
- Make the app run as a simple HTTP API inside the container
- Add a multi-stage build or slimmer image
