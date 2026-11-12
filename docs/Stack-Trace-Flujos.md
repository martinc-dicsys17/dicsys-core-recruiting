# Stack Trace - Documentación de Flujos

Este documento describe el flujo completo de las operaciones principales del sistema, mostrando cómo los datos viajan desde el usuario hasta la base de datos y viceversa.

## Arquitectura General

```
┌─────────────┐     ┌─────────────────┐     ┌─────────────────┐     ┌──────────────┐
│   Usuario   │────▶│    Frontend     │────▶│     Backend     │────▶│  PostgreSQL  │
│   (Browser) │◀────│  Flask + HTMX   │◀────│    FastAPI      │◀────│   Database   │
└─────────────┘     └─────────────────┘     └─────────────────┘     └──────────────┘
     :80                  :80                    :5000                  :5432
```

---

## FLUJO 1: Listar Usuarios (Lectura)

### Diagrama de Secuencia

```
┌──────────┐          ┌──────────────────┐          ┌──────────────────┐          ┌─────────────────┐          ┌────────────┐
│  Usuario │          │     Browser      │          │  Flask Frontend  │          │ FastAPI Backend │          │ PostgreSQL │
│  (Real)  │          │   (HTMX/JS)      │          │    :3003         │          │     :5000       │          │   :5432    │
└────┬─────┘          └────────┬─────────┘          └────────┬─────────┘          └────────┬────────┘          └─────┬──────┘
     │                         │                             │                             │                        │
     │  1. Click "Usuarios"    │                             │                             │                        │
     │────────────────────────▶│                             │                             │                        │
     │                         │                             │                             │                        │
     │                         │  2. GET /usuarios           │                             │                        │
     │                         │  (HX-Request: true)         │                             │                        │
     │                         │────────────────────────────▶│                             │                        │
     │                         │                             │                             │                        │
     │                         │                             │  3. api_request('GET',      │                        │
     │                         │                             │     '/usuarios')            │                        │
     │                         │                             │────────────────────────────▶│                        │
     │                         │                             │                             │                        │
     │                         │                             │                             │  4. SELECT * FROM      │
     │                         │                             │                             │  core_usuarios         │
     │                         │                             │                             │───────────────────────▶│
     │                         │                             │                             │                        │
     │                         │                             │                             │  5. ResultSet          │
     │                         │                             │                             │◀───────────────────────│
     │                         │                             │                             │                        │
     │                         │                             │  6. JSON Response           │                        │
     │                         │                             │  {usuarios: [...]}          │                        │
     │                         │                             │◀────────────────────────────│                        │
     │                         │                             │                             │                        │
     │                         │  7. HTML Partial            │                             │                        │
     │                         │  (tabla usuarios)           │                             │                        │
     │                         │◀────────────────────────────│                             │                        │
     │                         │                             │                             │                        │
     │  8. Renderiza tabla     │                             │                             │                        │
     │◀────────────────────────│                             │                             │                        │
     │                         │                             │                             │                        │
```

### Stack Trace Detallado

#### PASO 1-2: Usuario → Browser → Frontend
```
Usuario hace click en menú "Usuarios"
    ↓
Browser envía request HTTP:
    GET http://localhost/usuarios
    Headers:
        HX-Request: true (si es HTMX)
        Cookie: session=<token>
```

#### PASO 3: Frontend Flask - Recepción
```python
# frontend/modulos/usuarios/app_module.py

@usuarios_bp.route('')                          # ← Ruta: /usuarios
@login_required                                  # ← Verifica sesión
def list():
    api_request = get_api_request_func()        # ← Obtiene función helper
    token = session.get('token')                # ← Token JWT del usuario
    
    # Llamada al Backend
    data, _ = api_request('GET', '/usuarios', token=token)
```

#### PASO 4: Frontend → Backend (HTTP)
```python
# frontend/app.py - api_request()

def api_request(method, endpoint, data=None, token=None):
    url = f"{API_URL}/api/v1{endpoint}"         # ← http://backend:5000/api/v1/usuarios
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}'       # ← JWT Token
    }
    
    with httpx.Client(timeout=10.0) as client:
        response = client.get(url, headers=headers)
        return response.json(), response.status_code
```

#### PASO 5: Backend FastAPI - Router
```python
# backend/modules/usuarios/routers.py

@router.get("", response_model=UsuarioList)
async def listar_usuarios(
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(20, ge=1, le=100),
    activo: Optional[bool] = Query(None),
    db: Session = Depends(get_db)               # ← Inyección de dependencia DB
):
    resultado = UsuarioService.listar_usuarios(db, pagina, por_pagina, filtros)
    
    return UsuarioList(
        usuarios=[UsuarioResponse.model_validate(u) for u in resultado['usuarios']],
        total=resultado['total'],
        ...
    )
```

#### PASO 6: Backend - Service Layer
```python
# backend/modules/usuarios/services.py

class UsuarioService:
    @staticmethod
    def listar_usuarios(db: Session, pagina: int, por_pagina: int, filtros: Dict):
        query = db.query(Usuario)               # ← SQLAlchemy Query
        
        # Aplicar filtros
        if filtros.get('activo'):
            query = query.filter(Usuario.activo == filtros['activo'])
        
        # Paginación
        total = query.count()
        offset = (pagina - 1) * por_pagina
        usuarios = query.offset(offset).limit(por_pagina).all()
        
        return {'usuarios': usuarios, 'total': total, ...}
```

#### PASO 7: Backend - Database Layer
```python
# backend/database.py

def get_db():
    db = SessionLocal()                         # ← Crea sesión SQLAlchemy
    try:
        yield db                                # ← Inyecta en endpoint
    finally:
        db.close()                              # ← Cierra conexión

# SQL Generado:
# SELECT * FROM core_usuarios 
# ORDER BY created_at DESC 
# LIMIT 20 OFFSET 0
```

#### PASO 8: PostgreSQL
```sql
-- Tabla consultada
core_usuarios
    ├── id (UUID)
    ├── email (VARCHAR)
    ├── nombre (VARCHAR)
    ├── apellido (VARCHAR)
    ├── rol (VARCHAR)
    ├── activo (BOOLEAN)
    └── created_at (TIMESTAMP)
```

#### PASO 9-10: Respuesta de vuelta
```
PostgreSQL → SQLAlchemy (ORM Objects)
    ↓
Service → Router (UsuarioResponse models)
    ↓
FastAPI → JSON Response
    {
        "usuarios": [
            {"id": "uuid", "email": "user@mail.com", "nombre": "Juan", ...}
        ],
        "total": 15,
        "pagina": 1
    }
    ↓
Flask → Render Template
    render_template('usuarios/partials/table.html', usuarios=usuarios)
    ↓
Browser → HTMX swap HTML
    ↓
Usuario ve la tabla actualizada
```

---

## FLUJO 2: Crear Usuario (Escritura)

### Diagrama de Secuencia

```
┌──────────┐          ┌──────────────────┐          ┌──────────────────┐          ┌─────────────────┐          ┌────────────┐
│  Usuario │          │     Browser      │          │  Flask Frontend  │          │ FastAPI Backend │          │ PostgreSQL │
│  (Real)  │          │   (HTMX/JS)      │          │    :3003         │          │     :5000       │          │   :5432    │
└────┬─────┘          └────────┬─────────┘          └────────┬─────────┘          └────────┬────────┘          └─────┬──────┘
     │                         │                             │                             │                        │
     │  1. Llena formulario    │                             │                             │                        │
     │  y click "Guardar"      │                             │                             │                        │
     │────────────────────────▶│                             │                             │                        │
     │                         │                             │                             │                        │
     │                         │  2. POST /usuarios/nuevo    │                             │                        │
     │                         │  FormData: {email, pass...} │                             │                        │
     │                         │────────────────────────────▶│                             │                        │
     │                         │                             │                             │                        │
     │                         │                             │  3. Validar datos           │                        │
     │                         │                             │  Construir payload          │                        │
     │                         │                             │         │                   │                        │
     │                         │                             │         ▼                   │                        │
     │                         │                             │  4. api_request('POST',     │                        │
     │                         │                             │     '/usuarios', data)      │                        │
     │                         │                             │────────────────────────────▶│                        │
     │                         │                             │                             │                        │
     │                         │                             │                             │  5. Validar Schema     │
     │                         │                             │                             │  (Pydantic)            │
     │                         │                             │                             │         │              │
     │                         │                             │                             │         ▼              │
     │                         │                             │                             │  6. Hash password      │
     │                         │                             │                             │  (bcrypt)              │
     │                         │                             │                             │         │              │
     │                         │                             │                             │         ▼              │
     │                         │                             │                             │  7. INSERT INTO        │
     │                         │                             │                             │  core_usuarios         │
     │                         │                             │                             │───────────────────────▶│
     │                         │                             │                             │                        │
     │                         │                             │                             │  8. COMMIT + Return ID │
     │                         │                             │                             │◀───────────────────────│
     │                         │                             │                             │                        │
     │                         │                             │  9. JSON Response           │                        │
     │                         │                             │  {id, email, nombre...}     │                        │
     │                         │                             │◀────────────────────────────│                        │
     │                         │                             │                             │                        │
     │                         │  10. HX-Redirect            │                             │                        │
     │                         │  → /usuarios                │                             │                        │
     │                         │◀────────────────────────────│                             │                        │
     │                         │                             │                             │                        │
     │  11. Redirect + Flash   │                             │                             │                        │
     │  "Usuario creado"       │                             │                             │                        │
     │◀────────────────────────│                             │                             │                        │
     │                         │                             │                             │                        │
```

### Stack Trace Detallado

#### PASO 1-2: Usuario → Browser → Frontend
```
Usuario llena formulario:
    - Email: nuevo@usuario.com
    - Password: ********
    - Nombre: Juan
    - Apellido: Pérez
    - Rol: usuario
    
Click en "Guardar"
    ↓
Browser envía request HTTP:
    POST http://localhost/usuarios/nuevo
    Content-Type: application/x-www-form-urlencoded
    Body: email=nuevo@usuario.com&password=secret123&nombre=Juan&...
```

#### PASO 3: Frontend Flask - Recepción y Validación
```python
# frontend/modulos/usuarios/app_module.py

@usuarios_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
def create():
    if request.method == 'POST':
        api_request = get_api_request_func()
        token = session.get('token')
        
        # Construir payload desde form data
        data = {
            'email': request.form.get('email'),           # ← nuevo@usuario.com
            'password': request.form.get('password'),     # ← secret123
            'nombre': request.form.get('nombre'),         # ← Juan
            'apellido': request.form.get('apellido') or None,
            'dni': request.form.get('dni') or None,
            'telefono': request.form.get('telefono') or None,
            'avatar_url': request.form.get('avatar_url') or None,
            'rol': request.form.get('rol', 'usuario')     # ← usuario
        }
        
        # Llamada al Backend
        result, status = api_request('POST', '/usuarios', data, token=token)
```

#### PASO 4: Frontend → Backend (HTTP POST)
```python
# frontend/app.py - api_request()

def api_request(method, endpoint, data=None, token=None):
    url = "http://backend:5000/api/v1/usuarios"
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}'
    }
    
    with httpx.Client(timeout=10.0) as client:
        response = client.post(url, json=data, headers=headers)
        return response.json(), response.status_code

# Request enviado:
# POST /api/v1/usuarios
# {
#     "email": "nuevo@usuario.com",
#     "password": "secret123",
#     "nombre": "Juan",
#     "apellido": "Pérez",
#     "rol": "usuario"
# }
```

#### PASO 5: Backend FastAPI - Router + Validación Pydantic
```python
# backend/modules/usuarios/routers.py

@router.post("", response_model=UsuarioResponse, status_code=201)
async def crear_usuario(
    usuario_data: UsuarioCreate,                # ← Pydantic valida automáticamente
    db: Session = Depends(get_db),
    current_user_email: str = Depends(get_current_user_email)
):
    datos = usuario_data.model_dump()           # ← Convierte a dict
    usuario = UsuarioService.crear_usuario(db, datos, current_user_email)
    return UsuarioResponse.model_validate(usuario)
```

#### PASO 6: Validación Pydantic (Schema)
```python
# backend/modules/usuarios/schemas.py

class UsuarioCreate(BaseModel):
    email: EmailStr                             # ← Valida formato email
    password: str = Field(..., min_length=8)    # ← Mínimo 8 caracteres
    nombre: str = Field(..., min_length=2)      # ← Requerido, mín 2 chars
    apellido: Optional[str] = None
    dni: Optional[str] = None
    telefono: Optional[str] = None
    avatar_url: Optional[str] = None
    rol: RolEnum = RolEnum.usuario              # ← Enum: admin/usuario/moderador

# Si falla validación → HTTP 422 Unprocessable Entity
```

#### PASO 7: Backend - Service Layer (Lógica de Negocio)
```python
# backend/modules/usuarios/services.py

class UsuarioService:
    @staticmethod
    def crear_usuario(db: Session, datos: Dict, usuario_actual: str = None):
        try:
            password = datos.pop('password')    # ← Extrae password
            
            if usuario_actual:
                datos['updated_by'] = usuario_actual
            
            # Crear instancia del modelo
            usuario = Usuario(**datos)
            
            # Hash de password con bcrypt
            usuario.set_password(password)      # ← pwd_context.hash(password)
            
            # Persistir en DB
            db.add(usuario)
            db.commit()
            db.refresh(usuario)                 # ← Obtiene ID generado
            
            return usuario
            
        except IntegrityError as e:
            db.rollback()
            if 'email' in str(e.orig).lower():
                raise ValueError('El email ya está registrado')
            raise
```

#### PASO 8: Backend - Model Layer (ORM)
```python
# backend/modules/usuarios/models.py

class Usuario(Base):
    __tablename__ = 'core_usuarios'
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    nombre = Column(String(100), nullable=False)
    # ...
    
    def set_password(self, password: str):
        """Hash password con bcrypt"""
        self.password_hash = pwd_context.hash(password)
        # password_hash = "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.G..."
```

#### PASO 9: PostgreSQL - INSERT
```sql
-- SQL generado por SQLAlchemy
INSERT INTO core_usuarios 
    (id, email, password_hash, nombre, apellido, dni, telefono, avatar_url, rol, activo, created_at, updated_at, updated_by)
VALUES 
    ('550e8400-e29b-41d4-a716-446655440000',    -- UUID generado
     'nuevo@usuario.com',
     '$2b$12$LQv3c1yqBWVHxkd0LHAkCO...',        -- Password hasheado
     'Juan',
     'Pérez',
     NULL,
     NULL,
     NULL,
     'usuario',
     TRUE,
     '2026-01-19 10:30:00',
     '2026-01-19 10:30:00',
     'admin@sistema.com')
RETURNING id;

-- COMMIT
```

#### PASO 10-11: Respuesta de vuelta
```
PostgreSQL → Retorna registro insertado
    ↓
SQLAlchemy → Objeto Usuario con ID
    ↓
Service → Retorna Usuario
    ↓
Router → Serializa con UsuarioResponse
    {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "email": "nuevo@usuario.com",
        "nombre": "Juan",
        "apellido": "Pérez",
        "rol": "usuario",
        "activo": true,
        "created_at": "2026-01-19T10:30:00"
    }
    ↓
Flask Frontend → Verifica status 201
    if status in [200, 201]:
        return '', 200, {'HX-Redirect': url_for('usuarios.list')}
        flash('Usuario creado exitosamente', 'success')
    ↓
Browser (HTMX) → Detecta HX-Redirect
    ↓
Redirect automático a /usuarios
    ↓
Usuario ve listado actualizado con mensaje de éxito
```

---

## Resumen de Capas

| Capa | Tecnología | Responsabilidad |
|------|------------|-----------------|
| **Presentación** | Browser + HTMX | Interacción usuario, requests HTTP |
| **Frontend** | Flask + Jinja2 | Renderizado HTML, sesiones, routing |
| **API Gateway** | httpx | Comunicación Frontend ↔ Backend |
| **Backend API** | FastAPI | Endpoints REST, validación, auth |
| **Validación** | Pydantic | Schemas, tipos, constraints |
| **Negocio** | Services | Lógica de negocio, reglas |
| **ORM** | SQLAlchemy | Mapeo objeto-relacional |
| **Persistencia** | PostgreSQL | Almacenamiento de datos |

---

## Archivos Involucrados por Flujo

### Lectura (GET)
```
frontend/modulos/usuarios/app_module.py    → list()
frontend/app.py                            → api_request()
backend/modules/usuarios/routers.py        → listar_usuarios()
backend/modules/usuarios/services.py       → UsuarioService.listar_usuarios()
backend/modules/usuarios/models.py         → Usuario (ORM)
backend/database.py                        → get_db()
```

### Escritura (POST)
```
frontend/modulos/usuarios/app_module.py    → create()
frontend/app.py                            → api_request()
backend/modules/usuarios/routers.py        → crear_usuario()
backend/modules/usuarios/schemas.py        → UsuarioCreate (validación)
backend/modules/usuarios/services.py       → UsuarioService.crear_usuario()
backend/modules/usuarios/models.py         → Usuario.set_password()
backend/database.py                        → get_db(), commit()
```
