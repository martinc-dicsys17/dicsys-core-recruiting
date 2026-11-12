# Dockerfile multietapa para FastAPI
# Las dependencias salen de backend/uv.lock con uv sync --frozen (F03-P04): dos builds del mismo commit instalan
# exactamente lo mismo. Todas las dependencias compiladas traen wheels para esta versión de Python: sin compiladores.

# Etapa 1: dependencias de runtime en /opt/venv
FROM python:3.14.9-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /build

# Solo el lock y el pyproject: la capa de dependencias se reusa mientras no cambien
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev

# OCR de CV escaneados (Recruiting): modelo oficial de reconocimiento PP-OCRv6_rec_medium (multilingüe, incluye español)
# de RapidOCR 3.10.0. Se descarga y se verifica por SHA256 al construir la imagen, en la carpeta de modelos del paquete
# (donde ya viene la detección PP-OCRv6_det_small). En ejecución nunca se descarga nada (backend/core/cv_ocr.py).
ARG OCR_REC_URL=https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.10.0/onnx/PP-OCRv6/rec/PP-OCRv6_rec_medium.onnx
ARG OCR_REC_SHA256=eef444829dbbe18d7fea59a3f6eb75647518d2b3a9568d27c92e42940204894b
RUN /opt/venv/bin/python -c "import hashlib, pathlib, sys, urllib.request, rapidocr; \
destino = pathlib.Path(rapidocr.__file__).parent / 'models' / 'PP-OCRv6_rec_medium.onnx'; \
urllib.request.urlretrieve('${OCR_REC_URL}', destino); \
sha = hashlib.sha256(destino.read_bytes()).hexdigest(); \
print(destino, destino.stat().st_size, sha); \
sys.exit(0 if sha == '${OCR_REC_SHA256}' else 'SHA256 invalido del modelo OCR: ' + sha)"


# Etapa 1b: lo mismo más el grupo test (solo para la imagen de test)
FROM builder AS builder-test

RUN uv sync --frozen --group test


# Etapa 2: Base compartida por runtime y tests
FROM python:3.14.9-slim AS runtime-base

WORKDIR /app

# Crear usuario no-root para seguridad
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid appgroup --shell /bin/bash appuser

# Crear directorio para archivos subidos (fuera de /app que es read-only)
RUN mkdir -p /data/files/profile && chown -R appuser:appgroup /data

# Instalar solo dependencias de runtime
# unrar-free: carga masiva de CV en .rar; libreoffice-writer: vista previa de un CV Word en el modal de comparación
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    unrar-free \
    libreoffice-writer \
    fonts-liberation \
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
