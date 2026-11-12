"""
Modelo para la tabla staging `administracion_recibos_export`.

Esta tabla es poblada por el proceso de sincronizacion
`carga_administracion_recibos` (ver backend/modules/sincronizacion/services.py)
y es consumida por el sub-modulo de export de recibos por cliente.
"""

import uuid

from sqlalchemy import BigInteger, Column, DateTime, String
from sqlalchemy.dialects.postgresql import UUID

from backend.core.utils import utc_now
from backend.database import Base


class AdministracionReciboExport(Base):
    """Staging de DNIs a exportar, agrupados por cliente."""

    __tablename__ = "administracion_recibos_export"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    colaborador = Column(String(200), nullable=True)
    cliente = Column(String(100), nullable=True, index=True)
    apellido = Column(String(100), nullable=True)
    nombre = Column(String(100), nullable=True)
    dni = Column(BigInteger, nullable=True, index=True)

    created_at = Column(DateTime, nullable=False, default=utc_now)
