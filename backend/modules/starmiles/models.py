"""
Modelos para el módulo Star Miles.
"""

import uuid

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from backend.core.utils import utc_now
from backend.database import Base


class EmpleadoStarMiles(Base):
    """Contador de Star Miles por empleado (separado de la tabla Empleado)."""

    __tablename__ = "starmiles_empleados"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    empleado_id = Column(UUID(as_uuid=True), ForeignKey("nomina_empleados.id"), nullable=False, unique=True)

    # Contadores
    millas_historicas = Column(Integer, default=0, nullable=False)  # Total acumulado histórico
    millas_disponibles = Column(Integer, default=0, nullable=False)  # Ganadas - Canjeadas

    # Timestamps
    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    # Relaciones
    empleado = relationship("Empleado", backref="starmiles_cuenta")


class CategoriaDesafio(Base):
    """Categorías de desafíos."""

    __tablename__ = "starmiles_categorias"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    nombre = Column(String(100), nullable=False)
    descripcion = Column(String(255), nullable=True)
    color = Column(String(7), default="#3B82F6")  # Color hex para UI
    icono = Column(String(50), default="star")  # Nombre icono Lucide

    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)


class Desafio(Base):
    """Catálogo de desafíos disponibles."""

    __tablename__ = "starmiles_desafios"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    categoria_id = Column(UUID(as_uuid=True), ForeignKey("starmiles_categorias.id"), nullable=True)

    nombre = Column(String(150), nullable=False)
    descripcion = Column(Text, nullable=True)
    alcance = Column(String(255), nullable=True)  # A quiénes aplica
    star_miles = Column(Integer, nullable=False)  # Cantidad de millas que otorga

    # Vigencia
    fecha_inicio = Column(Date, nullable=True)
    fecha_vencimiento = Column(Date, nullable=True)
    activo = Column(Boolean, default=True)
    inscripcion_unica_por_empleado = Column(Boolean, nullable=False, default=False)

    # Imagen/banner opcional
    imagen_url = Column(String(500), nullable=True)

    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)

    # Relaciones
    categoria = relationship("CategoriaDesafio", backref="desafios")


class InscripcionDesafio(Base):
    """Inscripciones de empleados a desafíos."""

    __tablename__ = "starmiles_inscripciones"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    desafio_id = Column(UUID(as_uuid=True), ForeignKey("starmiles_desafios.id"), nullable=False)
    empleado_id = Column(UUID(as_uuid=True), ForeignKey("nomina_empleados.id"), nullable=False)

    # Estados: pendiente, aprobada, rechazada, completada, incompleta
    # Estados finales sin millas: rechazada, incompleta
    estado = Column(String(20), default="pendiente", nullable=False)

    # Fechas del flujo
    fecha_solicitud = Column(DateTime, nullable=False, default=utc_now)
    fecha_aprobacion = Column(DateTime, nullable=True)
    fecha_finalizacion = Column(DateTime, nullable=True)
    fecha_rechazo = Column(DateTime, nullable=True)

    # Aprobador
    aprobador_id = Column(UUID(as_uuid=True), ForeignKey("nomina_empleados.id"), nullable=True)

    # Comentarios
    comentario_solicitud = Column(Text, nullable=True)
    comentario_aprobador = Column(Text, nullable=True)

    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    # Relaciones
    desafio = relationship("Desafio", backref="inscripciones")
    empleado = relationship("Empleado", foreign_keys=[empleado_id], backref="inscripciones_desafios")
    aprobador = relationship("Empleado", foreign_keys=[aprobador_id], backref="inscripciones_aprobadas")

    # Inscripción única por empleado (DIC-144): busca las inscripciones de un empleado a un desafío por estado
    __table_args__ = (
        Index(
            "ix_starmiles_inscripciones_desafio_empleado_estado", "empresa_id", "desafio_id", "empleado_id", "estado"
        ),
    )


class ItemCanje(Base):
    """Catálogo de items canjeables."""

    __tablename__ = "starmiles_items_canje"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)

    # Tipo: producto, mercadolibre
    tipo = Column(String(20), nullable=False, default="producto")

    nombre = Column(String(150), nullable=False)
    descripcion = Column(Text, nullable=True)

    # Costo en Star Miles (solo para tipo 'producto', para 'mercadolibre' se calcula al canjear)
    star_miles_costo = Column(Integer, nullable=True)

    stock = Column(Integer, nullable=True)  # NULL = ilimitado

    # Imagen
    imagen_url = Column(String(500), nullable=True)

    activo = Column(Boolean, default=True)

    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)


class Canje(Base):
    """Solicitudes de canje de empleados."""

    __tablename__ = "starmiles_canjes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    item_id = Column(UUID(as_uuid=True), ForeignKey("starmiles_items_canje.id"), nullable=False)
    empleado_id = Column(UUID(as_uuid=True), ForeignKey("nomina_empleados.id"), nullable=False)

    cantidad = Column(Integer, default=1, nullable=False)
    star_miles_total = Column(Integer, nullable=False)  # Costo total al momento del canje

    # Para items tipo MercadoLibre: URL y precio calculado
    mercadolibre_url = Column(String(500), nullable=True)
    mercadolibre_precio = Column(Numeric(12, 2), nullable=True)  # Precio en pesos al momento del canje

    # Estados: pendiente, aprobado, rechazado, entregado
    estado = Column(String(20), default="pendiente", nullable=False)

    # Fechas
    fecha_solicitud = Column(DateTime, nullable=False, default=utc_now)
    fecha_aprobacion = Column(DateTime, nullable=True)
    fecha_entrega = Column(DateTime, nullable=True)
    fecha_rechazo = Column(DateTime, nullable=True)

    # Aprobador
    aprobador_id = Column(UUID(as_uuid=True), ForeignKey("nomina_empleados.id"), nullable=True)

    comentario = Column(Text, nullable=True)

    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)

    # Relaciones
    item = relationship("ItemCanje", backref="canjes")
    empleado = relationship("Empleado", foreign_keys=[empleado_id], backref="canjes")
    aprobador = relationship("Empleado", foreign_keys=[aprobador_id], backref="canjes_aprobados")


class ContenidoCMS(Base):
    """Contenido editable para la página principal (noticias, fotos, ganadores)."""

    __tablename__ = "starmiles_contenido_cms"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)

    # Tipos: noticia, banner, ganador, novedad
    tipo = Column(String(30), nullable=False)
    titulo = Column(String(200), nullable=False)
    contenido = Column(Text, nullable=True)
    imagen_url = Column(String(500), nullable=True)

    # Para ganadores
    empleado_id = Column(UUID(as_uuid=True), ForeignKey("nomina_empleados.id"), nullable=True)

    # Orden y visibilidad
    orden = Column(Integer, default=0)
    visible = Column(Boolean, default=True)
    fecha_publicacion = Column(DateTime, nullable=True)
    fecha_expiracion = Column(DateTime, nullable=True)

    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)

    # Relaciones
    empleado = relationship("Empleado", backref="menciones_starmiles")
