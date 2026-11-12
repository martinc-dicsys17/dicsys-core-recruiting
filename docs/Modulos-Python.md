# Módulos Python - Dicsys Core

## Dependencias Backend (backend/pyproject.toml)

| Paquete | Uso |
|---------|-----|
| fastapi | Framework web API |
| uvicorn[standard] | Servidor ASGI |
| sqlalchemy (<2.1) | ORM base de datos |
| psycopg2-binary | Driver PostgreSQL |
| pydantic | Validación de datos |
| pydantic-settings | Configuración desde env |
| PyJWT | JWT tokens |
| bcrypt | Hash de contraseñas |
| python-multipart | Form data |
| python-dotenv | Carga del .env |
| email-validator | Validación de emails |
| httpx | Cliente HTTP (integraciones) |
| sendgrid | Envío de emails |
| Pillow, pypdf, PyMuPDF | Imágenes y PDF |
| openpyxl | Excel |
| google-cloud-storage | Storage de datos críticos |
| pyotp, qrcode[pil] | 2FA (TOTP) |
| google-genai | LLM (Gemini) |

Grupo `test`: pytest, pytest-cov y httpx2 (transporte del TestClient).

## Dependencias Frontend (frontend/pyproject.toml)

| Paquete | Uso |
|---------|-----|
| flask | Framework web |
| httpx | Cliente HTTP para API |
| python-dotenv | Carga del .env |
| gunicorn | Servidor WSGI en producción |

Grupo `test`: pytest.

## Al agregar nuevas dependencias

1. `uv add --project backend <paquete>` (o `--project frontend`): actualiza `pyproject.toml` y `uv.lock`; se
   commitean los dos. CI falla si el lock queda desactualizado (`uv lock --check`).
2. Verificar el `Dockerfile` si requiere dependencias del sistema
3. Reconstruir imagen: `docker compose build --no-cache <servicio>`

## Estructura de un nuevo módulo backend

```
backend/modules/<nuevo_modulo>/
├── __init__.py
├── models.py      # Modelos SQLAlchemy
├── routers.py     # Endpoints FastAPI
├── schemas.py     # Esquemas Pydantic
└── services.py    # Lógica de negocio
```

Registrar el router en `main.py`:
```python
from backend.modules.<nuevo_modulo>.routers import router as nuevo_router
app.include_router(nuevo_router, prefix=settings.api_v1_prefix)
```

## Estructura de un nuevo módulo frontend

```
frontend/modulos/<nuevo_modulo>/
├── app_module.py           # Blueprint Flask
└── templates/<nuevo_modulo>/
    └── *.html              # Templates Jinja2
```

Registrar el blueprint en `frontend/app.py`:
```python
from modulos.<nuevo_modulo>.app_module import nuevo_bp
app.register_blueprint(nuevo_bp)
```
