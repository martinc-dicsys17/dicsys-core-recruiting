# Dockerfile multietapa para FastAPI
# Las dependencias salen de backend/uv.lock con uv sync --frozen (F03-P04): dos builds del mismo commit instalan
# exactamente lo mismo. Todas las dependencias compiladas traen wheels para esta versión de Python: sin compiladores.

# Etapa 1: dependencias de runtime en /opt/venv
FROM python:3.14.10-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /build

# Solo el lock y el pyproject: la capa de dependencias se reusa mientras no cambien
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev


# Etapa 1b: lo mismo más el grupo test (solo para la imagen de test)
FROM builder AS builder-test

RUN uv sync --frozen --group test


# Etapa 2: Base compartida por runtime y tests
FROM python:3.14.10-slim AS runtime-base

WORKDIR /app

# Crear usuario no-root para seguridad
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid appgroup --shell /bin/bash appuser

# Crear directorio para archivos subidos (fuera de /app que es read-only)
RUN mkdir -p /data/files/profile && chown -R appuser:appgroup /data

# Instalar solo dependencias de runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copiar entorno virtual desde builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Variables de entorno para Python. ALEMBIC_CONFIG: `alembic upgrade head` desde cualquier carpeta (F04)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ALEMBIC_CONFIG=/app/backend/alembic.ini

# Copiar código de la aplicación
COPY --chown=appuser:appgroup backend/ ./backend/

# Cambiar a usuario no-root
USER appuser

# Puerto expuesto
EXPOSE ${PORT}

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl --fail http://localhost:${PORT}/health || exit 1

# Comando de inicio con Uvicorn (--reload solo en desarrollo via ENVIRONMENT)
CMD ["sh", "-c", "if [ \"$ENVIRONMENT\" = 'development' ]; then uvicorn backend.main:app --host 0.0.0.0 --port ${PORT} --workers 1 --reload --reload-dir /app/backend; else uvicorn backend.main:app --host 0.0.0.0 --port ${PORT} --workers 5; fi"]


# Etapa de test: el runtime con el entorno que además trae el grupo test del lock.
FROM runtime-base AS test

COPY --from=builder-test /opt/venv /opt/venv

CMD ["pytest", "backend/tests", "-q"]


# Etapa final productiva. Debe permanecer ultima para que docker build use Uvicorn.
FROM runtime-base AS runtime
