"""
Schemas Pydantic para el módulo de Notificaciones.
"""

import uuid
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class NotificacionLogResponse(BaseModel):
    """Una fila del log de notificaciones."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tipo: str
    fecha_evento: date
    empleado_id: Optional[uuid.UUID] = None
    empleado_nombre: Optional[str] = None
    empleado_email: Optional[str] = None
    estado: str
    contexto_presentacion: Optional[str] = None
    mensaje_generado: Optional[str] = None
    webex_message_id: Optional[str] = None
    error_detalle: Optional[str] = None
    enviado_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class NotificacionLogList(BaseModel):
    """Listado de logs de notificaciones."""

    items: List[NotificacionLogResponse]
    total: int


class CumpleaneroResponse(BaseModel):
    """Empleado que cumple años hoy (vista previa antes de procesar)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    nombre: str
    apellido: str
    email_corporativo: Optional[str] = None
    fecha_nacimiento: Optional[date] = None


class CumpleanerosHoy(BaseModel):
    """Cumpleañeros del día con el estado del proceso."""

    items: List[CumpleaneroResponse]
    total: int
    en_ejecucion: bool


class ProcesoResponse(BaseModel):
    """Resultado de disparar el proceso de envío."""

    message: str
    en_ejecucion: bool


class WebexReaderEstado(BaseModel):
    """Estado de la integración OAuth lectora de Webex."""

    configurado: bool
    conectado: bool
    account_email: Optional[str] = None
    expira: Optional[str] = None
    authorize_url: Optional[str] = None


class WebexReaderCode(BaseModel):
    """Authorization code recibido en el callback OAuth."""

    code: str
    state: Optional[str] = None
    redirect_uri: Optional[str] = None  # el mismo usado al autorizar (derivado del host del frontend)
