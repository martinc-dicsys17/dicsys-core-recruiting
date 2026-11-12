"""
Schemas Pydantic del registro de proveedores (oficinas y contactos incluidos).
"""

import re
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from backend.core.domicilio import DomicilioBase
from backend.modules.administracion.clientes_schemas import _verificar_cuit
from backend.modules.administracion.proveedores_comun import datos_faltantes
from backend.modules.administracion.proveedores_models import OPCIONES_ACUERDO, RESPONSABILIDADES_IVA

TipoProveedor = Literal["proveedor", "herramienta", "sin_clasificar"]
Acuerdo = Literal[OPCIONES_ACUERDO]
TipoIva = Literal[RESPONSABILIDADES_IVA]


def _texto(valor):
    """Recorta espacios; en blanco queda vacío (None)."""
    if isinstance(valor, str):
        valor = valor.strip()
        return valor or None
    return valor


# ─── Proveedor ──────────────────────────────────────────────────────────────────


class ProveedorDatos(BaseModel):
    """
    Campos editables del registro. Referente, servicio, tipo de información y
    acuerdo son obligatorios; sin acuerdo firmado, también la política/NDA. El
    adjunto (obligatorio con acuerdo firmado) viaja aparte: en el alta, junto con
    estos datos por POST /con-adjunto; después, por /{id}/nda.
    """

    nombre: str = Field(..., min_length=2, max_length=200)
    razon_social: Optional[str] = Field(None, max_length=200)
    cuit: Optional[str] = None
    responsabilidad_afip: Optional[TipoIva] = None
    nro_ingresos_brutos: Optional[str] = Field(None, max_length=50)
    tipo: TipoProveedor = "sin_clasificar"
    referente_empleado_id: Optional[str] = None
    servicio_provisto: Optional[str] = Field(None, max_length=5000)
    tipo_informacion: Optional[str] = Field(None, max_length=5000)
    email: Optional[EmailStr] = None
    telefono_whatsapp: Optional[str] = None
    pagina_web: Optional[str] = Field(None, max_length=500)
    acuerdo_servicio: Optional[Acuerdo] = None
    politica_nda: Optional[str] = Field(None, max_length=5000)
    observaciones: Optional[str] = Field(None, max_length=5000)

    @field_validator(
        "nombre",
        "razon_social",
        "cuit",
        "responsabilidad_afip",
        "nro_ingresos_brutos",
        "referente_empleado_id",
        "servicio_provisto",
        "tipo_informacion",
        "email",
        "telefono_whatsapp",
        "pagina_web",
        "acuerdo_servicio",
        "politica_nda",
        "observaciones",
        mode="before",
    )
    @classmethod
    def recortar(cls, valor):
        return _texto(valor)

    @field_validator("cuit")
    @classmethod
    def cuit_valido(cls, valor):
        """Como en Clientes: 11 dígitos con dígito verificador; se guarda XX-XXXXXXXX-X."""
        if valor is None:
            return None
        digitos = re.sub(r"[\s-]", "", valor)
        if not re.fullmatch(r"\d{11}", digitos):
            raise ValueError("el CUIT debe tener 11 dígitos (formato: XX-XXXXXXXX-X)")
        if not _verificar_cuit(digitos):
            raise ValueError("CUIT inválido: el dígito verificador no es correcto")
        return f"{digitos[:2]}-{digitos[2:10]}-{digitos[10]}"

    @field_validator("telefono_whatsapp")
    @classmethod
    def solo_digitos(cls, valor):
        """Se guarda como lo pide WhatsApp: dígitos con código de país (5493511234567)."""
        if valor is None:
            return None
        digitos = re.sub(r"\D", "", valor)
        if not 8 <= len(digitos) <= 15:
            raise ValueError("debe tener entre 8 y 15 dígitos, con código de país (ej: 5493511234567)")
        return digitos

    @field_validator("pagina_web")
    @classmethod
    def con_esquema(cls, valor):
        if valor is None:
            return None
        if not re.match(r"^https?://", valor, re.IGNORECASE):
            valor = f"https://{valor}"
        if not re.match(r"^https?://[^\s/$.?#][^\s]*\.[^\s]+$", valor, re.IGNORECASE):
            raise ValueError("formato de URL inválido")
        return valor

    @model_validator(mode="after")
    def obligatorios(self):
        faltan = datos_faltantes(
            referente=self.referente_empleado_id,
            servicio_provisto=self.servicio_provisto,
            tipo_informacion=self.tipo_informacion,
            acuerdo_servicio=self.acuerdo_servicio,
            politica_nda=self.politica_nda,
        )
        if faltan:
            raise ValueError(f"Faltan datos obligatorios: {', '.join(faltan)}")
        return self


class ProveedorCreate(ProveedorDatos):
    pass


class ProveedorUpdate(ProveedorDatos):
    # Estado: activo se usa para todo; inactivo se ve y conserva su historial pero no entra en
    # evaluaciones nuevas (ni en facturas o pedidos). None = no cambia.
    activo: Optional[bool] = None


class EmpleadoRef(BaseModel):
    id: str
    nombre: str
    email: Optional[str] = None

    @classmethod
    def from_model(cls, empleado) -> Optional["EmpleadoRef"]:
        if empleado is None:
            return None
        return cls(
            id=str(empleado.id), nombre=f"{empleado.apellido}, {empleado.nombre}", email=empleado.email_corporativo
        )


class ProveedorResponse(BaseModel):
    id: str
    nombre: str
    razon_social: Optional[str] = None
    cuit: Optional[str] = None
    responsabilidad_afip: Optional[str] = None
    nro_ingresos_brutos: Optional[str] = None
    tipo: str
    referente: Optional[EmpleadoRef] = None
    servicio_provisto: Optional[str] = None
    tipo_informacion: Optional[str] = None
    email: Optional[str] = None
    telefono_whatsapp: Optional[str] = None
    pagina_web: Optional[str] = None
    acuerdo_servicio: Optional[str] = None
    politica_nda: Optional[str] = None
    politica_nda_archivo_nombre: Optional[str] = None
    observaciones: Optional[str] = None
    activo: bool
    updated_at: Optional[datetime] = None

    @classmethod
    def from_model(cls, proveedor) -> "ProveedorResponse":
        return cls(
            id=str(proveedor.id),
            nombre=proveedor.nombre,
            razon_social=proveedor.razon_social,
            cuit=proveedor.cuit,
            responsabilidad_afip=proveedor.responsabilidad_afip,
            nro_ingresos_brutos=proveedor.nro_ingresos_brutos,
            tipo=proveedor.tipo,
            referente=EmpleadoRef.from_model(proveedor.referente_rel),
            servicio_provisto=proveedor.servicio_provisto,
            tipo_informacion=proveedor.tipo_informacion,
            email=proveedor.email,
            telefono_whatsapp=proveedor.telefono_whatsapp,
            pagina_web=proveedor.pagina_web,
            acuerdo_servicio=proveedor.acuerdo_servicio,
            politica_nda=proveedor.politica_nda,
            politica_nda_archivo_nombre=proveedor.politica_nda_archivo_nombre,
            observaciones=proveedor.observaciones,
            activo=proveedor.activo,
            updated_at=proveedor.updated_at,
        )


class MetricasRegistro(BaseModel):
    activos: int
    sin_referente: int
    de_baja: int


class ProveedorList(BaseModel):
    items: List[ProveedorResponse]
    total: int
    pagina: int
    por_pagina: int
    total_paginas: int
    metricas: MetricasRegistro


# ─── Oficinas y contactos ───────────────────────────────────────────────────────


class OficinaDatos(DomicilioBase):
    nombre_oficina: Optional[str] = Field(None, max_length=100)
    es_legal: bool = False

    @field_validator("nombre_oficina", mode="before")
    @classmethod
    def recortar_nombre(cls, valor):
        return _texto(valor)


class OficinaResponse(OficinaDatos):
    id: str

    @classmethod
    def from_model(cls, oficina) -> "OficinaResponse":
        return cls(
            id=str(oficina.id),
            nombre_oficina=oficina.nombre_oficina,
            calle=oficina.calle,
            numero=oficina.numero,
            piso=oficina.piso,
            departamento=oficina.departamento,
            localidad=oficina.localidad,
            provincia=oficina.provincia,
            pais=oficina.pais,
            codigo_postal=oficina.codigo_postal,
            es_legal=oficina.es_legal,
        )


class ContactoDatos(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=150)
    apellido: Optional[str] = Field(None, max_length=100)
    cargo: Optional[str] = Field(None, max_length=150)
    telefono: Optional[str] = Field(None, max_length=30)
    email: Optional[EmailStr] = None
    es_principal: bool = False
    notas: Optional[str] = Field(None, max_length=500)
    oficina_id: Optional[str] = None

    @field_validator("nombre", "apellido", "cargo", "telefono", "email", "notas", "oficina_id", mode="before")
    @classmethod
    def recortar(cls, valor):
        return _texto(valor)


class ContactoResponse(ContactoDatos):
    id: str
    oficina: Optional[str] = None  # nombre de la oficina, para mostrar

    @classmethod
    def from_model(cls, contacto) -> "ContactoResponse":
        oficina = contacto.oficina if contacto.oficina and contacto.oficina.deleted_at is None else None
        return cls(
            id=str(contacto.id),
            nombre=contacto.nombre,
            apellido=contacto.apellido,
            cargo=contacto.cargo,
            telefono=contacto.telefono,
            email=contacto.email,
            es_principal=contacto.es_principal,
            notas=contacto.notas,
            oficina_id=str(oficina.id) if oficina else None,
            oficina=(oficina.nombre_oficina or oficina.calle) if oficina else None,
        )


# ─── Documentos ─────────────────────────────────────────────────────────────────


class DocumentoResponse(BaseModel):
    """Un documento de la pestaña Documentos: con su nombre original, sin la clave del storage."""

    id: str
    nombre: str
    extension: str  # «.pdf», para el ícono cuando no hay miniatura
    tipo_mime: str
    tamano: int
    con_miniatura: bool
    subido_por: Optional[str] = None
    subido_at: datetime

    @classmethod
    def from_model(cls, documento) -> "DocumentoResponse":
        punto = documento.clave.rfind(".")
        return cls(
            id=str(documento.id),
            nombre=documento.nombre,
            extension=documento.clave[punto:].lower() if punto >= 0 else "",
            tipo_mime=documento.tipo_mime,
            tamano=documento.tamano,
            con_miniatura=bool(documento.miniatura_clave),
            subido_por=documento.created_by,
            subido_at=documento.created_at,
        )


# ─── Ficha ──────────────────────────────────────────────────────────────────────


class EvaluacionHistorial(BaseModel):
    """Cómo le fue al proveedor en cada campaña."""

    evaluacion_id: str
    periodo: str
    evaluador: Optional[str] = None
    incidentes: Optional[str] = None
    mal_manejo: Optional[str] = None
    evidencia_incidentes: Optional[str] = None
    evidencia_mal_manejo: Optional[str] = None
    con_hallazgo: bool = False
    evaluado_at: Optional[datetime] = None


class ProveedorDetalle(ProveedorResponse):
    oficinas: List[OficinaResponse] = []
    contactos: List[ContactoResponse] = []
    documentos: List[DocumentoResponse] = []
    historial: List[EvaluacionHistorial] = []


class EmpleadoOpcion(BaseModel):
    """Empleado de la nómina elegible como usuario referente."""

    id: str
    nombre: str
    email: Optional[str] = None
