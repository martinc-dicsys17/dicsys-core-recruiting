"""
Esquemas Pydantic para usuarios.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, ValidationInfo, field_validator


class RolEnum(str, Enum):
    """Roles disponibles para usuarios."""

    admin = "admin"
    usuario = "usuario"


def limpiar_dni(valor):
    """Limpia el DNI removiendo puntos, guiones y espacios."""
    if valor is None:
        return None
    # Si ya es int, retornarlo
    if isinstance(valor, int):
        return valor
    # Si es string, limpiar y convertir
    limpio = str(valor).replace(".", "").replace("-", "").replace(" ", "").strip()
    if not limpio:
        return None
    return int(limpio)


def limpiar_telefono(valor):
    """Limpia el teléfono removiendo espacios, guiones y paréntesis innecesarios."""
    if valor is None:
        return None
    # Remover espacios, guiones y paréntesis, dejar solo números y el +
    limpio = "".join(c for c in str(valor) if c.isdigit() or c == "+")
    # Limitar a 20 caracteres
    return limpio[:20] if limpio else None


class UsuarioCreate(BaseModel):
    """Esquema para crear un nuevo usuario."""

    email: EmailStr
    email_secundario: Optional[EmailStr] = Field(None, description="El otro dominio de la persona (F22)")
    password: Optional[str] = Field(None, min_length=8, max_length=128)
    nombre: str = Field(..., min_length=2, max_length=100)
    apellido: Optional[str] = Field(None, max_length=100)
    dni: Optional[int] = None
    telefono: Optional[str] = Field(None, max_length=20)
    avatar_url: Optional[str] = None
    rol: RolEnum = RolEnum.usuario
    solicitar_password: bool = Field(
        False, description="Si es True, se envía magic link para que el usuario defina su password"
    )
    grupo_ids: Optional[list[str]] = Field(None, description="IDs de grupos de permisos a asignar")
    empresa_id: Optional[str] = Field(None, description="ID de empresa a asociar al usuario")
    totp_required: bool = Field(False, description="Si es True, el usuario deberá configurar 2FA en su primer login")

    @field_validator("dni", mode="before")
    @classmethod
    def validar_dni(cls, v):
        return limpiar_dni(v)

    @field_validator("telefono", mode="before")
    @classmethod
    def validar_telefono(cls, v):
        return limpiar_telefono(v)


class UsuarioUpdate(BaseModel):
    """Esquema para actualizar un usuario existente."""

    email: Optional[EmailStr] = None
    email_secundario: Optional[EmailStr] = Field(None, description="El otro dominio de la persona (F22)")
    nombre: Optional[str] = Field(None, min_length=2, max_length=100)
    apellido: Optional[str] = Field(None, max_length=100)
    dni: Optional[int] = None
    telefono: Optional[str] = Field(None, max_length=20)
    avatar_url: Optional[str] = None
    rol: Optional[RolEnum] = None
    activo: Optional[bool] = None
    grupo_ids: Optional[list[str]] = Field(None, description="IDs de grupos de permisos a asignar")
    totp_required: Optional[bool] = None

    @field_validator("dni", mode="before")
    @classmethod
    def validar_dni(cls, v):
        return limpiar_dni(v)

    @field_validator("telefono", mode="before")
    @classmethod
    def validar_telefono(cls, v):
        return limpiar_telefono(v)


class GrupoSimple(BaseModel):
    """Esquema simplificado de grupo para incluir en respuesta de usuario."""

    id: str
    nombre: str

    @field_validator("id", mode="before")
    @classmethod
    def convert_uuid(cls, v):
        if isinstance(v, uuid.UUID):
            return str(v)
        return v

    model_config = ConfigDict(from_attributes=True)


class UsuarioResponse(BaseModel):
    """Esquema para respuestas de usuario."""

    id: str
    email: EmailStr
    email_secundario: Optional[str] = None
    nombre: str
    apellido: Optional[str]
    dni: Optional[int]
    telefono: Optional[str]
    avatar_url: Optional[str]
    rol: str
    activo: bool
    requiere_password_change: bool = False
    totp_enabled: bool = False
    totp_required: bool = False
    ultimo_login: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    updated_by: Optional[str]
    grupos: list[GrupoSimple] = []
    departamento_id: Optional[str] = None
    departamento_nombre: Optional[str] = None

    @field_validator("id", mode="before")
    @classmethod
    def convert_uuid_to_str(cls, v):
        if isinstance(v, uuid.UUID):
            return str(v)
        return v

    model_config = ConfigDict(from_attributes=True)


class UsuarioList(BaseModel):
    """Esquema para listado paginado de usuarios."""

    usuarios: list[UsuarioResponse]
    total: int
    pagina: int
    por_pagina: int
    total_paginas: int


class ChangePassword(BaseModel):
    """Esquema para cambio de contraseña."""

    password_actual: str
    password_nueva: str = Field(..., min_length=8, max_length=128)
    confirmar_password: str

    @field_validator("confirmar_password")
    @classmethod
    def passwords_match(cls, v, info: ValidationInfo):
        if v != info.data.get("password_nueva", v):
            raise ValueError("Las contraseñas no coinciden")
        return v


class Token(BaseModel):
    """Esquema para token de autenticación."""

    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Datos contenidos en el token."""

    email: Optional[str] = None


class MagicLinkSetPassword(BaseModel):
    """Esquema para establecer password via magic link."""

    token: str
    password: str = Field(..., min_length=8, max_length=128)
    confirmar_password: str

    @field_validator("confirmar_password")
    @classmethod
    def passwords_match(cls, v, info: ValidationInfo):
        if v != info.data.get("password", v):
            raise ValueError("Las contraseñas no coinciden")
        return v


class AdminSetPassword(BaseModel):
    """Esquema para que un admin establezca el password de un usuario."""

    password: str = Field(..., min_length=8, max_length=128)
