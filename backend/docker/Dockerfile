# syntax=docker/dockerfile:1

FROM python:3.11-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /build

ARG INSTALL_ML=true
ARG TORCH_CPU_INDEX_URL=https://download.pytorch.org/whl/cpu

RUN DEBIAN_FRONTEND=noninteractive apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements-base.txt /requirements/backend-base.txt
COPY backend/requirements-ml.txt /requirements/backend-ml.txt
COPY backend/mcp_server/requirements.txt /requirements/mcp.txt

RUN python -m pip install --upgrade pip setuptools wheel \
    && mkdir -p /wheels \
    && python -m pip wheel \
        --wheel-dir=/wheels \
        -r /requirements/backend-base.txt \
    && python -m pip wheel \
        --wheel-dir=/wheels \
        -r /requirements/mcp.txt \
    && if [ "$INSTALL_ML" = "true" ]; then \
        python -m pip wheel \
            --wheel-dir=/wheels \
            --index-url="$TORCH_CPU_INDEX_URL" \
            torch torchvision; \
        python -m pip wheel \
            --wheel-dir=/wheels \
            --find-links=/wheels \
            -r /requirements/backend-ml.txt; \
    fi

COPY framework /build/framework

RUN python -m pip wheel \
    --wheel-dir=/wheels \
    /build/framework


FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

ARG INSTALL_ML=true

COPY backend/requirements-base.txt /requirements/backend-base.txt
COPY backend/requirements-ml.txt /requirements/backend-ml.txt
COPY backend/mcp_server/requirements.txt /requirements/mcp.txt

COPY --from=builder /wheels /wheels

RUN python -m pip install \
        --no-index \
        --find-links=/wheels \
        -r /requirements/backend-base.txt \
    && python -m pip install \
        --no-index \
        --find-links=/wheels \
        -r /requirements/mcp.txt \
    && if [ "$INSTALL_ML" = "true" ]; then \
        python -m pip install \
            --no-index \
            --find-links=/wheels \
            -r /requirements/backend-ml.txt; \
    fi \
    && python -m pip install \
        --no-index \
        --find-links=/wheels \
        /wheels/designlab_core-*.whl \
    && rm -rf /wheels /requirements

COPY backend /app

RUN sed -i 's/\r$//' /app/scripts/start.sh \
    && chmod +x /app/scripts/start.sh \
    && addgroup --system appgroup \
    && adduser --system --ingroup appgroup appuser \
    && chown -R appuser:appgroup /app

USER appuser

EXPOSE 8000

CMD ["/app/scripts/start.sh"]
