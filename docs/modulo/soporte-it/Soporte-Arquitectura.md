# Arquitectura del Módulo de Soporte Técnico

**Versión**: 2.0  
**Última actualización**: Marzo 23, 2026  
**Autor**: Equipo de Desarrollo Dicsys

---

## 1. VISIÓN GENERAL

El módulo de Soporte Técnico es un sistema completo de gestión de tickets y activos IT que permite:

- 🎫 **Gestión de Tickets**: Crear, asignar, seguir y resolver solicitudes de soporte
- 💻 **Gestión de Activos IT**: Inventario de equipos individuales (notebooks, monitores, periféricos)
- 📦 **Gestión de Insumos**: Control de stock de consumibles y refacciones
- 📋 **Historial de Activos**: Registro inmutable de eventos (Alta, Baja, Mantenimiento, Reparación)
- 🔧 **Mantenimiento Preventivo**: Máquina de estados para programar y ejecutar mantenimiento
- 👥 **Integración RRHH**: Vinculación con empleados para asignación de equipos

---

## 2. ARQUITECTURA DE CAPAS

```
┌─────────────────────────────────────────────────────────────┐
│                    FRONTEND (Flask + HTMX)                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │  Dashboard   │  │   Tickets    │  │    Stock     │      │
│  │  (Centro de  │  │   (Kanban)   │  │  (Inventario)│      │
│  │   Mando)     │  │              │  │              │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                            ↓ HTTP/JSON
┌─────────────────────────────────────────────────────────────┐
│                  API REST (FastAPI)                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Routers    │  │   Schemas    │  │  Validación  │      │
│  │  (Endpoints) │  │  (Pydantic)  │  │  (Pydantic)  │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│              LÓGICA DE NEGOCIO (Services)                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Tickets    │  │    Stock     │  │  Historial   │      │
│  │   Service    │  │   Service    │  │   Service    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│              MODELOS DE DATOS (SQLAlchemy)                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   Ticket     │  │    Activo    │  │  Historial   │      │
│  │              │  │              │  │   Activo     │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│  ┌──────────────┐                                           │
│  │ Mantenimiento│                                           │
│  │   Evento     │                                           │
│  └──────────────┘                                           │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│              BASE DE DATOS (PostgreSQL)                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │soporte_      │  │soporte_      │  │soporte_      │      │
│  │tickets       │  │activos       │  │historial_    │      │
│  │              │  │              │  │activo        │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│  ┌──────────────┐                                           │
│  │soporte_      │                                           │
│  │mantenimiento │                                           │
│  │_evento       │                                           │
│  └──────────────┘                                           │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. FLUJO DE DATOS

### 3.1 Crear Ticket

```
Usuario (Frontend)
    ↓
POST /soporte/tickets/crear (Flask)
    ↓
Validar datos (Pydantic)
    ↓
POST /api/v1/soporte/tickets (FastAPI)
    ↓
SoporteService.crear_ticket()
    ├─ Generar número secuencial
    ├─ Crear instancia Ticket
    ├─ Guardar en BD
    └─ Retornar ticket.to_dict()
    ↓
Respuesta JSON
    ↓
Redirigir a Kanban
```

### 3.2 Cambiar Estado de Mantenimiento

```
Usuario (Frontend) - Click "Notificar"
    ↓
notificarMantenimiento(id, name)
    ├─ Fetch POST /api/v1/soporte/mantenimiento/{id}/cambiar-estado
    └─ Body: {estado_nuevo: "primer_aviso", notas: "..."}
    ↓
FastAPI Endpoint
    ├─ Validar activo existe
    ├─ Validar estado_nuevo es válido
    └─ Llamar SoporteService.cambiar_estado_mantenimiento()
    ↓
SoporteService.cambiar_estado_mantenimiento()
    ├─ Obtener Activo
    ├─ Guardar estado_anterior
    ├─ Actualizar estado_mantenimiento
    ├─ Crear MantenimientoEvento (auditoría)
    ├─ Commit a BD
    └─ Retornar {evento, activo}
    ↓
Toast notification (verde)
    ↓
HTMX reload de tabla
    ├─ GET /soporte/dashboard/metrics
    └─ Renderizar dashboard_metrics.html
    ↓
Tabla actualizada con nuevo estado
```

### 3.3 Registrar Historial de Activo (Alta/Baja)

```
Usuario (Frontend) - Formulario Alta/Baja
    ↓
POST /soporte/tickets/{id}/procesar_hrbp
    ├─ Validar ticket existe
    ├─ Subir evidencias (fotos)
    ├─ Validar acuerdo obligatorio
    └─ Preparar payload
    ↓
POST /api/v1/soporte/historial
    ↓
SoporteService.crear_historial()
    ├─ Validar equipo existe
    ├─ Crear HistorialActivo
    ├─ Si es BAJA: liberar equipo (estado=disponible)
    ├─ Si es ALTA: asignar equipo (estado=asignado)
    ├─ Guardar matriz de estado físico
    └─ Commit a BD
    ↓
PUT /api/v1/soporte/stock/{id}
    ├─ Actualizar estado
    ├─ Actualizar asignado_id
    └─ Guardar detalles_estado
    ↓
PUT /api/v1/soporte/tickets/{id}/estado
    ├─ Cambiar estado a "resuelto"
    ├─ Guardar resolución con datos embebidos
    └─ Commit a BD
    ↓
Redirigir a Kanban
```

---

## 4. MODELOS DE DATOS

### 4.1 Diagrama ER

```
┌─────────────────────┐
│   core_usuarios     │
├─────────────────────┤
│ id (PK)             │
│ email               │
│ nombre              │
│ apellido            │
│ activo              │
└─────────────────────┘
         ↑
         │ (1:N)
         │
    ┌────┴────┐
    │          │
    │          │
┌───┴──────────┴──┐
│  soporte_       │
│  tickets        │
├─────────────────┤
│ id (PK)         │
│ numero          │
│ titulo          │
│ estado          │
│ prioridad       │
│ categoria       │
│ solicitante_id  │ ──→ core_usuarios
│ asignado_id     │ ──→ core_usuarios
│ colaborador_id  │ ──→ nomina_empleados
│ activo_id       │ ──→ soporte_activos
│ deleted_at      │
└─────────────────┘

┌─────────────────────┐
│  nomina_empleados   │
├─────────────────────┤
│ id (PK)             │
│ nombre              │
│ apellido            │
│ dni                 │
│ activo              │
└─────────────────────┘
         ↑
         │ (1:N)
         │
┌────────┴────────┐
│                 │
│                 │
┌─────────────────┴──┐
│  soporte_activos   │
├────────────────────┤
│ id (PK)            │
│ nombre             │
│ tipo               │
│ marca              │
│ modelo             │
│ numero_serie       │
│ numero_inventario  │
│ estado             │
│ asignado_id        │ ──→ nomina_empleados
│ estado_mantenimiento
│ fecha_proximo_mant │
│ deleted_at         │
└────────────────────┘
         ↑
         │ (1:N)
         │
┌────────┴──────────────────┐
│                           │
│                           │
┌──────────────────────────┐│
│ soporte_historial_activo ││
├──────────────────────────┤│
│ id (PK)                  ││
│ activo_id (FK)           ││
│ colaborador_id (FK)      ││
│ responsable_id (FK)      ││
│ fecha_hora               ││
│ tipo_evento              ││
│ estado_pantalla          ││
│ estado_carcasa           ││
│ estado_bateria           ││
│ estado_puertos           ││
│ estado_teclado_trackpad  ││
│ estado_audio_camara      ││
│ estado_general           ││
│ foto_superior            ││
│ foto_inferior            ││
│ foto_acuerdo             ││
│ costo_reparacion         ││
│ refacciones              ││
└──────────────────────────┘│
                            │
┌───────────────────────────┘
│
│
┌──────────────────────────────┐
│ soporte_mantenimiento_evento │
├──────────────────────────────┤
│ id (PK)                      │
│ activo_id (FK)               │
│ usuario_id (FK)              │
│ estado_anterior              │
│ estado_nuevo                 │
│ fecha_hora                   │
│ notas                        │
└──────────────────────────────┘

┌─────────────────────┐
│  soporte_insumos    │
├─────────────────────┤
│ id (PK)             │
│ nombre              │
│ categoria           │
│ descripcion         │
│ stock_actual        │
│ stock_minimo        │
│ unidad              │
│ deleted_at          │
└─────────────────────┘
         ↑
         │ (1:N)
         │
┌────────┴──────────────────┐
│ soporte_consumo_insumo    │
├───────────────────────────┤
│ id (PK)                   │
│ insumo_id (FK)            │
│ activo_id (FK)            │
│ empleado_id (FK)          │
│ usuario_id (FK)           │
│ cantidad                  │
│ motivo                    │
│ fecha_consumo             │
│ deleted_at                │
└───────────────────────────┘
```

### 4.2 Relaciones

| Tabla | Relación | Tabla Destino | Tipo | Notas |
|-------|----------|---------------|------|-------|
| soporte_tickets | solicitante_id | core_usuarios | N:1 | Usuario que crea ticket |
| soporte_tickets | asignado_id | core_usuarios | N:1 | Técnico asignado |
| soporte_tickets | colaborador_id | nomina_empleados | N:1 | Empleado afectado |
| soporte_tickets | activo_id | soporte_activos | N:1 | Equipo relacionado |
| soporte_activos | asignado_id | nomina_empleados | N:1 | Empleado asignado |
| soporte_historial_activo | activo_id | soporte_activos | N:1 | Equipo del evento |
| soporte_historial_activo | colaborador_id | nomina_empleados | N:1 | Empleado del evento |
| soporte_historial_activo | responsable_id | core_usuarios | N:1 | Técnico que ejecuta |
| soporte_mantenimiento_evento | activo_id | soporte_activos | N:1 | Equipo en mantenimiento |
| soporte_mantenimiento_evento | usuario_id | core_usuarios | N:1 | Usuario que cambia estado |
| soporte_consumo_insumo | insumo_id | soporte_insumos | N:1 | Insumo consumido |
| soporte_consumo_insumo | activo_id | soporte_activos | N:1 | Equipo donde se usó |
| soporte_consumo_insumo | empleado_id | nomina_empleados | N:1 | Empleado que recibió |
| soporte_consumo_insumo | usuario_id | core_usuarios | N:1 | Usuario que registró |

---

## 5. MÁQUINA DE ESTADOS

### 5.1 Estados de Ticket

```
                    ┌─────────────┐
                    │   ABIERTO   │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │ EN_PROGRESO │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  RESUELTO   │
                    └─────────────┘

                    ┌─────────────┐
                    │ CANCELADO   │ (desde cualquier estado)
                    └─────────────┘
```

### 5.2 Estados de Mantenimiento

```
┌──────────────┐
│ PROGRAMADO   │ (inicial)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│ PRIMER_AVISO │ (notificación enviada)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│SEGUNDO_AVISO │ (segunda notificación)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│INFORMAR_LIDER│ (escalar a líder)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│EN_EJECUCION  │ (mantenimiento en curso)
└──────┬───────┘
       │
       ├─────────────────┐
       │                 │
       ▼                 ▼
┌──────────────┐  ┌──────────────┐
│  REPARADO    │  │  DESECHADO   │
└──────────────┘  └──────────────┘

┌──────────────┐
│  PAUSADO     │ (desde cualquier estado)
└──────────────┘

┌──────────────┐
│  CANCELADO   │ (desde cualquier estado)
└──────────────┘
```

### 5.3 Estados de Stock

```
┌──────────────┐
│ DISPONIBLE   │ (inicial)
└──────┬───────┘
       │
       ▼
┌──────────────┐
│  ASIGNADO    │ (asignado a empleado)
└──────┬───────┘
       │
       ├─────────────────┐
       │                 │
       ▼                 ▼
┌──────────────┐  ┌──────────────┐
│EN_REPARACION │  │DISPONIBLE    │ (devuelto)
└──────┬───────┘  └──────────────┘
       │
       ├─────────────────┐
       │                 │
       ▼                 ▼
┌──────────────┐  ┌──────────────┐
│ DISPONIBLE   │  │DADO_DE_BAJA  │
└──────────────┘  └──────────────┘
```

---

## 6. FLUJOS DE NEGOCIO

### 6.1 Flujo: Alta de Empleado

```
1. Empleado ingresa al sistema
   ↓
2. Técnico crea ticket "Alta Empleado"
   ├─ Selecciona empleado
   ├─ Selecciona equipo principal
   └─ Selecciona periféricos
   ↓
3. Técnico completa formulario de entrega
   ├─ Evalúa estado físico (matriz 1-4)
   ├─ Sube fotos de evidencia
   ├─ Sube acuerdo de entrega firmado
   └─ Registra periféricos entregados
   ↓
4. Sistema registra historial
   ├─ Crea HistorialActivo (tipo="Alta")
   ├─ Guarda matriz de estado
   ├─ Guarda fotos
   └─ Actualiza Activo (estado=asignado)
   ↓
5. Sistema cierra ticket
   ├─ Cambia estado a "resuelto"
   ├─ Guarda resolución con datos embebidos
   └─ Notifica al solicitante
   ↓
6. Empleado recibe equipo
```

### 6.2 Flujo: Baja de Empleado

```
1. Empleado se va de la empresa
   ↓
2. Técnico crea ticket "Baja Empleado"
   ├─ Selecciona empleado
   └─ Sistema busca equipos asignados
   ↓
3. Técnico recibe equipo
   ├─ Evalúa estado físico (matriz 1-4)
   ├─ Sube fotos de evidencia
   ├─ Sube acuerdo de devolución firmado
   └─ Registra daños/detalles
   ↓
4. Sistema registra historial
   ├─ Crea HistorialActivo (tipo="Baja")
   ├─ Guarda matriz de estado FINAL
   ├─ Guarda fotos
   └─ Libera Activo (estado=disponible)
   ↓
5. Sistema cierra ticket
   ├─ Cambia estado a "resuelto"
   ├─ Guarda resolución con datos embebidos
   └─ Notifica al solicitante
   ↓
6. Equipo vuelve a disponible
```

### 6.3 Flujo: Mantenimiento Preventivo

```
1. Sistema detecta equipo próximo a mantenimiento
   ├─ fecha_proximo_mantenimiento <= hoy + 15 días
   └─ estado_mantenimiento = "programado"
   ↓
2. Dashboard muestra equipo en tabla "Próximos a Mantenimiento"
   ├─ Botón "Notificar" disponible
   └─ Columna "Estado" muestra "Programado"
   ↓
3. Técnico hace click en "Notificar"
   ├─ Frontend: POST /api/v1/soporte/mantenimiento/{id}/cambiar-estado
   ├─ Body: {estado_nuevo: "primer_aviso", notas: "Notificación enviada"}
   └─ Sistema crea MantenimientoEvento (auditoría)
   ↓
4. Estado cambia a "primer_aviso"
   ├─ Tabla se recarga vía HTMX
   ├─ Columna "Estado" muestra "Primer Aviso"
   └─ Toast verde: "Notificación enviada"
   ↓
5. Si empleado no confirma en X días
   ├─ Técnico hace click en "Segundo Aviso"
   ├─ Estado cambia a "segundo_aviso"
   └─ Sistema crea nuevo MantenimientoEvento
   ↓
6. Si aún no confirma
   ├─ Técnico hace click en "Informar Líder"
   ├─ Estado cambia a "informar_lider"
   └─ Sistema notifica a líder de área
   ↓
7. Líder autoriza mantenimiento
   ├─ Técnico ejecuta mantenimiento
   ├─ Estado cambia a "en_ejecucion"
   └─ Registra HistorialActivo (tipo="Mantenimiento Preventivo")
   ↓
8. Mantenimiento completado
   ├─ Estado cambia a "reparado"
   ├─ Actualiza fecha_proximo_mantenimiento (+6 meses)
   └─ Sistema crea MantenimientoEvento final
```

---

## 7. COMPONENTES CLAVE

### 7.1 SoporteService

**Responsabilidades**:
- Lógica de negocio para tickets, stock, historial
- Validaciones de integridad
- Transacciones multi-paso
- Generación de números secuenciales

**Métodos principales**:
- `crear_ticket()` - Crear nuevo ticket
- `cambiar_estado()` - Cambiar estado de ticket
- `crear_stock_item()` - Crear equipo
- `crear_historial()` - Registrar evento de activo
- `cambiar_estado_mantenimiento()` - Cambiar estado de mantenimiento
- `dashboard_metrics()` - Obtener métricas para Centro de Mando

### 7.2 Routers

**Responsabilidades**:
- Exponer endpoints REST
- Validar autenticación/autorización
- Parsear parámetros
- Retornar respuestas JSON

**Grupos**:
- Tickets (11 endpoints)
- Stock (8 endpoints)
- Historial (3 endpoints)
- Mantenimiento (3 endpoints)
- Utilidades (3 endpoints)

### 7.3 Schemas

**Responsabilidades**:
- Validar datos de entrada (Pydantic)
- Serializar datos de salida
- Documentar estructura de datos

**Tipos**:
- `*Create` - Para crear recursos
- `*Update` - Para actualizar recursos
- `*Response` - Para retornar datos

### 7.4 Modelos

**Responsabilidades**:
- Definir estructura de tablas
- Relaciones entre entidades
- Métodos `to_dict()` para serialización

**Modelos**:
- `Ticket` - Solicitudes de soporte
- `Activo` - Inventario de equipos IT individuales (notebooks, monitores, etc.)
- `Insumo` - Inventario de consumibles y refacciones
- `ConsumoInsumo` - Registro de uso de insumos
- `HistorialActivo` - Registro inmutable de eventos
- `MantenimientoEvento` - Auditoría de cambios de estado
- `ActivoTipo` - Catálogo de tipos de equipos
- `TicketCategoriaPersonalizada` - Categorías personalizadas de tickets

---

## 8. INTEGRACIÓN CON OTROS MÓDULOS

### 8.1 Módulo de Usuarios (core_usuarios)

- **Relación**: Tickets vinculan solicitante y asignado
- **Uso**: Autenticación, autorización, información de usuario
- **Endpoints**: `/api/v1/soporte/usuarios-lista`

### 8.2 Módulo de Nómina (nomina_empleados)

- **Relación**: Tickets y Stock vinculan colaboradores
- **Uso**: Información de empleados, asignación de equipos
- **Endpoints**: `/api/v1/soporte/colaboradores-lista`

### 8.3 Módulo de Permisos

- **Relación**: Control de acceso a endpoints
- **Uso**: Verificar permisos de usuario
- **Endpoints**: Protegidos con `@login_required`

---

## 9. SEGURIDAD

### 9.1 Autenticación

- JWT tokens en header `Authorization: Bearer <token>`
- Validación en `get_current_user()` dependency
- Tokens con expiración

### 9.2 Autorización

- Soft delete: usuarios no ven registros eliminados
- Filtrado por usuario: cada usuario ve solo sus tickets
- Roles: (futuro) técnico, admin, usuario

### 9.3 Validación de Datos

- Pydantic schemas validan entrada
- Limpieza de strings (trim, colapsar espacios)
- Restricciones de longitud

### 9.4 Protección de Archivos

- Subida de imágenes a `/data/files/support-img/`
- Nombres de archivo hasheados
- Validación de tipo MIME

---

## 10. PERFORMANCE

### 10.1 Optimizaciones Actuales

- Eager loading con `joinedload()` para relaciones
- Índices en campos frecuentes (estado, asignado_id)
- Caché de usuarios en sesión

### 10.2 Mejoras Futuras

- Paginación en listados
- Caché con Redis
- Índices adicionales en BD
- Compresión de imágenes

---

## 11. ESCALABILIDAD

### 11.1 Horizontal

- Stateless API (sin sesión en servidor)
- BD centralizada (PostgreSQL)
- Archivos en `/data/files/` (compartido)

### 11.2 Vertical

- Índices en BD
- Caché en memoria
- Compresión de datos

---

## 12. MONITOREO Y LOGGING

### 12.1 Actual

- Logs de FastAPI (INFO, WARNING, ERROR)
- Logs de Flask (INFO, WARNING, ERROR)
- Health check en `/health`

### 12.2 Futuro

- Logging estructurado (JSON)
- Métricas con Prometheus
- Trazas distribuidas con Jaeger
- Alertas en Slack

