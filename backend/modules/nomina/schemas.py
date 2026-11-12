"""
Schemas Pydantic para Empleados, Departamentos y Perfiles.
"""

import uuid
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# ============ DEPARTAMENTO ============
class DepartamentoCreate(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=100)
    descripcion: Optional[str] = Field(None, max_length=255)
    manager_id: Optional[str] = None


class DepartamentoUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=2, max_length=100)
    descripcion: Optional[str] = None
    manager_id: Optional[str] = None


class DepartamentoResponse(BaseModel):
    id: str
    nombre: str
    descripcion: Optional[str]
    manager_id: Optional[str] = None
    manager_nombre: Optional[str] = None
    manager_foto_thumbnail: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    @field_validator("id", mode="before")
    @classmethod
    def convert_uuid(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    @field_validator("manager_id", mode="before")
    @classmethod
    def convert_manager_uuid(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    @classmethod
    def from_model(cls, dep) -> "DepartamentoResponse":
        manager_foto = dep.manager_rel.foto if dep.manager_rel and dep.manager_rel.foto else None
        manager_thumb = manager_foto.replace("/fotos/nomina/", "/fotos/nomina/thumbnails/") if manager_foto else None
        return cls(
            id=str(dep.id),
            nombre=dep.nombre,
            descripcion=dep.descripcion,
            manager_id=str(dep.manager_id) if dep.manager_id else None,
            manager_nombre=dep.manager_rel.empleado_nombre_completo if dep.manager_rel else None,
            manager_foto_thumbnail=manager_thumb,
            created_at=dep.created_at,
            updated_at=dep.updated_at,
        )

    model_config = ConfigDict(from_attributes=True)


class DepartamentoList(BaseModel):
    items: List[DepartamentoResponse]
    total: int
    pagina: int
    por_pagina: int
    total_paginas: int


# ============ CATEGORIA ============
class CategoriaCreate(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=100)
    descripcion: Optional[str] = Field(None, max_length=255)
    departamento_id: Optional[str] = None


class CategoriaUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=2, max_length=100)
    descripcion: Optional[str] = None
    departamento_id: Optional[str] = None


class CategoriaResponse(BaseModel):
    id: str
    nombre: str
    descripcion: Optional[str]
    departamento_id: Optional[str] = None
    departamento_nombre: Optional[str] = None
    perfiles_count: int = 0
    created_at: datetime
    updated_at: datetime

    @field_validator("id", mode="before")
    @classmethod
    def convert_uuid(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    @field_validator("departamento_id", mode="before")
    @classmethod
    def convert_depto_uuid(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    @classmethod
    def from_model(cls, cat) -> "CategoriaResponse":
        perfiles_count = len([p for p in cat.perfiles if p.deleted_at is None]) if cat.perfiles else 0
        return cls(
            id=str(cat.id),
            nombre=cat.nombre,
            descripcion=cat.descripcion,
            departamento_id=str(cat.departamento_id) if cat.departamento_id else None,
            departamento_nombre=cat.departamento_cat_rel.nombre if cat.departamento_cat_rel else None,
            perfiles_count=perfiles_count,
            created_at=cat.created_at,
            updated_at=cat.updated_at,
        )

    model_config = ConfigDict(from_attributes=True)


class CategoriaList(BaseModel):
    items: List[CategoriaResponse]
    total: int
    pagina: int
    por_pagina: int
    total_paginas: int


# ============ PERFIL ============
class PerfilCreate(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=100)
    tipo: Optional[str] = Field(None, max_length=50)
    categoria_id: Optional[str] = None
    descripcion: Optional[str] = Field(None, max_length=255)


class PerfilUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=2, max_length=100)
    tipo: Optional[str] = Field(None, max_length=50)
    categoria_id: Optional[str] = None
    descripcion: Optional[str] = None


class PerfilResponse(BaseModel):
    id: str
    nombre: str
    tipo: Optional[str] = None
    categoria_id: Optional[str] = None
    categoria_nombre: Optional[str] = None
    departamento_cat_id: Optional[str] = None
    departamento_cat_nombre: Optional[str] = None
    descripcion: Optional[str]
    created_at: datetime
    updated_at: datetime

    @field_validator("id", mode="before")
    @classmethod
    def convert_uuid(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    @field_validator("categoria_id", mode="before")
    @classmethod
    def convert_cat_uuid(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    @field_validator("departamento_cat_id", mode="before")
    @classmethod
    def convert_depto_cat_uuid(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    @classmethod
    def from_model(cls, perfil) -> "PerfilResponse":
        cat = perfil.categoria_rel
        return cls(
            id=str(perfil.id),
            nombre=perfil.nombre,
            tipo=perfil.tipo,
            categoria_id=str(perfil.categoria_id) if perfil.categoria_id else None,
            categoria_nombre=cat.nombre if cat else None,
            departamento_cat_id=str(cat.departamento_id) if cat and cat.departamento_id else None,
            departamento_cat_nombre=cat.departamento_cat_rel.nombre if cat and cat.departamento_cat_rel else None,
            descripcion=perfil.descripcion,
            created_at=perfil.created_at,
            updated_at=perfil.updated_at,
        )

    model_config = ConfigDict(from_attributes=True)


class PerfilList(BaseModel):
    items: List[PerfilResponse]
    total: int
    pagina: int
    por_pagina: int
    total_paginas: int


# ============ CARRERA ============
class CarreraCreate(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=150)
    descripcion: Optional[str] = Field(None, max_length=255)


class CarreraUpdate(BaseModel):
    nombre: Optional[str] = Field(None, min_length=2, max_length=150)
    descripcion: Optional[str] = None


class CarreraResponse(BaseModel):
    id: str
    nombre: str
    descripcion: Optional[str]
    created_at: datetime
    updated_at: datetime

    @field_validator("id", mode="before")
    @classmethod
    def convert_uuid(cls, v):
        return str(v) if isinstance(v, uuid.UUID) else v

    model_config = ConfigDict(from_attributes=True)


class CarreraList(BaseModel):
    items: List[CarreraResponse]
    total: int
    pagina: int
    por_pagina: int
    total_paginas: int


# ============ EMPLEADO ============


class EmpleadoCreate(BaseModel):
    """Schema para crear empleado."""

    codigo: str = Field(..., min_length=1, max_length=50)
    cuil: int = Field(..., ge=20000000000, le=34999999999)
    apellido: str = Field(..., min_length=2, max_length=100)
    nombre: str = Field(..., min_length=2, max_length=100)
    fecha_nacimiento: Optional[date] = None
    dni: int = Field(..., ge=1000000)
    genero: Optional[str] = Field(None, max_length=20)
    nacionalidad: Optional[str] = Field(None, max_length=50)
    estado_civil: Optional[str] = Field(None, max_length=30)
    nivel_estudio: Optional[str] = Field(None, max_length=50)
    carrera_id: Optional[str] = None
    telefono_personal: Optional[str] = Field(None, max_length=30)
    email_personal: Optional[str] = Field(None, max_length=255)
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
    usar_direccion_laboral: Optional[bool] = False
    dir_obsequios_pais: Optional[str] = Field(None, max_length=50)
    dir_obsequios_provincia: Optional[str] = Field(None, max_length=50)
    dir_obsequios_localidad: Optional[str] = Field(None, max_length=100)
    dir_obsequios_codigo_postal: Optional[str] = Field(None, max_length=10)
    dir_obsequios_barrio: Optional[str] = Field(None, max_length=100)
    dir_obsequios_calle: Optional[str] = Field(None, max_length=150)
    dir_obsequios_numero: Optional[str] = Field(None, max_length=20)
    dir_obsequios_piso: Optional[str] = Field(None, max_length=10)
    dir_obsequios_departamento: Optional[str] = Field(None, max_length=10)
    # Ocasiones Especiales
    preferencia_alimentaria: Optional[str] = Field(None, max_length=100)
    instrucciones_entrega: Optional[str] = Field(None, max_length=500)
    contacto_emergencia: Optional[str] = Field(None, max_length=100)
    numero_emergencia: Optional[str] = Field(None, max_length=30)
    parentesco: Optional[str] = Field(None, max_length=50)
    fecha_alta: Optional[date] = None
    fecha_baja: Optional[date] = None
    motivo_baja: Optional[str] = Field(None, max_length=100)
    # email_corporativo no se recibe: es copia del email de la cuenta con su DNI (F22)
    departamento_id: Optional[str] = None
    perfil_id: Optional[str] = None
    hrbp_id: Optional[str] = None
    seniority: Optional[str] = Field(None, max_length=50)
    puesto: Optional[str] = Field(None, max_length=150)
    foto: Optional[str] = None


class EmpleadoUpdate(BaseModel):
    """Schema para actualizar empleado."""

    codigo: Optional[str] = Field(None, min_length=1, max_length=50)
    cuil: Optional[int] = Field(None, ge=20000000000, le=34999999999)
    apellido: Optional[str] = Field(None, min_length=2, max_length=100)
    nombre: Optional[str] = Field(None, min_length=2, max_length=100)
    fecha_nacimiento: Optional[date] = None
    dni: Optional[int] = None
    genero: Optional[str] = Field(None, max_length=20)
    nacionalidad: Optional[str] = Field(None, max_length=50)
    estado_civil: Optional[str] = Field(None, max_length=30)
    nivel_estudio: Optional[str] = Field(None, max_length=50)
    carrera_id: Optional[str] = None
    telefono_personal: Optional[str] = Field(None, max_length=30)
    email_personal: Optional[str] = Field(None, max_length=255)
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
    # Ocasiones Especiales
    preferencia_alimentaria: Optional[str] = Field(None, max_length=100)
    instrucciones_entrega: Optional[str] = Field(None, max_length=500)
    contacto_emergencia: Optional[str] = Field(None, max_length=100)
    numero_emergencia: Optional[str] = Field(None, max_length=30)
    parentesco: Optional[str] = Field(None, max_length=50)
    fecha_alta: Optional[date] = None
    fecha_baja: Optional[date] = None
    motivo_baja: Optional[str] = Field(None, max_length=100)
    # email_corporativo no se recibe: es copia del email de la cuenta con su DNI (F22)
    departamento_id: Optional[str] = None
    perfil_id: Optional[str] = None
    hrbp_id: Optional[str] = None
    seniority: Optional[str] = Field(None, max_length=50)
    puesto: Optional[str] = Field(None, max_length=150)
    foto: Optional[str] = None


class EmpleadoMiPerfilUpdate(BaseModel):
    """Schema para self-service: solo campos que el empleado puede editar de sí mismo.
    NO incluye campos sensibles como codigo, cuil, dni, departamento_id, perfil_id,
    hrbp_id, fecha_alta, fecha_baja, motivo_baja, email_corporativo, seniority, puesto, foto."""

    # Datos personales básicos
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
    # Emergencia y ocasiones
    preferencia_alimentaria: Optional[str] = Field(None, max_length=100)
    instrucciones_entrega: Optional[str] = Field(None, max_length=500)
    contacto_emergencia: Optional[str] = Field(None, max_length=100)
    numero_emergencia: Optional[str] = Field(None, max_length=30)
    parentesco: Optional[str] = Field(None, max_length=50)


class EmpleadoResponse(BaseModel):
    """Schema de respuesta de empleado."""

    id: str
    codigo: str
    cuil: str  # Formateado como XX-XXXXXXXX-X
    cuil_raw: int  # Valor numérico sin formato
    empleado: str
    apellido: str
    nombre: str
    fecha_nacimiento: Optional[str] = None
    edad: int
    dni: Optional[int] = None
    genero: Optional[str] = None
    nacionalidad: Optional[str] = None
    estado_civil: Optional[str] = None
    nivel_estudio: Optional[str] = None
    carrera_id: Optional[str] = None
    carrera_nombre: Optional[str] = None
    telefono_personal: Optional[str] = None
    email_personal: Optional[str] = None
    # Dirección Laboral
    dir_laboral_pais: Optional[str] = None
    dir_laboral_provincia: Optional[str] = None
    dir_laboral_localidad: Optional[str] = None
    dir_laboral_codigo_postal: Optional[str] = None
    dir_laboral_barrio: Optional[str] = None
    dir_laboral_calle: Optional[str] = None
    dir_laboral_numero: Optional[str] = None
    dir_laboral_piso: Optional[str] = None
    dir_laboral_departamento: Optional[str] = None
    # Dirección de Obsequios
    usar_direccion_laboral: Optional[bool] = False
    dir_obsequios_pais: Optional[str] = None
    dir_obsequios_provincia: Optional[str] = None
    dir_obsequios_localidad: Optional[str] = None
    dir_obsequios_codigo_postal: Optional[str] = None
    dir_obsequios_barrio: Optional[str] = None
    dir_obsequios_calle: Optional[str] = None
    dir_obsequios_numero: Optional[str] = None
    dir_obsequios_piso: Optional[str] = None
    dir_obsequios_departamento: Optional[str] = None
    # Ocasiones Especiales
    preferencia_alimentaria: Optional[str] = None
    instrucciones_entrega: Optional[str] = None
    contacto_emergencia: Optional[str] = None
    numero_emergencia: Optional[str] = None
    parentesco: Optional[str] = None
    fecha_alta: Optional[str] = None
    fecha_baja: Optional[str] = None
    motivo_baja: Optional[str] = None
    antiguedad: int
    email_corporativo: Optional[str] = None  # copia del email de la cuenta (F22)
    email_secundario: Optional[str] = None  # de la cuenta; solo en la consulta de un empleado (F22)
    departamento_id: Optional[str] = None
    departamento_nombre: Optional[str] = None
    perfil_id: Optional[str] = None
    perfil_nombre: Optional[str] = None
    hrbp_id: Optional[str] = None
    hrbp_nombre: Optional[str] = None
    seniority: Optional[str] = None
    puesto: Optional[str] = None
    foto: Optional[str] = None
    foto_thumbnail: Optional[str] = None
    activo: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, emp) -> "EmpleadoResponse":
        """Convierte modelo a response con campos calculados."""
        # Formatear CUIL: 20111111115 → 20-11111111-5
        cuil_str = str(emp.cuil)
        cuil_formateado = f"{cuil_str[:2]}-{cuil_str[2:10]}-{cuil_str[10:]}" if len(cuil_str) == 11 else cuil_str

        return cls(
            id=str(emp.id),
            codigo=emp.codigo,
            cuil=cuil_formateado,
            cuil_raw=emp.cuil,
            empleado=emp.empleado_nombre_completo,
            apellido=emp.apellido,
            nombre=emp.nombre,
            fecha_nacimiento=emp.fecha_nacimiento.strftime("%d/%m/%Y") if emp.fecha_nacimiento else None,
            edad=emp.edad,
            dni=emp.dni,
            genero=emp.genero,
            nacionalidad=emp.nacionalidad,
            estado_civil=emp.estado_civil,
            nivel_estudio=emp.nivel_estudio,
            carrera_id=str(emp.carrera_id) if emp.carrera_id else None,
            carrera_nombre=emp.carrera_rel.nombre if emp.carrera_rel else None,
            telefono_personal=emp.telefono_personal,
            email_personal=emp.email_personal,
            dir_laboral_pais=emp.dir_laboral_pais,
            dir_laboral_provincia=emp.dir_laboral_provincia,
            dir_laboral_localidad=emp.dir_laboral_localidad,
            dir_laboral_codigo_postal=emp.dir_laboral_codigo_postal,
            dir_laboral_barrio=emp.dir_laboral_barrio,
            dir_laboral_calle=emp.dir_laboral_calle,
            dir_laboral_numero=emp.dir_laboral_numero,
            dir_laboral_piso=emp.dir_laboral_piso,
            dir_laboral_departamento=emp.dir_laboral_departamento,
            usar_direccion_laboral=emp.usar_direccion_laboral or False,
            dir_obsequios_pais=emp.dir_obsequios_pais,
            dir_obsequios_provincia=emp.dir_obsequios_provincia,
            dir_obsequios_localidad=emp.dir_obsequios_localidad,
            dir_obsequios_codigo_postal=emp.dir_obsequios_codigo_postal,
            dir_obsequios_barrio=emp.dir_obsequios_barrio,
            dir_obsequios_calle=emp.dir_obsequios_calle,
            dir_obsequios_numero=emp.dir_obsequios_numero,
            dir_obsequios_piso=emp.dir_obsequios_piso,
            dir_obsequios_departamento=emp.dir_obsequios_departamento,
            preferencia_alimentaria=emp.preferencia_alimentaria,
            instrucciones_entrega=emp.instrucciones_entrega,
            contacto_emergencia=emp.contacto_emergencia,
            numero_emergencia=emp.numero_emergencia,
            parentesco=emp.parentesco,
            fecha_alta=emp.fecha_alta.strftime("%d/%m/%Y") if emp.fecha_alta else None,
            fecha_baja=emp.fecha_baja.strftime("%d/%m/%Y") if emp.fecha_baja else None,
            motivo_baja=emp.motivo_baja,
            antiguedad=emp.antiguedad,
            email_corporativo=emp.email_corporativo,
            departamento_id=str(emp.departamento_id) if emp.departamento_id else None,
            departamento_nombre=emp.departamento_rel.nombre if emp.departamento_rel else None,
            perfil_id=str(emp.perfil_id) if emp.perfil_id else None,
            perfil_nombre=emp.perfil_rel.nombre if emp.perfil_rel else None,
            hrbp_id=str(emp.hrbp_id) if emp.hrbp_id else None,
            hrbp_nombre=emp.hrbp_rel.empleado_nombre_completo if emp.hrbp_rel else None,
            seniority=emp.seniority,
            puesto=emp.puesto,
            foto=emp.foto,
            foto_thumbnail=emp.foto.replace("/fotos/nomina/", "/fotos/nomina/thumbnails/") if emp.foto else None,
            activo=emp.activo,
            created_at=emp.created_at,
            updated_at=emp.updated_at,
        )

    model_config = ConfigDict(from_attributes=True)


class EmpleadoList(BaseModel):
    """Schema para listado paginado."""

    items: List[EmpleadoResponse]
    total: int
    pagina: int
    por_pagina: int
    total_paginas: int
    grupos: Optional[List[dict]] = None


class EmpleadoBaja(BaseModel):
    """Schema para dar de baja a un empleado."""

    fecha_baja: date
    motivo_baja: str = Field(..., min_length=3, max_length=255)
