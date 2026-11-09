FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /uvx /bin/

ENV UV_PYTHON_DOWNLOADS=0 \
    UV_NO_DEV=1 \
    SCISSORHANDS_REGISTRY_DB=/data/projects.sqlite3

WORKDIR /app
COPY . /app
RUN uv sync --locked --no-dev --extra api --no-editable \
    && mkdir /data \
    && chown 10001:10001 /data

USER 10001:10001
EXPOSE 8000
CMD ["/app/.venv/bin/scissorhands-api", "--host", "0.0.0.0"]
