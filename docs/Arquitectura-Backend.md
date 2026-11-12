# Arquitectura Backend - Dicsys Core

## Estructura de directorios

```
backend/
├── database.py              # Configuración SQLAlchemy (engine, SessionLocal, Base)
├── dependencies.py          # Dependencias comunes de FastAPI
├── __init__.py
├── core/
│   ├── config.py            # Settings con Pydantic (env vars)
│   ├── email.py             # Servicio de email con SendGrid API
│   ├── exceptions.py        # Excepciones HTTP personalizadas
│   ├── utils.py             # Utilidades (UUID, datetime)
│   └── __init__.py
└── modules/
    ├── auth/
    │   ├── routers.py       # Endpoints: login, me, password, forgot/reset
    │   ├── schemas.py       # LoginRequest, TokenResponse, ProfileUpdate, etc.
    │   └── __init__.py
    ├── usuarios/
    │   ├── models.py        # Modelo Usuario (core_usuarios)
    │   ├── routers.py       # CRUD endpoints
    │   ├── schemas.py       # UsuarioCreate, UsuarioUpdate, UsuarioResponse
    │   ├── services.py      # UsuarioService (lógica de negocio)
    │   └── __init__.py
    └── permisos/
        ├── models.py        # Grupo, PermisoModulo, usuario_grupo (M2M)
        ├── routers.py       # Endpoints de grupos y permisos
        ├── schemas.py       # GrupoCreate, GrupoResponse, etc.
        ├── services.py      # GrupoService
        └── __init__.py
```

## Patrón de módulos

Cada módulo sigue la estructura:
- `models.py` - Modelos SQLAlchemy (tablas)
- `routers.py` - Endpoints FastAPI (APIRouter)
- `schemas.py` - Esquemas Pydantic (validación/serialización)
- `services.py` - Lógica de negocio (operaciones DB)

## Contrato de la API (lo que consume la SPA)

La SPA de v2 genera su cliente desde `/openapi.json`, así que lo que un endpoint declara tiene que ser lo que responde.
Los pilotos (`parametros` y `sincronizacion`) cumplen esto desde F07-P08; cada módulo se audita antes de su ola.

- **`response_model` en todo.** Nada de diccionarios sueltos: también los mensajes (`{"message": ...}`) y las
  respuestas de integraciones (los espacios de Webex) tienen su esquema.
- **Errores con forma estable** (`backend/core/errores.py`). Todo error es `{"detail": "texto en castellano"}`, para
  mostrar tal cual. El 422 de validación suma `errores`: `[{"campo": "nombre", "mensaje": "es obligatorio"}]`, para
  marcar cada campo del formulario. El OpenAPI declara ese 422 (`ErrorDeValidacion`) en todas las operaciones. Los
  demás códigos se declaran con `responses=responde(404, 409)`: el router declara 401 y 403, y cada endpoint los
  suyos. Un resultado que no es un error no se disfraza de 200: un proceso que no existe da 404, uno desactivado 409.
- **`operationId` escrito a mano, `<módulo>_<acción>`** (`parametros_listar`, `auth_login`): el cliente TypeScript lo
  usa como nombre de función (`parametrosListar()`). El que arma FastAPI cambia si se renombra la función o se mueve
  la ruta, y eso le rompe el código a la SPA. La lista de lo que consume la SPA está fija en
  `backend/tests/integration/test_contrato_pilotos.py` (F07-P09).
- **Ids de path como `uuid.UUID`.** Uno mal formado da 422 («Id: no es un identificador válido»), nunca 500.
- **Paginación uniforme** (`backend/core/paginacion.py`). Query: `pagina` (desde 1) y `por_pagina` (20 por defecto,
  hasta 100). Respuesta: `items`, `total`, `pagina`, `por_pagina` y `total_paginas`; el esquema hereda de
  `Pagina[T]` y puede sumar campos (las `categorias` de parámetros). El servicio devuelve la consulta y el router la
  pagina con `paginar()`.

## Tablas de base de datos

| Tabla | Descripción |
|-------|-------------|
| `core_usuarios` | Usuarios del sistema |
| `core_grupos` | Grupos de permisos |
| `core_permisos_modulo` | Permisos por módulo para cada grupo |
| `core_usuario_grupo` | Relación M2M usuarios-grupos |

## Dependencias principales

- **FastAPI**: Framework web async
- **SQLAlchemy**: ORM
- **Pydantic**: Validación de datos
- **PyJWT**: JWT tokens
- **bcrypt**: Hash de contraseñas
- **sendgrid**: Envío de emails
- **httpx**: Cliente HTTP async

La lista completa y las versiones están en `backend/pyproject.toml` y `backend/uv.lock`.

## Flujo de autenticación

1. `POST /api/v1/auth/login` → Valida credenciales → Retorna JWT
2. Endpoints protegidos leen `Authorization: Bearer <token>`
3. JWT contiene: `sub` (email), `user_id`, `rol`, `exp`

## Configuración

Todas las variables de entorno se cargan en `backend/core/config.py` usando Pydantic Settings:

```python
class Settings(BaseSettings):
    app_name: str
    debug: bool
    database_url: str
    jwt_secret_key: str
    sendgrid_api_key: str = ""
    # ...
    
    class Config:
        env_file = ".env"
```
