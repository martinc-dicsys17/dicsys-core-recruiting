"""Servicios de Parámetros de Recruiting (ítem «parametros»).

Origen: SkillService, HabilidadService, PersonaCatalogoService, PerfilPuestoService, ProvinciaService, CiudadService,
ArchivoCVService, LimpiezaRecruitingService y HistorialCargasConsultaService del módulo original (modulo-recluiter,
backend/modules/recruiting). Los catálogos son globales (sin empresa_id), como en el original; el historial de cargas
filtra siempre por la empresa activa. Todo nombre nuevo de un catálogo se guarda sin tildes (la ñ se conserva).
"""

import logging
import math
import os
import stat
import tempfile
import uuid
import zipfile
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.modules.recruiting.models import (
    Candidato,
    CandidatoDuplicado,
    Ciudad,
    EtapaArchivo,
    GestionBusqueda,
    HistorialCargaCV,
    HistorialCargaCVArchivo,
    HistorialPipeline,
    Postulacion,
    Provincia,
    RecruitingHabilidad,
    RecruitingLider,
    RecruitingMotivoBlacklist,
    RecruitingPerfilPuesto,
    RecruitingReclutador,
    RecruitingSkill,
    RecrutingConfig,
    Solicitud,
    TransicionEstado,
)
from backend.modules.recruiting.services import (
    MENSAJE_ERROR_INTERNO,
    ROL_CONSULTORA,
    ROL_FREELANCE,
    CandidatoService,
    _clave_ubicacion,
    _sin_tildes_conservando_enie,
    obtener_rol_recruiting,
    usuario_es_grupo_externos,
)
from backend.modules.usuarios.models import Usuario

MENSAJE_SIN_ACCESO = "No tenés acceso a Parámetros de Recruiting"


def exigir_parametros(db: Session, current_user: Usuario, empresa_id: uuid.UUID) -> None:
    """Parámetros no está disponible para el grupo EXTERNOS ni para los roles Freelance y Consultora (el permiso del ítem
    lo valida el router)."""
    if usuario_es_grupo_externos(db, current_user, empresa_id) or obtener_rol_recruiting(
        db, current_user, empresa_id
    ) in (ROL_FREELANCE, ROL_CONSULTORA):
        raise HTTPException(status_code=403, detail=MENSAJE_SIN_ACCESO)


def _nombre_nuevo(texto: Optional[str], etiqueta: str) -> str:
    """Nombre con los espacios colapsados y sin tildes; vacío es 400."""
    nombre = " ".join((texto or "").split())
    if not nombre:
        raise HTTPException(status_code=400, detail=" ".join(f"El nombre {etiqueta} es obligatorio.".split()))
    return _sin_tildes_conservando_enie(nombre)


# ---------------------------------------------------------------------------
# Smart Matching
# ---------------------------------------------------------------------------


class ConfigRecruitingService:
    @staticmethod
    def obtener(db: Session, empresa_id: uuid.UUID) -> int:
        """Porcentaje mínimo de coincidencia de Smart Matching de la empresa (50 si no lo configuró)."""
        config = db.query(RecrutingConfig).filter(RecrutingConfig.empresa_id == empresa_id).first()
        return config.match_minimo_porcentaje if config else 50

    @staticmethod
    def actualizar(db: Session, empresa_id: uuid.UUID, porcentaje: int, usuario: Optional[str]) -> int:
        """Guarda el porcentaje de la empresa (un único registro por empresa)."""
        config = db.query(RecrutingConfig).filter(RecrutingConfig.empresa_id == empresa_id).first()
        if config:
            config.match_minimo_porcentaje = porcentaje
            config.updated_by = usuario
        else:
            db.add(RecrutingConfig(empresa_id=empresa_id, match_minimo_porcentaje=porcentaje, updated_by=usuario))
        db.commit()
        return porcentaje


# ---------------------------------------------------------------------------
# Catálogos con nombre único y baja lógica: skills, habilidades, líderes, reclutadores y perfiles profesionales
# ---------------------------------------------------------------------------


class CatalogoNombreService:
    """ABM de un catálogo de nombres únicos (sin distinguir mayúsculas) con baja lógica. Se instancia por modelo para no
    repetir la lógica; `con_detalle` agrega categoría y sinónimos (skills y habilidades)."""

    def __init__(self, modelo, etiqueta: str, articulo: str = "un", con_detalle: bool = False, columna_id: str = "id"):
        self.modelo = modelo
        self.etiqueta = etiqueta
        self.articulo = articulo
        self.con_detalle = con_detalle
        self.columna_id = columna_id

    def _id(self, fila):
        return getattr(fila, self.columna_id)

    def listar(self, db: Session, activo_only: bool = True, q: Optional[str] = None) -> list:
        query = db.query(self.modelo)
        if activo_only:
            query = query.filter(self.modelo.activo.is_(True))
        if q and q.strip():
            query = query.filter(func.lower(self.modelo.nombre).like(f"%{q.strip().lower()}%"))
        return query.order_by(func.lower(self.modelo.nombre).asc()).all()

    def _obtener(self, db: Session, registro_id):
        fila = db.query(self.modelo).filter(getattr(self.modelo, self.columna_id) == registro_id).first()
        if not fila:
            raise HTTPException(status_code=404, detail=f"{self.etiqueta.capitalize()} no encontrado.")
        return fila

    def _validar_duplicado(self, db: Session, nombre: str, excluir=None) -> None:
        query = db.query(self.modelo).filter(func.lower(self.modelo.nombre) == func.lower(nombre))
        if excluir is not None:
            query = query.filter(getattr(self.modelo, self.columna_id) != excluir)
        duplicado = query.first()
        if duplicado:
            raise HTTPException(
                status_code=400, detail=f"Ya existe {self.articulo} {self.etiqueta} con el nombre '{duplicado.nombre}'."
            )

    def _guardar(self, db: Session, fila):
        try:
            db.commit()
        except IntegrityError:
            # Carrera contra la restricción única de la base
            db.rollback()
            raise HTTPException(status_code=400, detail=f"Ya existe {self.articulo} {self.etiqueta} con ese nombre.")
        db.refresh(fila)
        return fila

    def crear(self, db: Session, datos):
        nombre = _nombre_nuevo(datos.nombre, "")
        self._validar_duplicado(db, nombre)
        campos: Dict[str, Any] = {"nombre": nombre, "activo": bool(datos.activo)}
        if self.con_detalle:
            campos["categoria"] = (datos.categoria or "").strip() or None
            campos["sinonimos"] = list(datos.sinonimos or [])
        fila = self.modelo(**campos)
        db.add(fila)
        return self._guardar(db, fila)

    def actualizar(self, db: Session, registro_id, datos):
        fila = self._obtener(db, registro_id)
        if datos.nombre is not None:
            nombre = " ".join(datos.nombre.split())
            # Un nombre sin cambios se conserva tal cual (los registros existentes pueden tener tildes)
            if nombre != fila.nombre:
                nombre = _nombre_nuevo(nombre, "")
                self._validar_duplicado(db, nombre, excluir=self._id(fila))
                fila.nombre = nombre
        if self.con_detalle:
            if datos.categoria is not None:
                fila.categoria = datos.categoria.strip() or None
            if datos.sinonimos is not None:
                fila.sinonimos = list(datos.sinonimos)
        if datos.activo is not None:
            fila.activo = bool(datos.activo)
        return self._guardar(db, fila)

    def desactivar(self, db: Session, registro_id):
        """Baja lógica: los candidatos y las búsquedas guardan el nombre como texto, así que no se alteran."""
        fila = self._obtener(db, registro_id)
        fila.activo = False
        return self._guardar(db, fila)


SkillsAbm = CatalogoNombreService(RecruitingSkill, "skill", con_detalle=True)
HabilidadesAbm = CatalogoNombreService(RecruitingHabilidad, "habilidad", articulo="una", con_detalle=True)
LideresAbm = CatalogoNombreService(RecruitingLider, "líder")
ReclutadoresAbm = CatalogoNombreService(RecruitingReclutador, "reclutador")
PerfilesPuestoAbm = CatalogoNombreService(RecruitingPerfilPuesto, "perfil profesional")


# ---------------------------------------------------------------------------
# Provincias y ciudades (borrado físico, nombres únicos sin tildes ni mayúsculas)
# ---------------------------------------------------------------------------


class ProvinciaService:
    @staticmethod
    def listar(db: Session) -> List[Dict[str, Any]]:
        """Provincias con la cantidad de ciudades de cada una."""
        filas = (
            db.query(Provincia, func.count(Ciudad.ciudad_id))
            .outerjoin(Ciudad, Ciudad.provincia_id == Provincia.provincia_id)
            .group_by(Provincia.provincia_id)
            .order_by(Provincia.nombre.asc())
            .all()
        )
        return [{"provincia_id": p.provincia_id, "nombre": p.nombre, "cantidad_ciudades": n} for p, n in filas]

    @staticmethod
    def _obtener(db: Session, provincia_id: int) -> Provincia:
        provincia = db.query(Provincia).filter(Provincia.provincia_id == provincia_id).first()
        if not provincia:
            raise HTTPException(status_code=404, detail="Provincia no encontrada.")
        return provincia

    @staticmethod
    def _validar_nombre(db: Session, nombre: Optional[str], excluir_id: Optional[int] = None) -> str:
        nombre = _nombre_nuevo(nombre, "de la provincia")
        clave = _clave_ubicacion(nombre)
        for existente in db.query(Provincia).all():
            if existente.provincia_id != excluir_id and _clave_ubicacion(existente.nombre) == clave:
                raise HTTPException(status_code=409, detail=f"Ya existe una provincia con el nombre '{existente.nombre}'.")
        return nombre

    @staticmethod
    def _guardar(db: Session) -> None:
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=409, detail="No se pudo guardar la provincia porque ya existe una con ese nombre."
            )

    @staticmethod
    def crear(db: Session, datos) -> Dict[str, Any]:
        provincia = Provincia(nombre=ProvinciaService._validar_nombre(db, datos.nombre))
        db.add(provincia)
        ProvinciaService._guardar(db)
        db.refresh(provincia)
        return {"provincia_id": provincia.provincia_id, "nombre": provincia.nombre, "cantidad_ciudades": 0}

    @staticmethod
    def actualizar(db: Session, provincia_id: int, datos) -> Dict[str, Any]:
        provincia = ProvinciaService._obtener(db, provincia_id)
        if datos.nombre is not None and " ".join(datos.nombre.split()) != provincia.nombre:
            provincia.nombre = ProvinciaService._validar_nombre(db, datos.nombre, excluir_id=provincia.provincia_id)
        ProvinciaService._guardar(db)
        db.refresh(provincia)
        cantidad = db.query(func.count(Ciudad.ciudad_id)).filter(Ciudad.provincia_id == provincia.provincia_id).scalar()
        return {"provincia_id": provincia.provincia_id, "nombre": provincia.nombre, "cantidad_ciudades": cantidad or 0}

    @staticmethod
    def eliminar(db: Session, provincia_id: int) -> None:
        """Borrado físico; no se permite si la provincia tiene ciudades."""
        provincia = ProvinciaService._obtener(db, provincia_id)
        nombre = provincia.nombre
        cantidad = db.query(func.count(Ciudad.ciudad_id)).filter(Ciudad.provincia_id == provincia.provincia_id).scalar() or 0
        if cantidad:
            asociadas = "1 ciudad asociada" if cantidad == 1 else f"{cantidad} ciudades asociadas"
            raise HTTPException(
                status_code=409, detail=f"No se puede eliminar la provincia '{nombre}' porque tiene {asociadas}."
            )
        try:
            db.delete(provincia)
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=409, detail=f"No se puede eliminar la provincia '{nombre}' porque está siendo utilizada."
            )


class MotivoBlacklistAbmService:
    """ABM de motivos de Blacklist (recruiting_motivos_blacklist): catálogo global, borrado físico."""

    @staticmethod
    def listar(db: Session) -> List[RecruitingMotivoBlacklist]:
        return db.query(RecruitingMotivoBlacklist).order_by(RecruitingMotivoBlacklist.id.asc()).all()

    @staticmethod
    def _obtener(db: Session, motivo_id: int) -> RecruitingMotivoBlacklist:
        motivo = db.query(RecruitingMotivoBlacklist).filter(RecruitingMotivoBlacklist.id == motivo_id).first()
        if not motivo:
            raise HTTPException(status_code=404, detail="Motivo no encontrado.")
        return motivo

    @staticmethod
    def _validar_motivo(db: Session, texto: Optional[str], excluir_id: Optional[int] = None) -> str:
        motivo = _nombre_nuevo(texto, "del motivo")
        clave = _clave_ubicacion(motivo)
        for existente in db.query(RecruitingMotivoBlacklist).all():
            if existente.id != excluir_id and _clave_ubicacion(existente.motivo) == clave:
                raise HTTPException(status_code=409, detail=f"Ya existe un motivo con el nombre '{existente.motivo}'.")
        return motivo

    @staticmethod
    def _guardar(db: Session) -> None:
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="No se pudo guardar el motivo porque ya existe uno con ese nombre.")

    @staticmethod
    def crear(db: Session, datos) -> RecruitingMotivoBlacklist:
        motivo = RecruitingMotivoBlacklist(motivo=MotivoBlacklistAbmService._validar_motivo(db, datos.motivo))
        db.add(motivo)
        MotivoBlacklistAbmService._guardar(db)
        db.refresh(motivo)
        return motivo

    @staticmethod
    def actualizar(db: Session, motivo_id: int, datos) -> RecruitingMotivoBlacklist:
        motivo = MotivoBlacklistAbmService._obtener(db, motivo_id)
        if datos.motivo is not None and " ".join(datos.motivo.split()) != motivo.motivo:
            motivo.motivo = MotivoBlacklistAbmService._validar_motivo(db, datos.motivo, excluir_id=motivo.id)
        MotivoBlacklistAbmService._guardar(db)
        db.refresh(motivo)
        return motivo

    @staticmethod
    def eliminar(db: Session, motivo_id: int) -> None:
        """Borrado físico; 409 si el motivo está siendo utilizado."""
        motivo = MotivoBlacklistAbmService._obtener(db, motivo_id)
        texto = motivo.motivo
        try:
            db.delete(motivo)
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail=f"No se puede eliminar el motivo '{texto}' porque está siendo utilizado.")


class CiudadService:
    @staticmethod
    def listar(db: Session, provincia_id: Optional[int] = None) -> List[Dict[str, Any]]:
        query = db.query(Ciudad, Provincia.nombre).join(Provincia, Provincia.provincia_id == Ciudad.provincia_id)
        if provincia_id is not None:
            query = query.filter(Ciudad.provincia_id == provincia_id)
        filas = query.order_by(Provincia.nombre.asc(), Ciudad.nombre.asc()).all()
        return [
            {"ciudad_id": c.ciudad_id, "nombre": c.nombre, "provincia_id": c.provincia_id, "provincia_nombre": pn}
            for c, pn in filas
        ]

    @staticmethod
    def _obtener(db: Session, ciudad_id: int) -> Ciudad:
        ciudad = db.query(Ciudad).filter(Ciudad.ciudad_id == ciudad_id).first()
        if not ciudad:
            raise HTTPException(status_code=404, detail="Ciudad no encontrada.")
        return ciudad

    @staticmethod
    def _validar(db: Session, nombre: Optional[str], provincia_id: int, excluir_id: Optional[int] = None) -> str:
        provincia = db.query(Provincia).filter(Provincia.provincia_id == provincia_id).first()
        if not provincia:
            raise HTTPException(status_code=400, detail="La provincia seleccionada no existe.")
        nombre = _nombre_nuevo(nombre, "de la ciudad")
        clave = _clave_ubicacion(nombre)
        for existente in db.query(Ciudad).filter(Ciudad.provincia_id == provincia_id).all():
            if existente.ciudad_id != excluir_id and _clave_ubicacion(existente.nombre) == clave:
                raise HTTPException(
                    status_code=409, detail=f"Ya existe una ciudad con el nombre '{existente.nombre}' en esta provincia."
                )
        return nombre

    @staticmethod
    def _guardar(db: Session) -> None:
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=409, detail="No se pudo guardar la ciudad porque ya existe una con ese nombre en la provincia."
            )

    @staticmethod
    def _fila(db: Session, ciudad: Ciudad) -> Dict[str, Any]:
        provincia = db.query(Provincia.nombre).filter(Provincia.provincia_id == ciudad.provincia_id).scalar()
        return {
            "ciudad_id": ciudad.ciudad_id,
            "nombre": ciudad.nombre,
            "provincia_id": ciudad.provincia_id,
            "provincia_nombre": provincia,
        }

    @staticmethod
    def crear(db: Session, datos) -> Dict[str, Any]:
        ciudad = Ciudad(nombre=CiudadService._validar(db, datos.nombre, datos.provincia_id), provincia_id=datos.provincia_id)
        db.add(ciudad)
        CiudadService._guardar(db)
        db.refresh(ciudad)
        return CiudadService._fila(db, ciudad)

    @staticmethod
    def actualizar(db: Session, ciudad_id: int, datos) -> Dict[str, Any]:
        ciudad = CiudadService._obtener(db, ciudad_id)
        provincia_id = datos.provincia_id if datos.provincia_id is not None else ciudad.provincia_id
        nombre = datos.nombre if datos.nombre is not None else ciudad.nombre
        if " ".join(nombre.split()) == ciudad.nombre and provincia_id == ciudad.provincia_id:
            return CiudadService._fila(db, ciudad)
        ciudad.nombre = CiudadService._validar(db, nombre, provincia_id, excluir_id=ciudad.ciudad_id)
        ciudad.provincia_id = provincia_id
        CiudadService._guardar(db)
        db.refresh(ciudad)
        return CiudadService._fila(db, ciudad)

    @staticmethod
    def eliminar(db: Session, ciudad_id: int) -> None:
        """Borrado físico; si la base lo impide por referencias se informa sin mostrar el error técnico."""
        ciudad = CiudadService._obtener(db, ciudad_id)
        nombre = ciudad.nombre
        try:
            db.delete(ciudad)
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(
                status_code=409, detail=f"No se puede eliminar la ciudad '{nombre}' porque está siendo utilizada."
            )


# ---------------------------------------------------------------------------
# Archivos de CV: carpetas del almacenamiento físico (solo lectura) y limpieza
# ---------------------------------------------------------------------------


class ArchivoCVService:
    """Consulta de solo lectura de las tres carpetas donde se archivan los CV originales de la carga individual y masiva
    (cv_procesados_ok, cv_duplicados y cv_errores, dentro de CV_STORAGE_DIR) y descarga de sus archivos, individual o en
    ZIP. Las carpetas son globales (no se separan por empresa), como el almacenamiento actual. El cliente nunca aporta una
    ruta: solo el nombre de la carpeta (validado contra una lista fija) y el de un archivo regular, directamente dentro de
    ella (sin subcarpetas ni enlaces simbólicos). Nada se crea, mueve, modifica ni elimina."""

    CARPETAS = (CandidatoService.CARPETA_CV_OK, CandidatoService.CARPETA_CV_DUPLICADOS, CandidatoService.CARPETA_CV_ERRORES)
    TAM_BLOQUE = 64 * 1024
    MOTIVO_NO_DISPONIBLE = "Motivo no disponible"

    @staticmethod
    def formatear_tamano(tamano_bytes: int, cero: str = "0 MB") -> str:
        """Tamaño en KB, MB o GB con dos decimales y coma decimal (ej. '125,40 MB'); sin contenido, `cero`."""
        if not tamano_bytes or tamano_bytes <= 0:
            return cero
        unidades = ("KB", "MB", "GB")
        valor = tamano_bytes / 1024
        indice = 0
        while round(valor, 2) >= 1024 and indice < len(unidades) - 1:
            valor /= 1024
            indice += 1
        texto = f"{valor:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")
        return f"{texto} {unidades[indice]}"

    @staticmethod
    def _nombre_valido(nombre: str) -> bool:
        """Nombre simple: sin separadores de ruta, ':' (flujos NTFS), caracteres de control ni prefijo '.' (ocultos)."""
        return (
            bool(nombre)
            and len(nombre) <= 255
            and not nombre.startswith(".")
            and not any(c in nombre for c in ("/", "\\", ":"))
            and not any(ord(c) < 32 for c in nombre)
        )

    @classmethod
    def _ruta_carpeta(cls, carpeta: str) -> str:
        if carpeta not in cls.CARPETAS:
            raise HTTPException(status_code=404, detail="Carpeta de CV no válida")
        return os.path.join(CandidatoService._raiz_cv_storage(), carpeta)

    @classmethod
    def _inspeccionar(cls, carpeta: str) -> List[Dict[str, Any]]:
        """Archivos regulares de la carpeta con su tamaño real y su fecha de modificación (los más recientes primero)."""
        ruta = cls._ruta_carpeta(carpeta)
        if not os.path.isdir(ruta):
            return []
        archivos: List[Dict[str, Any]] = []
        try:
            with os.scandir(ruta) as entradas:
                for entrada in entradas:
                    if not cls._nombre_valido(entrada.name):
                        continue
                    try:
                        if not entrada.is_file(follow_symlinks=False):
                            continue
                        info = entrada.stat(follow_symlinks=False)
                    except OSError:
                        continue  # el archivo desapareció durante el listado
                    archivos.append(
                        {"nombre": entrada.name, "ruta": entrada.path, "bytes": info.st_size, "mtime": info.st_mtime}
                    )
        except OSError as e:
            logging.getLogger(__name__).error(f"No se pudo leer la carpeta de CV {carpeta}: {e}")
            raise HTTPException(status_code=500, detail="No se pudo leer la carpeta de CV")
        archivos.sort(key=lambda a: (-a["mtime"], a["nombre"]))
        return archivos

    @classmethod
    def _resumen_de(cls, carpeta: str, archivos: List[Dict[str, Any]]) -> Dict[str, Any]:
        total = sum(a["bytes"] for a in archivos)
        return {
            "carpeta": carpeta,
            "cantidad_archivos": len(archivos),
            "tamano_total_bytes": total,
            "tamano_total": cls.formatear_tamano(total),
        }

    @classmethod
    def _verificar_acceso(cls, carpeta: str) -> None:
        """Un almacenamiento que el backend no puede leer ni escribir (raíz sin permisos o inexistente e imposible de
        crear) es un error de configuración, no una carpeta vacía: 503 en lugar de informar cero archivos."""
        problema = CandidatoService.problema_acceso_cv_storage(carpeta)
        if problema:
            logging.getLogger(__name__).error(f"Almacenamiento de CV no disponible ({carpeta}): {problema}")
            raise HTTPException(
                status_code=503,
                detail="El almacenamiento de CV no está disponible: el servidor no puede leer o escribir sus carpetas. "
                "Avisá a soporte.",
            )

    @classmethod
    def resumen(cls) -> List[Dict[str, Any]]:
        """Cantidad de archivos y espacio ocupado de las tres carpetas, sobre el almacenamiento físico real."""
        for carpeta in cls.CARPETAS:
            cls._verificar_acceso(carpeta)
        return [cls._resumen_de(carpeta, cls._inspeccionar(carpeta)) for carpeta in cls.CARPETAS]

    @classmethod
    def listar(
        cls, carpeta: str, pagina: Optional[int] = None, por_pagina: Optional[int] = None, buscar: Optional[str] = None
    ) -> Dict[str, Any]:
        """Resumen de una carpeta y detalle de sus archivos (nombre, tamaño y fecha), más recientes primero. Sin
        `pagina`/`por_pagina` devuelve todos; con ellos, solo la página pedida (se ajusta a la última si se pasa).
        `buscar` filtra por nombre, sin distinguir mayúsculas, antes de paginar."""
        cls._ruta_carpeta(carpeta)  # carpeta no válida: 404 antes que el diagnóstico del almacenamiento
        cls._verificar_acceso(carpeta)
        archivos = cls._inspeccionar(carpeta)
        detalle = cls._resumen_de(carpeta, archivos)
        q = (buscar or "").strip().lower()
        if q:
            archivos = [a for a in archivos if q in a["nombre"].lower()]
        detalle["total_filtrado"] = len(archivos)
        if pagina is not None or por_pagina is not None:
            por_pagina = max(1, min(int(por_pagina or 20), 200))
            total_paginas = max(1, -(-len(archivos) // por_pagina))
            pagina = min(max(1, int(pagina or 1)), total_paginas)
            archivos = archivos[(pagina - 1) * por_pagina : pagina * por_pagina]
            detalle.update({"pagina": pagina, "por_pagina": por_pagina, "total_paginas": total_paginas})
        con_motivo = carpeta == CandidatoService.CARPETA_CV_ERRORES
        motivos = cls._leer_motivos_errores() if con_motivo and archivos else {}
        detalle["archivos"] = [
            {
                "nombre": a["nombre"],
                "tamano_bytes": a["bytes"],
                "tamano": cls.formatear_tamano(a["bytes"], cero="0 KB"),
                "modificado": datetime.fromtimestamp(a["mtime"], tz=timezone.utc),
                **(
                    dict(zip(("motivo_error", "motivo_detalle"), cls.presentar_motivo(motivos.get(a["nombre"]))))
                    if con_motivo
                    else {}
                ),
            }
            for a in archivos
        ]
        return detalle

    # (fragmentos del mensaje original en minúsculas, resumen para la columna, explicación y cómo solucionarlo)
    _MOTIVOS_PRESENTACION = (
        (
            ("email válido", "email valido"),
            "Falta email válido",
            "No se encontró un email válido en el CV, y sin email no se puede registrar al candidato. "
            "Solución: verificá que el documento tenga un email de contacto escrito como texto (no como imagen) y volvé a cargarlo.",
        ),
        (
            ("formato no admitido", "formato de archivo no válido"),
            "Formato de archivo no admitido",
            "El archivo no tiene un formato permitido. Solución: convertilo a PDF, DOC o DOCX y volvé a cargarlo.",
        ),
        (
            ("excede el tamaño",),
            "Archivo demasiado grande",
            "El archivo supera el tamaño máximo permitido. Solución: reducí su peso (por ejemplo, exportando el PDF con menor calidad de imágenes) y volvé a cargarlo.",
        ),
        (
            ("está vacío", "esta vacio"),
            "Archivo vacío",
            "El archivo no tiene contenido. Solución: verificá que el documento original se abra correctamente y volvé a cargarlo.",
        ),
        (
            (
                "no se pudo leer",
                "error al leer",
                "comprimido",
                "archivo zip",
                "archivo rar",
                "zip está dañado",
                "librería rarfile",
                "herramienta 'unrar'",
            ),
            "No se pudo leer el archivo",
            "El archivo está dañado o no pudo abrirse. Solución: abrilo en tu equipo para comprobarlo, guardalo nuevamente y volvé a cargarlo.",
        ),
        (
            ("no se pudo guardar el candidato",),
            "No se pudo guardar el candidato",
            "Ocurrió un error al guardar al candidato en la base de datos. Solución: volvé a cargar el CV; si persiste, avisá a soporte.",
        ),
        (
            ("no se pudo completar la operación", "no se pudo completar la operacion"),
            "Error interno al procesar el CV",
            "Ocurrió un error inesperado del sistema mientras se procesaba el CV. Solución: volvé a cargarlo; si persiste, avisá a soporte.",
        ),
    )

    @classmethod
    def presentar_motivo(cls, motivo: Optional[str]) -> Tuple[str, str]:
        """(resumen para la columna, texto completo para el tooltip) del motivo guardado, que no se modifica. El completo
        incluye la explicación y el mensaje original como detalle técnico; un motivo no reconocido se muestra tal cual y
        sin motivo (históricos) es «Motivo no disponible»."""
        original = (motivo or "").strip()
        if not original:
            return cls.MOTIVO_NO_DISPONIBLE, cls.MOTIVO_NO_DISPONIBLE
        bajo = original.lower()
        for fragmentos, resumen, explicacion in cls._MOTIVOS_PRESENTACION:
            if any(f in bajo for f in fragmentos):
                return resumen, explicacion + "\n\nDetalle técnico: " + original
        return original, original

    @classmethod
    def _leer_motivos_errores(cls) -> Dict[str, str]:
        """Motivos registrados en cv_errores (archivo guardado -> motivo); con varias líneas del mismo archivo gana la
        última. Un índice inexistente o con líneas dañadas nunca rompe el listado."""
        import json

        ruta = os.path.join(
            cls._ruta_carpeta(CandidatoService.CARPETA_CV_ERRORES), CandidatoService.ARCHIVO_MOTIVOS_ERRORES
        )
        motivos: Dict[str, str] = {}
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                for linea in f:
                    try:
                        dato = json.loads(linea)
                    except ValueError:
                        continue
                    if (
                        isinstance(dato, dict)
                        and isinstance(dato.get("archivo"), str)
                        and isinstance(dato.get("motivo"), str)
                        and dato["motivo"].strip()
                    ):
                        motivos[dato["archivo"]] = dato["motivo"].strip()
        except OSError:
            pass
        return motivos

    @classmethod
    def abrir_archivo(cls, carpeta: str, nombre: str) -> Dict[str, Any]:
        """Valida y resuelve un archivo para descargarlo: ruta armada solo con la carpeta autorizada y un nombre simple, que
        debe existir como archivo regular (no enlace simbólico) directamente en esa carpeta."""
        ruta_carpeta = cls._ruta_carpeta(carpeta)
        if not isinstance(nombre, str) or not cls._nombre_valido(nombre):
            raise HTTPException(status_code=400, detail="Nombre de archivo no válido")
        ruta = os.path.join(ruta_carpeta, nombre)
        try:
            info = os.lstat(ruta)
        except OSError:
            raise HTTPException(status_code=404, detail="Archivo no encontrado")
        if not stat.S_ISREG(info.st_mode) or os.path.dirname(os.path.realpath(ruta)) != os.path.realpath(ruta_carpeta):
            raise HTTPException(status_code=404, detail="Archivo no encontrado")
        return {"ruta": ruta, "nombre": nombre, "tamano_bytes": info.st_size}

    @classmethod
    def crear_zip(cls, carpeta: str) -> Dict[str, Any]:
        """ZIP de los archivos de la carpeta (nombres originales, sin rutas) en un temporal anónimo que se elimina al
        cerrarlo; quien lo recibe debe cerrarlo (ver `iterar_y_cerrar`). Los originales no se tocan."""
        archivos = cls._inspeccionar(carpeta)
        if not archivos:
            raise HTTPException(status_code=404, detail=f"No hay archivos para descargar en {carpeta}")
        temporal = tempfile.TemporaryFile(prefix="cv_zip_", suffix=".zip")
        incluidos = 0
        try:
            with zipfile.ZipFile(temporal, "w", zipfile.ZIP_DEFLATED, strict_timestamps=False) as zf:
                for archivo in archivos:
                    try:
                        zf.write(archivo["ruta"], arcname=archivo["nombre"])
                        incluidos += 1
                    except FileNotFoundError:
                        continue  # el archivo desapareció mientras se armaba el ZIP
            if incluidos == 0:
                raise HTTPException(status_code=404, detail=f"No hay archivos para descargar en {carpeta}")
            temporal.flush()
            tamano = temporal.seek(0, os.SEEK_END)
            temporal.seek(0)
        except BaseException:
            temporal.close()
            raise
        return {"archivo": temporal, "tamano_bytes": tamano, "nombre": f"{carpeta}.zip", "cantidad_archivos": incluidos}

    @classmethod
    def iterar_y_cerrar(cls, archivo):
        """Entrega el archivo por bloques y lo cierra al terminar o ante cualquier corte."""
        try:
            while True:
                bloque = archivo.read(cls.TAM_BLOQUE)
                if not bloque:
                    break
                yield bloque
        finally:
            archivo.close()


class LimpiezaRecruitingService:
    """Limpieza de los datos operativos de Recruiting (Parámetros > Archivos de CV > «Limpiar BD»), solo para
    administradores (el router exige `require_admin`).

    Elimina candidatos, búsquedas, postulaciones, pipeline (gestión, historial, transiciones, adjuntos de etapa y casos
    duplicados), las notificaciones internas de Recruiting y los CV físicos (de candidatos, adjuntos, duplicados pendientes y
    las carpetas cv_procesados_ok, cv_duplicados y cv_errores). No toca usuarios, roles, permisos, empresas, parámetros,
    catálogos ni otros módulos. Las carpetas se conservan (solo se eliminan sus archivos). Alcance global, igual que el
    almacenamiento de CV."""

    @staticmethod
    def ejecutar(db: Session, current_user: Usuario, confirmar: bool) -> Dict[str, Any]:
        from backend.core.storage import cloud_storage
        from backend.modules.notificaciones_internas.models import NotificacionInterna

        # Operación destructiva: el router ya exige administrador y acá se vuelve a validar
        if getattr(current_user, "rol", None) != "admin":
            raise HTTPException(status_code=403, detail="No tenés permiso para limpiar los datos de Recruiting")
        if not confirmar:
            raise HTTPException(status_code=400, detail="Debés confirmar la limpieza para ejecutarla")

        # Dependientes primero: respeta las claves foráneas hacia candidatos y búsquedas
        etapas = (
            ("recruiting_transiciones_estado", TransicionEstado),
            ("recruiting_historial_pipeline", HistorialPipeline),
            ("recruiting_etapa_archivos", EtapaArchivo),
            ("recruiting_candidatos_duplicados", CandidatoDuplicado),
            ("recruiting_gestionBusqueda", GestionBusqueda),
            ("recruiting_postulaciones", Postulacion),
            ("recruiting_oportunidades", Solicitud),
            ("recruiting_candidatos", Candidato),
        )
        registros: Dict[str, int] = {}
        try:
            # Claves de almacenamiento a eliminar: se leen antes de borrar los registros que las referencian
            claves = {
                "cv_candidatos": [
                    c for (c,) in db.query(Candidato.cv_url).filter(Candidato.cv_url.isnot(None), Candidato.cv_url != "")
                ],
                "adjuntos_etapas": [
                    c for (c,) in db.query(EtapaArchivo.ruta_archivo).filter(EtapaArchivo.ruta_archivo.isnot(None))
                ],
                "cv_duplicados_pendientes": [
                    c
                    for (c,) in db.query(CandidatoDuplicado.archivo_temp_key).filter(
                        CandidatoDuplicado.archivo_temp_key.isnot(None)
                    )
                ],
            }
            for nombre, modelo in etapas:
                registros[nombre] = db.query(modelo).delete(synchronize_session=False)
            registros["core_notificaciones_internas"] = (
                db.query(NotificacionInterna)
                .filter(or_(NotificacionInterna.origen.ilike("recruiting%"), NotificacionInterna.enlace.ilike("/recruiting%")))
                .delete(synchronize_session=False)
            )
            db.commit()
        except Exception as e:
            db.rollback()
            logging.getLogger(__name__).error(f"Falló la limpieza de datos de Recruiting: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=MENSAJE_ERROR_INTERNO)

        # Archivos físicos: solo después de confirmar la baja de los registros (nunca quedan registros sin archivo)
        log = logging.getLogger(__name__)
        archivos: Dict[str, int] = {}
        for origen, lista in claves.items():
            borrados = 0
            for clave in set(lista):
                try:
                    if cloud_storage.delete(clave):
                        borrados += 1
                except Exception as e_arch:
                    log.warning(f"No se pudo eliminar el archivo {clave} durante la limpieza de Recruiting: {e_arch}")
            archivos[origen] = borrados
        for carpeta in ArchivoCVService.CARPETAS:
            borrados = 0
            for a in ArchivoCVService._inspeccionar(carpeta):
                try:
                    os.remove(a["ruta"])
                    borrados += 1
                except OSError as e_arch:
                    log.warning(f"No se pudo eliminar {a['ruta']} durante la limpieza de Recruiting: {e_arch}")
            archivos[carpeta] = borrados
        # El índice oculto de motivos no cuenta como archivo, pero se elimina para no asignar motivos viejos a CV futuros
        try:
            os.remove(
                os.path.join(
                    ArchivoCVService._ruta_carpeta(CandidatoService.CARPETA_CV_ERRORES),
                    CandidatoService.ARCHIVO_MOTIVOS_ERRORES,
                )
            )
        except FileNotFoundError:
            pass
        except OSError as e_ind:
            log.warning(f"No se pudo eliminar el índice de motivos de cv_errores: {e_ind}")
        log.warning(f"Limpieza de datos de Recruiting ejecutada por {current_user.email}: registros={registros} archivos={archivos}")
        return {
            "registros": registros,
            "archivos": archivos,
            "total_registros": sum(registros.values()),
            "total_archivos": sum(archivos.values()),
        }


# ---------------------------------------------------------------------------
# Historial de cargas de CV (solo consulta; el router exige administrador)
# ---------------------------------------------------------------------------


class HistorialCargasConsultaService:
    """Consulta del registro de auditoría de las cargas de CV (recruiting_historial_cargas_cv y su detalle por archivo).
    Siempre filtra por la empresa activa y solo expone metadatos: nunca contenido del CV ni datos personales extraídos."""

    TIPOS_CARGA = ("individual", "masiva")
    RESULTADOS = ("completada", "parcial", "fallida", "cancelada")

    @staticmethod
    def listar(
        db: Session,
        empresa_id: uuid.UUID,
        fecha_desde: Optional[date] = None,
        fecha_hasta: Optional[date] = None,
        usuario: Optional[str] = None,
        tipo_carga: Optional[str] = None,
        resultado: Optional[str] = None,
        pagina: int = 1,
        por_pagina: int = 20,
    ) -> Dict[str, Any]:
        q = db.query(HistorialCargaCV).filter(HistorialCargaCV.empresa_id == empresa_id)
        if fecha_desde:
            q = q.filter(HistorialCargaCV.fecha_operacion >= datetime.combine(fecha_desde, time.min))
        if fecha_hasta:
            q = q.filter(HistorialCargaCV.fecha_operacion < datetime.combine(fecha_hasta + timedelta(days=1), time.min))
        if usuario and usuario.strip():
            patron = "%" + usuario.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            q = q.filter(HistorialCargaCV.usuario_nombre.ilike(patron, escape="\\"))
        if tipo_carga:
            q = q.filter(HistorialCargaCV.tipo_carga == tipo_carga)
        if resultado:
            q = q.filter(HistorialCargaCV.resultado == resultado)
        total = q.count()
        items = (
            q.order_by(HistorialCargaCV.fecha_operacion.desc(), HistorialCargaCV.id.desc())
            .offset((pagina - 1) * por_pagina)
            .limit(por_pagina)
            .all()
        )
        return {
            "items": items,
            "total": total,
            "pagina": pagina,
            "por_pagina": por_pagina,
            "total_paginas": max(1, math.ceil(total / por_pagina)),
        }

    @staticmethod
    def detalle(db: Session, empresa_id: uuid.UUID, historial_id: uuid.UUID) -> Dict[str, Any]:
        operacion = (
            db.query(HistorialCargaCV)
            .filter(HistorialCargaCV.id == historial_id, HistorialCargaCV.empresa_id == empresa_id)
            .first()
        )
        if not operacion:
            raise HTTPException(status_code=404, detail="Operación no encontrada")
        archivos = (
            db.query(HistorialCargaCVArchivo)
            .filter(HistorialCargaCVArchivo.historial_id == operacion.id, HistorialCargaCVArchivo.empresa_id == empresa_id)
            .order_by(HistorialCargaCVArchivo.orden.asc(), HistorialCargaCVArchivo.id.asc())
            .all()
        )
        return {"operacion": operacion, "archivos": archivos}
