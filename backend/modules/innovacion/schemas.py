"""
Schemas Pydantic para el módulo de Innovación.
"""

import uuid
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.modules.innovacion.models import TIPOS_CERTIFICACION

TIPOS_VALIDOS = list(TIPOS_CERTIFICACION.keys())

# Base del repositorio de casos de uso de innovación.
REPO_INNOVACION_BASE = "github.com/Dicsys-SA/innovacion-casos-uso/"


def normalizar_repo_url(v):
    """Inserta el segmento `tree/main/` en las URLs del repo de casos de uso.

    GitHub necesita `/tree/<branch>/` para apuntar a una carpeta dentro de un
    repo; el frontend construye la URL sin ese segmento. Lo agregamos acá de
    forma idempotente: no toca URLs que ya tengan `/tree/` o `/blob/`, ni las
    que apunten a otro repositorio.
    """
    if not v:
        return v
    if REPO_INNOVACION_BASE in v and "/tree/" not in v and "/blob/" not in v:
        v = v.replace(REPO_INNOVACION_BASE, REPO_INNOVACION_BASE + "tree/main/", 1)
    return v


# === CERTIFICACIÓN ===


class CertificacionCreate(BaseModel):
    tipo_certificacion: str = Field(...)
    titulo: Optional[str] = Field(None, max_length=200)
    descripcion: Optional[str] = None

    @field_validator("tipo_certificacion")
    @classmethod
    def validar_tipo(cls, v):
        if v not in TIPOS_VALIDOS:
            raise ValueError(f"Tipo debe ser uno de: {', '.join(TIPOS_VALIDOS)}")
        return v


class CertificacionUpdate(BaseModel):
    titulo: Optional[str] = Field(None, max_length=200)
    descripcion: Optional[str] = None
    estado: Optional[str] = None
    # Campos Finalista del Challenge
    repo_presentacion: Optional[str] = Field(None, max_length=500)
    repo_demo: Optional[str] = Field(None, max_length=500)
    tematica: Optional[str] = Field(None, max_length=200)
    tecnologias: Optional[List[str]] = None
    fecha_presentacion: Optional[date] = None
    fecha_aprobacion: Optional[date] = None
    # Campos Training / Formación (fechas de certificados, imágenes se suben por endpoint separado)
    cert_noncode_origen: Optional[str] = None
    cert_noncode_fecha: Optional[date] = None
    cert_n8n_origen: Optional[str] = None
    cert_n8n_fecha: Optional[date] = None
    cert_ruta1_fecha: Optional[date] = None
    cert_ruta2_fecha: Optional[date] = None
    cert_ruta3_fecha: Optional[date] = None

    @field_validator("estado")
    @classmethod
    def validar_estado(cls, v):
        if v is None:
            return v
        estados_validos = ["sin_iniciar", "iniciado", "en_progreso", "en_revision", "completada"]
        if v not in estados_validos:
            raise ValueError(f"Estado debe ser uno de: {', '.join(estados_validos)}")
        return v

    @field_validator("repo_presentacion", "repo_demo")
    @classmethod
    def validar_url_git(cls, v):
        if v is None:
            return v
        v = v.strip()
        if not v:
            return None
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("La URL debe comenzar con http:// o https://")
        return normalizar_repo_url(v)


class CertificacionMiPathUpdate(BaseModel):
    """Schema restringido para que el usuario edite SU certificación.
    No incluye: estado, fecha_aprobacion (solo admin)."""

    titulo: Optional[str] = Field(None, max_length=200)
    descripcion: Optional[str] = None
    repo_presentacion: Optional[str] = Field(None, max_length=500)
    repo_demo: Optional[str] = Field(None, max_length=500)
    tematica: Optional[str] = Field(None, max_length=200)
    tecnologias: Optional[List[str]] = None
    fecha_presentacion: Optional[date] = None
    # Campos Training / Formación (fechas de certificados)
    cert_noncode_origen: Optional[str] = None
    cert_noncode_fecha: Optional[date] = None
    cert_n8n_origen: Optional[str] = None
    cert_n8n_fecha: Optional[date] = None
    cert_ruta1_fecha: Optional[date] = None
    cert_ruta2_fecha: Optional[date] = None
    cert_ruta3_fecha: Optional[date] = None

    @field_validator("repo_presentacion", "repo_demo")
    @classmethod
    def validar_url_git(cls, v):
        if v is None:
            return v
        v = v.strip()
        if not v:
            return None
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("La URL debe comenzar con http:// o https://")
        return normalizar_repo_url(v)


class CertificacionResponse(BaseModel):
    id: str
    empleado_id: str
    tipo_certificacion: str
    tipo_nombre: Optional[str] = None
    empleado_nombre: Optional[str] = None
    empleado_foto: Optional[str] = None
    empleado_departamento: Optional[str] = None
    empleado_puesto: Optional[str] = None
    empleado_perfil: Optional[str] = None
    estado: str
    titulo: Optional[str] = None
    descripcion: Optional[str] = None
    repo_presentacion: Optional[str] = None
    repo_demo: Optional[str] = None
    tematica: Optional[str] = None
    tecnologias: Optional[List[str]] = None
    fecha_presentacion: Optional[date] = None
    fecha_aprobacion: Optional[date] = None
    # Training / Formación
    cert_noncode_origen: Optional[str] = None
    cert_noncode_imagen: Optional[str] = None
    cert_noncode_fecha: Optional[date] = None
    cert_noncode_plan: Optional[str] = None
    cert_n8n_origen: Optional[str] = None
    cert_n8n_imagen: Optional[str] = None
    cert_n8n_fecha: Optional[date] = None
    cert_n8n_plan: Optional[str] = None
    cert_ruta1_imagen: Optional[str] = None
    cert_ruta1_fecha: Optional[date] = None
    cert_ruta2_imagen: Optional[str] = None
    cert_ruta2_fecha: Optional[date] = None
    cert_ruta3_imagen: Optional[str] = None
    cert_ruta3_fecha: Optional[date] = None
    progreso_completados: Optional[str] = None
    porcentaje_avance: Optional[str] = None
    fecha_registro: Optional[datetime] = None
    fecha_en_progreso: Optional[datetime] = None
    fecha_en_presentacion: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    @field_validator("id", "empleado_id", mode="before")
    @classmethod
    def convert_uuid(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_model(cls, cert) -> "CertificacionResponse":
        tipo_info = TIPOS_CERTIFICACION.get(cert.tipo_certificacion, {})
        empleado_nombre = None
        empleado_foto = None
        empleado_departamento = None
        empleado_puesto = None
        empleado_perfil = None
        if cert.empleado_rel:
            empleado_nombre = f"{cert.empleado_rel.apellido}, {cert.empleado_rel.nombre}"
            empleado_foto = cert.empleado_rel.foto
            if empleado_foto:
                empleado_foto = empleado_foto.replace("/fotos/nomina/", "/fotos/nomina/thumbnails/")
            empleado_departamento = (
                cert.empleado_rel.departamento_rel.nombre if cert.empleado_rel.departamento_rel else None
            )
            empleado_puesto = cert.empleado_rel.puesto
            empleado_perfil = cert.empleado_rel.perfil_rel.nombre if cert.empleado_rel.perfil_rel else None
        return cls(
            id=str(cert.id),
            empleado_id=str(cert.empleado_id),
            tipo_certificacion=cert.tipo_certificacion,
            tipo_nombre=tipo_info.get("nombre", cert.tipo_certificacion),
            empleado_nombre=empleado_nombre,
            empleado_foto=empleado_foto,
            empleado_departamento=empleado_departamento,
            empleado_puesto=empleado_puesto,
            empleado_perfil=empleado_perfil,
            estado=cert.estado,
            titulo=cert.titulo,
            descripcion=cert.descripcion,
            repo_presentacion=cert.repo_presentacion,
            repo_demo=cert.repo_demo,
            tematica=cert.tematica,
            tecnologias=cert.tecnologias or [],
            fecha_presentacion=cert.fecha_presentacion,
            fecha_aprobacion=cert.fecha_aprobacion,
            cert_noncode_origen=cert.cert_noncode_origen,
            cert_noncode_imagen=cert.cert_noncode_imagen,
            cert_noncode_fecha=cert.cert_noncode_fecha,
            cert_noncode_plan=cert.cert_noncode_plan,
            cert_n8n_origen=cert.cert_n8n_origen,
            cert_n8n_imagen=cert.cert_n8n_imagen,
            cert_n8n_fecha=cert.cert_n8n_fecha,
            cert_n8n_plan=cert.cert_n8n_plan,
            cert_ruta1_imagen=cert.cert_ruta1_imagen,
            cert_ruta1_fecha=cert.cert_ruta1_fecha,
            cert_ruta2_imagen=cert.cert_ruta2_imagen,
            cert_ruta2_fecha=cert.cert_ruta2_fecha,
            cert_ruta3_imagen=cert.cert_ruta3_imagen,
            cert_ruta3_fecha=cert.cert_ruta3_fecha,
            progreso_completados=cert.progreso_completados,
            porcentaje_avance=cert.porcentaje_avance,
            fecha_registro=cert.fecha_registro,
            fecha_en_progreso=cert.fecha_en_progreso,
            fecha_en_presentacion=cert.fecha_en_presentacion,
            created_at=cert.created_at,
            updated_at=cert.updated_at,
        )


class CertificacionList(BaseModel):
    items: List[CertificacionResponse]
    total: int
    pagina: int
    por_pagina: int
    total_paginas: int


# === EVENTO ===


class EventoCreate(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=200)
    fecha: date
    duenio: Optional[str] = Field(None, max_length=100)
    tags: Optional[List[str]] = None


class EventoUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=2, max_length=200)
    fecha: Optional[date] = None
    duenio: Optional[str] = Field(None, max_length=100)
    tags: Optional[List[str]] = None


class EventoResponse(BaseModel):
    id: str
    nombre: str
    fecha: date
    duenio: Optional[str] = None
    tags: Optional[List[str]] = None
    cantidad_asistentes: int = 0
    created_at: datetime
    updated_at: datetime

    @field_validator("id", mode="before")
    @classmethod
    def convert_uuid(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    model_config = ConfigDict(from_attributes=True)


class EventoList(BaseModel):
    items: List[EventoResponse]
    total: int
    pagina: int
    por_pagina: int
    total_paginas: int


class EventoAsistenciaRequest(BaseModel):
    empleado_ids: List[str] = Field(..., min_length=1)

    @field_validator("empleado_ids")
    @classmethod
    def validar_no_vacio(cls, v):
        if not v:
            raise ValueError("Debe incluir al menos un empleado")
        return v


class MiEventoResponse(BaseModel):
    """Evento visto desde la perspectiva del usuario (para las medallas)."""

    id: str
    nombre: str
    fecha: date

    @field_validator("id", mode="before")
    @classmethod
    def convert_uuid(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    model_config = ConfigDict(from_attributes=True)
