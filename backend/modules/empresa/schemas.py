"""
Schemas Pydantic para el módulo de Empresa.
"""

import re
import uuid
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ─── Constantes ───────────────────────────────────────────────────────────────

RESPONSABILIDADES_AFIP = [
    "Responsable Inscripto",
    "Sujeto Exento",
    "Consumidor Final",
    "Responsable Monotributo",
    "Cliente del Exterior",
    "Sujeto No Categorizado",
]


def _verificar_cuit(cuit: str) -> bool:
    """Valida el dígito verificador del CUIT usando el algoritmo oficial."""
    coeficientes = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    digitos = [int(d) for d in cuit]
    suma = sum(d * c for d, c in zip(digitos[:10], coeficientes))
    resto = 11 - (suma % 11)
    if resto == 10:
        verificador = 9
    elif resto == 11:
        verificador = 0
    else:
        verificador = resto
    return digitos[10] == verificador


# ─── Domicilio ────────────────────────────────────────────────────────────────


class EmpresaDomicilioCreate(BaseModel):
    """Schema para crear domicilio de empresa."""

    calle: str = Field(..., min_length=2, max_length=200)
    numero: Optional[str] = Field(None, max_length=20)
    piso: Optional[str] = Field(None, max_length=20)
    departamento: Optional[str] = Field(None, max_length=20)
    localidad: str = Field(..., min_length=2, max_length=100)
    provincia: str = Field(..., min_length=2, max_length=100)
    pais: Optional[str] = Field("Argentina", max_length=100)
    codigo_postal: Optional[str] = Field(None, max_length=10)

    @field_validator("codigo_postal", mode="before")
    @classmethod
    def validar_cp(cls, v):
        if v is None:
            return v
        v = v.strip().upper()
        if not re.match(r"^[a-zA-Z0-9]+$", v):
            raise ValueError("Código postal solo puede contener letras y números")
        return v


class EmpresaDomicilioResponse(BaseModel):
    """Schema de respuesta de domicilio de empresa."""

    id: str
    empresa_id: str
    calle: str
    numero: Optional[str] = None
    piso: Optional[str] = None
    departamento: Optional[str] = None
    localidad: str
    provincia: str
    pais: str
    codigo_postal: Optional[str] = None
    vigente: bool
    created_at: datetime

    @field_validator("id", "empresa_id", mode="before")
    @classmethod
    def convert_uuid(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    model_config = ConfigDict(from_attributes=True)


# ─── Empresa ──────────────────────────────────────────────────────────────────


class EmpresaCreate(BaseModel):
    """Schema para crear empresa."""

    cuit: str = Field(..., min_length=11, max_length=13)
    razon_social: str = Field(..., min_length=2, max_length=200)
    nombre_fantasia: Optional[str] = Field(None, max_length=200)
    responsabilidad_afip: str
    logo: Optional[str] = Field(None, max_length=500)
    sitio_web: Optional[str] = Field(None, max_length=255)
    telefono: Optional[str] = Field(None, max_length=30)
    email_contacto: Optional[str] = Field(None, max_length=255)
    observaciones: Optional[str] = None
    dominios_email: Optional[List[str]] = None
    # Datos fiscales
    nro_ingresos_brutos: Optional[str] = Field(None, max_length=50)
    fecha_inicio_actividades: Optional[date] = None
    nro_inscripcion_municipal: Optional[str] = Field(None, max_length=50)
    regimen_retencion: Optional[str] = Field(None, max_length=100)

    @field_validator("cuit")
    @classmethod
    def validar_cuit(cls, v):
        limpio = v.replace("-", "")
        if not re.match(r"^\d{11}$", limpio):
            raise ValueError("CUIT debe tener 11 dígitos (formato: XX-XXXXXXXX-X)")
        if not _verificar_cuit(limpio):
            raise ValueError("CUIT inválido: el dígito verificador no es correcto")
        return f"{limpio[:2]}-{limpio[2:10]}-{limpio[10]}"

    @field_validator("responsabilidad_afip")
    @classmethod
    def validar_responsabilidad(cls, v):
        if v not in RESPONSABILIDADES_AFIP:
            raise ValueError(f"Responsabilidad AFIP inválida. Valores permitidos: {', '.join(RESPONSABILIDADES_AFIP)}")
        return v

    @field_validator("razon_social", "nombre_fantasia", mode="before")
    @classmethod
    def normalizar_texto(cls, v):
        if v is None:
            return v
        return " ".join(v.strip().split()).upper()

    @field_validator("sitio_web", mode="before")
    @classmethod
    def normalizar_web(cls, v):
        if v is None:
            return v
        v = v.strip()
        return v if v else None

    @field_validator("telefono", mode="before")
    @classmethod
    def validar_telefono(cls, v):
        if v is None:
            return v
        if not re.match(r"^[\d\s\-\+\(\)]+$", v):
            raise ValueError("Teléfono solo puede contener números, +, -, espacios y paréntesis")
        return v


class EmpresaUpdate(BaseModel):
    """Schema para actualizar empresa."""

    cuit: Optional[str] = Field(None, min_length=11, max_length=13)
    razon_social: Optional[str] = Field(None, min_length=2, max_length=200)
    nombre_fantasia: Optional[str] = Field(None, max_length=200)
    responsabilidad_afip: Optional[str] = None
    logo: Optional[str] = Field(None, max_length=500)
    sitio_web: Optional[str] = Field(None, max_length=255)
    telefono: Optional[str] = Field(None, max_length=30)
    email_contacto: Optional[str] = Field(None, max_length=255)
    observaciones: Optional[str] = None
    activo: Optional[bool] = None
    dominios_email: Optional[List[str]] = None
    # Datos fiscales
    nro_ingresos_brutos: Optional[str] = Field(None, max_length=50)
    fecha_inicio_actividades: Optional[date] = None
    nro_inscripcion_municipal: Optional[str] = Field(None, max_length=50)
    regimen_retencion: Optional[str] = Field(None, max_length=100)

    @field_validator("cuit", mode="before")
    @classmethod
    def validar_cuit(cls, v):
        if v is None:
            return v
        limpio = v.replace("-", "")
        if not re.match(r"^\d{11}$", limpio):
            raise ValueError("CUIT debe tener 11 dígitos (formato: XX-XXXXXXXX-X)")
        if not _verificar_cuit(limpio):
            raise ValueError("CUIT inválido: el dígito verificador no es correcto")
        return f"{limpio[:2]}-{limpio[2:10]}-{limpio[10]}"

    @field_validator("responsabilidad_afip", mode="before")
    @classmethod
    def validar_responsabilidad(cls, v):
        if v is None:
            return v
        if v not in RESPONSABILIDADES_AFIP:
            raise ValueError(f"Responsabilidad AFIP inválida. Valores permitidos: {', '.join(RESPONSABILIDADES_AFIP)}")
        return v

    @field_validator("razon_social", "nombre_fantasia", mode="before")
    @classmethod
    def normalizar_texto(cls, v):
        if v is None:
            return v
        return " ".join(v.strip().split()).upper()

    @field_validator("telefono", mode="before")
    @classmethod
    def validar_telefono(cls, v):
        if v is None:
            return v
        if not re.match(r"^[\d\s\-\+\(\)]+$", v):
            raise ValueError("Teléfono solo puede contener números, +, -, espacios y paréntesis")
        return v


class EmpresaResponse(BaseModel):
    """Schema de respuesta de empresa."""

    id: str
    cuit: str
    razon_social: str
    nombre_fantasia: Optional[str] = None
    responsabilidad_afip: str
    logo: Optional[str] = None
    sitio_web: Optional[str] = None
    telefono: Optional[str] = None
    email_contacto: Optional[str] = None
    observaciones: Optional[str] = None
    activo: bool
    dominios_email: Optional[List[str]] = None
    # Datos fiscales
    nro_ingresos_brutos: Optional[str] = None
    fecha_inicio_actividades: Optional[date] = None
    nro_inscripcion_municipal: Optional[str] = None
    regimen_retencion: Optional[str] = None
    # Relaciones
    domicilios: List[EmpresaDomicilioResponse] = []
    created_at: datetime
    updated_at: datetime

    @field_validator("id", mode="before")
    @classmethod
    def convert_uuid(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    @field_validator("dominios_email", mode="before")
    @classmethod
    def parse_dominios(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            import json

            try:
                return json.loads(v)
            except json.JSONDecodeError, TypeError:
                return None
        return v

    model_config = ConfigDict(from_attributes=True)


class EmpresaList(BaseModel):
    """Schema para listado paginado de empresas."""

    items: List[EmpresaResponse]
    total: int
    pagina: int
    por_pagina: int
    total_paginas: int


# ─── Usuario-Empresa ─────────────────────────────────────────────────────────


class UsuarioEmpresaResponse(BaseModel):
    """Schema de respuesta para la asociación usuario-empresa."""

    usuario_id: str
    empresa_id: str
    usuario_nombre: Optional[str] = None
    usuario_email: Optional[str] = None
    created_at: Optional[datetime] = None

    @field_validator("usuario_id", "empresa_id", mode="before")
    @classmethod
    def convert_uuid(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    model_config = ConfigDict(from_attributes=True)
