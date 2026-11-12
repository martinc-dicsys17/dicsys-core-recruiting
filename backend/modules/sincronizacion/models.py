"""
Modelos para el módulo de Sincronización de Datos.
"""

import uuid

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from backend.core.utils import utc_now
from backend.database import Base


class ProcesoSincronizacion(Base):
    """Modelo para procesos de sincronización/actualización de datos."""

    __tablename__ = "core_procesos_sincronizacion"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    codigo = Column(String(50), unique=True, nullable=False)  # ej: 'sync_nomina_odoo'
    nombre = Column(String(150), nullable=False)
    descripcion = Column(Text, nullable=True)

    # Configuración del proceso
    tipo_origen = Column(String(50), nullable=False)  # 'odoo', 'api', 'archivo', etc.
    configuracion = Column(Text, nullable=True)  # JSON con config específica
    query_sql = Column(Text, nullable=True)  # Query SQL para extraer datos (si aplica)

    # Estado
    activo = Column(Boolean, default=True)

    # Última ejecución
    ultima_ejecucion = Column(DateTime, nullable=True)
    ultimo_resultado = Column(String(20), nullable=True)  # 'exitoso', 'error', 'parcial'
    ultimo_mensaje = Column(Text, nullable=True)
    registros_procesados = Column(Integer, default=0)
    registros_actualizados = Column(Integer, default=0)
    registros_creados = Column(Integer, default=0)
    registros_errores = Column(Integer, default=0)

    # Soft delete y timestamps
    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)


class LogSincronizacion(Base):
    """Log de ejecuciones de sincronización."""

    __tablename__ = "core_logs_sincronizacion"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    proceso_id = Column(UUID(as_uuid=True), nullable=False)

    fecha_inicio = Column(DateTime, nullable=False, default=utc_now)
    fecha_fin = Column(DateTime, nullable=True)
    resultado = Column(String(20), nullable=True)  # 'exitoso', 'error', 'parcial'
    mensaje = Column(Text, nullable=True)

    registros_procesados = Column(Integer, default=0)
    registros_actualizados = Column(Integer, default=0)
    registros_creados = Column(Integer, default=0)
    registros_errores = Column(Integer, default=0)

    detalle_errores = Column(Text, nullable=True)  # JSON con errores específicos
    ejecutado_por = Column(String(255), nullable=True)

    created_at = Column(DateTime, nullable=False, default=utc_now)
