# MusicLounge Jukebox for Plex — production image
# Mirrors RiderMusic's Docker shape (Ubuntu 24.04 + gunicorn) for consistency
# across the product family.

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.12 \
        python3.12-venv \
        python3-pip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dedicated venv inside the image — mirrors RiderMusic's own venv
# convention, and sidesteps Ubuntu 24's PEP 668 externally-managed-
# environment restriction cleanly (no --break-system-packages needed).
RUN python3.12 -m venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x docker-entrypoint.sh

# Bake config.example.py in as the default config.py. This is safe:
# .dockerignore already excludes any real local config.py from ever
# entering the build context (even if you're building from a directory
# that has a real one sitting right next to the Dockerfile), so this
# only ever copies the placeholder-default template — never real
# secrets. Real values are supplied via environment variables at
# runtime (see docker-compose.yml and README.md), which Docker never
# writes into any image layer. A bind-mounted config.py, if you
# provide one, simply overwrites this at container start.
RUN cp config.example.py config.py

RUN mkdir -p /app/data

EXPOSE 8679

# docker-entrypoint.sh initializes the DB schema (idempotent — safe
# on every start, not just the first) before handing off to gunicorn.
# gthread, not plain sync workers: a sync worker blocks for the entire
# duration of a request, which for /stream and /art means a single slow
# listener holds a worker hostage for minutes. 2 processes x 4 threads
# = 8 concurrent request slots instead of just 2. See MUSICLOUNGE-SCOPE.md.
ENTRYPOINT ["./docker-entrypoint.sh"]
