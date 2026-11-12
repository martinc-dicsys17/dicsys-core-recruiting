"""
Modelo de Usuario para SQLAlchemy.
"""

import uuid

import bcrypt
from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from backend.core.utils import utc_now
from backend.database import Base


class Usuario(Base):
    """Modelo de usuario en la base de datos."""

    __tablename__ = "core_usuarios"

    # Campos principales
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), nullable=False, index=True)  # Unicidad controlada por lógica (excluye soft-deleted)
    email_secundario = Column(String(255), nullable=True)  # el otro dominio de la persona; se edita en Usuarios (F22)
    password_hash = Column(String(255), nullable=False)

    # Información personal
    nombre = Column(String(100), nullable=False)
    apellido = Column(String(100), nullable=True)
    dni = Column(
        Integer, nullable=True, index=True
    )  # Unicidad controlada por lógica (excluye soft-deleted) # JOIN con Empleado por este campo
    telefono = Column(String(20), nullable=True)
    avatar_url = Column(String(500), nullable=True)

    # Configuración de cuenta
    rol = Column(String(50), nullable=False, default="usuario")
    activo = Column(Boolean, nullable=False, default=True)

    # Control de primer login
    requiere_password_change = Column(Boolean, nullable=False, default=False)
    magic_link_token = Column(String(255), nullable=True, unique=True, index=True)
    magic_link_expires = Column(DateTime, nullable=True)

    # 2FA (TOTP)
    totp_secret = Column(String(255), nullable=True)
    totp_enabled = Column(Boolean, nullable=False, default=False)
    totp_required = Column(Boolean, nullable=False, default=False)
    totp_backup_codes = Column(String(1000), nullable=True)  # JSON string con códigos

    # Timestamps
    ultimo_login = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)
    deleted_at = Column(DateTime, nullable=True, index=True)

    # Relación con grupos: ahora es por empresa, se consulta via query directa en GrupoService

    def set_password(self, password: str) -> None:
        """Establece la contraseña hasheada."""
        # bcrypt solo procesa 72 bytes: passlib truncaba en silencio y
        # bcrypt>=5 lanza ValueError, así que truncamos para mantener el
        # comportamiento histórico de los hashes existentes.
        self.password_hash = bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")

    def verify_password(self, password: str) -> bool:
        """Verifica si la contraseña es correcta."""
        try:
            return bcrypt.checkpw(password.encode("utf-8")[:72], self.password_hash.encode("utf-8"))
        except ValueError:
            return False

    def to_dict(self, include_sensitive: bool = False) -> dict:
        """Convierte el modelo a diccionario."""
        data = {
            "id": str(self.id),
            "email": self.email,
            "email_secundario": self.email_secundario,
            "nombre": self.nombre,
            "apellido": self.apellido,
            "dni": self.dni,
            "telefono": self.telefono,
            "avatar_url": self.avatar_url,
            "rol": self.rol,
            "activo": self.activo,
            "requiere_password_change": self.requiere_password_change,
            "ultimo_login": self.ultimo_login.isoformat() if self.ultimo_login else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "updated_by": self.updated_by,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
        }

        if include_sensitive:
            data["password_hash"] = self.password_hash

        return data

    def __repr__(self) -> str:
        return f"<Usuario {self.email}>"
