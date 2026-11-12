"""
Campos de domicilio compartidos por los módulos que guardan direcciones
(empresa, clientes, oficinas de proveedores). Cada módulo tiene su propia
tabla; lo que se comparte es la validación.
"""

from typing import Optional

from pydantic import BaseModel, Field, ValidationInfo, field_validator


class DomicilioBase(BaseModel):
    calle: str = Field(..., min_length=1, max_length=200)
    numero: Optional[str] = Field(None, max_length=20)
    piso: Optional[str] = Field(None, max_length=20)
    departamento: Optional[str] = Field(None, max_length=20)
    localidad: str = Field(..., min_length=1, max_length=100)
    provincia: Optional[str] = Field(None, max_length=100)
    pais: str = Field("Argentina", min_length=1, max_length=100)
    codigo_postal: Optional[str] = Field(None, max_length=10)

    @field_validator(
        "calle", "numero", "piso", "departamento", "localidad", "provincia", "pais", "codigo_postal", mode="before"
    )
    @classmethod
    def recortar(cls, valor, info: ValidationInfo):
        """Recorta espacios; un opcional en blanco queda vacío (None) y el país, Argentina."""
        if isinstance(valor, str):
            valor = valor.strip()
            if not valor and info.field_name == "pais":
                return "Argentina"
            return valor or None
        return valor
