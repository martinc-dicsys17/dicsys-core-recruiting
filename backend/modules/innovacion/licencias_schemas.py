"""
Schemas Pydantic para Gestión de Licencias.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.modules.innovacion.licencias_models import (
    MONEDA_DEFAULT,
    MONEDAS_VALIDAS,
)


def _validar_moneda(valor):
    if valor is None:
        return valor
    if valor not in MONEDAS_VALIDAS:
        raise ValueError(f"Moneda debe ser una de: {list(MONEDAS_VALIDAS)}")
    return valor


class ProveedorResponse(BaseModel):
    """Proveedor del catálogo, para elegir de los ya creados."""

    id: str
    nombre: str

    @classmethod
    def from_model(cls, proveedor) -> "ProveedorResponse":
        return cls(id=str(proveedor.id), nombre=proveedor.nombre)


class ProveedorCreate(BaseModel):
    """Schema para crear un proveedor del catálogo."""

    nombre: str = Field(..., min_length=2, max_length=150)


class HerramientaCreate(BaseModel):
    """Schema para crear una herramienta del catálogo.

    El proveedor llega elegido del catálogo (proveedor_id) o por nombre
    (proveedor_nombre), que se crea al vuelo si no existe.
    """

    nombre: str = Field(..., min_length=2, max_length=150)
    proveedor_id: Optional[str] = None
    proveedor_nombre: Optional[str] = Field(None, max_length=150)
    costo_referencia: Optional[Decimal] = Field(None, ge=0, max_digits=10, decimal_places=2)
    moneda: str = Field(default=MONEDA_DEFAULT)

    @field_validator("moneda")
    @classmethod
    def validar_moneda(cls, v):
        return _validar_moneda(v)


class HerramientaUpdate(BaseModel):
    """Corrige una herramienta. proveedor_id vacío la desasigna."""

    nombre: Optional[str] = Field(None, min_length=2, max_length=150)
    proveedor_id: Optional[str] = None
    proveedor_nombre: Optional[str] = Field(None, max_length=150)
    costo_referencia: Optional[Decimal] = Field(None, ge=0, max_digits=10, decimal_places=2)
    moneda: Optional[str] = None

    @field_validator("moneda")
    @classmethod
    def validar_moneda(cls, v):
        return _validar_moneda(v)


class HerramientaResponse(BaseModel):
    """Schema de respuesta de herramienta."""

    id: str
    nombre: str
    proveedor_id: Optional[str] = None
    proveedor: Optional[str] = None
    costo_referencia: Optional[float] = None
    moneda: str
    activo: bool

    @classmethod
    def from_model(cls, herramienta) -> "HerramientaResponse":
        return cls(
            id=str(herramienta.id),
            nombre=herramienta.nombre,
            proveedor_id=str(herramienta.proveedor_id) if herramienta.proveedor_id else None,
            proveedor=herramienta.proveedor_nombre,
            costo_referencia=float(herramienta.costo_referencia) if herramienta.costo_referencia is not None else None,
            moneda=herramienta.moneda or MONEDA_DEFAULT,
            activo=herramienta.activo,
        )

    model_config = ConfigDict(from_attributes=True)


class EquipoOpcion(BaseModel):
    """Equipo y empleados elegibles para seleccionar a sus integrantes."""

    id: str
    nombre: str
    empleado_ids: List[str]


class EmpleadoOpcion(BaseModel):
    """Datos minimos para buscar y seleccionar empleados en licencias."""

    id: str
    nombre: str
    codigo: str

    @classmethod
    def from_fila(cls, empleado) -> "EmpleadoOpcion":
        return cls(
            id=str(empleado.id),
            nombre=f"{empleado.apellido}, {empleado.nombre}",
            codigo=empleado.codigo,
        )


class LicenciaDatosCreate(BaseModel):
    """Condiciones comunes al alta individual y a la asignacion por lote."""

    herramienta_id: str = Field(..., min_length=1)
    fecha_inicio: date
    fecha_fin: Optional[date] = None
    costo_mensual: Optional[Decimal] = Field(None, ge=0, max_digits=10, decimal_places=2)
    moneda: str = Field(default=MONEDA_DEFAULT)
    nro_pedido_compra: Optional[str] = Field(None, max_length=50)

    @field_validator("moneda")
    @classmethod
    def validar_moneda(cls, v):
        return _validar_moneda(v)

    @model_validator(mode="after")
    def validar_fechas(self):
        if self.fecha_fin is not None and self.fecha_fin < self.fecha_inicio:
            raise ValueError("La fecha de fin no puede ser anterior a la fecha de inicio")
        return self


class LicenciaCreate(LicenciaDatosCreate):
    """Alta individual, conservada para los clientes existentes."""

    empleado_id: str = Field(..., min_length=1)


class LicenciasLoteCreate(LicenciaDatosCreate):
    """Una licencia por empleado; el costo mensual se aplica a cada persona."""

    empleado_ids: List[uuid.UUID] = Field(..., min_length=1)


class LicenciasLoteResponse(BaseModel):
    creadas: int


class LicenciaUpdate(BaseModel):
    """Schema para actualizar licencia."""

    herramienta_id: Optional[str] = None
    empleado_id: Optional[str] = None
    fecha_inicio: Optional[date] = None
    fecha_fin: Optional[date] = None
    costo_mensual: Optional[Decimal] = Field(None, ge=0, max_digits=10, decimal_places=2)
    moneda: Optional[str] = None
    nro_pedido_compra: Optional[str] = Field(None, max_length=50)

    @field_validator("herramienta_id", "empleado_id", "fecha_inicio", "moneda")
    @classmethod
    def validar_no_nulo(cls, valor):
        if valor is None:
            raise ValueError("El campo no puede ser nulo")
        return valor

    @field_validator("moneda")
    @classmethod
    def validar_moneda(cls, v):
        return _validar_moneda(v)


class LicenciaResponse(BaseModel):
    """Schema de respuesta de licencia."""

    id: str
    herramienta_id: str
    herramienta: str
    proveedor_id: Optional[str] = None
    proveedor: Optional[str] = None
    empleado_id: str
    empleado_nombre: Optional[str] = None
    fecha_inicio: str
    fecha_fin: Optional[str] = None
    costo_mensual: Optional[float] = None
    moneda: str
    nro_pedido_compra: Optional[str] = None
    activa: bool
    esta_vencida: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, lic) -> "LicenciaResponse":
        """Convierte modelo a response."""
        return cls(
            id=str(lic.id),
            herramienta_id=str(lic.herramienta_id),
            herramienta=lic.herramienta_rel.nombre if lic.herramienta_rel else "",
            proveedor_id=(
                str(lic.herramienta_rel.proveedor_id)
                if lic.herramienta_rel and lic.herramienta_rel.proveedor_id
                else None
            ),
            proveedor=lic.herramienta_rel.proveedor_nombre if lic.herramienta_rel else None,
            empleado_id=str(lic.empleado_id),
            empleado_nombre=lic.empleado_rel.empleado_nombre_completo if lic.empleado_rel else None,
            fecha_inicio=lic.fecha_inicio.strftime("%d/%m/%Y") if lic.fecha_inicio else None,
            fecha_fin=lic.fecha_fin.strftime("%d/%m/%Y") if lic.fecha_fin else None,
            costo_mensual=float(lic.costo_mensual) if lic.costo_mensual is not None else None,
            moneda=lic.moneda or MONEDA_DEFAULT,
            nro_pedido_compra=lic.nro_pedido_compra,
            activa=lic.activa,
            esta_vencida=lic.esta_vencida,
            created_at=lic.created_at,
            updated_at=lic.updated_at,
        )

    model_config = ConfigDict(from_attributes=True)


class TotalMoneda(BaseModel):
    """Los costos no se suman entre monedas: un total por cada una."""

    moneda: str
    total: float


class EmpleadoLicencias(BaseModel):
    """Una fila del listado: el empleado y las licencias que tiene."""

    empleado_id: str
    empleado_nombre: str
    licencias: List[LicenciaResponse]
    cantidad: int
    cantidad_activas: int
    totales: List[TotalMoneda]

    @classmethod
    def from_grupo(cls, grupo: dict) -> "EmpleadoLicencias":
        licencias = [LicenciaResponse.from_model(lic) for lic in grupo["licencias"]]

        return cls(
            empleado_id=str(grupo["empleado_id"]),
            empleado_nombre=grupo["empleado_nombre"],
            licencias=licencias,
            cantidad=len(licencias),
            cantidad_activas=sum(1 for lic in licencias if lic.activa),
            totales=[TotalMoneda(**total) for total in grupo["totales"]],
        )


class EquipoLicencias(BaseModel):
    """Equipo con sus empleados y gasto del mes actual."""

    equipo_id: Optional[str]
    equipo_nombre: str
    empleados: List[EmpleadoLicencias]
    total_empleados: int
    totales: List[TotalMoneda]

    @classmethod
    def from_grupo(cls, grupo: dict) -> "EquipoLicencias":
        return cls(
            equipo_id=str(grupo["equipo_id"]) if grupo["equipo_id"] is not None else None,
            equipo_nombre=grupo["equipo_nombre"],
            empleados=[EmpleadoLicencias.from_grupo(empleado) for empleado in grupo["empleados"]],
            total_empleados=grupo["total_empleados"],
            totales=[TotalMoneda(**total) for total in grupo["totales"]],
        )


class MetricasGasto(BaseModel):
    """Gasto vigente de este mes y del anterior, para ver el efecto de los cambios."""

    mes_actual: List[TotalMoneda]
    mes_anterior: List[TotalMoneda]
    delta: List[TotalMoneda]
    # sube | baja | estable | mixta. Mixta es cuando las monedas van para
    # lados distintos: no se pinta, para no dar una señal falsa.
    tendencia: str


class EmpleadoLicenciasList(BaseModel):
    """Listado paginado por empleado. El gasto va en metricas."""

    items: List[EmpleadoLicencias]
    total: int
    pagina: int
    por_pagina: int
    total_paginas: int
    metricas: MetricasGasto


class EquipoLicenciasList(BaseModel):
    """Listado paginado por equipo con totales generales sin duplicados."""

    items: List[EquipoLicencias]
    total: int
    total_empleados: int
    pagina: int
    por_pagina: int
    total_paginas: int
    metricas: MetricasGasto


class RevocacionSeleccion(BaseModel):
    herramienta_id: uuid.UUID
    empleado_ids: List[uuid.UUID] = Field(default_factory=list)
    equipo_ids: List[uuid.UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def requiere_seleccion(self):
        if not self.empleado_ids and not self.equipo_ids:
            raise ValueError("Seleccioná empleados o equipos")
        return self


class RevocacionLicencias(BaseModel):
    licencia_ids: List[uuid.UUID] = Field(..., min_length=1)


class LicenciasMultipleCreate(BaseModel):
    empleado_ids: List[uuid.UUID] = Field(..., min_length=1)
    licencias: List[LicenciaDatosCreate] = Field(..., min_length=1)

    @model_validator(mode="after")
    def herramientas_unicas(self):
        ids = [lic.herramienta_id for lic in self.licencias]
        if len(ids) != len(set(ids)):
            raise ValueError("No repitas herramientas en la asignación")
        return self
