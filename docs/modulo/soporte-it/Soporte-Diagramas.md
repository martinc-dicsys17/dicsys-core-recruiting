# Diagramas y Diseño - Módulo de Soporte

---

## 1. DIAGRAMA DE SECUENCIA: Crear Ticket

```
Usuario          Frontend         FastAPI         BD
  │                 │               │              │
  │─ Click Crear ──→│               │              │
  │                 │               │              │
  │                 │─ POST /tickets│              │
  │                 │──────────────→│              │
  │                 │               │              │
  │                 │               │─ Validar ───→│
  │                 │               │              │
  │                 │               │─ INSERT ────→│
  │                 │               │              │
  │                 │               │← ID ────────│
  │                 │               │              │
  │                 │← JSON ────────│              │
  │                 │               │              │
  │← Redirigir ────│               │              │
  │                 │               │              │
```

---

## 2. DIAGRAMA DE SECUENCIA: Cambiar Estado Mantenimiento

```
Usuario          Frontend         FastAPI         BD
  │                 │               │              │
  │─ Click Notif ──→│               │              │
  │                 │               │              │
  │                 │─ POST /mant/{id}/cambiar-estado
  │                 │──────────────→│              │
  │                 │               │              │
  │                 │               │─ Validar ───→│
  │                 │               │              │
  │                 │               │─ UPDATE ────→│
  │                 │               │              │
  │                 │               │─ INSERT ────→│ (MantenimientoEvento)
  │                 │               │              │
  │                 │               │← OK ────────│
  │                 │               │              │
  │                 │← JSON ────────│              │
  │                 │               │              │
  │← Toast Verde ──│               │              │
  │                 │               │              │
  │                 │─ GET /dashboard/metrics
  │                 │──────────────→│              │
  │                 │               │              │
  │                 │               │─ SELECT ───→│
  │                 │               │              │
  │                 │               │← Datos ────│
  │                 │               │              │
  │                 │← HTML ────────│              │
  │                 │               │              │
  │← Tabla Actualizada
  │                 │               │              │
```

---

## 3. DIAGRAMA DE SECUENCIA: Alta de Empleado

```
Técnico          Frontend         FastAPI         BD
  │                 │               │              │
  │─ Formulario ───→│               │              │
  │                 │               │              │
  │                 │─ POST /procesar_hrbp
  │                 │──────────────→│              │
  │                 │               │              │
  │                 │               │─ Validar ───→│
  │                 │               │              │
  │                 │               │─ INSERT ────→│ (HistorialActivo)
  │                 │               │              │
  │                 │               │─ UPDATE ────→│ (StockItem)
  │                 │               │              │
  │                 │               │─ UPDATE ────→│ (Ticket)
  │                 │               │              │
  │                 │               │← OK ────────│
  │                 │               │              │
  │                 │← Redirigir ───│              │
  │                 │               │              │
  │← Kanban ───────│               │              │
  │                 │               │              │
```

---

## 4. DIAGRAMA DE COMPONENTES

```
┌─────────────────────────────────────────────────────────┐
│                    FRONTEND LAYER                       │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │  Dashboard   │  │   Tickets    │  │    Stock     │ │
│  │  (HTMX)      │  │  (Kanban)    │  │ (Inventario) │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │         Alpine.js (Estado Local)                │  │
│  │  - dashboardManager()                           │  │
│  │  - notificarMantenimiento()                     │  │
│  │  - Toast notifications                         │  │
│  └──────────────────────────────────────────────────┘  │
│                                                         │
└─────────────────────────────────────────────────────────┘
                         ↓ HTTP/JSON
┌─────────────────────────────────────────────────────────┐
│                    API LAYER (FastAPI)                 │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │   Routers    │  │   Schemas    │  │ Validación   │ │
│  │  (Endpoints) │  │  (Pydantic)  │  │ (Pydantic)   │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │         Dependencias                            │  │
│  │  - get_current_user()                           │  │
│  │  - get_db()                                     │  │
│  └──────────────────────────────────────────────────┘  │
│                                                         │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│              BUSINESS LOGIC LAYER                       │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │         SoporteService                          │  │
│  │  - crear_ticket()                               │  │
│  │  - cambiar_estado()                             │  │
│  │  - crear_stock_item()                           │  │
│  │  - crear_historial()                            │  │
│  │  - cambiar_estado_mantenimiento()               │  │
│  │  - dashboard_metrics()                          │  │
│  └──────────────────────────────────────────────────┘  │
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │         Utilidades                              │  │
│  │  - limpiar_datos()                              │  │
│  │  - _tiempo_relativo()                           │  │
│  └──────────────────────────────────────────────────┘  │
│                                                         │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│              DATA ACCESS LAYER                          │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │   Ticket     │  │  StockItem   │  │  Historial   │ │
│  │   (Model)    │  │   (Model)    │  │   (Model)    │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
│                                                         │
│  ┌──────────────┐                                      │
│  │Mantenimiento │                                      │
│  │  Evento      │                                      │
│  │  (Model)     │                                      │
│  └──────────────┘                                      │
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │         SQLAlchemy ORM                          │  │
│  │  - Session management                           │  │
│  │  - Query building                               │  │
│  │  - Relationship loading                         │  │
│  └──────────────────────────────────────────────────┘  │
│                                                         │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│              DATABASE LAYER (PostgreSQL)               │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │soporte_      │  │soporte_      │  │soporte_      │ │
│  │tickets       │  │stock         │  │historial_    │ │
│  │              │  │              │  │activo        │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
│                                                         │
│  ┌──────────────┐                                      │
│  │soporte_      │                                      │
│  │mantenimiento │                                      │
│  │_evento       │                                      │
│  └──────────────┘                                      │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 5. DIAGRAMA DE FLUJO: Máquina de Estados Mantenimiento

```
                    ┌─────────────────┐
                    │   PROGRAMADO    │ (inicial)
                    │ (fecha_proximo_  │
                    │  mantenimiento)  │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │ Técnico hace     │
                    │ click "Notificar"│
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │ PRIMER_AVISO     │
                    │ (notificación 1) │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │ Empleado no      │
                    │ responde en X    │
                    │ días             │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │ SEGUNDO_AVISO    │
                    │ (notificación 2) │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │ Aún no responde  │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │ INFORMAR_LIDER   │
                    │ (escalar)        │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │ Líder autoriza   │
                    │ mantenimiento    │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │ EN_EJECUCION     │
                    │ (en curso)       │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │ Mantenimiento    │
                    │ completado       │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │ REPARADO         │
                    │ (fecha_proximo_  │
                    │  mantenimiento   │
                    │  += 6 meses)     │
                    └──────────────────┘

Transiciones alternativas:
- PAUSADO (desde cualquier estado)
- CANCELADO (desde cualquier estado)
- DESECHADO (desde EN_EJECUCION)
```

---

## 6. DIAGRAMA DE FLUJO: Alta de Empleado

```
┌─────────────────────────────────────────────────────────┐
│ 1. Empleado ingresa al sistema                          │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│ 2. Técnico crea ticket "Alta Empleado"                  │
│    - Selecciona empleado                                │
│    - Selecciona equipo principal                        │
│    - Selecciona periféricos                             │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│ 3. Técnico completa formulario de entrega               │
│    - Evalúa estado físico (matriz 1-4)                  │
│    - Sube fotos de evidencia                            │
│    - Sube acuerdo de entrega FIRMADO                    │
│    - Registra periféricos entregados                    │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│ 4. Sistema registra historial                           │
│    - POST /api/v1/soporte/historial                     │
│    - Crea HistorialActivo (tipo="Alta")                 │
│    - Guarda matriz de estado                            │
│    - Guarda fotos                                       │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│ 5. Sistema actualiza equipo                             │
│    - PUT /api/v1/soporte/stock/{id}                     │
│    - estado = "asignado"                                │
│    - asignado_id = empleado.id                          │
│    - detalles_estado = matriz                           │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│ 6. Sistema cierra ticket                                │
│    - PUT /api/v1/soporte/tickets/{id}/estado            │
│    - estado = "resuelto"                                │
│    - resolucion = datos embebidos                       │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│ 7. Empleado recibe equipo                               │
│    - Equipo está asignado                               │
│    - Historial registrado                               │
│    - Fotos y acuerdo guardados                          │
└─────────────────────────────────────────────────────────┘
```

---

## 7. DIAGRAMA DE FLUJO: Baja de Empleado

```
┌─────────────────────────────────────────────────────────┐
│ 1. Empleado se va de la empresa                         │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│ 2. Técnico crea ticket "Baja Empleado"                  │
│    - Selecciona empleado                                │
│    - Sistema busca equipos asignados                    │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│ 3. Técnico recibe equipo                                │
│    - Evalúa estado físico (matriz 1-4)                  │
│    - Sube fotos de evidencia                            │
│    - Sube acuerdo de devolución FIRMADO                 │
│    - Registra daños/detalles                            │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│ 4. Sistema registra historial                           │
│    - POST /api/v1/soporte/historial                     │
│    - Crea HistorialActivo (tipo="Baja")                 │
│    - Guarda matriz de estado FINAL                      │
│    - Guarda fotos                                       │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│ 5. Sistema libera equipo                                │
│    - PUT /api/v1/soporte/stock/{id}                     │
│    - estado = "disponible"                              │
│    - asignado_id = NULL                                 │
│    - detalles_estado = matriz FINAL                     │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│ 6. Sistema cierra ticket                                │
│    - PUT /api/v1/soporte/tickets/{id}/estado            │
│    - estado = "resuelto"                                │
│    - resolucion = datos embebidos                       │
└────────────────────┬────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────┐
│ 7. Equipo vuelve a disponible                           │
│    - Puede ser asignado a otro empleado                 │
│    - Historial completo guardado                        │
│    - Fotos y acuerdo guardados                          │
└─────────────────────────────────────────────────────────┘
```

---

## 8. MATRIZ DE ESTADO FÍSICO

```
Escala de evaluación (1-4):

1 = Excelente
   - Sin daños visibles
   - Funciona perfectamente
   - Limpio

2 = Bueno
   - Daños menores (rayones, abolladuras)
   - Funciona correctamente
   - Limpieza normal

3 = Regular
   - Daños moderados (grietas, partes sueltas)
   - Funciona con limitaciones
   - Necesita limpieza

4 = Malo
   - Daños graves (rotura, no funciona)
   - No funciona o funciona parcialmente
   - Muy sucio

Componentes evaluados:
- Pantalla
- Carcasa/Estética
- Batería
- Puertos/Conectividad
- Teclado/Trackpad
- Audio/Cámara
- Estado General
```

---

## 9. ESTRUCTURA DE DATOS: HistorialActivo

```json
{
  "id": "uuid",
  "equipo_id": "uuid",
  "colaborador_id": "uuid",
  "responsable_id": "uuid",
  "fecha_hora": "2026-03-05T15:30:00",
  "tipo_evento": "Alta|Baja|Mantenimiento Preventivo|Reparacion",
  "notas_adicionales": "string",
  "matriz_estado": {
    "pantalla": 1,
    "carcasa": 1,
    "bateria": 1,
    "puertos": 1,
    "teclado_trackpad": 1,
    "audio_camara": 1,
    "estado_general": 1
  },
  "evidencia_fotografica": {
    "foto_superior": "url",
    "foto_inferior": "url",
    "foto_trasero": "url",
    "foto_adicional_1": "url",
    "foto_adicional_2": "url",
    "foto_acuerdo": "url",
    "fotos_factura": ["url1", "url2"],
    "fotos_evidencias": ["url1", "url2"]
  },
  "costo_reparacion": 0.0,
  "origen_refaccion": "stock|comprada",
  "refacciones": "string"
}
```

---

## 10. ESTRUCTURA DE DATOS: MantenimientoEvento

```json
{
  "id": "uuid",
  "stock_item_id": "uuid",
  "usuario_id": "uuid",
  "estado_anterior": "programado|primer_aviso|...",
  "estado_nuevo": "programado|primer_aviso|...",
  "fecha_hora": "2026-03-05T15:30:00",
  "notas": "Notificación enviada al colaborador"
}
```

