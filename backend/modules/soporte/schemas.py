"""
Schemas Pydantic para el módulo de Soporte Técnico (v28.0).
"""

import re
import uuid
from datetime import datetime
from typing import Annotated, Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator

# Tipo anotado que convierte UUID→str automáticamente (patrón del proyecto)
StrUUID = Annotated[str, BeforeValidator(lambda v: str(v) if isinstance(v, uuid.UUID) else v)]

# ─── Configuración Maestras ────────────────────────────────────────


class EstadoBase(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)
    clave: str = Field(..., min_length=1, max_length=100)
    color: Optional[str] = Field(None, max_length=50)

    @field_validator("color")
    @classmethod
    def validar_color(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not re.match(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$", v):
            raise ValueError("Color debe ser un valor hexadecimal válido (#RGB, #RRGGBB o #RRGGBBAA)")
        return v


class EstadoResponse(EstadoBase):
    id: StrUUID
    model_config = ConfigDict(from_attributes=True)


class MarcaResponse(BaseModel):
    id: StrUUID
    nombre: str
    model_config = ConfigDict(from_attributes=True)


class MarcaListResponse(BaseModel):
    items: List[MarcaResponse]
    total: int


class ActivoTipoBase(BaseModel):
    nombre: str
    clave: str
    requiere_especificaciones: bool = False
    frecuencia_mantenimiento_meses: int = 0
    activo: bool = True


class ActivoTipoCreate(ActivoTipoBase):
    pass


class ActivoTipoResponse(ActivoTipoBase):
    id: StrUUID
    model_config = ConfigDict(from_attributes=True)


class ActivoTipoListResponse(BaseModel):
    items: List[ActivoTipoResponse]
    total: int


# ─── Categorías ────────────────────────────────────────────────────


class CategoriaSimpleResponse(BaseModel):
    id: StrUUID
    nombre_display: str
    nombre_normalizado: str
    tipo_ticket_asociado: str
    model_config = ConfigDict(from_attributes=True)


class CategoriaResponse(CategoriaSimpleResponse):
    subcategorias: List["SubcategoriaResponse"] = []
    model_config = ConfigDict(from_attributes=True)


class SubcategoriaResponse(BaseModel):
    id: StrUUID
    categoria_id: StrUUID
    nombre_display: str
    categoria: Optional[CategoriaSimpleResponse] = None
    model_config = ConfigDict(from_attributes=True)


# ─── Matriz de Estado y Evidencias ─────────────────────────────────

# Valores permitidos para la matriz de estado físico
VALORES_MATRIZ_ESTADO = ["Excelente", "Bueno", "Regular", "Malo", "No aplica"]


class MatrizEstadoBase(BaseModel):
    pantalla: Optional[str] = None
    teclado: Optional[str] = None
    bateria: Optional[str] = None
    carcasa_superior: Optional[str] = None
    carcasa_inferior: Optional[str] = None
    touchpad: Optional[str] = None
    puertos: Optional[str] = None
    cargador: Optional[str] = None

    @field_validator(
        "pantalla", "teclado", "bateria", "carcasa_superior", "carcasa_inferior", "touchpad", "puertos", "cargador"
    )
    @classmethod
    def validar_estado_componente(cls, v: Optional[str]) -> Optional[str]:
        """Valida que el valor sea uno de los permitidos."""
        if v is None:
            return v
        if v not in VALORES_MATRIZ_ESTADO:
            raise ValueError(f"Debe ser uno de: {', '.join(VALORES_MATRIZ_ESTADO)}")
        return v


class MatrizEstadoResponse(MatrizEstadoBase):
    id: StrUUID
    model_config = ConfigDict(from_attributes=True)


class EvidenciaResponse(BaseModel):
    id: StrUUID
    url: str
    tipo: str
    categoria: str = "general"
    model_config = ConfigDict(from_attributes=True)


# ─── Tickets ───────────────────────────────────────────────────────


class TicketCreateSchema(BaseModel):
    titulo: str = Field(..., min_length=3, max_length=200)
    descripcion: Optional[str] = None
    prioridad: str = "media"
    subcategoria_id: UUID
    solicitante_id: UUID
    asignado_id: Optional[UUID] = None
    estado_id: Optional[UUID] = None
    activo_id: Optional[UUID] = None
    colaborador_id: Optional[UUID] = None
    tipo_operacion: Optional[str] = None
    fecha_programada: Optional[datetime] = None
    # Campos proceso de alta IT
    modalidad_trabajo: Optional[str] = None
    requiere_nextcloud: bool = False
    listas_correo: Optional[str] = None
    necesita_computadora: bool = False
    gama_computadora: Optional[str] = None
    cliente_servicio: Optional[str] = None
    # Sistemas a habilitar en el alta (claves de SISTEMAS_DISPONIBLES)
    sistemas_habilitados: Optional[List[str]] = None


class TicketReparacionCreate(TicketCreateSchema):
    activo_id: UUID
    diagnostico: Optional[str] = None
    matriz_entrada: Optional[MatrizEstadoBase] = None


class TicketAltaBajaCreate(TicketCreateSchema):
    colaborador_id: UUID
    tipo_operacion: str
    entrega_kit_bienvenida: bool = False
    matriz_estado: Optional[MatrizEstadoBase] = None
    modalidad_trabajo: Optional[str] = None
    requiere_nextcloud: bool = False
    listas_correo: Optional[str] = None
    necesita_computadora: bool = False
    gama_computadora: Optional[str] = None
    cliente_servicio: Optional[str] = None


class TicketMantenimientoCreate(TicketCreateSchema):
    activo_id: UUID
    mantenimiento_id: Optional[UUID] = None
    is_preventivo: bool = True
    fecha_programada: Optional[datetime] = None


# Schema para autocompletar datos del colaborador al crear ticket de alta
class ColaboradorAltaInfo(BaseModel):
    id: StrUUID
    nombre: str
    apellido: str
    dni: Optional[int] = None
    telefono_personal: Optional[str] = None
    email_personal: Optional[str] = None
    email_corporativo: Optional[str] = None
    puesto: Optional[str] = None
    seniority: Optional[str] = None
    departamento: Optional[str] = None
    lider: Optional[str] = None
    lider_email: Optional[str] = None
    cliente_servicio: Optional[str] = None
    fecha_alta: Optional[str] = None
    dir_laboral_provincia: Optional[str] = None
    dir_laboral_localidad: Optional[str] = None
    dir_laboral_calle: Optional[str] = None
    dir_laboral_numero: Optional[str] = None
    dir_laboral_piso: Optional[str] = None
    dir_laboral_departamento: Optional[str] = None
    dir_laboral_codigo_postal: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class EmpleadoRel(BaseModel):
    id: StrUUID
    nombre: str
    apellido: str
    model_config = ConfigDict(from_attributes=True)


# ─── Activos IT ────────────────────────────────────────────────────


class ActivoCreate(BaseModel):
    nombre: str
    tipo_id: UUID
    marca_id: Optional[UUID] = None
    marca: Optional[str] = None
    modelo: Optional[str] = None
    numero_serie: Optional[str] = None
    numero_inventario: Optional[str] = None
    procesador: Optional[str] = None
    memoria: Optional[str] = None
    disco_principal: Optional[str] = None
    disco_secundario: Optional[str] = None
    mac_ethernet: Optional[str] = None
    mac_wifi: Optional[str] = None
    estado: str = "disponible"
    asignado_id: Optional[UUID] = None
    fecha_compra: Optional[datetime] = None
    fecha_fin_garantia: Optional[datetime] = None
    notas: Optional[str] = None


class ActivoUpdate(BaseModel):
    nombre: Optional[str] = None
    tipo_id: Optional[UUID] = None
    marca_id: Optional[UUID] = None
    marca: Optional[str] = None
    modelo: Optional[str] = None
    numero_serie: Optional[str] = None
    numero_inventario: Optional[str] = None
    procesador: Optional[str] = None
    memoria: Optional[str] = None
    disco_principal: Optional[str] = None
    disco_secundario: Optional[str] = None
    mac_ethernet: Optional[str] = None
    mac_wifi: Optional[str] = None
    estado: Optional[str] = None
    asignado_id: Optional[UUID] = None
    fecha_fin_garantia: Optional[datetime] = None
    notas: Optional[str] = None


class ActivoResponse(BaseModel):
    id: StrUUID
    nombre: str
    tipo_rel: Optional[ActivoTipoResponse] = None
    marca_rel: Optional[MarcaResponse] = None
    modelo: Optional[str] = None
    numero_serie: Optional[str] = None
    numero_inventario: Optional[str] = None
    estado: str
    asignado_id: Optional[StrUUID] = None
    asignado_nombre: Optional[str] = None
    asignado_rel: Optional[EmpleadoRel] = None
    fecha_fin_garantia: Optional[datetime] = None
    procesador: Optional[str] = None
    memoria: Optional[str] = None
    disco_principal: Optional[str] = None
    disco_secundario: Optional[str] = None
    mac_ethernet: Optional[str] = None
    mac_wifi: Optional[str] = None
    notas: Optional[str] = None
    matriz_estado: Optional[MatrizEstadoResponse] = None
    tipo_display: Optional[str] = None
    marca_nombre: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="after")
    def resolve_asignado(self) -> "ActivoResponse":
        if self.asignado_rel:
            self.asignado_nombre = f"{self.asignado_rel.apellido}, {self.asignado_rel.nombre}"
            self.asignado_id = self.asignado_rel.id
        return self


class ActivoListResponse(BaseModel):
    items: List[ActivoResponse]
    total: int


# ─── Tickets ───────────────────────────────────────────────────────


class TicketResponse(BaseModel):
    id: StrUUID
    numero: int
    tipo_ticket: str
    titulo: str
    descripcion: Optional[str] = None
    prioridad: str
    estado_id: StrUUID
    estado_rel: Optional[EstadoResponse] = None
    subcategoria: Optional[SubcategoriaResponse] = None
    solicitante_id: StrUUID
    solicitante: Optional[EmpleadoRel] = None
    asignado_id: Optional[StrUUID] = None
    asignado: Optional[EmpleadoRel] = None
    es_falla: bool = False
    resolucion: Optional[str] = None
    created_at: datetime
    created_by: Optional[str] = None

    # Campos específicos de TicketReparacion y TicketMantenimiento
    activo_id: Optional[StrUUID] = None
    activo: Optional[ActivoResponse] = None
    diagnostico: Optional[str] = None

    # Campos específicos de TicketAltaBaja
    colaborador_id: Optional[StrUUID] = None
    colaborador: Optional[EmpleadoRel] = None
    tipo_operacion: Optional[str] = None
    entrega_kit_bienvenida: bool = False
    matriz_estado_id: Optional[StrUUID] = None
    matriz_estado: Optional[MatrizEstadoResponse] = None
    # Campos proceso de alta IT
    modalidad_trabajo: Optional[str] = None
    requiere_nextcloud: bool = False
    listas_correo: Optional[str] = None
    necesita_computadora: bool = False
    gama_computadora: Optional[str] = None
    cliente_servicio: Optional[str] = None
    # Datos extendidos del colaborador desde nómina (solo lectura)
    colaborador_info: Optional[Dict] = None

    # Evidencias del ticket
    evidencias: List[EvidenciaResponse] = []

    # Pedido de compra vinculado (si existe)
    pedido_compra: Optional["PedidoCompraResponse"] = None

    model_config = ConfigDict(from_attributes=True)


class TicketListResponse(BaseModel):
    items: List[TicketResponse]
    total: int
    stats: Optional[Dict[str, int]] = None


class KanbanColumn(BaseModel):
    id: StrUUID
    clave: str
    nombre: str
    color: Optional[str] = None
    tickets: List[TicketResponse]


class KanbanResponse(BaseModel):
    kanban: Dict[str, List[KanbanColumn]]  # Aquí 'kanban' tiene 'columnas'
    stats: Dict[str, int]


# ─── Insumos y Stock ───────────────────────────────────────────────


class InsumoCreate(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=150)
    descripcion: Optional[str] = Field(None, max_length=255)
    stock_actual: int = Field(0, ge=0)
    stock_minimo: int = Field(0, ge=0)
    unidad_medida: str = Field("unidades", max_length=20)
    categoria_id: Optional[UUID] = None


class InsumoUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=2, max_length=150)
    descripcion: Optional[str] = Field(None, max_length=255)
    stock_minimo: Optional[int] = Field(None, ge=0)
    unidad_medida: Optional[str] = Field(None, max_length=20)
    categoria_id: Optional[UUID] = None


class AjusteStockSchema(BaseModel):
    cantidad: int
    motivo: str = Field("Ajuste manual de stock", max_length=255)


class CategoriaCreate(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=100)
    tipo_ticket_asociado: str = Field("generico", max_length=20)
    parent_id: Optional[UUID] = None


class CategoriaUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=2, max_length=100)
    tipo_ticket_asociado: Optional[str] = Field(None, max_length=20)


class InsumoResponse(BaseModel):
    id: StrUUID
    nombre: str
    descripcion: Optional[str] = None
    stock_actual: int = 0
    stock_minimo: int = 0
    unidad_medida: str = "unidades"
    categoria_id: Optional[StrUUID] = None
    model_config = ConfigDict(from_attributes=True)


class TicketInsumoCreate(BaseModel):
    insumo_id: UUID
    cantidad: int = 1
    generar_pedido_compra: bool = False


class TicketInsumoResponse(BaseModel):
    id: StrUUID
    insumo: InsumoResponse
    cantidad: int
    generar_pedido_compra: bool
    pedido_compra_id: Optional[StrUUID] = None
    model_config = ConfigDict(from_attributes=True)


class MovimientoInsumoCreate(BaseModel):
    insumo_id: UUID
    tipo: str
    cantidad: int
    activo_id: Optional[UUID] = None
    empleado_id: Optional[UUID] = None
    empleado_asignador_id: Optional[UUID] = None
    motivo: Optional[str] = None


# ─── Pedidos de Compra ─────────────────────────────────────────────


class PedidoEstadoResponse(BaseModel):
    id: StrUUID
    nombre: str
    clave: str
    color: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class PedidoPresupuestoResponse(BaseModel):
    id: StrUUID
    proveedor: Optional[str] = None
    url_archivo: Optional[str] = None
    articulo_descripcion: Optional[str] = None
    monto: Optional[float] = None
    es_seleccionado: bool = False
    es_obligatorio: bool = True
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class PedidoAprobacionResponse(BaseModel):
    id: StrUUID
    departamento_id: Optional[StrUUID] = None
    aprobador_id: Optional[StrUUID] = None
    aprobador: Optional[EmpleadoRel] = None
    estado: str
    fecha_decision: Optional[datetime] = None
    observaciones: Optional[str] = None
    orden_aprobacion: int = 1
    model_config = ConfigDict(from_attributes=True)


class PedidoCompraResponse(BaseModel):
    id: StrUUID
    numero: str
    tipo_pedido: str
    descripcion: Optional[str] = None
    monto_estimado: Optional[float] = None
    monto_final: Optional[float] = None
    estado_id: Optional[StrUUID] = None
    estado_rel: Optional[PedidoEstadoResponse] = None
    fecha_solicitud: datetime
    fecha_recepcion: Optional[datetime] = None
    solicitante_id: Optional[StrUUID] = None
    solicitante: Optional[EmpleadoRel] = None
    ticket_id: Optional[StrUUID] = None
    insumo_id: Optional[StrUUID] = None
    insumo_nombre: Optional[str] = None
    cantidad_solicitada: int = 0
    cantidad_recibida: int = 0
    notas: Optional[str] = None
    requiere_doble_aprobacion: bool = False
    presupuestos: List[PedidoPresupuestoResponse] = []
    aprobaciones: List[PedidoAprobacionResponse] = []
    created_at: datetime

    @model_validator(mode="after")
    def resolve_insumo(self) -> "PedidoCompraResponse":
        return self

    model_config = ConfigDict(from_attributes=True)


class PedidoCompraListResponse(BaseModel):
    items: List[PedidoCompraResponse]
    total: int


class PedidoPresupuestoCreate(BaseModel):
    proveedor: Optional[str] = Field(None, max_length=200)
    articulo_descripcion: Optional[str] = None
    monto: Optional[float] = None
    es_obligatorio: bool = True


# ─── Historial de Activos ──────────────────────────────────────────

TIPOS_EVENTO_HISTORIAL = ["Alta", "Baja", "Reparacion", "Mantenimiento Preventivo"]


class HistorialActivoCreate(BaseModel):
    """Schema para registrar un evento técnico desde el endpoint.
    responsable_id se resuelve internamente desde el JWT (no viene del frontend)."""

    activo_id: UUID
    colaborador_id: Optional[UUID] = None
    tipo_evento: str = Field(..., min_length=1, max_length=50)
    notas_adicionales: Optional[str] = Field(None, max_length=1000)
    pedido_compra_id: Optional[UUID] = None
    matriz_estado: Optional[MatrizEstadoBase] = None

    @field_validator("tipo_evento")
    @classmethod
    def validar_tipo_evento(cls, v: str) -> str:
        if v not in TIPOS_EVENTO_HISTORIAL:
            raise ValueError(f"Debe ser uno de: {', '.join(TIPOS_EVENTO_HISTORIAL)}")
        return v


class HistorialActivoResponse(BaseModel):
    id: StrUUID
    activo_id: StrUUID
    tipo_evento: str
    fecha_hora: datetime
    notas_adicionales: Optional[str] = None
    colaborador_nombre: Optional[str] = None
    responsable_nombre: Optional[str] = None
    pedido_compra_id: Optional[StrUUID] = None
    estado_pantalla: Optional[str] = None
    estado_carcasa: Optional[str] = None
    estado_bateria: Optional[str] = None
    estado_puertos: Optional[str] = None
    estado_teclado_trackpad: Optional[str] = None
    estado_audio_camara: Optional[str] = None
    evidencias: Optional[List[Dict[str, Any]]] = []

    model_config = ConfigDict(from_attributes=True)


# Resolver forward references de Pydantic v2
CategoriaResponse.model_rebuild()
TicketResponse.model_rebuild()
PedidoCompraResponse.model_rebuild()
