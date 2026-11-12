"""
Schemas Pydantic para Sincronización de Datos.
"""

import json
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from backend.core.paginacion import Pagina


class ProcesoCreate(BaseModel):
    codigo: str = Field(..., min_length=2, max_length=50)
    nombre: str = Field(..., min_length=2, max_length=150)
    descripcion: Optional[str] = None
    tipo_origen: str = Field(..., max_length=50)
    configuracion: Optional[str] = None
    query_sql: Optional[str] = None
    activo: Optional[bool] = True


class ProcesoUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=2, max_length=150)
    descripcion: Optional[str] = None
    configuracion: Optional[str] = None
    query_sql: Optional[str] = None
    activo: Optional[bool] = None


class ProcesoResponse(BaseModel):
    id: str
    codigo: str
    nombre: str
    descripcion: Optional[str]
    tipo_origen: str
    configuracion: Optional[str]
    query_sql: Optional[str]
    activo: bool
    ultima_ejecucion: Optional[datetime]
    ultimo_resultado: Optional[str]
    ultimo_mensaje: Optional[str]
    registros_procesados: int
    registros_actualizados: int
    registros_creados: int
    registros_errores: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_custom(cls, obj):
        return cls(
            id=str(obj.id),
            codigo=obj.codigo,
            nombre=obj.nombre,
            descripcion=obj.descripcion,
            tipo_origen=obj.tipo_origen,
            configuracion=obj.configuracion,
            query_sql=obj.query_sql,
            activo=obj.activo,
            ultima_ejecucion=obj.ultima_ejecucion,
            ultimo_resultado=obj.ultimo_resultado,
            ultimo_mensaje=obj.ultimo_mensaje,
            registros_procesados=obj.registros_procesados or 0,
            registros_actualizados=obj.registros_actualizados or 0,
            registros_creados=obj.registros_creados or 0,
            registros_errores=obj.registros_errores or 0,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )

    model_config = ConfigDict(from_attributes=True)


class ProcesoList(Pagina[ProcesoResponse]):
    pass


class EjecucionResponse(BaseModel):
    exito: bool
    mensaje: str
    registros_procesados: int = 0
    registros_actualizados: int = 0
    registros_creados: int = 0
    registros_errores: int = 0
    errores: Optional[List[str]] = None


class LogResponse(BaseModel):
    """Una ejecución de un proceso. El detalle se guarda como JSON en detalle_errores: una lista de errores (los logs
    viejos) o {errores, actualizaciones}; acá sale siempre separado en las dos listas."""

    id: str
    proceso_id: str
    fecha_inicio: datetime
    fecha_fin: Optional[datetime]
    resultado: Optional[str]
    mensaje: Optional[str]
    registros_procesados: int
    registros_actualizados: int
    registros_creados: int
    registros_errores: int
    ejecutado_por: Optional[str]
    detalle_errores: List[dict[str, Any] | str] = Field(default_factory=list)
    actualizaciones: List[dict[str, Any] | str] = Field(default_factory=list)

    @classmethod
    def del_log(cls, log) -> "LogResponse":
        try:
            detalle = json.loads(log.detalle_errores) if log.detalle_errores else []
        except json.JSONDecodeError:
            detalle = [log.detalle_errores]
        if isinstance(detalle, dict):
            errores, actualizaciones = detalle.get("errores") or [], detalle.get("actualizaciones") or []
        else:
            errores, actualizaciones = detalle, []
        return cls(
            id=str(log.id),
            proceso_id=str(log.proceso_id),
            fecha_inicio=log.fecha_inicio,
            fecha_fin=log.fecha_fin,
            resultado=log.resultado,
            mensaje=log.mensaje,
            registros_procesados=log.registros_procesados or 0,
            registros_actualizados=log.registros_actualizados or 0,
            registros_creados=log.registros_creados or 0,
            registros_errores=log.registros_errores or 0,
            ejecutado_por=log.ejecutado_por,
            detalle_errores=errores,
            actualizaciones=actualizaciones,
        )


class LogList(Pagina[LogResponse]):
    pass
