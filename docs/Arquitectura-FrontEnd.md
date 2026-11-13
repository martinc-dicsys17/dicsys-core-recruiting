# Arquitectura Frontend - Dicsys Core

> **Legacy.** Es el frontend de Flask + HTMX + Alpine que corre hoy. Las pantallas nuevas ya no se hacen acá:
> se desarrollan en Vue 3 siguiendo a Blacklist (ver `frontend-vue/README.md` y la regla en `CLAUDE.md`). La SPA convive
> con este frontend; este documento rige solo para las pantallas legacy existentes, que se migran únicamente cuando se
> pida. Plan general de migración: [`update-techs-v2-final.md`](../update-techs-v2-final.md).

## Estructura de directorios

```
frontend/
├── app.py                          # App Flask principal (factory pattern)
├── Dockerfile                      # Imagen Docker (uv sync --frozen)
├── pyproject.toml                  # Dependencias Python
├── uv.lock                         # Versiones fijadas (uv)
└── modulos/
    ├── __init__.py
    ├── core/
    │   ├── app_module.py           # Blueprint: login, logout, dashboard, profile, health
    │   └── templates/core/
    │       ├── base.html           # Template base con Tailwind + Alpine.js
    │       ├── login.html
    │       ├── dashboard.html
    │       └── profile.html
    ├── usuarios/
    │   ├── app_module.py           # Blueprint: CRUD usuarios
    │   └── templates/usuarios/
    │       ├── list.html
    │       ├── form.html
    │       └── partials/table.html
    └── permisos/
        ├── app_module.py           # Blueprint: gestión grupos/permisos
        └── templates/permisos/
            ├── grupos.html
            └── partials/grupos_grid.html
```

## Patrón modular

Cada módulo tiene:
- `app_module.py` - Blueprint Flask con rutas
- `templates/<modulo>/` - Templates Jinja2 específicos

## Stack tecnológico

- **Flask**: Framework web Python
- **HTMX**: Interactividad sin JavaScript complejo
- **Alpine.js**: Reactividad ligera en el cliente
- **Tailwind CSS**: Estilos utility-first
- **httpx**: Cliente HTTP para llamadas al backend

## Comunicación con Backend

El frontend se comunica con el backend FastAPI via HTTP:

```python
# frontend/app.py
def api_request(method, endpoint, data=None, token=None):
    url = f"{API_URL}/api/v1{endpoint}"
    headers = {'Content-Type': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    
    with httpx.Client(timeout=10.0) as client:
        response = client.request(method, url, json=data, headers=headers)
        return response.json(), response.status_code
```

## Sesiones

- El token JWT se almacena en `session['token']`
- Los datos del usuario en `session['user']`
- Decorador `@login_required` protege rutas

## Variables de entorno

| Variable | Descripción |
|----------|-------------|
| `SECRET_KEY` | Clave para sesiones Flask |
| `DEBUG` | Modo debug |
| `API_URL` | URL del backend (http://backend:5000) |
| `FLASK_PORT` | Puerto del servidor (default: 80) |

## Rutas principales

| Ruta | Módulo | Descripción |
|------|--------|-------------|
| `/` | core | Redirect a dashboard o login |
| `/login` | core | Página de login |
| `/logout` | core | Cerrar sesión |
| `/dashboard` | core | Panel principal |
| `/profile` | core | Perfil del usuario |
| `/health` | core | Health check |
| `/usuarios` | usuarios | Listado de usuarios |
| `/usuarios/nuevo` | usuarios | Crear usuario |
| `/usuarios/<id>` | usuarios | Editar usuario |
| `/permisos/grupos` | permisos | Gestión de grupos |
