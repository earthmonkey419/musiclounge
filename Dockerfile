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

# config.py (Plex token, admin password, SMTP credentials) is never
# baked into the image — bind-mount it at runtime. See README.md.
# .dockerignore keeps it, the sqlite db, and dev files out of the
# build context as a second layer of protection.

RUN mkdir -p /app/data

EXPOSE 8679

# gthread, not plain sync workers: a sync worker blocks for the entire
# duration of a request, which for /stream and /art means a single slow
# listener holds a worker hostage for minutes. 2 processes x 4 threads
# = 8 concurrent request slots instead of just 2. See MUSICLOUNGE-SCOPE.md.
CMD ["gunicorn", "--bind", "0.0.0.0:8679", "--workers", "2", "--threads", "4", "--worker-class", "gthread", "app:app"]
