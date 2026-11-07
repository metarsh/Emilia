FROM node:26-bookworm-slim AS node
FROM python:3.12-slim-bookworm AS builder

RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev && rm -rf /var/lib/apt/lists/*
RUN python -m venv /opt/venv

COPY requirements.txt /tmp/requirements.txt
RUN /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

FROM python:3.12-slim-bookworm AS runtime
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libcairo2 libglib2.0-0 libgl1 libgomp1 libatomic1 ca-certificates && rm -rf /var/lib/apt/lists/*

COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY Emilia /app/Emilia
COPY LICENSE /app/LICENSE
RUN useradd --uid 1000 --create-home emilia && mkdir -p /app/sessions /app/state /app/downloads && chown -R emilia:emilia /app
USER 1000:1000
STOPSIGNAL SIGTERM

HEALTHCHECK --interval=60s --timeout=5s --start-period=180s --retries=3 CMD python -c "import os,sys,time; p='/tmp/emilia_heartbeat'; sys.exit(0 if os.path.exists(p) and time.time()-os.path.getmtime(p)<180 else 1)"
CMD ["python", "-m", "Emilia"]

FROM runtime AS production
