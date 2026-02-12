FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./

RUN pip install --no-cache-dir build hatch

COPY . .

RUN python -m build --wheel

FROM python:3.12-slim AS runtime

WORKDIR /app

RUN groupadd --gid 1000 venomqa \
    && useradd --uid 1000 --gid venomqa --shell /bin/bash --create-home venomqa

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/dist/*.whl /tmp/

RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl

COPY --chown=venomqa:venomqa . /app

RUN mkdir -p /app/reports /app/journeys && chown -R venomqa:venomqa /app

USER venomqa

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV VENOMQA_REPORT_DIR=/app/reports

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD venomqa --help > /dev/null 2>&1 || exit 1

ENTRYPOINT ["venomqa"]
CMD ["--help"]
