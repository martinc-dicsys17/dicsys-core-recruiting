# Dockerfile del frontend - Flask + HTMX + Alpine.js
# Producción corre gunicorn como usuario no-root; el dev server de Flask (python app.py)
# solo se usa cuando ENVIRONMENT=development (mismo criterio que el backend).
# Las dependencias salen de frontend/uv.lock con uv sync --frozen (F03-P04).

# Dependencias de runtime en /opt/venv
FROM python:3.14.9-slim AS deps

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /build
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev


# Lo mismo más el grupo test (solo para la imagen de test)
FROM deps AS deps-test

RUN uv sync --frozen --group test


FROM python:3.14.9-slim AS base

ARG FLASK_PORT=80
ENV FLASK_PORT=${FLASK_PORT} \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# curl para el healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Usuario no-root (mismo UID/GID que el backend: el deploy hace chown 1000:1000).
# Con home: gunicorn 26 crea su socket de control bajo $HOME y sin home loguea un error.
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid appgroup --create-home --shell /bin/bash appuser

WORKDIR /app

COPY --from=deps /opt/venv /opt/venv

# Copiar código fuente
COPY --chown=appuser:appgroup . .

EXPOSE ${FLASK_PORT}


FROM base AS test

COPY --from=deps-test /opt/venv /opt/venv

USER appuser

CMD ["pytest", "tests", "-q"]


# Etapa final productiva. Debe permanecer última para que docker build use gunicorn.
FROM base AS runtime

USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl --fail http://localhost:${FLASK_PORT}/health || exit 1

# gunicorn con threads: el BFF hace llamadas HTTP síncronas al backend (hasta 120 s en
# subidas de PDF), por eso --timeout 180. Calibrar GUNICORN_WORKERS/THREADS con la VM real.
# --no-control-socket: el socket de control de gunicorn 26 no se usa dentro del contenedor.
CMD ["sh", "-c", "if [ \"$ENVIRONMENT\" = 'development' ]; then python app.py; else gunicorn --bind 0.0.0.0:${FLASK_PORT} --worker-class gthread --workers ${GUNICORN_WORKERS:-2} --threads ${GUNICORN_THREADS:-8} --timeout ${GUNICORN_TIMEOUT:-180} --no-control-socket --access-logfile - --error-logfile - app:app; fi"]
