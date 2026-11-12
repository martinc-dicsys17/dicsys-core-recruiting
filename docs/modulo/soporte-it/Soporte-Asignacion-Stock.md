# Flujo de Asignación de Stock - Módulo de Soporte

## Resumen Ejecutivo

Este documento explica cómo funciona la asignación de equipos (notebooks) a empleados en el módulo de Soporte IT.

## Arquitectura del Flujo

```
┌─────────────────┐
│   FRONTEND      │
│  (Alpine.js)    │
└────────┬────────┘
         │
         │ POST /soporte/stock/{item_id}/editar
         │ Form Data: {
         │   estado: "asignado",
         │   asignado_id: "uuid-del-empleado",
         │   asignado_a: "Nombre Completo"
         │ }
         ▼
┌─────────────────┐
│   FLASK ROUTE   │
│  app_module.py  │
└────────┬────────┘
         │
         │ PUT /api/v1/soporte/stock/{item_id}
         │ JSON: {
         │   estado: "asignado",
         │   asignado_id: "uuid",
         │   asignado_a: "Nombre"
         │ }
         ▼
┌─────────────────┐
│  FASTAPI ROUTER │
│   routers.py    │
└────────┬────────┘
         │
         │ datos.model_dump(exclude_unset=True)
         │
         ▼
┌─────────────────┐
│    SERVICE      │
│  services.py    │
└────────┬────────┘
         │
         │ UPDATE soporte_stock
         │ SET asignado_id = ?, estado = ?
         │
         ▼
┌─────────────────┐
│   DATABASE      │
│   PostgreSQL    │
└─────────────────┘
```

## Componentes Clave

### 1. Frontend - Modal de Edición

**Archivo**: `frontend/modulos/soporte/templates/soporte/partials/modal_stock_item.html`

**Campos Críticos**:
```html
<!-- Hidden inputs que envían los datos al servidor -->
<input type="hidden" name="asignado_id" x-model="form.asignado_id">
<input type="hidden" name="asignado_a" x-model="form.asignado_a">

<!-- Dropdown de búsqueda de empleados -->
<input type="text" 
       x-model="form.asignado_a" 
       @focus="openSearchEmpleados = true"
       placeholder="Nombre completo o buscar empleado...">
```

**Estado Alpine.js**:
```javascript
form: {
    asignado_id: '',      // UUID del empleado (FK a nomina_empleados)
    asignado_a: '',       // Nombre completo del empleado (para display)
    estado: 'disponible'  // Estado del equipo
}
```

**Carga de Empleados**:
```javascript
async init() {
    // Cargar lista de empleados desde /soporte/empleados-lista
    const res = await fetch('/soporte/empleados-lista');
    const data = await res.json();
    this.usuarios_lista = data.empleados || [];
    window.empleados_lista = data.empleados || [];
}
```

**Selección de Empleado**:
```html
<div @click="form.asignado_id = emp.id; 
             form.asignado_a = emp.nombre; 
             openSearchEmpleados = false">
    <div x-text="emp.nombre"></div>
</div>
```

### 2. Flask Route - Proxy al Backend

**Archivo**: `frontend/modulos/soporte/app_module.py`

**Endpoint**: `POST /soporte/stock/<item_id>/editar`

```python
@soporte_bp.route('/stock/<item_id>/editar', methods=['POST'])
@login_required
def stock_editar(item_id):
    """Actualiza un item de stock."""
    api_request = get_api_request_func()
    token = session.get('token')
    
    # Extraer datos del formulario
    datos = {
        'estado': request.form.get('estado', 'disponible'),
        'asignado_id': request.form.get('asignado_id') or None,
        'asignado_a': request.form.get('asignado_a', '').strip() or None,
        # ... otros campos
    }
    
    # Llamar al backend FastAPI
    result, status = api_request('PUT', f'/soporte/stock/{item_id}', 
                                 data=datos, token=token)
    
    if status == 200:
        flash('Item actualizado', 'success')
    else:
        flash('Error al actualizar', 'error')
    
    return redirect(url_for('soporte.stock_list'))
```

### 3. FastAPI Router - Validación y Procesamiento

**Archivo**: `backend/modules/soporte/routers.py`

**Endpoint**: `PUT /api/v1/soporte/stock/{item_id}`

```python
@router.put("/stock/{item_id}")
async def actualizar_stock_item(
    item_id: str,
    datos: StockItemUpdate,
    db: Session = Depends(get_db),
):
    """Actualiza un item de stock existente."""
    # CRITICAL: Use exclude_unset instead of exclude_none
    # exclude_unset only excludes fields that weren't provided
    # exclude_none would prevent clearing asignado_id by setting it to None
    item = SoporteService.actualizar_stock_item(
        db, item_id, datos.model_dump(exclude_unset=True)
    )
    if not item:
        raise HTTPException(status_code=404, detail="Item no encontrado")
    return item.to_dict()
```

**Schema de Validación**:
```python
class StockItemUpdate(BaseModel):
    nombre: Optional[str] = None
    estado: Optional[str] = None
    asignado_id: Optional[str] = None  # UUID del empleado
    asignado_a: Optional[str] = None   # Nombre del empleado
    # ... otros campos
```

### 4. Service Layer - Lógica de Negocio

**Archivo**: `backend/modules/soporte/services.py`

**Método**: `actualizar_stock_item()`

```python
@staticmethod
def actualizar_stock_item(db: Session, item_id: str, datos: Dict[str, Any]) -> Optional[StockItem]:
    """Actualiza un item de stock existente."""
    from backend.modules.nomina.models import Empleado
    
    # Limpiar datos (remover strings vacíos, etc)
    datos = limpiar_datos(datos)
    
    # Buscar el item
    item = db.query(StockItem).filter(
        StockItem.id == uuid.UUID(item_id),
        StockItem.deleted_at.is_(None)
    ).first()
    
    if not item:
        return None
    
    # VALIDACIÓN CRÍTICA: Verificar que el empleado existe y está activo
    if 'asignado_id' in datos and datos['asignado_id']:
        try:
            asignado_uuid = uuid.UUID(datos['asignado_id'])
            empleado = db.query(Empleado).filter(
                Empleado.id == asignado_uuid,
                Empleado.deleted_at.is_(None),
                Empleado.activo == True
            ).first()
            if not empleado:
                raise ValueError(f"El empleado con ID {datos['asignado_id']} no existe o está inactivo")
        except ValueError as e:
            raise e
    
    # Actualizar campos
    campos = ['nombre', 'tipo', 'marca', 'modelo', 'estado', 'asignado_a', 'notas', ...]
    for campo in campos:
        if campo in datos:
            val = datos[campo]
            setattr(item, campo, val if val != '' else None)
    
    # Actualizar asignado_id (UUID)
    if 'asignado_id' in datos:
        item.asignado_id = uuid.UUID(datos['asignado_id']) if datos['asignado_id'] else None
    
    # Actualizar timestamps
    item.updated_at = datetime.utcnow()
    
    # Commit
    db.commit()
    db.refresh(item)
    
    return item
```

### 5. Modelo de Datos

**Archivo**: `backend/modules/soporte/models.py`

```python
class StockItem(Base):
    __tablename__ = "soporte_stock"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre = Column(String(200), nullable=False)
    tipo = Column(String(50), nullable=False)
    estado = Column(String(50), default='disponible')
    
    # Asignación a empleado
    asignado_id = Column(UUID(as_uuid=True), ForeignKey('nomina_empleados.id'), nullable=True)
    asignado_a = Column(String(255), nullable=True)  # Nombre para display
    
    # Relación con Empleado
    asignado = relationship("Empleado", foreign_keys=[asignado_id])
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)
```

## Flujo de Datos Detallado

### Paso 1: Usuario Abre Modal de Edición

1. Usuario hace clic en botón "Editar" de un notebook
2. Se ejecuta `openEditModal(item)` en Alpine.js
3. Se carga el formulario con los datos actuales del item
4. Se cargan los empleados disponibles desde `/soporte/empleados-lista`

### Paso 2: Usuario Busca y Selecciona Empleado

1. Usuario escribe en el campo "Asignado a"
2. Se abre dropdown con lista filtrada de empleados
3. Usuario hace clic en un empleado
4. Se actualiza `form.asignado_id` con el UUID del empleado
5. Se actualiza `form.asignado_a` con el nombre completo

### Paso 3: Usuario Cambia Estado y Guarda

1. Usuario selecciona estado "Asignado" en el dropdown
2. Usuario hace clic en "Guardar Cambios"
3. Se envía POST a `/soporte/stock/{item_id}/editar` con:
   ```
   estado=asignado
   asignado_id=550e8400-e29b-41d4-a716-446655440000
   asignado_a=Juan Pérez
   ```

### Paso 4: Flask Procesa y Reenvía al Backend

1. Flask recibe el POST
2. Extrae los datos del formulario
3. Hace PUT a `/api/v1/soporte/stock/{item_id}` con JSON:
   ```json
   {
     "estado": "asignado",
     "asignado_id": "550e8400-e29b-41d4-a716-446655440000",
     "asignado_a": "Juan Pérez"
   }
   ```

### Paso 5: FastAPI Valida y Procesa

1. FastAPI recibe el PUT
2. Valida el schema con Pydantic
3. Llama al servicio con `datos.model_dump(exclude_unset=True)`
4. El servicio actualiza la base de datos
5. Retorna el item actualizado

### Paso 6: Respuesta al Usuario

1. Flask recibe respuesta del backend
2. Muestra mensaje de éxito/error
3. Redirige a la lista de stock
4. Usuario ve el equipo actualizado con el empleado asignado

## Puntos Críticos de Implementación

### 1. Uso de `x-model` en lugar de `:value`

**PROBLEMA ANTERIOR**:
```html
<!-- ❌ INCORRECTO - No envía datos en POST -->
<input type="hidden" name="asignado_id" :value="form.asignado_id">
```

**SOLUCIÓN ACTUAL**:
```html
<!-- ✅ CORRECTO - Envía datos en POST -->
<input type="hidden" name="asignado_id" x-model="form.asignado_id">
```

**Razón**: Alpine.js `:value` solo actualiza el atributo HTML pero no el valor del input para el formulario. `x-model` crea un binding bidireccional que actualiza el valor real del input.

### 2. Uso de `exclude_unset=True` en lugar de `exclude_none=True`

**PROBLEMA ANTERIOR**:
```python
# ❌ INCORRECTO - No permite limpiar campos con None
datos.model_dump(exclude_none=True)
```

**SOLUCIÓN ACTUAL**:
```python
# ✅ CORRECTO - Permite limpiar campos con None
datos.model_dump(exclude_unset=True)
```

**Razón**: 
- `exclude_none=True`: Excluye todos los campos con valor `None`, incluso si el usuario quiso limpiar el campo
- `exclude_unset=True`: Solo excluye campos que no fueron enviados en la request, permite enviar `None` para limpiar

### 3. Validación de Empleado Activo

```python
# Verificar que el empleado existe y está activo
if 'asignado_id' in datos and datos['asignado_id']:
    empleado = db.query(Empleado).filter(
        Empleado.id == asignado_uuid,
        Empleado.deleted_at.is_(None),
        Empleado.activo == True
    ).first()
    if not empleado:
        raise ValueError("El empleado no existe o está inactivo")
```

### 4. Carga Asíncrona de Empleados

```javascript
// Cargar empleados al inicializar el componente
async init() {
    const res = await fetch('/soporte/empleados-lista');
    const data = await res.json();
    window.empleados_lista = data.empleados || [];
}

// Recargar si es necesario al abrir modal
async cargarEmpleadosSiEsNecesario() {
    if (!window.empleados_lista || window.empleados_lista.length === 0) {
        // Cargar empleados
    }
}
```

## Endpoints Relacionados

### GET /soporte/empleados-lista

**Propósito**: Obtener lista de empleados activos para asignar equipos

**Response**:
```json
{
  "empleados": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "nombre": "Juan Pérez",
      "codigo": "EMP001",
      "departamento": "IT"
    }
  ]
}
```

### PUT /api/v1/soporte/stock/{item_id}

**Propósito**: Actualizar un item de stock

**Request Body**:
```json
{
  "estado": "asignado",
  "asignado_id": "550e8400-e29b-41d4-a716-446655440000",
  "asignado_a": "Juan Pérez"
}
```

**Response**:
```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "nombre": "Lenovo ThinkPad",
  "estado": "asignado",
  "asignado_id": "550e8400-e29b-41d4-a716-446655440000",
  "asignado_a": "Juan Pérez",
  "asignado_nombre": "Juan Pérez"
}
```

## Debugging

### Logs en Frontend

```javascript
// En el submit del formulario
@submit="console.log('Form submit:', {
    asignado_id: form.asignado_id, 
    asignado_a: form.asignado_a, 
    estado: form.estado
})"
```

### Logs en Flask

```python
print(f"\n=== DEBUG STOCK EDITAR ===")
print(f"Item ID: {item_id}")
print(f"Form data completo: {dict(request.form)}")
print(f"asignado_id raw: '{request.form.get('asignado_id')}'")
print(f"asignado_a raw: '{request.form.get('asignado_a')}'")
print(f"estado raw: '{request.form.get('estado')}'")
print(f"=========================\n")
```

### Logs en Service

```python
logger.log_operation(
    operation="actualizar_stock_item_DEBUG",
    usuario_id="sistema",
    params={"item_id": item_id, "datos_recibidos": datos},
    result={},
    duration_ms=0
)
```

## Casos de Uso

### Caso 1: Asignar Notebook a Empleado Nuevo

1. Notebook está en estado "disponible"
2. Usuario abre modal de edición
3. Busca empleado "María García"
4. Selecciona empleado del dropdown
5. Cambia estado a "asignado"
6. Guarda cambios
7. Sistema actualiza:
   - `estado = 'asignado'`
   - `asignado_id = UUID de María`
   - `asignado_a = 'María García'`

### Caso 2: Cambiar Asignación de Notebook

1. Notebook está asignado a "Juan Pérez"
2. Usuario abre modal de edición
3. Busca empleado "Pedro López"
4. Selecciona nuevo empleado
5. Guarda cambios
6. Sistema actualiza:
   - `asignado_id = UUID de Pedro`
   - `asignado_a = 'Pedro López'`
   - Estado permanece "asignado"

### Caso 3: Liberar Notebook (Desasignar)

1. Notebook está asignado a un empleado
2. Usuario abre modal de edición
3. Cambia estado a "disponible"
4. Limpia el campo "Asignado a"
5. Guarda cambios
6. Sistema actualiza:
   - `estado = 'disponible'`
   - `asignado_id = NULL`
   - `asignado_a = NULL`

### Caso 4: Enviar a Reparación

1. Notebook está asignado a un empleado
2. Usuario abre modal de edición
3. Cambia estado a "en_reparacion"
4. Guarda cambios
5. Sistema actualiza:
   - `estado = 'en_reparacion'`
   - `asignado_id` permanece (para saber a quién devolver)
   - `asignado_a` permanece

## Mejoras Futuras

### 1. Validación en Frontend

```javascript
// Validar que si estado es "asignado", debe haber un empleado
if (form.estado === 'asignado' && !form.asignado_id) {
    alert('Debe seleccionar un empleado para asignar el equipo');
    return false;
}
```

### 2. Historial de Asignaciones

Crear tabla `soporte_asignaciones_historial` para trackear:
- Quién tuvo el equipo
- Cuándo se asignó
- Cuándo se desasignó
- Motivo del cambio

### 3. Notificaciones

Enviar email al empleado cuando se le asigna un equipo:
```python
if estado_cambio_a_asignado:
    enviar_email_asignacion(empleado.email, item.nombre)
```

### 4. Validación de Duplicados

Evitar que un empleado tenga múltiples notebooks asignados:
```python
notebooks_asignados = db.query(StockItem).filter(
    StockItem.asignado_id == empleado_id,
    StockItem.tipo == 'notebook',
    StockItem.estado == 'asignado'
).count()

if notebooks_asignados > 0:
    raise ValueError("El empleado ya tiene un notebook asignado")
```

## Conclusión

El flujo de asignación de stock funciona correctamente con los siguientes componentes clave:

1. **Frontend**: Alpine.js con `x-model` para binding bidireccional
2. **Flask**: Proxy que valida y reenvía requests al backend
3. **FastAPI**: Validación con Pydantic y `exclude_unset=True`
4. **Service**: Lógica de negocio con validaciones de empleado activo
5. **Database**: Foreign key a `nomina_empleados` con soft delete

Los bugs anteriores se resolvieron usando `x-model` en lugar de `:value` y `exclude_unset=True` en lugar de `exclude_none=True`.
