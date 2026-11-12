"""
Schemas Pydantic para autenticación.
"""

import uuid
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class LoginRequest(BaseModel):
    """Schema para solicitud de login."""

    email: EmailStr
    password: str


class EmpresaResumen(BaseModel):
    """Schema resumido de empresa para la lista de empresas en login."""

    id: str
    razon_social: str
    nombre_fantasia: Optional[str] = None
    cuit: str
    logo: Optional[str] = None

    @field_validator("id", mode="before")
    @classmethod
    def convert_uuid(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    model_config = ConfigDict(from_attributes=True)


class EmpleadoEnEmpresa(BaseModel):
    """La ficha de nómina de la persona en la empresa activa (se une a la cuenta por DNI)."""

    id: str
    foto: Optional[str] = None
    foto_thumbnail: Optional[str] = None
    perfil_nombre: Optional[str] = None


class ItemMenu(BaseModel):
    """Un ítem del menú; sin permiso propio queda como rótulo de sus hijos (sin ruta)."""

    codigo: str
    nombre: str
    icono: Optional[str] = None
    ruta: Optional[str] = None
    es_link: bool = False
    orden: int = 0
    items: List["ItemMenu"] = []


class ModuloMenu(BaseModel):
    """Un módulo del menú con los ítems que el usuario ve."""

    codigo: str
    nombre: str
    icono: Optional[str] = None
    orden: int = 0
    items: List[ItemMenu] = []


class SesionActual(BaseModel):
    """GET /auth/me (F07-P02): lo que necesita el shell de la SPA en una sola llamada. Sin empresa en el token
    (antes de elegirla), empresa, empleado, permisos y menú vienen vacíos."""

    id: str
    email: str
    nombre: Optional[str] = None
    apellido: Optional[str] = None
    dni: Optional[int] = None
    telefono: Optional[str] = None
    avatar_url: Optional[str] = None
    rol: str
    activo: bool
    empresa: Optional[EmpresaResumen] = None
    empresas: List[EmpresaResumen] = []
    empleado: Optional[EmpleadoEnEmpresa] = None
    permisos: dict[str, bool] = {}
    menu: List[ModuloMenu] = []


class PedidoDescarga(BaseModel):
    """POST /auth/descargas (F07-P06): la ruta de la API (o de /storage) que se quiere bajar, sin query."""

    ruta: str = Field(..., min_length=2, max_length=1000)


class DescargaFirmada(BaseModel):
    """Una URL firmada: sirve para un GET de esa ruta hasta que vence."""

    url: str
    expira_en: int  # segundos


class RefrescoResponse(BaseModel):
    """POST /auth/refresh (F07-P03): un access token nuevo (el refresh nuevo va en la cookie, nunca en el cuerpo)."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int  # segundos


class TokenResponse(BaseModel):
    """Schema para respuesta de token."""

    access_token: str
    token_type: str = "bearer"
    user: dict
    empresas: Optional[List[EmpresaResumen]] = None
    requiere_seleccion_empresa: bool = False


class SeleccionarEmpresaRequest(BaseModel):
    """Schema para solicitud de selección de empresa."""

    empresa_id: str = Field(..., min_length=1)

    @field_validator("empresa_id")
    @classmethod
    def validar_uuid(cls, v):
        try:
            uuid.UUID(v)
        except ValueError:
            raise ValueError("empresa_id debe ser un UUID válido")
        return v


class ProfileUpdate(BaseModel):
    """Schema para actualizar perfil. Sin rol, email ni DNI: los cambia un admin en Usuarios. El email (F22) y el
    DNI (PG-25), porque la cuenta y su ficha de nómina se unen por DNI: con el propio, cualquiera podía quedar con la
    ficha de otra persona o sacarse el control de email corporativo del login."""

    nombre: Optional[str] = Field(None, min_length=2, max_length=100)
    apellido: Optional[str] = Field(None, max_length=100)
    telefono: Optional[str] = Field(None, max_length=20)
    avatar_url: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    """Schema para cambio de contraseña desde perfil."""

    password_actual: str
    password_nueva: str = Field(..., min_length=8, max_length=128)


class MiPerfilResponse(BaseModel):
    """Respuesta de GET /auth/me/perfil — datos del usuario + empleado vinculado."""

    # Usuario
    id: str
    email: str
    nombre: str
    apellido: Optional[str] = None
    dni: Optional[int] = None
    telefono: Optional[str] = None
    avatar_url: Optional[str] = None
    rol: str
    # Empleado vinculado (None si no tiene)
    empleado: Optional[dict] = None


class MiPerfilUpdate(BaseModel):
    """Schema restringido para que el usuario edite sus datos personales.
    NO incluye campos administrativos (codigo, cuil, departamento, perfil, etc.)."""

    # Datos personales
    genero: Optional[str] = Field(None, max_length=20)
    nacionalidad: Optional[str] = Field(None, max_length=50)
    estado_civil: Optional[str] = Field(None, max_length=30)
    nivel_estudio: Optional[str] = Field(None, max_length=50)
    carrera_id: Optional[str] = None
    telefono_personal: Optional[str] = Field(None, max_length=30)
    email_personal: Optional[EmailStr] = Field(None, max_length=255)
    # Dirección Laboral
    dir_laboral_pais: Optional[str] = Field(None, max_length=50)
    dir_laboral_provincia: Optional[str] = Field(None, max_length=50)
    dir_laboral_localidad: Optional[str] = Field(None, max_length=100)
    dir_laboral_codigo_postal: Optional[str] = Field(None, max_length=10)
    dir_laboral_barrio: Optional[str] = Field(None, max_length=100)
    dir_laboral_calle: Optional[str] = Field(None, max_length=150)
    dir_laboral_numero: Optional[str] = Field(None, max_length=20)
    dir_laboral_piso: Optional[str] = Field(None, max_length=10)
    dir_laboral_departamento: Optional[str] = Field(None, max_length=10)
    # Dirección de Obsequios
    usar_direccion_laboral: Optional[bool] = None
    dir_obsequios_pais: Optional[str] = Field(None, max_length=50)
    dir_obsequios_provincia: Optional[str] = Field(None, max_length=50)
    dir_obsequios_localidad: Optional[str] = Field(None, max_length=100)
    dir_obsequios_codigo_postal: Optional[str] = Field(None, max_length=10)
    dir_obsequios_barrio: Optional[str] = Field(None, max_length=100)
    dir_obsequios_calle: Optional[str] = Field(None, max_length=150)
    dir_obsequios_numero: Optional[str] = Field(None, max_length=20)
    dir_obsequios_piso: Optional[str] = Field(None, max_length=10)
    dir_obsequios_departamento: Optional[str] = Field(None, max_length=10)
    # Emergencia y preferencias
    preferencia_alimentaria: Optional[str] = Field(None, max_length=100)
    instrucciones_entrega: Optional[str] = Field(None, max_length=500)
    contacto_emergencia: Optional[str] = Field(None, max_length=100)
    numero_emergencia: Optional[str] = Field(None, max_length=30)
    parentesco: Optional[str] = Field(None, max_length=50)


class ForgotPasswordRequest(BaseModel):
    """Schema para solicitar recuperación de contraseña."""

    email: EmailStr


class ResetPasswordRequest(BaseModel):
    """Schema para restablecer contraseña con token."""

    token: str
    password: str = Field(..., min_length=8, max_length=128)


# ─── 2FA (TOTP) ──────────────────────────────────────────────────────────────


class TwoFactorSetupResponse(BaseModel):
    """Respuesta de POST /auth/me/2fa/setup."""

    qr_base64: str
    secret_manual: str
    issuer: str = "Dicsys Core"


class TwoFactorCodeRequest(BaseModel):
    """Request con código de 6 dígitos para enable/disable 2FA."""

    code: str = Field(..., min_length=6, max_length=6)


class TwoFactorEnableResponse(BaseModel):
    """Respuesta de POST /auth/me/2fa/enable."""

    enabled: bool = True
    backup_codes: list[str]


class TwoFactorVerifyRequest(BaseModel):
    """Request para verificar 2FA durante login."""

    temp_token: str
    code: str = Field(..., min_length=6, max_length=16)  # 6 TOTP, o un código de respaldo (10 con guion y espacios)
