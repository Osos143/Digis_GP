# MongoDB image for the RAN telco platform.
#
# This is a thin wrapper around the official MongoDB image. It exists as its own
# Dockerfile (rather than just referencing `image: mongo` directly in
# docker-compose) so that init scripts -- which MongoDB automatically executes
# on first startup of an empty data directory -- are baked into the image and
# version-controlled alongside the rest of the platform.
FROM mongo:7

# Anything in /docker-entrypoint-initdb.d/ is run once, automatically, the
# first time the container starts with an empty database.
COPY init/ /docker-entrypoint-initdb.d/
