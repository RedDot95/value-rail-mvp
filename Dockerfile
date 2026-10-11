# syntax=docker/dockerfile:1
# Research worker/UI image; config/default.toml remains offline by default.
# Build:  docker build -t value-rail-mvp .
# Run:    docker run --rm -p 127.0.0.1:8000:8000 -v value_rail_data:/data value-rail-mvp
# Expose beyond localhost ONLY behind a TLS reverse proxy and with VALUE_RAIL_BASIC_USER/PASSWORD set.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VALUE_RAIL_DB_PATH=/data/value_rail.db \
    VALUE_RAIL_CONFIG_PATH=/app/config/default.toml \
    VALUE_RAIL_FIXTURES_DIR=/app/tests/fixtures \
    VALUE_RAIL_MIGRATIONS_DIR=/app/migrations \
    VALUE_RAIL_ALERT_LOG_FILE=/data/alerts.log

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export PIP_CERT=/run/secrets/proxy_ca; fi; \
    pip install --no-cache-dir .
COPY --chown=10001:10001 config ./config
COPY --chown=10001:10001 migrations ./migrations
COPY --chown=10001:10001 tests/fixtures ./tests/fixtures

RUN useradd --system --uid 10001 app && mkdir -p /data && chown app /data
USER app
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/livez')"

# init-db is idempotent (alembic upgrade head + seed). Fixtures are loaded explicitly:
#   docker exec <ctr> value-rail load-fixtures
CMD ["sh", "-c", "value-rail init-db && uvicorn value_rail.web.app:create_app --factory --host 0.0.0.0 --port 8000"]
