"""
Schemas Pydantic para Star Miles.
"""

import uuid
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ============ CATEGORIA DESAFIO ============


class CategoriaDesafioCreate(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=100)
    descripcion: Optional[str] = Field(None, max_length=255)
    color: Optional[str] = Field("#3B82F6", max_length=7)
    icono: Optional[str] = Field("star", max_length=50)

    @field_validator("color", mode="before")
    @classmethod
    def validar_color_hex(cls, v):
        if v is None:
            return "#3B82F6"
        import re

        if not re.match(r"^#[0-9a-fA-F]{6}$", v):
            raise ValueError("Color debe ser formato hex (#RRGGBB)")
        return v


class CategoriaDesafioUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=2, max_length=100)
    descripcion: Optional[str] = None
    color: Optional[str] = Field(None, max_length=7)
    icono: Optional[str] = Field(None, max_length=50)

    @field_validator("color", mode="before")
    @classmethod
    def validar_color_hex(cls, v):
        if v is None:
            return v
        import re

        if not re.match(r"^#[0-9a-fA-F]{6}$", v):
            raise ValueError("Color debe ser formato hex (#RRGGBB)")
        return v


class CategoriaDesafioResponse(BaseModel):
    id: str
    nombre: str
    descripcion: Optional[str]
    color: str
    icono: str
    created_at: datetime

    @field_validator("id", mode="before")
    @classmethod
    def convert_uuid(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    model_config = ConfigDict(from_attributes=True)


# ============ DESAFIO ============


class DesafioCreate(BaseModel):
    categoria_id: Optional[str] = None
    nombre: str = Field(..., min_length=2, max_length=150)
    descripcion: Optional[str] = None
    alcance: Optional[str] = Field(None, max_length=255)
    star_miles: int = Field(..., gt=0)
    fecha_inicio: Optional[date] = None
    fecha_vencimiento: Optional[date] = None
    activo: Optional[bool] = True
    inscripcion_unica_por_empleado: bool = False
    imagen_url: Optional[str] = Field(None, max_length=500)


class DesafioUpdate(BaseModel):
    categoria_id: Optional[str] = None
    nombre: Optional[str] = Field(None, min_length=2, max_length=150)
    descripcion: Optional[str] = None
    alcance: Optional[str] = None
    star_miles: Optional[int] = Field(None, gt=0)
    fecha_inicio: Optional[date] = None
    fecha_vencimiento: Optional[date] = None
    activo: Optional[bool] = None
    inscripcion_unica_por_empleado: Optional[bool] = None
    imagen_url: Optional[str] = None


class DesafioResponse(BaseModel):
    id: str
    categoria_id: Optional[str]
    categoria_nombre: Optional[str] = None
    nombre: str
    descripcion: Optional[str]
    alcance: Optional[str]
    star_miles: int
    fecha_inicio: Optional[date]
    fecha_vencimiento: Optional[date]
    activo: bool
    inscripcion_unica_por_empleado: bool
    imagen_url: Optional[str]
    vigente: bool = True
    total_inscriptos: int = 0
    total_completados: int = 0
    millas_distribuidas: int = 0
    created_at: datetime
    updated_at: datetime

    @field_validator("id", "categoria_id", mode="before")
    @classmethod
    def convert_uuid(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    model_config = ConfigDict(from_attributes=True)


class DesafioList(BaseModel):
    items: List[DesafioResponse]
    total: int
    pagina: int
    por_pagina: int
    total_paginas: int


# ============ INSCRIPCION DESAFIO ============


class InscripcionCreate(BaseModel):
    desafio_id: str
    comentario_solicitud: Optional[str] = None


class InscripcionAprobar(BaseModel):
    comentario_aprobador: Optional[str] = None


class InscripcionRechazar(BaseModel):
    comentario_aprobador: str = Field(..., min_length=3)


class InscripcionCancelar(BaseModel):
    comentario_aprobador: str = Field(..., min_length=3)


class InscripcionRevocar(BaseModel):
    comentario_aprobador: str = Field(..., min_length=3)


class InscripcionFinalizar(BaseModel):
    comentario_aprobador: Optional[str] = None


class InscripcionIncompleta(BaseModel):
    comentario_aprobador: str = Field(..., min_length=3)


class InscripcionResponse(BaseModel):
    id: str
    desafio_id: str
    desafio_nombre: str
    desafio_star_miles: int
    empleado_id: str
    empleado_nombre: str
    estado: str
    fecha_solicitud: datetime
    fecha_aprobacion: Optional[datetime]
    fecha_finalizacion: Optional[datetime]
    fecha_rechazo: Optional[datetime]
    aprobador_id: Optional[str]
    aprobador_nombre: Optional[str] = None
    comentario_solicitud: Optional[str]
    comentario_aprobador: Optional[str]
    created_at: datetime

    @field_validator("id", "desafio_id", "empleado_id", "aprobador_id", mode="before")
    @classmethod
    def convert_uuid(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    model_config = ConfigDict(from_attributes=True)


class InscripcionList(BaseModel):
    items: List[InscripcionResponse]
    total: int
    pagina: int
    por_pagina: int
    total_paginas: int


# ============ ITEM CANJE ============

# Tasa de conversión: 1 peso = 1 milla
TASA_PESOS_A_MILLAS = 1


class ItemCanjeCreate(BaseModel):
    tipo: str = Field("producto", pattern=r"^(producto|mercadolibre)$")
    nombre: str = Field(..., min_length=2, max_length=150)
    descripcion: Optional[str] = None
    star_miles_costo: Optional[int] = Field(None, ge=0)
    stock: Optional[int] = Field(None, ge=0)
    imagen_url: Optional[str] = Field(None, max_length=500)
    activo: Optional[bool] = True


class ItemCanjeUpdate(BaseModel):
    tipo: Optional[str] = Field(None, pattern=r"^(producto|mercadolibre)$")
    nombre: Optional[str] = Field(None, min_length=2, max_length=150)
    descripcion: Optional[str] = None
    star_miles_costo: Optional[int] = Field(None, ge=0)
    stock: Optional[int] = None
    imagen_url: Optional[str] = None
    activo: Optional[bool] = None


class ItemCanjeResponse(BaseModel):
    id: str
    tipo: str
    nombre: str
    descripcion: Optional[str]
    star_miles_costo: Optional[int] = None
    stock: Optional[int]
    imagen_url: Optional[str]
    activo: bool
    created_at: datetime
    updated_at: datetime

    @field_validator("id", mode="before")
    @classmethod
    def convert_uuid(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    model_config = ConfigDict(from_attributes=True)


class ItemCanjeList(BaseModel):
    items: List[ItemCanjeResponse]
    total: int
    pagina: int
    por_pagina: int
    total_paginas: int


# ============ CANJE ============


class CanjeCreate(BaseModel):
    item_id: str
    cantidad: int = Field(1, ge=1)
    comentario: Optional[str] = None
    mercadolibre_url: Optional[str] = Field(None, max_length=500)
    star_miles_calculado: Optional[int] = Field(None, ge=0)
    mercadolibre_precio: Optional[float] = Field(None, ge=0)


class CanjeAprobar(BaseModel):
    comentario: Optional[str] = None


class CanjeRechazar(BaseModel):
    comentario: str = Field(..., min_length=3)


class CanjeRechazarYReintegrar(BaseModel):
    comentario: str = Field(..., min_length=3)


class CanjeEntregar(BaseModel):
    comentario: Optional[str] = None


class CanjeResponse(BaseModel):
    id: str
    item_id: str
    item_nombre: str
    item_tipo: str = "producto"
    item_imagen_url: Optional[str] = None
    empleado_id: str
    empleado_nombre: str
    cantidad: int
    star_miles_total: int
    mercadolibre_url: Optional[str] = None
    mercadolibre_precio: Optional[float] = None
    estado: str
    fecha_solicitud: datetime
    fecha_aprobacion: Optional[datetime]
    fecha_entrega: Optional[datetime]
    fecha_rechazo: Optional[datetime]
    aprobador_id: Optional[str]
    aprobador_nombre: Optional[str] = None
    comentario: Optional[str]
    created_at: datetime

    @field_validator("id", "item_id", "empleado_id", "aprobador_id", mode="before")
    @classmethod
    def convert_uuid(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    @field_validator("mercadolibre_precio", mode="before")
    @classmethod
    def convert_decimal(cls, v):
        return float(v) if v is not None else None

    model_config = ConfigDict(from_attributes=True)


class CanjeList(BaseModel):
    items: List[CanjeResponse]
    total: int
    pagina: int
    por_pagina: int
    total_paginas: int


# ============ MERCADOLIBRE ============


class MercadoLibrePrecioResponse(BaseModel):
    item_id: str
    titulo: str
    precio: float
    moneda: str
    cotizacion_usd: Optional[float] = None
    precio_usd: Optional[float] = None
    star_miles: int
    url: str


class CalcularMillasRequest(BaseModel):
    precio: float = Field(..., gt=0, description="Precio en pesos argentinos")


class CalcularMillasResponse(BaseModel):
    precio_ars: float
    cotizacion_usd: float
    precio_usd: float
    star_miles: int


# ============ EMPLEADO STAR MILES ============


class EmpleadoStarMilesResponse(BaseModel):
    id: str
    empleado_id: str
    empleado_nombre: str
    millas_historicas: int
    millas_disponibles: int
    created_at: datetime
    updated_at: datetime

    @field_validator("id", "empleado_id", mode="before")
    @classmethod
    def convert_uuid(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    model_config = ConfigDict(from_attributes=True)


# ============ CONTENIDO CMS ============


class ContenidoCMSCreate(BaseModel):
    tipo: str = Field(..., pattern=r"^(banner|noticia)$")
    titulo: str = Field(..., min_length=2, max_length=200)
    contenido: Optional[str] = None
    imagen_url: Optional[str] = Field(None, max_length=500)
    empleado_id: Optional[str] = None
    orden: Optional[int] = 0
    visible: Optional[bool] = True
    fecha_publicacion: Optional[datetime] = None
    fecha_expiracion: Optional[datetime] = None


class ContenidoCMSUpdate(BaseModel):
    tipo: Optional[str] = Field(None, pattern=r"^(banner|noticia)$")
    titulo: Optional[str] = Field(None, min_length=2, max_length=200)
    contenido: Optional[str] = None
    imagen_url: Optional[str] = None
    empleado_id: Optional[str] = None
    orden: Optional[int] = None
    visible: Optional[bool] = None
    fecha_publicacion: Optional[datetime] = None
    fecha_expiracion: Optional[datetime] = None


class ContenidoCMSResponse(BaseModel):
    id: str
    tipo: str
    titulo: str
    contenido: Optional[str]
    imagen_url: Optional[str]
    empleado_id: Optional[str]
    empleado_nombre: Optional[str] = None
    orden: int
    visible: bool
    fecha_publicacion: Optional[datetime]
    fecha_expiracion: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    @field_validator("id", "empleado_id", mode="before")
    @classmethod
    def convert_uuid(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    model_config = ConfigDict(from_attributes=True)


class ContenidoCMSList(BaseModel):
    items: List[ContenidoCMSResponse]
    total: int


# ============ VISTA 360 EMPLEADOS ============


class Empleado360InscripcionResponse(BaseModel):
    id: str
    desafio_nombre: str
    desafio_star_miles: int
    estado: str
    fecha_solicitud: datetime
    fecha_finalizacion: Optional[datetime] = None

    @field_validator("id", mode="before")
    @classmethod
    def convert_uuid(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    model_config = ConfigDict(from_attributes=True)


class Empleado360CanjeResponse(BaseModel):
    id: str
    item_nombre: str
    cantidad: int
    star_miles_total: int
    estado: str
    fecha_solicitud: datetime
    fecha_entrega: Optional[datetime] = None

    @field_validator("id", mode="before")
    @classmethod
    def convert_uuid(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    model_config = ConfigDict(from_attributes=True)


class Empleado360Response(BaseModel):
    id: Optional[str] = None
    posicion: Optional[int] = None
    empleado_id: str
    empleado_nombre: str
    empleado_email: Optional[str] = None
    empleado_cargo: Optional[str] = None
    millas_historicas: int
    millas_disponibles: int
    total_inscripciones: int
    total_canjes: int
    inscripciones: List[Empleado360InscripcionResponse] = []
    canjes: List[Empleado360CanjeResponse] = []

    @field_validator("id", "empleado_id", mode="before")
    @classmethod
    def convert_uuid(cls, v):
        if v is None:
            return None
        return str(v) if isinstance(v, uuid.UUID) else v

    model_config = ConfigDict(from_attributes=True)


class Empleado360List(BaseModel):
    items: List[Empleado360Response]
    total: int
    pagina: int
    por_pagina: int
    total_paginas: int
    total_millas_acreditadas: int = 0
    total_millas_canjeadas: int = 0
    total_inscripciones: int = 0
    total_canjes: int = 0
