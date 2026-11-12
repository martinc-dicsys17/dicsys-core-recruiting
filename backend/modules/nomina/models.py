"""
Modelos para el módulo de Nómina - Empleados.
"""

import uuid
from datetime import date

from sqlalchemy import BigInteger, Boolean, Column, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from backend.core.utils import utc_now
from backend.database import Base


class Departamento(Base):
    """Modelo de Departamento laboral."""

    __tablename__ = "nomina_departamentos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    nombre = Column(String(100), nullable=False)
    descripcion = Column(String(255), nullable=True)
    # Cierra el ciclo departamentos ↔ empleados: la FK se crea con ALTER después de las dos tablas (con nombre, para
    # poder borrarla); sin use_alter SQLAlchemy no puede ordenar las tablas de nómina
    manager_id = Column(
        UUID(as_uuid=True),
        ForeignKey("nomina_empleados.id", use_alter=True, name="nomina_departamentos_manager_id_fkey"),
        nullable=True,
    )

    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)

    empleados = relationship("Empleado", back_populates="departamento_rel", foreign_keys="Empleado.departamento_id")
    manager_rel = relationship("Empleado", foreign_keys=[manager_id])
    categorias = relationship(
        "Categoria", back_populates="departamento_cat_rel", foreign_keys="Categoria.departamento_id"
    )


class Categoria(Base):
    """Modelo de Categoría de perfil. Pertenece a un Departamento."""

    __tablename__ = "nomina_categorias"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    nombre = Column(String(100), nullable=False)
    descripcion = Column(String(255), nullable=True)
    departamento_id = Column(UUID(as_uuid=True), ForeignKey("nomina_departamentos.id"), nullable=True)

    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)

    departamento_cat_rel = relationship("Departamento", foreign_keys=[departamento_id])
    perfiles = relationship("Perfil", back_populates="categoria_rel")


class Perfil(Base):
    """Modelo de Perfil/Rol laboral."""

    __tablename__ = "nomina_perfiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    nombre = Column(String(100), nullable=False)
    tipo = Column(String(50), nullable=True)  # DEVELOPER, MANAGER, LIDER, HRBP, DIRECTOR
    categoria_id = Column(UUID(as_uuid=True), ForeignKey("nomina_categorias.id"), nullable=True)
    descripcion = Column(String(255), nullable=True)

    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)

    categoria_rel = relationship("Categoria", back_populates="perfiles", foreign_keys=[categoria_id])
    empleados = relationship("Empleado", back_populates="perfil_rel")


class Carrera(Base):
    """Modelo de Carrera académica."""

    __tablename__ = "nomina_carreras"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    nombre = Column(String(150), nullable=False)
    descripcion = Column(String(255), nullable=True)

    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)

    empleados = relationship("Empleado", back_populates="carrera_rel")


class Empleado(Base):
    """Modelo de Empleado."""

    __tablename__ = "nomina_empleados"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    codigo = Column(String(50), unique=True, nullable=False)  # Código manual existente
    cuil = Column(BigInteger, unique=True, nullable=False)  # 11 dígitos numéricos (ej: 20111111115)

    # Datos personales
    apellido = Column(String(100), nullable=False)
    nombre = Column(String(100), nullable=False)
    fecha_nacimiento = Column(Date, nullable=True)
    dni = Column(Integer, nullable=False)  # Único por lógica (no DB) para permitir duplicados en soft-deleted
    genero = Column(String(20), nullable=True)  # Masculino, Femenino, Otro
    nacionalidad = Column(String(50), nullable=True)
    estado_civil = Column(String(30), nullable=True)  # Soltero, Casado, etc.
    nivel_estudio = Column(String(50), nullable=True)  # Primario, Secundario, Universitario, etc.
    carrera_id = Column(UUID(as_uuid=True), ForeignKey("nomina_carreras.id"), nullable=True)

    # Contacto personal
    telefono_personal = Column(String(30), nullable=True)
    email_personal = Column(String(255), nullable=True)

    # Dirección Laboral
    dir_laboral_pais = Column(String(50), nullable=True)
    dir_laboral_provincia = Column(String(50), nullable=True)
    dir_laboral_localidad = Column(String(100), nullable=True)
    dir_laboral_codigo_postal = Column(String(10), nullable=True)
    dir_laboral_barrio = Column(String(100), nullable=True)
    dir_laboral_calle = Column(String(150), nullable=True)
    dir_laboral_numero = Column(String(20), nullable=True)
    dir_laboral_piso = Column(String(10), nullable=True)
    dir_laboral_departamento = Column(String(10), nullable=True)

    # Dirección de Obsequios y Ocasiones Especiales
    usar_direccion_laboral = Column(Boolean, default=False)
    dir_obsequios_pais = Column(String(50), nullable=True)
    dir_obsequios_provincia = Column(String(50), nullable=True)
    dir_obsequios_localidad = Column(String(100), nullable=True)
    dir_obsequios_codigo_postal = Column(String(10), nullable=True)
    dir_obsequios_barrio = Column(String(100), nullable=True)
    dir_obsequios_calle = Column(String(150), nullable=True)
    dir_obsequios_numero = Column(String(20), nullable=True)
    dir_obsequios_piso = Column(String(10), nullable=True)
    dir_obsequios_departamento = Column(String(10), nullable=True)

    # Ocasiones Especiales
    preferencia_alimentaria = Column(String(100), nullable=True)  # Dulce, Salado, Sin TACC, etc.
    instrucciones_entrega = Column(String(500), nullable=True)

    # Contacto de emergencia
    contacto_emergencia = Column(String(100), nullable=True)
    numero_emergencia = Column(String(30), nullable=True)
    parentesco = Column(String(50), nullable=True)

    # Datos laborales
    fecha_alta = Column(Date, nullable=True)
    fecha_baja = Column(Date, nullable=True)
    motivo_baja = Column(String(100), nullable=True)  # Lista fija de motivos
    email_corporativo = Column(String(255), nullable=True)  # copia del email de la cuenta con su DNI (F22)

    # FKs a tablas de catálogo
    departamento_id = Column(UUID(as_uuid=True), ForeignKey("nomina_departamentos.id"), nullable=True)
    perfil_id = Column(UUID(as_uuid=True), ForeignKey("nomina_perfiles.id"), nullable=True)

    # FKs a otros empleados
    hrbp_id = Column(UUID(as_uuid=True), ForeignKey("nomina_empleados.id"), nullable=True)

    seniority = Column(String(50), nullable=True)  # Junior, Semi-Senior, Senior, etc.
    puesto = Column(String(150), nullable=True)  # Puesto cubierto actualmente (texto libre)
    foto = Column(String(500), nullable=True)  # URL relativa de la foto del empleado

    # Relaciones
    departamento_rel = relationship("Departamento", back_populates="empleados", foreign_keys=[departamento_id])
    perfil_rel = relationship("Perfil", back_populates="empleados", foreign_keys=[perfil_id])
    carrera_rel = relationship("Carrera", back_populates="empleados", foreign_keys=[carrera_id])
    hrbp_rel = relationship("Empleado", remote_side="Empleado.id", foreign_keys=[hrbp_id])

    # Soft delete y timestamps
    activo = Column(Boolean, default=True)
    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)

    @property
    def empleado_nombre_completo(self) -> str:
        """Retorna Apellido, Nombre."""
        return f"{self.apellido}, {self.nombre}"

    @property
    def edad(self) -> int:
        """Calcula la edad basada en fecha de nacimiento."""
        if not self.fecha_nacimiento:
            return 0
        hoy = date.today()
        return (
            hoy.year
            - self.fecha_nacimiento.year
            - ((hoy.month, hoy.day) < (self.fecha_nacimiento.month, self.fecha_nacimiento.day))
        )

    @property
    def antiguedad(self) -> int:
        """Calcula la antigüedad en años desde fecha de alta."""
        if not self.fecha_alta:
            return 0
        fecha_ref = self.fecha_baja if self.fecha_baja else date.today()
        return (
            fecha_ref.year
            - self.fecha_alta.year
            - ((fecha_ref.month, fecha_ref.day) < (self.fecha_alta.month, self.fecha_alta.day))
        )
