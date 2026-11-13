"""Servicios del módulo Recruiting.

El alcance de visibilidad de un usuario (qué búsquedas y qué candidatos ve), el Dashboard y Candidatos (listado, ficha,
carga de CV individual y masiva, y los catálogos que usa el formulario). Las reglas salen del módulo original
(modulo-recluiter, backend/modules/recruiting/services.py: DashboardService, CandidatoService,
aplicar_filtro_ownership_candidatos y usuario_es_grupo_externos).
"""

import asyncio
import logging
import os
import re
import tempfile
import unicodedata
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, UploadFile
from sqlalchemy import and_, exists, false, func, or_, select
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.orm.attributes import set_committed_value

from backend.core.utils import utc_now
from backend.database import SessionLocal, engine
from backend.modules.permisos.models import Grupo, usuario_grupo
from backend.modules.recruiting.headline_cv import detectar_headline_cv, puesto_vigente_es_condicion
from backend.modules.recruiting.models import (
    Candidato,
    CandidatoDuplicado,
    Ciudad,
    GestionBusqueda,
    Postulacion,
    Provincia,
    RecruitingHabilidad,
    RecruitingLider,
    RecruitingNivelSeniority,
    RecruitingPerfilPuesto,
    RecruitingReclutador,
    RecruitingSkill,
    RecrutingConfig,
    Solicitud,
    TransicionEstado,
    fecha_hoy,
)
from backend.modules.recruiting.schemas import (
    AsignarCandidatoRequest,
    CandidatoCreate,
    CandidatoUpdate,
    OportunidadCreate,
    OportunidadUpdate,
    RecruitingDashboard,
    RecruitingDashboardAviso,
    RecruitingDashboardKpis,
    RecruitingDashboardResumen,
    lista_de_textos,
)
from backend.modules.usuarios.models import Usuario

# Argentina no tiene horario de verano: UTC-3 fijo, como en el resto del Core
ZONA_ARGENTINA = timezone(timedelta(hours=-3))

ESTADOS_BUSQUEDA_ACTIVA = ("Abierta", "Pre-ingreso")
ESTADO_BUSQUEDA_ABIERTA = "Abierta"
ESTADO_EN_PROCESO = "En proceso"

# Grupos de permisos que definen la visibilidad, por nombre (como en el módulo original)
GRUPO_EXTERNOS = "EXTERNOS"
PARTES_NOMBRE_GRUPO_RECRUITING = ("recruit", "reclut", "recluit")


def es_grupo_externos(nombres) -> bool:
    """True si los nombres de grupo del usuario lo hacen EXTERNOS: tiene el grupo EXTERNOS y ninguno de Recruiting."""
    return GRUPO_EXTERNOS in {n.strip().upper() for n in nombres} and not incluye_grupo_recruiting(nombres)


def incluye_grupo_recruiting(nombres) -> bool:
    """True si algún nombre de grupo es de Recruiting ("recruit", "reclut" o "recluit", sin distinguir mayúsculas)."""
    return any(parte in n.strip().lower() for n in nombres for parte in PARTES_NOMBRE_GRUPO_RECRUITING)


MAX_AVISOS = 8
MAX_TRANSICIONES = 5
MAX_CANDIDATOS_NUEVOS = 3


@dataclass(frozen=True)
class AlcanceRecruiting:
    """Qué búsquedas y qué candidatos de la empresa activa ve un usuario.

    - Admin: todo.
    - Grupo de Recruiting (nombre con "recruit", "reclut" o "recluit"): todas las búsquedas y todos los candidatos.
    - Grupo EXTERNOS (sin grupo de Recruiting): solo las búsquedas que tiene asignadas (externo_id) y los candidatos
      que cargó él.
    - Cualquier otro usuario con acceso al módulo: todas las búsquedas y solo los candidatos que cargó él.
    """

    usuario_id: uuid.UUID
    es_admin: bool
    es_externo: bool
    ve_todos_los_candidatos: bool

    @classmethod
    def de(cls, db: Session, usuario: Usuario, empresa_id: uuid.UUID) -> "AlcanceRecruiting":
        if usuario.rol == "admin":
            return cls(usuario_id=usuario.id, es_admin=True, es_externo=False, ve_todos_los_candidatos=True)
        nombres = db.scalars(
            select(Grupo.nombre)
            .join(usuario_grupo, Grupo.id == usuario_grupo.c.grupo_id)
            .where(
                usuario_grupo.c.usuario_id == usuario.id,
                usuario_grupo.c.empresa_id == empresa_id,
                Grupo.activo.is_(True),
                Grupo.deleted_at.is_(None),
            )
        ).all()
        return cls(
            usuario_id=usuario.id,
            es_admin=False,
            es_externo=es_grupo_externos(nombres),
            ve_todos_los_candidatos=incluye_grupo_recruiting(nombres),
        )

    def filtro_busquedas(self) -> list:
        """Condiciones extra sobre Solicitud: el externo ve solo las búsquedas que tiene asignadas."""
        return [Solicitud.externo_id == self.usuario_id] if self.es_externo else []

    def filtro_candidatos(self) -> list:
        """Condiciones extra sobre Candidato: quien no ve todos ve solo los que cargó."""
        return [] if self.ve_todos_los_candidatos else [Candidato.creador_id == self.usuario_id]


def _hora_local(momento: datetime | None) -> str | None:
    """Fecha y hora corta (dd/mm hh:mm) en hora argentina; en la base las fechas son UTC sin zona."""
    if momento is None:
        return None
    return momento.replace(tzinfo=timezone.utc).astimezone(ZONA_ARGENTINA).strftime("%d/%m %H:%M")


class DashboardService:
    """Indicadores, avisos y resumen operativo del Dashboard de Recruiting, acotados a lo que ve el usuario."""

    @staticmethod
    def obtener(db: Session, empresa_id: uuid.UUID, usuario: Usuario) -> RecruitingDashboard:
        alcance = AlcanceRecruiting.de(db, usuario, empresa_id)
        busquedas_visibles = [
            Solicitud.empresa_id == empresa_id,
            Solicitud.activo.is_(True),
            *alcance.filtro_busquedas(),
        ]
        candidatos_visibles = [
            Candidato.empresa_id == empresa_id,
            Candidato.activo.is_(True),
            *alcance.filtro_candidatos(),
        ]

        busquedas_totales, busquedas_activas = db.execute(
            select(func.count(), func.count().filter(Solicitud.estado.in_(ESTADOS_BUSQUEDA_ACTIVA))).where(
                *busquedas_visibles
            )
        ).one()
        total_candidatos = db.scalar(select(func.count()).select_from(Candidato).where(*candidatos_visibles))
        postulaciones_en_proceso = DashboardService._en_proceso(db, empresa_id, alcance)
        skills_catalogo, habilidades_catalogo = db.execute(
            select(
                select(func.count())
                .select_from(RecruitingSkill)
                .where(RecruitingSkill.activo.is_(True))
                .scalar_subquery(),
                select(func.count())
                .select_from(RecruitingHabilidad)
                .where(RecruitingHabilidad.activo.is_(True))
                .scalar_subquery(),
            )
        ).one()

        avisos = [
            *DashboardService._busquedas_sin_postulantes(db, busquedas_visibles),
            *DashboardService._transiciones_recientes(db, empresa_id, alcance),
            *DashboardService._candidatos_nuevos(db, candidatos_visibles),
        ]
        avisos.sort(key=lambda aviso: aviso.created_at or datetime.min, reverse=True)

        return RecruitingDashboard(
            kpis=RecruitingDashboardKpis(
                busquedas_activas=busquedas_activas,
                total_candidatos=total_candidatos,
                postulaciones_en_proceso=postulaciones_en_proceso,
                skills_catalogo=skills_catalogo,
                habilidades_catalogo=habilidades_catalogo,
            ),
            avisos=avisos[:MAX_AVISOS],
            resumen_operativo=RecruitingDashboardResumen(
                tasa_candidatos_proceso=round(postulaciones_en_proceso / total_candidatos * 100, 1)
                if total_candidatos > 0
                else 0,
                busquedas_totales=busquedas_totales,
            ),
        )

    @staticmethod
    def _en_proceso(db: Session, empresa_id: uuid.UUID, alcance: AlcanceRecruiting) -> int:
        """Candidatos 'En proceso' en el pipeline (GestionBusqueda). Sin ninguno, cuenta las postulaciones del modelo
        anterior (Postulacion), como el módulo original."""
        en_pipeline = db.scalar(
            select(func.count())
            .select_from(GestionBusqueda)
            .join(Candidato, GestionBusqueda.candidato_id == Candidato.id)
            .where(
                GestionBusqueda.empresa_id == empresa_id,
                GestionBusqueda.activo.is_(True),
                GestionBusqueda.deleted_at.is_(None),
                Candidato.deleted_at.is_(None),
                GestionBusqueda.estado == ESTADO_EN_PROCESO,
                *alcance.filtro_candidatos(),
            )
        )
        if en_pipeline:
            return en_pipeline
        return db.scalar(
            select(func.count())
            .select_from(Postulacion)
            .join(Candidato, Postulacion.candidato_id == Candidato.id)
            .where(
                Postulacion.empresa_id == empresa_id,
                Postulacion.activo.is_(True),
                Postulacion.deleted_at.is_(None),
                Candidato.deleted_at.is_(None),
                Postulacion.estado == ESTADO_EN_PROCESO,
                *alcance.filtro_candidatos(),
            )
        )

    @staticmethod
    def _busquedas_sin_postulantes(db: Session, busquedas_visibles: list) -> list[RecruitingDashboardAviso]:
        """Búsquedas abiertas sin ningún candidato activo, ni en el pipeline ni en postulaciones. Una sola consulta
        (el original contaba candidatos búsqueda por búsqueda); alcanza con las más recientes, porque el panel muestra
        como mucho MAX_AVISOS avisos ordenados por fecha."""
        busquedas = db.scalars(
            select(Solicitud)
            .where(
                *busquedas_visibles,
                Solicitud.estado == ESTADO_BUSQUEDA_ABIERTA,
                ~exists().where(GestionBusqueda.oportunidad_id == Solicitud.id, GestionBusqueda.activo.is_(True)),
                ~exists().where(Postulacion.solicitud_id == Solicitud.id, Postulacion.activo.is_(True)),
            )
            .order_by(Solicitud.created_at.desc())
            .limit(MAX_AVISOS)
        ).all()
        return [
            RecruitingDashboardAviso(
                id=f"sin_cands_{busqueda.id}",
                tipo="busqueda_sin_candidatos",
                titulo=f"Búsqueda sin postulantes: {busqueda.titulo}",
                descripcion=(
                    f"La búsqueda para {busqueda.cliente or 'Cliente Confidencial'} no tiene candidatos asignados "
                    "en el embudo."
                ),
                tiempo=f"{busqueda.dias_abierta} días abierta",
                icono="alert-triangle",
                color="amber",
                enlace=f"/recruiting/oportunidades/{busqueda.id}",
                created_at=busqueda.created_at,
            )
            for busqueda in busquedas
        ]

    @staticmethod
    def _transiciones_recientes(
        db: Session, empresa_id: uuid.UUID, alcance: AlcanceRecruiting
    ) -> list[RecruitingDashboardAviso]:
        """Los últimos cambios de estado de candidatos que el usuario ve, con el nombre en la misma consulta."""
        filas = db.execute(
            select(TransicionEstado, Candidato.nombre, Candidato.apellido)
            .join(Candidato, TransicionEstado.candidato_id == Candidato.id)
            .where(TransicionEstado.empresa_id == empresa_id, *alcance.filtro_candidatos())
            .order_by(TransicionEstado.created_at.desc())
            .limit(MAX_TRANSICIONES)
        ).all()
        return [
            RecruitingDashboardAviso(
                id=str(transicion.id),
                tipo="transicion",
                titulo=f"Cambio de etapa: {nombre} {apellido}",
                descripcion=f"Pasó a '{transicion.estado_nuevo}'"
                + (f" ({transicion.motivo_rechazo})" if transicion.motivo_rechazo else ""),
                tiempo=_hora_local(transicion.created_at),
                icono="arrow-right-circle",
                color="primary",
                enlace=f"/recruiting/candidatos/{transicion.candidato_id}",
                created_at=transicion.created_at,
            )
            for transicion, nombre, apellido in filas
        ]

    @staticmethod
    def _candidatos_nuevos(db: Session, candidatos_visibles: list) -> list[RecruitingDashboardAviso]:
        """Los últimos candidatos registrados que el usuario ve."""
        candidatos = db.scalars(
            select(Candidato)
            .where(*candidatos_visibles)
            .order_by(Candidato.created_at.desc())
            .limit(MAX_CANDIDATOS_NUEVOS)
        ).all()
        return [
            RecruitingDashboardAviso(
                id=str(candidato.id),
                tipo="candidato_nuevo",
                titulo=f"Nuevo candidato: {candidato.nombre} {candidato.apellido}",
                descripcion=(
                    f"{candidato.headline or 'Perfil General'} · {candidato.seniority or 'Seniority no especificado'}"
                ),
                tiempo=_hora_local(candidato.created_at),
                icono="user-plus",
                color="emerald",
                enlace=f"/recruiting/candidatos/{candidato.id}",
                created_at=candidato.created_at,
            )
            for candidato in candidatos
        ]


# ---------------------------------------------------------------------------
# Roles y ownership de Candidatos (reglas del módulo original, sobre los helpers de grupos de arriba)
# ---------------------------------------------------------------------------

ROL_ADMIN = "ADMIN"
ROL_LIDER = "LIDER"
ROL_RECRUITER = "RECRUITER"
ROL_FREELANCE = "FREELANCE"
ROL_CONSULTORA = "CONSULTORA"


def _nombres_de_grupos(db: Session, usuario: Usuario, empresa_id: Optional[uuid.UUID]) -> List[str]:
    """Nombres de los grupos activos del usuario en la empresa activa."""
    consulta = (
        select(Grupo.nombre)
        .join(usuario_grupo, Grupo.id == usuario_grupo.c.grupo_id)
        .where(usuario_grupo.c.usuario_id == usuario.id, Grupo.activo.is_(True), Grupo.deleted_at.is_(None))
    )
    if empresa_id:
        consulta = consulta.where(usuario_grupo.c.empresa_id == empresa_id)
    return list(db.scalars(consulta).all())


def obtener_rol_recruiting(db: Session, user: Optional[Usuario], empresa_id: Optional[uuid.UUID] = None) -> str:
    """Rol operativo del usuario en Recruiting: ADMIN (rol admin) o, según el nombre de sus grupos, FREELANCE,
    CONSULTORA, LIDER o RECRUITER; sin grupo reconocible, RECRUITER."""
    if not user:
        return ROL_RECRUITER
    if getattr(user, "rol", "") == "admin":
        return ROL_ADMIN
    for nombre in _nombres_de_grupos(db, user, empresa_id):
        normal = "".join(c for c in unicodedata.normalize("NFKD", nombre.lower()) if not unicodedata.combining(c))
        if "freelance" in normal or "extern" in normal:
            return ROL_FREELANCE
        if "consultora" in normal:
            return ROL_CONSULTORA
        if "lider" in normal or "leader" in normal or ("der" in normal and "colab" not in normal):
            return ROL_LIDER
        if "recruiter" in normal or "reclutad" in normal or "recruiting" in normal:
            return ROL_RECRUITER
    return ROL_RECRUITER


def usuario_es_grupo_externos(db: Session, user: Optional[Usuario], empresa_id: Optional[uuid.UUID] = None) -> bool:
    """True si el usuario pertenece al grupo EXTERNOS (y no es admin ni de un grupo de Recruiting)."""
    if not user or getattr(user, "rol", "") == "admin":
        return False
    return es_grupo_externos(_nombres_de_grupos(db, user, empresa_id))


def aplicar_filtro_ownership_candidatos(
    query, user: Optional[Usuario], rol: str, db: Session, empresa_id: Optional[uuid.UUID] = None
):
    """Visibilidad de candidatos según el grupo: admin y grupos de Recruiting ven todos los de la empresa; cualquier otro
    usuario (EXTERNOS incluido) ve solo los que cargó él."""
    if not user or getattr(user, "rol", "") == "admin" or rol == ROL_ADMIN:
        return query
    if incluye_grupo_recruiting(_nombres_de_grupos(db, user, empresa_id)):
        return query
    return query.filter(Candidato.creador_id == user.id)


# ---------------------------------------------------------------------------
# Extracción de texto de CV (contenedores OLE de .doc y enlaces de LinkedIn)
# ---------------------------------------------------------------------------


# Palabras que aparecen junto a "LinkedIn" y no son un slug de perfil /in/.
_LINKEDIN_SLUG_STOPWORDS = frozenset(
    {
        "recruiter",
        "premium",
        "profile",
        "perfil",
        "url",
        "com",
        "www",
        "experiencia",
        "experience",
        "contacto",
        "contact",
        "in",
        "en",
        "sales",
        "navigator",
        "learning",
        "jobs",
        "company",
        "pulse",
        "feed",
        "linkedin",
        "http",
        "https",
    }
)


_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def _leer_streams_ole(data: bytes, nombres: Tuple[str, ...]) -> Dict[str, bytes]:
    """Lee streams de un contenedor OLE2 (Compound File) sin dependencias externas. Lanza ValueError si esta corrupto."""
    import struct

    if data[:8] != _OLE_MAGIC or len(data) < 512:
        raise ValueError("No es un contenedor OLE2")

    def u32(off):
        return struct.unpack_from("<I", data, off)[0]

    ssz = 1 << struct.unpack_from("<H", data, 30)[0]
    mini_ssz = 1 << struct.unpack_from("<H", data, 32)[0]
    dir_start, cutoff, minifat_start, difat_start = u32(48), u32(56), u32(60), u32(68)
    fin = 0xFFFFFFFE

    def sector(sid: int) -> bytes:
        ini = (sid + 1) * ssz
        if ini >= len(data):
            raise ValueError("Sector fuera de rango")
        return data[ini : ini + ssz]

    difat = [u32(76 + 4 * i) for i in range(109)]
    sid_difat, vueltas = difat_start, 0
    while sid_difat < 0xFFFFFFFA and vueltas < 1000:
        bloque = sector(sid_difat)
        valores = struct.unpack("<%dI" % (ssz // 4), bloque)
        difat.extend(valores[:-1])
        sid_difat = valores[-1]
        vueltas += 1
    fat: List[int] = []
    for sid in difat:
        if sid < 0xFFFFFFFA:
            fat.extend(struct.unpack("<%dI" % (ssz // 4), sector(sid)))

    def cadena(inicio: int, tabla: List[int]) -> List[int]:
        res, sid = [], inicio
        while sid < 0xFFFFFFFA and len(res) <= len(tabla):
            res.append(sid)
            sid = tabla[sid] if sid < len(tabla) else fin
        return res

    def leer_regular(inicio: int) -> bytes:
        return b"".join(sector(sid) for sid in cadena(inicio, fat))

    directorio = leer_regular(dir_start)
    entradas = []
    for i in range(len(directorio) // 128):
        e = directorio[i * 128 : (i + 1) * 128]
        largo = struct.unpack_from("<H", e, 64)[0]
        nombre = e[: max(0, largo - 2)].decode("utf-16-le", errors="ignore")
        entradas.append((nombre, e[66], struct.unpack_from("<I", e, 116)[0], struct.unpack_from("<I", e, 120)[0]))

    raiz = next((en for en in entradas if en[1] == 5), None)
    mini_stream, minifat = b"", []
    if raiz is not None and minifat_start < 0xFFFFFFFA:
        mini_stream = leer_regular(raiz[2])
        mf = leer_regular(minifat_start)
        minifat = list(struct.unpack("<%dI" % (len(mf) // 4), mf))

    resultado: Dict[str, bytes] = {}
    for nombre, tipo, inicio, tam in entradas:
        if tipo != 2 or nombre not in nombres:
            continue
        if tam < cutoff:
            partes = [mini_stream[sid * mini_ssz : (sid + 1) * mini_ssz] for sid in cadena(inicio, minifat)]
            resultado[nombre] = b"".join(partes)[:tam]
        else:
            resultado[nombre] = leer_regular(inicio)[:tam]
    return resultado


def _extraer_texto_doc_binario(contenido: bytes) -> str:
    """Texto del cuerpo de un .doc binario (Word 97-2003): contenedor OLE2 + tabla de piezas (CLX) del WordDocument.
    Lanza ValueError si el archivo no es un .doc legible."""
    import re as _re
    import struct

    streams = _leer_streams_ole(contenido, ("WordDocument", "0Table", "1Table"))
    wd = streams.get("WordDocument")
    if not wd or len(wd) < 0x40 or struct.unpack_from("<H", wd, 0)[0] != 0xA5EC:
        raise ValueError("El archivo no es un documento de Word valido")
    flags = struct.unpack_from("<H", wd, 0x0A)[0]
    if flags & 0x0100:
        raise ValueError("El documento esta cifrado")
    tabla = streams.get("1Table" if flags & 0x0200 else "0Table", b"")
    ccp_text = struct.unpack_from("<I", wd, 0x4C)[0]

    piezas: List[str] = []
    fc_clx = lcb_clx = 0
    if len(wd) >= 0x1AA:
        fc_clx, lcb_clx = struct.unpack_from("<II", wd, 0x1A2)
    clx = tabla[fc_clx : fc_clx + lcb_clx] if lcb_clx else b""
    i = 0
    while i < len(clx) and clx[i] == 1:  # Prc: se omite
        i += 3 + struct.unpack_from("<H", clx, i + 1)[0]
    if i < len(clx) and clx[i] == 2:
        lcb = struct.unpack_from("<I", clx, i + 1)[0]
        plc = clx[i + 5 : i + 5 + lcb]
        n = (len(plc) - 4) // 12
        cps = struct.unpack_from("<%dI" % (n + 1), plc, 0)
        for k in range(n):
            cp0, cp1 = cps[k], min(cps[k + 1], ccp_text)
            if cp1 <= cp0:
                continue
            fc = struct.unpack_from("<I", plc, 4 * (n + 1) + 8 * k + 2)[0]
            largo = cp1 - cp0
            if fc & 0x40000000:
                ini = (fc & 0x3FFFFFFF) // 2
                piezas.append(wd[ini : ini + largo].decode("cp1252", errors="replace"))
            else:
                ini = fc & 0x3FFFFFFF
                piezas.append(wd[ini : ini + 2 * largo].decode("utf-16-le", errors="replace"))
    else:  # documentos sin CLX: el texto va seguido desde fcMin
        fc_min, fc_mac = struct.unpack_from("<II", wd, 0x18)
        piezas.append(wd[fc_min:fc_mac].decode("cp1252", errors="replace"))

    texto = "".join(piezas)
    # Campos: se conserva el texto visible y, en los hipervinculos, tambien la URL
    texto = _re.sub(
        r'\x13\s*HYPERLINK\s+"?([^"\x13\x14\x15]*)"?[^\x13\x14\x15]*\x14([^\x13\x14\x15]*)\x15', r"\2 \1", texto
    )
    texto = _re.sub(r"\x13[^\x13\x14\x15]*\x14", "", texto)
    texto = texto.replace("\x07", " | ").replace("\r", "\n").replace("\x0b", "\n").replace("\x0c", "\n")
    texto = _re.sub(r"[\x00-\x08\x0e-\x1f]", "", texto)
    texto = _re.sub(r"(?:[ \t]*\|[ \t]*){2,}", " ", texto)
    texto = _re.sub(r"[ \t]*\|[ \t]*$", "", texto, flags=_re.MULTILINE)
    texto = _re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


def _reparar_linkedin_fragmentado(texto: str) -> str:
    """Recompone URLs de LinkedIn partidas por saltos de linea o espacios (tipico de PDF)."""
    import re

    texto = re.sub(r"(https?:)\s*/\s*/", r"\1//", texto, flags=re.IGNORECASE)
    texto = re.sub(r"(https?://)\s+", r"\1", texto, flags=re.IGNORECASE)
    texto = re.sub(r"(www)\s*\.\s*(linkedin)", r"\1.\2", texto, flags=re.IGNORECASE)
    texto = re.sub(r"(linkedin)\s*\.\s*(com)", r"\1.\2", texto, flags=re.IGNORECASE)
    texto = re.sub(r"(linkedin\.com)\s*/\s*(in)\s*/\s*", r"\1/in/", texto, flags=re.IGNORECASE)
    texto = re.sub(r"(linkedin\.com/in/)[\s]+", r"\1", texto, flags=re.IGNORECASE)
    texto = re.sub(
        r"(linkedin\.com/in/[A-Za-z0-9_%-]+)-\s+([A-Za-z0-9_%-]+)",
        r"\1-\2",
        texto,
        flags=re.IGNORECASE,
    )
    return texto


def _limpiar_slug_linkedin(raw: str) -> Optional[str]:
    """Normaliza el segmento /in/{slug} descartando query, locale y puntuacion."""
    import re
    from urllib.parse import unquote, unquote_plus

    if not raw:
        return None
    slug = unquote(unquote_plus(raw.strip()))
    slug = slug.split("?")[0].split("#")[0].strip("/")
    partes = [p for p in slug.split("/") if p]
    if partes:
        slug = partes[0]
    slug = re.sub(r"[.,;:)\]\}>]+$", "", slug).strip(".")
    if not slug or slug.lower() in _LINKEDIN_SLUG_STOPWORDS:
        return None
    if len(slug) < 3:
        return None
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_%.-]{1,99}", slug):
        return None
    return slug


def extraer_linkedin_url(texto: Optional[str]) -> Optional[str]:
    """
    Detecta el perfil /in/ de LinkedIn en texto extraido de un CV.

    Acepta http/https, www, dominio pelado, subdominios de pais, querystrings,
    texto 'LinkedIn: ...' y URLs fragmentadas. Ignora company/jobs/school.
    Devuelve siempre https://www.linkedin.com/in/{slug} o None.
    """
    import re

    if not texto:
        return None

    texto = _reparar_linkedin_fragmentado(texto)
    in_re = re.compile(
        r"(?:https?://)?(?:[\w-]+\.)?linkedin\.com/in/([A-Za-z0-9][A-Za-z0-9_%.-]*)",
        re.IGNORECASE,
    )
    for match in in_re.finditer(texto):
        slug = _limpiar_slug_linkedin(match.group(1))
        if slug:
            return f"https://www.linkedin.com/in/{slug}"

    label_re = re.compile(
        r"(?:perfil\s+(?:de\s+)?)?linkedin(?:\s*(?:url|profile|perfil))?\s*[:|.\-ΓÇôΓÇö]\s*(\S+)",
        re.IGNORECASE,
    )
    for match in label_re.finditer(texto):
        candidato = match.group(1)
        in_match = in_re.search(candidato)
        if in_match:
            slug = _limpiar_slug_linkedin(in_match.group(1))
            if slug:
                return f"https://www.linkedin.com/in/{slug}"
        token = candidato.strip().strip("/")
        if token.lower().startswith("in/"):
            token = token[3:]
        slug = _limpiar_slug_linkedin(token)
        if slug:
            return f"https://www.linkedin.com/in/{slug}"

    espacio_re = re.compile(
        r"linkedin(?:\s+(?:url|profile|perfil))?\s+(/?in/)?([A-Za-z0-9][A-Za-z0-9_%.-]{2,99})",
        re.IGNORECASE,
    )
    for match in espacio_re.finditer(texto):
        slug = _limpiar_slug_linkedin(match.group(2))
        if slug:
            return f"https://www.linkedin.com/in/{slug}"

    return None


def _uris_desde_pdf_fitz(doc) -> List[str]:
    """Lee URIs de anotaciones/links del PDF (iconos de LinkedIn sin texto visible)."""
    uris: List[str] = []
    try:
        for i in range(len(doc)):
            for link in doc[i].get_links() or []:
                uri = link.get("uri")
                if uri:
                    uris.append(str(uri))
    except Exception:
        return uris
    return uris


def _uris_desde_docx_documento(doc) -> List[str]:
    """Lee targets de hipervinculos de un Document de python-docx."""
    uris: List[str] = []
    try:
        for rel in doc.part.rels.values():
            reltype = str(getattr(rel, "reltype", "") or "")
            if "hyperlink" not in reltype.lower():
                continue
            target = getattr(rel, "target_ref", None)
            if target:
                uris.append(str(target))
    except Exception:
        return uris
    return uris


def _uris_desde_docx_rels_xml(contenido_rels: bytes) -> List[str]:
    """Lee hipervinculos desde word/_rels/document.xml.rels."""
    import xml.etree.ElementTree as ET

    uris: List[str] = []
    try:
        tree = ET.fromstring(contenido_rels)
        for rel in tree:
            target = rel.attrib.get("Target") or ""
            if target:
                uris.append(target)
    except Exception:
        return uris
    return uris


def _sin_tildes_conservando_enie(nombre: str) -> str:
    """Los datos nuevos se guardan sin tildes ni acentos en las vocales; la ñ se conserva."""
    resultado = []
    for c in unicodedata.normalize("NFD", nombre):
        if unicodedata.combining(c) and not (c == chr(0x303) and resultado and resultado[-1] in "nN"):
            continue
        resultado.append(c)
    return unicodedata.normalize("NFC", "".join(resultado))


# ---------------------------------------------------------------------------
# Catálogos de solo lectura que usa el formulario de Candidatos (el ABM es de Parámetros)
# ---------------------------------------------------------------------------

_ACENTOS_ORIGEN = "áàäâãéèëêíìïîóòöôõúùüûñç"
_ACENTOS_DESTINO = "aaaaaeeeeiiiiooooouuuunc"


def _clave_ubicacion(nombre: Optional[str]) -> str:
    """Clave de comparación de nombres de ubicación: sin tildes, sin distinguir mayúsculas y con espacios colapsados."""
    sin_tildes = "".join(c for c in unicodedata.normalize("NFKD", nombre or "") if not unicodedata.combining(c))
    return " ".join(sin_tildes.casefold().split())


class CatalogoCandidatosService:
    """Lecturas de los catálogos de Parámetros que alimentan los combos del formulario y los filtros del listado."""

    @staticmethod
    def skills(db: Session) -> List[RecruitingSkill]:
        return (
            db.query(RecruitingSkill)
            .filter(RecruitingSkill.activo.is_(True))
            .order_by(func.lower(RecruitingSkill.nombre).asc())
            .all()
        )

    @staticmethod
    def habilidades(db: Session) -> List[RecruitingHabilidad]:
        return (
            db.query(RecruitingHabilidad)
            .filter(RecruitingHabilidad.activo.is_(True))
            .order_by(func.lower(RecruitingHabilidad.nombre).asc())
            .all()
        )

    @staticmethod
    def niveles_seniority(db: Session) -> List[RecruitingNivelSeniority]:
        return db.query(RecruitingNivelSeniority).order_by(RecruitingNivelSeniority.id.asc()).all()

    @staticmethod
    def provincias(db: Session) -> List[Dict[str, Any]]:
        """Las provincias con la cantidad de ciudades que tiene cada una."""
        filas = (
            db.query(Provincia, func.count(Ciudad.ciudad_id))
            .outerjoin(Ciudad, Ciudad.provincia_id == Provincia.provincia_id)
            .group_by(Provincia.provincia_id)
            .order_by(Provincia.nombre.asc())
            .all()
        )
        return [
            {"provincia_id": p.provincia_id, "nombre": p.nombre, "cantidad_ciudades": cantidad} for p, cantidad in filas
        ]

    @staticmethod
    def ciudades(db: Session, provincia_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Las ciudades con el nombre de su provincia, opcionalmente solo las de una provincia."""
        consulta = db.query(Ciudad, Provincia.nombre).join(Provincia, Provincia.provincia_id == Ciudad.provincia_id)
        if provincia_id is not None:
            consulta = consulta.filter(Ciudad.provincia_id == provincia_id)
        return [
            {
                "ciudad_id": c.ciudad_id,
                "nombre": c.nombre,
                "provincia_id": c.provincia_id,
                "provincia_nombre": provincia_nombre,
            }
            for c, provincia_nombre in consulta.order_by(Provincia.nombre.asc(), Ciudad.nombre.asc()).all()
        ]


class SkillService:
    """Catálogo de skills activas, en la forma que usa la detección de skills de un CV."""

    @staticmethod
    def obtener_catalogo_activo(db: Session) -> List[Dict[str, Any]]:
        return [
            {
                "id": str(s.id),
                "nombre": s.nombre,
                "categoria": s.categoria,
                "sinonimos": s.sinonimos or [],
                "activo": s.activo,
            }
            for s in CatalogoCandidatosService.skills(db)
        ]


# ---------------------------------------------------------------------------
# CandidatoService
# ---------------------------------------------------------------------------


class CVSinEmailError(HTTPException):
    """El CV no contiene un email válido: no se registra ningún candidato."""

    def __init__(self, detail: str):
        super().__init__(status_code=422, detail=detail)


class CVEmailDuplicadoError(HTTPException):
    """Ya existe un candidato con el email del CV: el CV se omite sin modificar la ficha existente."""

    def __init__(self, email: str, candidato_id: Optional[uuid.UUID] = None):
        self.email = email
        self.candidato_id = candidato_id
        super().__init__(status_code=409, detail=f"Ya existe un candidato registrado con este email: {email}")


class CVDuplicadoDistintoError(CVEmailDuplicadoError):
    """Ya existe un candidato con el email del CV y el archivo es distinto: se devuelven ambos para compararlos (no se persiste nada)."""

    def __init__(
        self, email: str, actual: Dict[str, Any], nuevo: Dict[str, Any], candidato_id: Optional[uuid.UUID] = None
    ):
        super().__init__(email, candidato_id)
        self.actual = actual
        self.nuevo = nuevo


MENSAJE_ERROR_INTERNO = "No se pudo completar la operación. Intentá nuevamente"


class CVPersistenciaError(Exception):
    """Falló el guardado del candidato en la base de datos."""

    def __init__(self, email: str, causa: Exception):
        self.email = email
        self.causa = causa
        super().__init__(f"No se pudo guardar el candidato en la base de datos: {causa}")


class OcultadorCandidatosEnBusqueda:
    """
    Tarea 21: en la tabla de candidatos asignados a una busqueda, un usuario del grupo EXTERNOS ve completos solo los candidatos que el mismo
    presento (los que creo, los que asocio y los de un caso de CV duplicado que presento). Los demas se muestran anonimos, sin nombre ni
    datos de contacto. Administradores y usuarios internos nunca ven nada oculto (no se aplica ningun enmascaramiento).
    """

    EMAIL_OCULTO = "Oculto"
    CAMPOS_CONTACTO_OCULTOS = ("telefono", "linkedin_url", "cv_url")

    def __init__(self, db: Session, empresa_id: uuid.UUID, viewer: Optional[Usuario]):
        self.db = db
        self.viewer = viewer
        self.activo = bool(viewer) and usuario_es_grupo_externos(db, viewer, empresa_id)

    def _presentado_por_el_viewer(self, candidato: Any, gestion: Any) -> bool:
        if candidato.creador_id == self.viewer.id:
            return True
        if (gestion.updated_by or "").strip().lower() == (self.viewer.email or "").strip().lower():
            return True
        return self.db.query(
            exists().where(
                CandidatoDuplicado.candidato_id == candidato.id,
                CandidatoDuplicado.oportunidad_id == gestion.oportunidad_id,
                CandidatoDuplicado.presentado_por_id == self.viewer.id,
            )
        ).scalar()

    def es_anonimo(self, candidato: Any, gestion: Any) -> bool:
        return self.activo and not self._presentado_por_el_viewer(candidato, gestion)

    def es_anonimo_en_algun_contexto_sin_presentar(self, candidato: Any) -> bool:
        """True si el viewer (EXTERNOS) no presento nunca al candidato: en toda busqueda donde aparece se muestra anonimo."""
        if not self.activo:
            return False
        if candidato.creador_id == self.viewer.id:
            return False
        email = (self.viewer.email or "").strip().lower()
        gestiones = (
            self.db.query(GestionBusqueda)
            .filter(
                GestionBusqueda.candidato_id == candidato.id,
                GestionBusqueda.deleted_at.is_(None),
            )
            .all()
        )
        if any((g.updated_by or "").strip().lower() == email for g in gestiones):
            return False
        return not self.db.query(
            exists().where(
                CandidatoDuplicado.candidato_id == candidato.id,
                CandidatoDuplicado.presentado_por_id == self.viewer.id,
            )
        ).scalar()

    @staticmethod
    def etiqueta(candidato: Any) -> str:
        referencia = getattr(candidato, "codigo", None) or str(candidato.id)[:8].upper()
        return f"Candidato Anonimo #{referencia}"

    def aplicar(self, datos: Dict[str, Any], candidato: Any, gestion: Any) -> Dict[str, Any]:
        """Enmascara in situ la fila del candidato en la busqueda (si corresponde) y la devuelve."""
        if not self.es_anonimo(candidato, gestion):
            return datos
        etiqueta = self.etiqueta(candidato)
        for campo in ("nombre", "nombre_pila"):
            datos[campo] = etiqueta
        datos["apellido"] = ""
        datos["es_anonimo"] = True
        if "presentado_por" in datos:
            datos["presentado_por"] = None
        datos["email"] = self.EMAIL_OCULTO
        for campo in self.CAMPOS_CONTACTO_OCULTOS:
            datos[campo] = None
        return datos


class CandidatoService:
    """Operaciones de negocio y persistencia para Candidatos del Banco de Talentos."""

    ESTADOS_VALIDOS: set[str] = {
        "Activo",
        "Rechazado",
        "Baja del proceso",
        "Sin respuesta",
    }

    SENIORITIES_VALIDOS: set[str] = {
        "Trainee",
        "Junior",
        "Semi Senior",
        "Senior",
        "Líder Técnico",
        "Arquitecto",
    }

    @staticmethod
    def consulta(
        db: Session,
        empresa_id: uuid.UUID,
        busqueda: Optional[str] = None,
        estado: Optional[str] = None,
        fuente: Optional[str] = None,
        seniority: Optional[str] = None,
        ubicacion: Optional[str] = None,
        current_user: Optional[Usuario] = None,
        categorias: Optional[List[str]] = None,
        puesto: Optional[str] = None,
        skills: Optional[List[str]] = None,
    ):
        """
        Consulta de candidatos de la empresa activa con filtros opcionales y acotada al ownership del usuario; el router
        la pagina con paginar(). Orden: más recientes primero.
        - Siempre excluye las bajas lógicas (activo == False o deleted_at).
        - `estado` filtra por el estado del candidato (Activo, Rechazado, Baja del proceso, Sin respuesta).
        """
        query = db.query(Candidato).filter(
            Candidato.empresa_id == empresa_id,
        )

        rol = obtener_rol_recruiting(db, current_user, empresa_id)
        query = aplicar_filtro_ownership_candidatos(query, current_user, rol, db, empresa_id=empresa_id)

        # Siempre excluir bajas lógicas/soft delete
        query = query.filter(Candidato.activo.is_(True), Candidato.deleted_at.is_(None))

        estado_limpio = (estado or "").strip()
        if estado_limpio:
            query = query.filter(Candidato.estado == estado_limpio)

        if fuente:
            query = query.filter(Candidato.fuente == fuente.strip())

        # Búsqueda de texto: cada palabra debe aparecer en algún campo (AND entre palabras, OR entre campos), por lo que
        # "juan perez" encuentra nombre="juan" + apellido="perez". Sin distinguir mayúsculas ni acentos.
        for palabra in _clave_ubicacion(busqueda).split():
            patron = "%" + palabra.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            query = query.filter(
                or_(
                    *[
                        func.translate(func.lower(columna), _ACENTOS_ORIGEN, _ACENTOS_DESTINO).like(patron, escape="\\")
                        for columna in (
                            Candidato.codigo,
                            Candidato.nombre,
                            Candidato.apellido,
                            Candidato.email,
                            Candidato.dni,
                            Candidato.ubicacion,
                        )
                    ]
                )
            )

        if seniority:
            query = query.filter(Candidato.seniority.ilike(seniority.strip()))

        if ubicacion:
            u_clean = _clave_ubicacion(ubicacion)
            if u_clean == "cordoba":
                query = query.filter(
                    or_(Candidato.ubicacion.ilike("%cordoba%"), Candidato.ubicacion.ilike("%córdoba%"))
                )
            elif u_clean == "buenos aires":
                query = query.filter(
                    or_(Candidato.ubicacion.ilike("%buenos aires%"), Candidato.ubicacion.ilike("%caba%"))
                )
            elif u_clean == "otros":
                query = query.filter(
                    and_(
                        Candidato.ubicacion.isnot(None),
                        ~Candidato.ubicacion.ilike("%cordoba%"),
                        ~Candidato.ubicacion.ilike("%córdoba%"),
                        ~Candidato.ubicacion.ilike("%buenos aires%"),
                        ~Candidato.ubicacion.ilike("%caba%"),
                    )
                )
            else:
                query = query.filter(
                    or_(
                        Candidato.ubicacion.ilike(f"%{ubicacion.strip()}%"),
                        Candidato.ubicacion.ilike(f"%{u_clean}%"),
                    )
                )

        # Perfil de puesto: es el campo "headline" del candidato (el "Puesto" de su ficha); coincidencia exacta sin distinguir mayúsculas
        puesto_limpio = (puesto or "").strip()
        if puesto_limpio:
            query = query.filter(func.lower(func.trim(Candidato.headline)) == puesto_limpio.lower())

        # Categorías de skills: el candidato debe tener al menos una skill activa de alguna de las categorías elegidas
        # (OR entre categorías). Cada categoría se resuelve contra el catálogo recruiting_skills y sus skills se comparan
        # con la lista de nombres que el candidato guarda en "skills" (JSONB): un único predicado por fila, sin duplicar filas.
        categorias_pedidas = CandidatoService._normalizar_categorias_filtro(categorias)
        if categorias_pedidas:
            claves = {CandidatoService._clave_categoria(c) for c in categorias_pedidas}
            nombres_skills = [
                nombre
                for nombre, categoria in db.query(RecruitingSkill.nombre, RecruitingSkill.categoria)
                .filter(
                    RecruitingSkill.activo.is_(True),
                    RecruitingSkill.categoria.isnot(None),
                )
                .all()
                if CandidatoService._clave_categoria(categoria) in claves
            ]
            if nombres_skills:
                query = query.filter(
                    or_(*[Candidato.skills.contains([nombre]) for nombre in sorted(set(nombres_skills))])
                )
            else:
                # Categoría inexistente o sin skills activas: no hay coincidencias
                query = query.filter(false())

        # Skills específicas (opcional): se suman a la categoría; el candidato debe tener cada skill pedida
        for nombre_skill in dict.fromkeys(" ".join((s or "").split()) for s in (skills or [])):
            if nombre_skill and len(nombre_skill) <= CandidatoService.MAX_LARGO_CATEGORIA:
                query = query.filter(Candidato.skills.contains([nombre_skill]))

        return query.order_by(Candidato.created_at.desc())

    # Máximo de categorías combinables en el filtro del listado y largo máximo del nombre de una categoría
    MAX_CATEGORIAS_FILTRO = 20
    MAX_LARGO_CATEGORIA = 100

    @staticmethod
    def _clave_categoria(categoria: Optional[str]) -> str:
        """Clave de comparación de una categoría: sin distinguir mayúsculas ni espacios repetidos o sobrantes."""
        return " ".join((categoria or "").split()).casefold()

    @staticmethod
    def _normalizar_categorias_filtro(categorias: Optional[List[str]]) -> List[str]:
        """Limpia las categorías recibidas por el filtro: sin vacías, sin repetidas y acotadas en cantidad y largo."""
        limpias: List[str] = []
        vistas = set()
        for categoria in categorias or []:
            nombre = " ".join((categoria or "").split())
            clave = CandidatoService._clave_categoria(nombre)
            if not clave or len(nombre) > CandidatoService.MAX_LARGO_CATEGORIA or clave in vistas:
                continue
            vistas.add(clave)
            limpias.append(nombre)
        return limpias[: CandidatoService.MAX_CATEGORIAS_FILTRO]

    @staticmethod
    def listar_perfiles_puesto(db: Session) -> List[str]:
        """
        Perfiles de puesto activos del catálogo recruiting_perfiles_puesto, ordenados por nombre.
        Alimenta el combo "Perfil de puesto" del listado de candidatos, que filtra por el campo "headline" del candidato
        (coincidencia exacta sin distinguir mayúsculas), por lo que los nombres del catálogo deben coincidir con él.
        """
        filas = db.query(RecruitingPerfilPuesto.nombre).filter(RecruitingPerfilPuesto.activo.is_(True)).all()
        perfiles = {}
        for (nombre,) in filas:
            limpio = " ".join((nombre or "").split())
            if limpio:
                perfiles.setdefault(limpio.lower(), limpio)
        return sorted(perfiles.values(), key=lambda p: p.lower())

    @staticmethod
    def get_by_id(
        db: Session,
        empresa_id: uuid.UUID,
        id: str,
        current_user: Optional[Usuario] = None,
    ) -> Candidato:
        """Obtiene un candidato por UUID o por su codigo secuencial dentro de la empresa activa, validando permisos."""
        cand_id_str = (id or "").strip()
        candidato = None

        try:
            cand_uuid = uuid.UUID(cand_id_str)
            candidato = (
                db.query(Candidato)
                .filter(
                    Candidato.id == cand_uuid,
                    Candidato.deleted_at.is_(None),
                    Candidato.empresa_id == empresa_id,
                )
                .first()
            )
        except ValueError:
            pass

        if not candidato:
            candidato = (
                db.query(Candidato)
                .filter(
                    Candidato.codigo.ilike(cand_id_str),
                    Candidato.deleted_at.is_(None),
                    Candidato.empresa_id == empresa_id,
                )
                .first()
            )

        if not candidato:
            raise HTTPException(status_code=404, detail="Candidato no encontrado")

        if current_user:
            rol = obtener_rol_recruiting(db, current_user, empresa_id)
            if rol != ROL_ADMIN:
                q = db.query(Candidato).filter(Candidato.id == candidato.id)
                q = aplicar_filtro_ownership_candidatos(q, current_user, rol, db, empresa_id)
                if not q.first():
                    raise HTTPException(status_code=403, detail="No tenes permiso para acceder a este candidato.")

        return candidato

    @staticmethod
    def permisos(db: Session, empresa_id: uuid.UUID, current_user: Usuario) -> Dict[str, bool]:
        """Acciones habilitadas en el listado: el grupo EXTERNOS no elimina ni asigna candidatos, ni carga CV fuera de una
        búsqueda."""
        no_externo = not usuario_es_grupo_externos(db, current_user, empresa_id)
        return {
            "puede_eliminar_candidatos": no_externo,
            "puede_cargar_cv_general": no_externo,
            "puede_carga_masiva": no_externo,
            "puede_asignar_candidatos": no_externo,
        }

    @staticmethod
    def exigir_carga_general(db: Session, empresa_id: uuid.UUID, current_user: Usuario) -> None:
        if usuario_es_grupo_externos(db, current_user, empresa_id):
            raise HTTPException(
                status_code=403,
                detail="Los usuarios del grupo EXTERNOS solo pueden cargar CV desde una búsqueda asignada",
            )

    @staticmethod
    def exigir_carga_masiva(db: Session, empresa_id: uuid.UUID, current_user: Usuario) -> None:
        if usuario_es_grupo_externos(db, current_user, empresa_id):
            raise HTTPException(
                status_code=403, detail="Los usuarios del grupo EXTERNOS no pueden realizar cargas masivas de CV"
            )

    @staticmethod
    def eliminar(db: Session, empresa_id: uuid.UUID, id: str, current_user: Usuario) -> Candidato:
        """Baja lógica de un candidato; el grupo EXTERNOS no puede darlos de baja."""
        if usuario_es_grupo_externos(db, current_user, empresa_id):
            raise HTTPException(status_code=403, detail="Los usuarios del grupo EXTERNOS no pueden eliminar candidatos")
        return CandidatoService.delete(db, empresa_id, id, current_user=current_user)

    @staticmethod
    def get_ficha(db: Session, empresa_id: uuid.UUID, id: str, current_user: Optional[Usuario] = None) -> Candidato:
        """Obtiene la ficha de un candidato; los candidatos anonimos para el usuario no pueden abrirse."""
        candidato = CandidatoService.get_by_id(db, empresa_id, id, current_user=current_user)
        if OcultadorCandidatosEnBusqueda(db, empresa_id, current_user).es_anonimo_en_algun_contexto_sin_presentar(
            candidato
        ):
            raise HTTPException(status_code=403, detail="No se puede ver la ficha de un candidato anonimo.")
        return candidato

    @staticmethod
    def validar_operable(
        db: Session, empresa_id: uuid.UUID, id: str, current_user: Optional[Usuario] = None
    ) -> Candidato:
        """Impide operar (mover, descartar, adjuntar, desvincular) sobre un candidato anonimo para el usuario."""
        candidato = CandidatoService.get_by_id(db, empresa_id, id, current_user=current_user)
        if OcultadorCandidatosEnBusqueda(db, empresa_id, current_user).es_anonimo_en_algun_contexto_sin_presentar(
            candidato
        ):
            raise HTTPException(status_code=403, detail="No se puede operar sobre un candidato anonimo.")
        return candidato

    @staticmethod
    def _generar_siguiente_codigo(db: Session, empresa_id: uuid.UUID) -> str:
        """Genera el siguiente codigo amigable correlativo para el tenant (ej: C-1001, C-1002)."""
        ultimo = (
            db.query(Candidato.codigo)
            .filter(
                Candidato.empresa_id == empresa_id,
                Candidato.codigo.isnot(None),
            )
            .order_by(Candidato.created_at.desc())
            .first()
        )
        if ultimo and ultimo[0]:
            try:
                num = int(ultimo[0].replace("C-", ""))
                return f"C-{num + 1}"
            except Exception:
                pass

        total_previo = db.query(Candidato).filter(Candidato.empresa_id == empresa_id).count()
        return f"C-{1000 + total_previo + 1}"

    @staticmethod
    def _resolver_ubicacion_catalogo(
        db: Session,
        provincia_id: Optional[int],
        ciudad_id: Optional[int],
    ) -> Tuple[Optional[int], Optional[int], Optional[str]]:
        """
        Valida provincia y ciudad contra los catálogos de Parámetros (recruiting_provincias / recruiting_ciudades)
        y devuelve (provincia_id, ciudad_id, texto de ubicacion "Ciudad, Provincia").
        La ciudad debe pertenecer a la provincia elegida. Sin provincia ni ciudad devuelve (None, None, None).
        """
        if provincia_id is None and ciudad_id is None:
            return None, None, None
        if provincia_id is None:
            raise HTTPException(status_code=400, detail="Seleccioná una provincia antes de elegir la ciudad.")

        provincia = db.query(Provincia).filter(Provincia.provincia_id == provincia_id).first()
        if not provincia:
            raise HTTPException(status_code=400, detail="La provincia seleccionada no existe.")
        if ciudad_id is None:
            # La provincia generica se presenta al usuario como "Otros" (misma regla que el alta por CV)
            if provincia.nombre == CandidatoService.PROVINCIA_NO_IDENTIFICADA:
                return provincia.provincia_id, None, CandidatoService.UBICACION_NO_IDENTIFICADA
            return provincia.provincia_id, None, provincia.nombre

        ciudad = (
            db.query(Ciudad)
            .filter(
                Ciudad.ciudad_id == ciudad_id,
                Ciudad.provincia_id == provincia.provincia_id,
            )
            .first()
        )
        if not ciudad:
            raise HTTPException(status_code=400, detail="La ciudad seleccionada no pertenece a la provincia elegida.")
        return provincia.provincia_id, ciudad.ciudad_id, f"{ciudad.nombre}, {provincia.nombre}"

    @staticmethod
    def create(
        db: Session,
        empresa_id: uuid.UUID,
        datos: CandidatoCreate,
        usuario: Optional[str] = None,
        current_user: Optional[Usuario] = None,
    ) -> Candidato:
        """
        Crea un nuevo candidato validando unicidad de email dentro del tenant y asigna creador_id.
        Genera automaticamente su codigo amigable (ej: C-1001).
        """
        email_limpio = datos.email.strip().lower()

        # Validar estado si fue enviado
        estado = (datos.estado or "Activo").strip()
        if estado not in CandidatoService.ESTADOS_VALIDOS:
            estado = "Activo"

        # Provincia y ciudad del catálogo de Parámetros: si se informan, definen también el texto de ubicacion
        hay_ids_ubicacion = datos.provincia_id is not None or datos.ciudad_id is not None
        provincia_id, ciudad_id, ubicacion_catalogo = CandidatoService._resolver_ubicacion_catalogo(
            db, datos.provincia_id, datos.ciudad_id
        )

        # Si ya existe un candidato con ese email, actualizar sus datos (upsert)
        existente = (
            db.query(Candidato)
            .filter(
                Candidato.empresa_id == empresa_id,
                Candidato.email.ilike(email_limpio),
                Candidato.deleted_at.is_(None),
            )
            .first()
        )

        if existente:
            if current_user:
                rol = obtener_rol_recruiting(db, current_user, empresa_id)
                if rol != ROL_ADMIN and existente.creador_id and existente.creador_id != current_user.id:
                    raise HTTPException(
                        status_code=400, detail="Ya existe un candidato registrado con este email por otro usuario."
                    )

            if datos.nombre:
                existente.nombre = datos.nombre.strip()
            if datos.apellido is not None:
                existente.apellido = (datos.apellido or "").strip()
            if datos.telefono is not None:
                existente.telefono = datos.telefono.strip() if datos.telefono else None
            if hay_ids_ubicacion:
                existente.provincia_id = provincia_id
                existente.ciudad_id = ciudad_id
                existente.ubicacion = ubicacion_catalogo
            elif datos.ubicacion is not None:
                ubicacion_texto = datos.ubicacion.strip() if datos.ubicacion else None
                if ubicacion_texto != existente.ubicacion:
                    existente.provincia_id = None
                    existente.ciudad_id = None
                existente.ubicacion = ubicacion_texto
            if datos.dni is not None:
                existente.dni = datos.dni.strip() if datos.dni else None
            if datos.fecha_nacimiento is not None:
                existente.fecha_nacimiento = datos.fecha_nacimiento
            if datos.linkedin_url is not None:
                existente.linkedin_url = datos.linkedin_url.strip() if datos.linkedin_url else None
            if datos.cv_url is not None:
                existente.cv_url = datos.cv_url.strip() if datos.cv_url else None
            if datos.headline is not None:
                existente.headline = (datos.headline or "").strip() or None
            if datos.seniority is not None:
                existente.seniority = datos.seniority.strip() if datos.seniority else None
            if datos.modalidad is not None:
                existente.modalidad = datos.modalidad.strip() if datos.modalidad else None
            if datos.skills is not None:
                existente.skills = datos.skills
            if datos.habilidades is not None:
                existente.habilidades = datos.habilidades
            if datos.pretension_salarial is not None:
                existente.pretension_salarial = datos.pretension_salarial
            moneda_upsert = datos.moneda or datos.moneda_pretension
            if moneda_upsert is not None:
                existente.moneda_pretension = (moneda_upsert or "ARS").strip().upper()[:3]
            if estado:
                existente.estado = estado
            if datos.fuente is not None:
                existente.fuente = (datos.fuente or "Portal Propio").strip()
            existente.updated_at = utc_now()
            existente.updated_by = usuario

            db.commit()
            db.refresh(existente)
            return existente

        codigo_nuevo = CandidatoService._generar_siguiente_codigo(db, empresa_id)

        moneda_pretension_nueva = (datos.moneda or datos.moneda_pretension or "ARS").strip().upper()[:3]

        creador_id = current_user.id if current_user else None

        nuevo = Candidato(
            empresa_id=empresa_id,
            codigo=codigo_nuevo,
            nombre=datos.nombre.strip(),
            apellido=(datos.apellido or "").strip(),
            email=email_limpio,
            telefono=datos.telefono.strip() if datos.telefono else None,
            ubicacion=ubicacion_catalogo
            if hay_ids_ubicacion
            else (datos.ubicacion.strip() if datos.ubicacion else None),
            provincia_id=provincia_id,
            ciudad_id=ciudad_id,
            dni=datos.dni.strip() if datos.dni else None,
            fecha_nacimiento=datos.fecha_nacimiento,
            linkedin_url=datos.linkedin_url.strip() if datos.linkedin_url else None,
            cv_url=datos.cv_url.strip() if datos.cv_url else None,
            headline=(datos.headline or "").strip() or None,
            seniority=datos.seniority.strip() if datos.seniority else None,
            modalidad=datos.modalidad.strip() if datos.modalidad else None,
            skills=datos.skills or [],
            habilidades=datos.habilidades or [],
            pretension_salarial=datos.pretension_salarial,
            moneda_pretension=moneda_pretension_nueva,
            estado=estado,
            fuente=(datos.fuente or "Portal Propio").strip(),
            creador_id=creador_id,
            updated_by=usuario,
        )

        db.add(nuevo)
        db.commit()
        db.refresh(nuevo)
        return nuevo

    @staticmethod
    def update(
        db: Session,
        empresa_id: uuid.UUID,
        id: str,
        datos: CandidatoUpdate,
        usuario: Optional[str] = None,
        current_user: Optional[Usuario] = None,
    ) -> Candidato:
        """
        Actualiza los datos de un candidato existente verificando permisos.
        Valida que el nuevo email no este duplicado.
        """
        candidato = CandidatoService.get_by_id(db, empresa_id, id, current_user=current_user)

        if datos.email is not None:
            nuevo_email = datos.email.strip().lower()
            if nuevo_email != candidato.email.lower():
                dup = (
                    db.query(Candidato)
                    .filter(
                        Candidato.empresa_id == empresa_id,
                        Candidato.id != candidato.id,
                        Candidato.email.ilike(nuevo_email),
                        Candidato.deleted_at.is_(None),
                    )
                    .first()
                )
                if dup:
                    raise HTTPException(
                        status_code=400,
                        detail=f"El email '{nuevo_email}' ya pertenece a otro candidato",
                    )
                candidato.email = nuevo_email

        if datos.nombre is not None:
            candidato.nombre = datos.nombre.strip()
        if datos.apellido is not None:
            candidato.apellido = datos.apellido.strip()
        if datos.telefono is not None:
            candidato.telefono = datos.telefono.strip() or None
        if "provincia_id" in datos.model_fields_set or "ciudad_id" in datos.model_fields_set:
            # Provincia y ciudad del catálogo: definen también el texto de ubicacion (o lo limpian si se quitan)
            provincia_id, ciudad_id, ubicacion_catalogo = CandidatoService._resolver_ubicacion_catalogo(
                db, datos.provincia_id, datos.ciudad_id
            )
            candidato.provincia_id = provincia_id
            candidato.ciudad_id = ciudad_id
            candidato.ubicacion = ubicacion_catalogo
        elif datos.ubicacion is not None:
            ubicacion_texto = datos.ubicacion.strip() or None
            if ubicacion_texto != candidato.ubicacion:
                candidato.provincia_id = None
                candidato.ciudad_id = None
            candidato.ubicacion = ubicacion_texto
        if datos.dni is not None:
            candidato.dni = datos.dni.strip() or None
        if "fecha_nacimiento" in datos.model_fields_set:
            candidato.fecha_nacimiento = datos.fecha_nacimiento

        if datos.linkedin_url is not None:
            candidato.linkedin_url = datos.linkedin_url.strip() or None
        if datos.cv_url is not None:
            candidato.cv_url = datos.cv_url.strip() or None
        if datos.headline is not None:
            candidato.headline = datos.headline.strip() or None
        if datos.seniority is not None:
            candidato.seniority = datos.seniority.strip() or None
        if datos.modalidad is not None:
            candidato.modalidad = datos.modalidad.strip() or None
        if datos.skills is not None:
            candidato.skills = datos.skills
        if datos.habilidades is not None:
            candidato.habilidades = datos.habilidades
        if datos.pretension_salarial is not None:
            candidato.pretension_salarial = datos.pretension_salarial
        nueva_moneda = datos.moneda or datos.moneda_pretension
        if nueva_moneda is not None:
            candidato.moneda_pretension = (nueva_moneda or "ARS").strip().upper()[:3]
        if datos.estado is not None:
            est = datos.estado.strip()
            if est in CandidatoService.ESTADOS_VALIDOS:
                candidato.estado = est
        if datos.fuente is not None:
            candidato.fuente = datos.fuente.strip() or None

        candidato.updated_at = utc_now()
        candidato.updated_by = usuario

        db.commit()
        db.refresh(candidato)
        return candidato

    @staticmethod
    def delete(
        db: Session,
        empresa_id: uuid.UUID,
        id: str,
        current_user: Optional[Usuario] = None,
    ) -> Candidato:
        """Soft-delete de un candidato marcando activo=False y deleted_at."""
        candidato = CandidatoService.get_by_id(db, empresa_id, id, current_user=current_user)
        candidato.activo = False
        candidato.deleted_at = utc_now()
        db.commit()
        db.refresh(candidato)
        return candidato

    @staticmethod
    async def subir_cv(
        db: Session,
        empresa_id: uuid.UUID,
        id: str,
        archivo: UploadFile,
        usuario: Optional[str] = None,
    ) -> Candidato:
        """
        Sube el archivo de CV para un candidato existente.
        - Extensiones admitidas: .pdf, .doc, .docx
        - Tamaño máximo: 2 MB (2 * 1024 * 1024 bytes)
        - Almacenamiento: nombrado con el ID del candidato para tenerlo directamente conectado.
          Key: recruiting/cv/{candidato.id}.{ext}
        """
        import os

        from backend.core.storage import cloud_storage

        candidato = CandidatoService.get_by_id(db, empresa_id, id)

        if not archivo.filename:
            raise HTTPException(status_code=400, detail="No se seleccionó ningún archivo de CV")

        nombre_archivo = archivo.filename.lower()
        _, ext = os.path.splitext(nombre_archivo)
        ext = ext.lower()

        extensiones_validas = {".pdf", ".doc", ".docx"}
        if ext not in extensiones_validas:
            raise HTTPException(
                status_code=400, detail="Formato de archivo no válido. Solo se admiten archivos PDF, DOC y DOCX."
            )

        contenido = await archivo.read()
        max_bytes = 2 * 1024 * 1024  # 2 MB
        if len(contenido) > max_bytes:
            raise HTTPException(status_code=400, detail="El archivo excede el tamaño máximo permitido de 2 MB.")

        # Content types correspondientes
        content_types = {
            ".pdf": "application/pdf",
            ".doc": "application/msword",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }
        content_type = content_types.get(ext, archivo.content_type or "application/octet-stream")

        # Guardar en storage nombrado con el id del candidato
        # Ej: recruiting/cv/{candidato.id}.pdf
        key = f"recruiting/cv/{candidato.id}{ext}"
        cloud_storage.upload(key, contenido, content_type)

        # Actualizar cv_url del candidato
        candidato.cv_url = key
        candidato.updated_at = utc_now()
        if usuario:
            candidato.updated_by = usuario

        db.commit()
        db.refresh(candidato)
        return candidato

    @staticmethod
    def _texto_de_span_pdf(span: Dict[str, Any]) -> str:
        """
        Texto de un span de PyMuPDF ("rawdict"). Los títulos con letras espaciadas ("M A R C O S   M A R A N G O N I")
        llegan con un espacio entre todas las letras y sin separación entre palabras; en ese caso las palabras se
        reconstruyen con la distancia entre letras (la separación entre palabras es claramente mayor).
        """
        caracteres = span.get("chars") or []
        texto = "".join(c.get("c", "") for c in caracteres)
        tokens = texto.split()
        if len(tokens) < 5 or any(len(t) != 1 for t in tokens):
            return texto.strip()
        letras = [c for c in caracteres if c.get("c", "").strip()]
        huecos = [letras[i + 1]["bbox"][0] - letras[i]["bbox"][2] for i in range(len(letras) - 1)]
        mediana = sorted(huecos)[len(huecos) // 2]
        palabras = [letras[0]["c"]]
        for hueco, letra in zip(huecos, letras[1:]):
            if hueco > max(mediana * 1.6, mediana + 4):
                palabras.append(letra["c"])
            else:
                palabras[-1] += letra["c"]
        return " ".join(palabras)

    @staticmethod
    def _extraer_encabezado_visual_pdf(contenido: bytes, max_lineas: int = 4) -> str:
        """
        Texto "destacado" de la parte superior de la primera página de un PDF, en orden de lectura visual.

        El texto lineal de un PDF sigue el orden en que se dibujó cada bloque, no el orden en que se lee: con columnas
        laterales o encabezados gráficos el nombre llega después de secciones enteras (perfil, habilidades). Acá se usan
        las posiciones y los tamaños de fuente: se toman las líneas de la mitad superior de la página 1 cuyo tamaño
        sobresale del cuerpo del CV y no es mucho menor que el título más grande, se descartan las repetidas (texto en negrita simulada con
        una copia superpuesta) y se ordenan por posición. Devuelve "" si no se puede determinar (PDF escaneado, error).
        """
        try:
            import fitz

            with fitz.open(stream=contenido, filetype="pdf") as doc:
                if len(doc) == 0:
                    return ""
                pagina = doc[0]
                alto = float(pagina.rect.height) or 1.0
                lineas = []  # (y, x, tamaño, texto)
                tamanos_cuerpo: List[Tuple[float, int]] = []
                for bloque in pagina.get_text("rawdict").get("blocks", []):
                    for linea in bloque.get("lines", []):
                        textos = [(s, CandidatoService._texto_de_span_pdf(s)) for s in linea.get("spans", [])]
                        textos = [(s, t) for s, t in textos if t]
                        if not textos:
                            continue
                        texto = " ".join(t for _, t in textos).strip()
                        tamano = max(float(s.get("size", 0)) for s, _ in textos)
                        for s, t in textos:
                            tamanos_cuerpo.append((float(s.get("size", 0)), len(t)))
                        x0, y0 = linea["bbox"][0], linea["bbox"][1]
                        lineas.append((float(y0), float(x0), tamano, texto))
                if not lineas or not tamanos_cuerpo:
                    return ""
                # Tamaño del cuerpo: mediana ponderada por cantidad de caracteres
                tamanos_cuerpo.sort()
                total = sum(n for _, n in tamanos_cuerpo)
                acumulado = 0
                cuerpo = tamanos_cuerpo[-1][0]
                for tam, n in tamanos_cuerpo:
                    acumulado += n
                    if acumulado >= total / 2:
                        cuerpo = tam
                        break
                zona = [lin for lin in lineas if lin[0] <= alto * 0.5]
                if not zona:
                    return ""
                maximo = max(lin[2] for lin in zona)
                umbral = max(cuerpo * 1.3, maximo * 0.55)  # el apellido suele ir en un cuerpo menor que el nombre
                destacadas = sorted((lin for lin in zona if lin[2] >= umbral), key=lambda lin: (round(lin[0]), lin[1]))
                resultado: List[str] = []
                for _, _, _, texto in destacadas:
                    if texto not in resultado:
                        resultado.append(texto)
                return "\n".join(resultado[:max_lineas])
        except Exception:
            return ""

    @staticmethod
    def _extraer_texto_de_archivo(contenido: bytes, ext: str) -> str:
        """Extrae el texto completo de un archivo PDF o DOCX utilizando librerías nativas con manejo robusto de buffers."""
        logger = logging.getLogger(__name__)
        texto = ""
        ext = ext.lower().strip()

        if ext == ".pdf":
            from backend.modules.recruiting import pdf_texto_cv

            # 1. PyMuPDF página por página, en orden de lectura (columnas, margen de fechas). Las URIs de los enlaces
            #    se agregan al final y no cuentan como texto: no deciden si una página necesita OCR.
            paginas: List[str] = []
            paginas_ocr: List[int] = []
            uris: List[str] = []
            try:
                import fitz

                with fitz.open(stream=contenido, filetype="pdf") as doc:
                    for i in range(len(doc)):
                        pagina = doc[i]
                        paginas.append(pdf_texto_cv.texto_pagina_ordenado(pagina))
                        if pdf_texto_cv.pagina_necesita_ocr(pagina):
                            paginas_ocr.append(i)
                    uris = _uris_desde_pdf_fitz(doc)
            except Exception as e_fitz:
                logger.warning(f"Extracción PyMuPDF no exitosa: {e_fitz}. Probando con pypdf...")
                paginas, paginas_ocr, uris = [], [], []

            # 1b. OCR solo de las páginas escaneadas (PDF mixto o escaneado, aunque tenga enlaces); el resto conserva
            #     el texto digital. Si el OCR falla, la página queda con lo que ya tenía.
            if paginas_ocr:
                from backend.core.cv_ocr import reconocer_cajas_pdf

                for i, cajas in reconocer_cajas_pdf(contenido, paginas_ocr).items():
                    paginas[i] = pdf_texto_cv.combinar_texto_pagina(
                        paginas[i], pdf_texto_cv.texto_desde_cajas_ocr(cajas)
                    )
            texto = "\n".join(p.strip() for p in paginas if p.strip()).strip()

            # 2. Fallback con pypdf
            if not texto:
                try:
                    from io import BytesIO

                    from pypdf import PdfReader

                    stream = BytesIO(contenido)
                    reader = PdfReader(stream)
                    paginas = []
                    for page in reader.pages:
                        try:
                            t = page.extract_text()
                            if t:
                                paginas.append(t)
                        except Exception:
                            continue
                    texto = "\n".join(paginas).strip()
                except Exception as e_pypdf:
                    logger.warning(f"Extracción pypdf no exitosa: {e_pypdf}")
                    texto = ""

            # 3. Ultimo recurso: ningún texto en todo el documento y ninguna página ya reconocida -> OCR de las primeras
            #    páginas (texto dibujado de una forma que la evaluación por página no detectó).
            if not texto and not paginas_ocr:
                from backend.core.cv_ocr import extraer_texto_pdf_por_ocr

                texto = extraer_texto_pdf_por_ocr(contenido)

            # 4. URIs de los enlaces (iconos de LinkedIn sin texto visible), siempre al final
            if uris:
                texto = (texto + "\n" + "\n".join(uris)).strip()

        elif ext == ".docx":
            # 1. Intentar con python-docx (extrae párrafos, tablas y textos estándar)
            try:
                from io import BytesIO

                import docx

                doc = docx.Document(BytesIO(contenido))
                parrafos = []
                from docx.table import Table as _DocxTable
                from docx.text.paragraph import Paragraph as _DocxParagraph

                # Recorrer el cuerpo en orden de documento: el encabezado con el nombre suele estar en una tabla
                for elemento in doc.element.body.iterchildren():
                    if elemento.tag.endswith("}p"):
                        p = _DocxParagraph(elemento, doc)
                        if p.text and p.text.strip():
                            parrafos.append(p.text.strip())
                    elif elemento.tag.endswith("}tbl"):
                        table = _DocxTable(elemento, doc)
                        for row in table.rows:
                            fila_textos = [cell.text.strip() for cell in row.cells if cell.text and cell.text.strip()]
                            if fila_textos:
                                parrafos.append(" | ".join(fila_textos))
                parrafos.extend(_uris_desde_docx_documento(doc))
                texto = "\n".join(parrafos).strip()
            except Exception as e_docx_lib:
                logger.warning(f"Extracción python-docx no exitosa: {e_docx_lib}. Probando extracción XML directa...")
                texto = ""

            # 2. Fallback de extracción directa del XML interno del docx
            if not texto:
                try:
                    import xml.etree.ElementTree as ET
                    import zipfile
                    from io import BytesIO

                    with zipfile.ZipFile(BytesIO(contenido)) as docx_zip:
                        xml_content = docx_zip.read("word/document.xml")
                        tree = ET.fromstring(xml_content)
                        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                        parrafos = []
                        for p in tree.iterfind(".//w:p", ns):
                            textos_p = [node.text for node in p.iterfind(".//w:t", ns) if node.text]
                            if textos_p:
                                parrafos.append("".join(textos_p))
                        try:
                            parrafos.extend(_uris_desde_docx_rels_xml(docx_zip.read("word/_rels/document.xml.rels")))
                        except Exception:
                            pass
                        texto = "\n".join(parrafos).strip()
                except Exception as e_docx_xml:
                    logger.warning(f"Extracción docx XML no exitosa: {e_docx_xml}")
                    texto = ""

        elif ext == ".doc":
            # .doc es formato binario OLE2 (Word 97-2003) - no es ZIP como .docx
            if contenido[:2] == b"PK":
                # Un .docx renombrado como .doc
                return CandidatoService._extraer_texto_de_archivo(contenido, ".docx")

            # Estrategia 1: lector propio de OLE2 + tabla de piezas de Word (sin dependencias externas)
            try:
                texto = _extraer_texto_doc_binario(contenido)
            except Exception as e_doc:
                logger.warning(f"Extraccion de .doc binario no exitosa: {e_doc}")
                texto = ""

            # Estrategia 2: antiword (si esta disponible en el sistema)
            if not texto and contenido[:8] == _OLE_MAGIC:
                try:
                    import shutil
                    import subprocess

                    if shutil.which("antiword"):
                        result_proc = subprocess.run(
                            ["antiword", "-"],
                            input=contenido,
                            capture_output=True,
                            timeout=10,
                        )
                        texto = result_proc.stdout.decode("utf-8", errors="ignore").strip()
                except Exception:
                    texto = ""

            # Estrategia 3: extraer strings imprimibles solo de contenedores OLE2 reales (un archivo que no es .doc no se interpreta)
            if not texto and contenido[:8] == _OLE_MAGIC:
                try:
                    import re as _re

                    raw = contenido.decode("latin1", errors="ignore")
                    tokens = _re.findall(r"[A-Za-z0-9@._+\-/\xc0-\xff]{3,}", raw)
                    texto = " ".join(tokens).strip()
                except Exception:
                    texto = ""

        return texto or ""

    # Ubicación que se asigna cuando el CV no permite identificar una provincia y ciudad del catálogo
    UBICACION_NO_IDENTIFICADA = "Otros"
    PROVINCIA_NO_IDENTIFICADA = "No identificada"

    @staticmethod
    def _provincia_no_identificada_id(db: Session) -> Optional[int]:
        """Id de la provincia generica del catalogo (None si aun no fue sembrada)."""
        provincia = db.query(Provincia).filter(Provincia.nombre == CandidatoService.PROVINCIA_NO_IDENTIFICADA).first()
        return provincia.provincia_id if provincia else None

    # Etiquetas que indican una ubicación explícita (ej. "Ubicación: ...", "Location: ..."), al inicio de una línea
    # o dentro de una línea de contacto ("Email: ... Location: Córdoba, Argentina. LinkedIn: ...")
    ETIQUETAS_UBICACION_CV = (
        "ubicacion",
        "domicilio",
        "direccion",
        "residencia",
        "lugar de residencia",
        "localidad",
        "ciudad",
        "vive en",
        "reside en",
        "radicado en",
        "location",
        "address",
        "city",
        "based in",
        "lives in",
        "resides in",
    )
    # Cantidad de caracteres iniciales del CV considerados "encabezado" (datos de contacto del candidato)
    ZONA_ENCABEZADO_CV = 700
    # Cantidad de líneas, antes y después del email o del nombre del candidato, que forman su bloque de contacto.
    # En los PDF con columnas laterales el texto llega desordenado y los datos de contacto pueden quedar lejos del inicio.
    LINEAS_CONTEXTO_CONTACTO = 3
    # Abreviaturas habituales del nombre de una provincia (clave normalizada; fragmentos de expresión regular).
    # Sirven para reconocer la provincia en el contexto de una ubicación ("La Plata, BsAs") y para su capital.
    ABREVIATURAS_PROVINCIA = {"cordoba": (r"cba",), "buenos aires": (r"bs\.?\s*as\.?",)}
    # Ciudad capital de cada provincia en el catálogo (nombre normalizado) y si el nombre de la provincia solo
    # ("Córdoba", "Cba", "Buenos Aires", "BsAs") ya indica esa capital. No la indica: "Córdoba, Argentina" o "Buenos Aires,
    # Argentina" pueden ser cualquier localidad de la provincia, así que se conserva la provincia sin ciudad. La capital se
    # asigna solo con una expresión inequívoca ("Córdoba Capital", "Ciudad de Córdoba", "Capital, Córdoba", "CABA"...).
    CAPITALES_PROVINCIA = {"cordoba": ("cordoba capital", False), "buenos aires": ("caba", False)}
    # Provincias para las que "Provincia de <Provincia>" NO identifica a la capital (es la provincia completa)
    PROVINCIAS_SIN_CAPITAL_IMPLICITA = ("buenos aires",)
    # Expresiones que identifican a la capital sin ambigüedad (fragmentos de expresión regular sobre texto sin tildes);
    # pueden ir precedidas por un barrio: "Almagro - CABA", "Palermo, Capital Federal".
    ALIAS_CAPITAL_INEQUIVOCOS = {
        "buenos aires": (
            r"caba",
            r"c\.?\s?a\.?\s?b\.?\s?a\.?",
            r"gcba",
            r"capital federal",
            r"ciudad autonoma de buenos aires",
            r"ciudad de buenos aires",
            r"buenos aires city",
        ),
    }
    # Localidades que no son ciudades del catálogo pero pertenecen a un partido que sí lo es (clave de provincia ->
    # {nombre de la localidad, sin tildes: clave de la ciudad/partido del catálogo}). La ciudad normalizada es el partido
    # y el texto de ubicación conserva la localidad del CV ("Tristan Suarez, Buenos Aires" con ciudad Ezeiza).
    LOCALIDADES_PARTIDO = {
        "buenos aires": {"Tristan Suarez": "ezeiza", "Villa Ballester": "san martin"},
    }
    # Partículas que van en minúscula dentro del nombre de una localidad ("San Nicolas de los Arroyos")
    PARTICULAS_LOCALIDAD = frozenset({"de", "del", "la", "las", "los", "el", "y"})
    PAISES_UBICACION = ("argentina", "argentine", "arg", "ar")
    # Instituciones: una ciudad que aparece dentro de su nombre ("Universidad de Mar del Plata") no es una residencia
    INSTITUCIONES_UBICACION = (
        r"universidad|instituto|colegio|escuela|facultad|banco|municipalidad|hospital|club|empresa"
    )

    @staticmethod
    def _segmentos_ubicacion(linea: str) -> List[str]:
        """
        Divide una línea de contacto en segmentos que pueden ser una ubicación: los símbolos, viñetas y guiones largos
        separan; los caracteres invisibles se eliminan y los emails, URLs, teléfonos y rótulos de contacto se descartan.
        Devuelve los segmentos como claves normalizadas (sin tildes, en minúsculas y sin espacios repetidos).
        """
        import re

        partes = []
        for c in linea or "":
            categoria = unicodedata.category(c)
            if c == "\t":
                partes.append(" ")
            elif categoria in ("Cf", "Cc"):
                continue
            elif categoria in ("So", "Sm") or c in "|•·–—":
                partes.append(" | ")
            else:
                partes.append(c)
        clave = _clave_ubicacion("".join(partes))
        clave = re.sub(r"\S+@\S+|(?:https?://|www\.)\S+|\S*linkedin\S*|\S*github\S*", " | ", clave)
        clave = re.sub(r"\+?\(?\d[\d\s().\-]{5,}\d", " | ", clave)
        clave = re.sub(
            r"(?<![a-z])(?:cel|cell|cellphone|tel|telefono|celular|movil|mobile|phone|whatsapp|email|e-mail|mail|correo"
            r"|portfolio)\s*:?",
            " | ",
            clave,
        )
        return [s.strip(" .,;:-") for s in clave.split("|") if s.strip(" .,;:-")]

    # Organismos cuyo nombre incluye una provincia ("Gobierno de Córdoba", "Banco de la Provincia de Buenos Aires"):
    # la provincia de una institución no es la residencia del candidato
    ORGANISMOS_PROVINCIA = r"gobierno|ministerio|provincial|policia|poder judicial|legislatura|tribunal"

    @staticmethod
    def _provincia_sin_ciudad_catalogo(
        provincias: List[Any],
        fuente_provincia: Dict[int, str],
        valores_etiqueta: List[Tuple[str, str]],
        bloques: List[str],
        seccion: "re.Pattern[str]",
        rango_anios: "re.Pattern[str]",
        contacto: "re.Pattern[str]",
    ) -> Optional[Tuple[Any, str]]:
        """
        (provincia, clave de la localidad o "") declarada como ubicación del candidato cuando su localidad no está en el catálogo.
        Respaldo de detectar_ubicacion_catalogo: solo se usa si no se identificó ninguna ciudad. La ubicación debe tener la
        forma "<Localidad>, <Provincia>[, País]" o "Provincia de <Provincia>", y estar en el valor de un rótulo
        ("Localidad: ...", que puede continuar en la línea siguiente) o en una línea de contacto del bloque de contacto
        (línea sola o junto a teléfono/email/LinkedIn). Nunca dentro de instituciones, organismos, estudios ni experiencia
        con fechas. Si se mencionan dos provincias distintas, es ambiguo y devuelve None.
        """
        import re

        paises = "|".join(CandidatoService.PAISES_UBICACION)
        localidad = r"[a-z][a-z.'\-]*(?: [a-z][a-z.'\-]*){0,4}"
        patrones = {
            p.provincia_id: re.compile(
                r"^(?:(?P<localidad>"
                + localidad
                + r")\s*[,;/\-]\s*)?(?:(?:provincia|pcia\.?|prov\.?) de )?(?:"
                + fuente_provincia[p.provincia_id]
                + r")(?:\s*[,;/\-]?\s*(?:"
                + paises
                + r"))*$"
            )
            for p in provincias
            if p.nombre != CandidatoService.PROVINCIA_NO_IDENTIFICADA and fuente_provincia.get(p.provincia_id)
        }
        institucion = re.compile(
            r"(?<![a-z])(?:"
            + CandidatoService.INSTITUCIONES_UBICACION
            + r"|"
            + CandidatoService.ORGANISMOS_PROVINCIA
            + r")(?![a-z])"
        )

        def provincias_en(fragmento: str, exigir_contacto: bool) -> Dict[int, str]:
            encontradas: Dict[int, str] = {}  # provincia_id -> primera localidad mencionada con ella ("" si ninguna)
            for linea in fragmento.splitlines():
                clave_linea = _clave_ubicacion(linea)
                if not clave_linea:
                    continue
                if seccion.match(clave_linea):
                    break
                if rango_anios.search(clave_linea) or institucion.search(clave_linea):
                    continue
                segmentos = CandidatoService._segmentos_ubicacion(linea)
                if exigir_contacto and not (len(segmentos) == 1 or contacto.search(clave_linea)):
                    continue
                for seg in segmentos:
                    for pid, rx in patrones.items():
                        m = rx.match(seg)
                        if m and not encontradas.get(pid):
                            encontradas[pid] = (m.group("localidad") or "").strip()
            return encontradas

        por_id = {p.provincia_id: p for p in provincias}
        # Valor de un rótulo de ubicación: solo, o unido a la línea siguiente cuando quedó partido ("Residencia: Tristán / Suárez, Buenos Aires")
        for valor, siguiente in valores_etiqueta:
            for fragmento in (valor, f"{valor} {siguiente}" if siguiente else ""):
                encontradas = provincias_en(fragmento, exigir_contacto=False) if fragmento else {}
                if len(encontradas) == 1:
                    pid, localidad_clave = next(iter(encontradas.items()))
                    return por_id[pid], localidad_clave
        for bloque in bloques:
            encontradas = provincias_en(bloque, exigir_contacto=True)
            if len(encontradas) == 1:
                pid, localidad_clave = next(iter(encontradas.items()))
                return por_id[pid], localidad_clave
        return None

    @staticmethod
    def _nombre_localidad_cv(texto: Optional[str], clave: str) -> str:
        """
        Nombre de una localidad tal como figura en el CV, sin tildes (la ñ se conserva) y con mayúscula inicial en cada
        palabra salvo las partículas ("Hernando", "Villa Cañas", "San Nicolas de los Arroyos"). Si no se encuentra en el
        texto original se arma desde su clave normalizada.
        """
        import re

        variantes = {"a": "aáàâä", "e": "eéèêë", "i": "iíìîï", "o": "oóòôö", "u": "uúùûü", "n": "nñ"}
        patron = "".join(r"\s+" if c == " " else "[" + re.escape(variantes.get(c, c)) + "]" for c in clave)
        m = re.search(r"(?<![^\W\d_])" + patron + r"(?![^\W\d_])", texto or "", re.IGNORECASE)
        palabras = _sin_tildes_conservando_enie(m.group(0) if m else clave).split()
        return " ".join(
            p.lower() if i and p.lower() in CandidatoService.PARTICULAS_LOCALIDAD else p[:1].upper() + p[1:].lower()
            for i, p in enumerate(palabras)
        )

    @staticmethod
    def detectar_ubicacion_catalogo(
        db: Optional[Session], texto: Optional[str], nombre_completo: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Detecta provincia y ciudad del candidato en el texto de un CV comparando con los catálogos de Parámetros
        (recruiting_provincias / recruiting_ciudades). No crea registros ni infiere ciudades que no estén en el catálogo.
        Devuelve {"provincia_id", "ciudad_id", "ubicacion"} o None si no hay una coincidencia confiable.

        Criterios (nombres comparados sin tildes, sin distinguir mayúsculas ni espacios repetidos, como palabras completas):
        - Línea con etiqueta de ubicación ("Ubicación:", "Domicilio:", "Location:"...), al inicio o dentro de una línea de
          contacto, con el valor en la misma línea o en la siguiente: alcanza con que figure una ciudad del catálogo.
        - Bloque de contacto del CV (primeros caracteres, más las líneas que rodean al email y al nombre del candidato):
          la ciudad debe estar acompañada de su provincia o del país ("La Plata, Buenos Aires", "Pilar - Argentina"),
          para no confundirla con nombres de personas, empresas o instituciones. Si hay más de una ubicación distinta, es ambiguo.
        - Una ciudad cuya provincia es otra de las mencionadas a su alrededor se descarta.
        - "<Provincia> Capital" también se reconoce como "Ciudad de <Provincia>", "<Provincia>, <Provincia>" y "Capital, <Provincia>".
        - Localidades de un partido del catálogo (LOCALIDADES_PARTIDO: "Tristán Suárez" -> Ezeiza): la ciudad es el partido y
          el texto de ubicación conserva la localidad ("Tristan Suarez, Buenos Aires").
        - Respaldo (solo si no se identificó ninguna ciudad): una ubicación "<Localidad>, <Provincia>" cuya localidad no está
          en el catálogo ("Hernando, Córdoba") o "Provincia de <Provincia>" conserva la provincia, sin ciudad
          (_provincia_sin_ciudad_catalogo), y el texto de ubicación conserva la localidad ("Hernando, Cordoba").
        - Capital de una provincia solo con una expresión inequívoca: "Córdoba Capital", "Ciudad de Córdoba", "Capital,
          Córdoba" -> Córdoba Capital; "CABA", "Capital Federal", "Ciudad Autónoma de Buenos Aires", "Ciudad de Buenos Aires",
          "Buenos Aires City" -> CABA. Solo cuando es la ubicación del candidato (línea con etiqueta, o dato de contacto en
          el bloque de contacto: línea sola o junto a teléfono/email/LinkedIn), nunca dentro de nombres, estudios o
          experiencia. El nombre de la provincia solo ("Córdoba, Argentina", "Buenos Aires, Argentina", "BsAs") no es la
          capital: se conserva la provincia sin ciudad. Una localidad concreta ("Lomas de Zamora", "Tigre") se respeta y
          nunca se reemplaza por la capital. No se infiere residencia de universidades, empleadores ni característica telefónica.
        """
        import re
        from types import SimpleNamespace

        if db is None or not (texto or "").strip():
            return None
        provincias = db.query(Provincia).all()
        ciudades = db.query(Ciudad).all()
        if not provincias or not ciudades:
            return None
        provincia_por_id = {p.provincia_id: p for p in provincias}
        clave_provincia = {p.provincia_id: _clave_ubicacion(p.nombre) for p in provincias}
        paises = "|".join(CandidatoService.PAISES_UBICACION)

        def palabra(patron: str, sin_de: bool = False):
            previo = r"(?<!\bde )" if sin_de else ""
            return re.compile(previo + r"(?<![a-z0-9])(?:" + patron + r")(?![a-z0-9])")

        fuente_provincia = {
            pid: "|".join([re.escape(clave)] + list(CandidatoService.ABREVIATURAS_PROVINCIA.get(clave, ())))
            for pid, clave in clave_provincia.items()
            if clave
        }
        patron_provincia = {pid: palabra(fuente) for pid, fuente in fuente_provincia.items()}
        # Separadores admitidos entre una ciudad y su provincia o país ("La Plata, Buenos Aires", "Pilar - Argentina")
        hueco_provincia = r"(?:[\s,;:/|()\-.–—]|provincia de |pcia\.? de |prov\.? de )*"
        # Una ciudad dentro del nombre de una institución ("Universidad de Mar del Plata") no es una residencia
        dentro_de_institucion = re.compile(
            r"(?:" + CandidatoService.INSTITUCIONES_UBICACION + r")(?:\s+[a-z]+){0,4}\s+(?:de|del|en)\s+$"
        )

        # Líneas que no describen la ubicación del candidato: títulos de sección y datos de experiencia con fechas
        seccion = re.compile(
            r"^(?:educacion|experiencia(?: laboral| profesional)?|estudios|formacion(?: academica)?|"
            r"trayectoria(?: laboral)?|cursos|idiomas|habilidades|skills)\b"
        )
        rango_anios = re.compile(r"(?:19|20)\d{2}\s*[-/–—]\s*(?:(?:19|20)\d{2}|actual|presente|actualidad|present)")
        contacto = re.compile(r"@|linkedin|\+\s*\d|(?<![a-z])(?:tel|cel|whatsapp|movil|telefono|celular)\b")

        # Patrones de cada ciudad del catálogo
        patrones = []
        patrones_alias = []  # variantes de la capital de la provincia; se buscan línea por línea
        capitales = []  # (expresión de ubicación sin provincia explícita, ciudad capital)
        for ciudad in ciudades:
            provincia = provincia_por_id.get(ciudad.provincia_id)
            nombre = _clave_ubicacion(ciudad.nombre)
            if not provincia or not nombre:
                continue
            patrones.append((palabra(re.escape(nombre)), ciudad))
            if nombre.endswith(" capital"):
                base = nombre[: -len(" capital")].strip()
                if base and base == clave_provincia.get(provincia.provincia_id):
                    b = re.escape(base)
                    sufijo = re.escape(nombre[len(base) :].strip())
                    separador = r"[\s,;:/|()\-]+"
                    # Variantes de la capital de la provincia: "Ciudad de X", "X, X" y "Capital, X" (la provincia las confirma)
                    patrones_alias.append(
                        (
                            palabra(
                                r"ciudad de " + b + r"|" + b + separador + b + r"|" + sufijo + separador + b,
                                sin_de=True,
                            ),
                            ciudad,
                        )
                    )

        # Localidades de un partido del catálogo: se reconocen como ese partido y conservan su nombre para el texto de ubicación
        ciudad_por_clave = {(c.provincia_id, _clave_ubicacion(c.nombre)): c for c in ciudades}
        for clave_prov, localidades in CandidatoService.LOCALIDADES_PARTIDO.items():
            provincia_loc = next((p for p in provincias if clave_provincia[p.provincia_id] == clave_prov), None)
            for nombre_localidad, clave_partido in localidades.items():
                partido = provincia_loc and ciudad_por_clave.get((provincia_loc.provincia_id, clave_partido))
                if partido:
                    patrones.append(
                        (
                            palabra(re.escape(_clave_ubicacion(nombre_localidad))),
                            SimpleNamespace(
                                ciudad_id=partido.ciudad_id,
                                provincia_id=partido.provincia_id,
                                nombre=partido.nombre,
                                localidad=nombre_localidad,
                            ),
                        )
                    )

        # Expresiones de ubicación (sin provincia explícita) que corresponden a la capital de una provincia del catálogo
        separador_capital = r"[\s,;:/\-]+"
        for clave_prov, (clave_ciudad, provincia_sola) in CandidatoService.CAPITALES_PROVINCIA.items():
            provincia_cap = next((p for p in provincias if clave_provincia[p.provincia_id] == clave_prov), None)
            ciudad_cap = next(
                (
                    c
                    for c in ciudades
                    if provincia_cap
                    and c.provincia_id == provincia_cap.provincia_id
                    and _clave_ubicacion(c.nombre) == clave_ciudad
                ),
                None,
            )
            if not ciudad_cap:
                continue
            prov_alt = "|".join(
                [re.escape(clave_prov)] + list(CandidatoService.ABREVIATURAS_PROVINCIA.get(clave_prov, ()))
            )
            formas = [re.escape(clave_ciudad), r"(?:" + prov_alt + r")" + separador_capital + r"capital"]
            if provincia_sola:
                formas.append(r"(?:" + prov_alt + r")")
            if clave_prov in CandidatoService.PROVINCIAS_SIN_CAPITAL_IMPLICITA:
                prefijo = r"(?:ciudad de )?"
            else:
                prefijo = r"(?:(?:ciudad|provincia) de )?"
            sufijo_pais = r"(?:" + separador_capital + r"(?:" + prov_alt + r"|" + paises + r"))*"
            capitales.append(
                (re.compile(r"^" + prefijo + r"(?:" + "|".join(formas) + r")" + sufijo_pais + r"$"), ciudad_cap)
            )
            alias = CandidatoService.ALIAS_CAPITAL_INEQUIVOCOS.get(clave_prov, ())
            if alias:
                # Con un barrio o localidad delante ("Almagro - CABA"), salvo que sea una institución
                capitales.append(
                    (
                        re.compile(
                            r"^(?!.*\b(?:" + CandidatoService.INSTITUCIONES_UBICACION + r")\b)"
                            r"(?:[a-z0-9 .]{2,30}?"
                            + separador_capital
                            + r")?(?:"
                            + "|".join(alias)
                            + r")"
                            + sufijo_pais
                            + r"$"
                        ),
                        ciudad_cap,
                    )
                )

        def buscar(fragmento: str, exigir_provincia: bool):
            if exigir_provincia:
                # Bloque de contacto: se descartan las líneas de experiencia con fechas y todo lo posterior a un título de sección
                utiles = []
                for linea in fragmento.splitlines():
                    clave_l = _clave_ubicacion(linea)
                    if seccion.match(clave_l):
                        break
                    if rango_anios.search(clave_l):
                        continue
                    utiles.append(linea)
                fragmento = "\n".join(utiles)
            region = _clave_ubicacion(fragmento)
            hallazgos = []
            if not region:
                return hallazgos
            for regex, ciudad in patrones:
                for m in regex.finditer(region):
                    ini, fin = m.span()
                    ventana = region[max(0, ini - 40) : fin + 40]
                    # Otra provincia mencionada al lado: ubicación ambigua o de otra zona
                    if any(pid != ciudad.provincia_id and rx.search(ventana) for pid, rx in patron_provincia.items()):
                        continue
                    # La ciudad es parte de un topónimo más largo de otra zona ("San Miguel de Tucumán"): no es la del catálogo
                    continuacion = re.match(r"\s+(?:de|del)\s+(?:la\s+|los\s+|las\s+)?(?=[a-z])", region[fin:])
                    if continuacion:
                        resto = region[fin + continuacion.end() :]
                        if not (
                            any(rx.match(resto) for rx in patron_provincia.values())
                            or re.match(r"(?:" + paises + r"|provincia|pcia|prov)(?![a-z0-9])", resto)
                        ):
                            continue
                    if exigir_provincia:
                        # La provincia debe estar en la propia expresión o pegada a la ciudad (sin otras palabras en medio),
                        # o bien la ciudad debe ir seguida del país ("Pilar - Argentina")
                        fuente = fuente_provincia.get(ciudad.provincia_id)
                        confirmada = bool(fuente) and bool(
                            patron_provincia[ciudad.provincia_id].search(region[ini:fin])
                            or re.search(r"(?<![a-z0-9])(?:" + fuente + r")" + hueco_provincia + r"$", region[:ini])
                            or re.match(hueco_provincia + r"(?:" + fuente + r")(?![a-z0-9])", region[fin:])
                        )
                        if not confirmada:
                            confirmada = bool(
                                re.match(hueco_provincia + r"(?:" + paises + r")(?![a-z0-9])", region[fin:])
                                and not dentro_de_institucion.search(region[max(0, ini - 60) : ini])
                            )
                        if not confirmada:
                            continue
                    hallazgos.append((ini, fin, ciudad))
            # Descartar coincidencias contenidas en otra más larga (ej. "San Martín" dentro de "San Martín de los Andes")
            hallazgos = [
                h
                for h in hallazgos
                if not any(
                    o is not h and o[0] <= h[0] and h[1] <= o[1] and (o[1] - o[0]) > (h[1] - h[0]) for o in hallazgos
                )
            ]
            # Variantes de la capital ("Córdoba, Córdoba", "Capital, Córdoba"...): dentro de una misma línea, sin pasar de
            # un título de sección y sin tomar líneas de experiencia con fechas
            for nro, linea in enumerate(fragmento.splitlines()):
                clave_linea = _clave_ubicacion(linea)
                if not clave_linea:
                    continue
                if exigir_provincia and seccion.match(clave_linea):
                    break
                if rango_anios.search(clave_linea):
                    continue
                for regex, ciudad in patrones_alias:
                    for m in regex.finditer(clave_linea):
                        ini, fin = m.span()
                        ventana = clave_linea[max(0, ini - 40) : fin + 40]
                        if any(
                            pid != ciudad.provincia_id and rx.search(ventana) for pid, rx in patron_provincia.items()
                        ):
                            continue
                        hallazgos.append((nro * 100000 + ini, nro * 100000 + fin, ciudad))
            return hallazgos

        def resolver(hallazgos, una_sola: bool):
            if not hallazgos:
                return None
            distintas = {h[2].ciudad_id for h in hallazgos}
            if una_sola and len(distintas) > 1:
                return None
            primera = min(h[0] for h in hallazgos)
            candidatas = {h[2].ciudad_id for h in hallazgos if h[0] == primera}
            if len(candidatas) > 1:
                return None
            return next(h[2] for h in hallazgos if h[0] == primera)

        def capital_en_segmento(segmento: str):
            clave = _clave_ubicacion(segmento).strip(" .,;:-")
            if not clave:
                return None
            for regex, ciudad in capitales:
                if regex.match(clave):
                    return ciudad
            return None

        lineas = (texto or "").replace("\r", "").splitlines()
        claves_lineas = [_clave_ubicacion(lin) for lin in lineas]
        indices = [i for i, c in enumerate(claves_lineas) if c]  # posiciones de las líneas con contenido

        # 1. Líneas con etiqueta explícita de ubicación ("Ubicación: ...", "Location: ..."), al inicio o dentro de una línea
        #    de contacto; el valor puede estar en la misma línea o en la siguiente
        etiquetas = "|".join(re.escape(e) for e in CandidatoService.ETIQUETAS_UBICACION_CV)
        etiqueta_inicio = re.compile(r"^(?:" + etiquetas + r")\b")
        etiqueta_medio = re.compile(r"(?:^|[\s|,;])(?:" + etiquetas + r")\s*:\s*(.*)$")
        ciudad_detectada = None
        valores_etiqueta: List[
            Tuple[str, str]
        ] = []  # (valor del rótulo, línea siguiente) para el respaldo por provincia
        for pos, i in enumerate(indices):
            clave_linea = claves_lineas[i]
            m_inicio = etiqueta_inicio.match(clave_linea)
            if m_inicio:
                valor = clave_linea[m_inicio.end() :].lstrip(" :.-")
            else:
                m_medio = etiqueta_medio.search(clave_linea)
                if not m_medio:
                    continue
                valor = m_medio.group(1)
            # El valor llega hasta el siguiente rótulo de la línea ("... Córdoba, Argentina. LinkedIn: ...")
            valor = re.split(r"\s[a-z][a-z\-]{1,15}\s*:", " " + valor)[0].strip()
            if not valor and pos + 1 < len(indices):
                valor = claves_lineas[indices[pos + 1]]
            if not valor:
                continue
            valores_etiqueta.append((valor, claves_lineas[indices[pos + 1]] if pos + 1 < len(indices) else ""))
            ciudad_detectada = resolver(buscar(valor, exigir_provincia=False), una_sola=False)
            if not ciudad_detectada:
                for segmento in CandidatoService._segmentos_ubicacion(valor):
                    ciudad_detectada = capital_en_segmento(segmento)
                    if ciudad_detectada:
                        break
            if ciudad_detectada:
                break

        # 2. Bloques de contacto: ciudad confirmada por su provincia o país, o capital como dato de contacto del candidato
        def ciudad_en_bloque(bloque: str):
            ciudad = resolver(buscar(bloque, exigir_provincia=True), una_sola=True)
            if ciudad:
                return ciudad
            encontradas = {}
            for linea in bloque.splitlines():
                clave_linea = _clave_ubicacion(linea)
                if not clave_linea:
                    continue
                if seccion.match(clave_linea):
                    break
                if rango_anios.search(clave_linea):
                    continue
                segmentos = [
                    s
                    for s in CandidatoService._segmentos_ubicacion(linea)
                    if s not in CandidatoService.PAISES_UBICACION
                ]
                for seg in segmentos:
                    ciudad_seg = capital_en_segmento(seg)
                    # Dato de ubicación del candidato: línea que es solo la ubicación, o junto a datos de contacto
                    if ciudad_seg and (len(segmentos) == 1 or contacto.search(clave_linea)):
                        encontradas[ciudad_seg.ciudad_id] = ciudad_seg
            return next(iter(encontradas.values())) if len(encontradas) == 1 else None

        if not ciudad_detectada:
            bloques = [(texto or "")[: CandidatoService.ZONA_ENCABEZADO_CV]]
            # Además del inicio del texto: las líneas que rodean al email y al nombre del candidato
            anclas = []
            email_cv = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", texto or "")
            if email_cv:
                correo = email_cv.group(0).lower()
                anclas.extend(pos for pos, i in enumerate(indices) if correo in lineas[i].lower())
                anclas = anclas[:1]
            palabras_nombre = (
                [p for p in _clave_ubicacion(nombre_completo).split() if len(p) >= 3] if nombre_completo else []
            )
            if len(palabras_nombre) >= 2:
                for pos, i in enumerate(indices):
                    if all(p in set(re.findall(r"[a-z]+", claves_lineas[i])) for p in palabras_nombre):
                        anclas.append(pos)
                        break
            # Hacia arriba y hacia abajo de cada ancla, hasta N líneas y sin cruzar un título de sección
            # ("Experiencia laboral", "Estudios"): lo que está más allá ya no son datos de contacto
            cerca = set()
            for pos in anclas:
                cerca.add(pos)
                for paso in (-1, 1):
                    q, recorridas = pos + paso, 0
                    while 0 <= q < len(indices) and recorridas < CandidatoService.LINEAS_CONTEXTO_CONTACTO:
                        if seccion.match(claves_lineas[indices[q]]):
                            break
                        cerca.add(q)
                        q += paso
                        recorridas += 1
            grupo = []
            for pos in sorted(cerca) + [None]:
                if grupo and (pos is None or pos != grupo[-1] + 1):
                    bloques.append("\n".join(lineas[indices[p]] for p in grupo))
                    grupo = []
                if pos is not None:
                    grupo.append(pos)
            for bloque in bloques:
                ciudad_detectada = ciudad_en_bloque(bloque)
                if ciudad_detectada:
                    break

        if not ciudad_detectada:
            # 3. Respaldo: la ubicación nombra una provincia del catálogo pero la localidad no está en él
            #    ("Hernando, Córdoba, Argentina", "Provincia de Buenos Aires"): se conserva la provincia, sin ciudad.
            provincia_sola = CandidatoService._provincia_sin_ciudad_catalogo(
                provincias, fuente_provincia, valores_etiqueta, bloques, seccion, rango_anios, contacto
            )
            if provincia_sola is None:
                return None
            provincia, clave_localidad = provincia_sola
            localidad = CandidatoService._nombre_localidad_cv(texto, clave_localidad) if clave_localidad else ""
            return {
                "provincia_id": provincia.provincia_id,
                "ciudad_id": None,
                "ubicacion": f"{localidad}, {provincia.nombre}" if localidad else provincia.nombre,
            }
        provincia = provincia_por_id[ciudad_detectada.provincia_id]
        # Una localidad de un partido conserva su nombre ("Tristan Suarez, Buenos Aires"); la ciudad guardada es el partido
        localidad = getattr(ciudad_detectada, "localidad", None) or ciudad_detectada.nombre
        return {
            "provincia_id": provincia.provincia_id,
            "ciudad_id": ciudad_detectada.ciudad_id,
            "ubicacion": f"{localidad}, {provincia.nombre}",
        }

    # ------------------------------------------------------------------------------------------------------------
    # Identificación del nombre del candidato
    # ------------------------------------------------------------------------------------------------------------
    # Palabras (sin tildes y en minúsculas) propias de títulos de sección, puestos, idiomas y niveles, tecnologías,
    # ubicaciones, instituciones y frases de perfil. Es solo UNA de las señales de descarte: un texto se acepta como
    # nombre únicamente si, además, tiene forma de nombre y está respaldado por el contexto del documento (email,
    # LinkedIn, nombre del archivo, posición). Por eso este vocabulario no necesita ser exhaustivo.
    PALABRAS_NO_NOMBRE = frozenset(
        """
        perfil profesional profesionales resumen sobre acerca mi objetivo objetivos presentacion introduccion extracto
        summary profile about me objective objectives overview introduction hola hello hi soy i am
        experiencia laboral trayectoria historial antecedentes empleo empleos work employment experience career history
        educacion formacion academica academico estudios estudio titulos titulo capacitacion capacitaciones education
        studies training academic background
        datos personales personal informacion contacto contactar contact details info telefono celular movil mobile phone
        cel tel email correo mail web website portfolio linkedin github domicilio direccion address nacionalidad
        nationality civil
        idiomas idioma lenguajes languages language certificaciones certificados certificado certification
        certifications certificates cursos curso courses proyectos proyecto projects project referencias referencia
        references herramientas tecnologias tecnologia tecnologicas tecnicas tecnicos tools technologies technology
        technical habilidades habilidad competencias competencia aptitudes aptitud skills skill soft hard sociales
        blandas principales conocimientos conocimiento fortalezas fortaleza intereses interes hobbies logros
        responsabilidades funciones tareas achievements responsibilities strengths knowledge interests otros otras
        adicional adicionales additional other varios disponibilidad disponible availability
        curriculum curriculo vitae cv resume doc docx pdf esp eng spa documento archivo document file
        espanol spanish castellano ingles english portugues portuguese frances french aleman german italiano italian chino
        mandarin japones japanese nativo nativa native bilingue bilingual fluido fluida fluent avanzado avanzada advanced
        intermedio intermedia intermediate basico basica basic medio alto bajo lectura escritura oral conversacion
        hablado escrito nivel level proficiency limitado limited working
        desarrollador desarrolladora developer dev programador programadora analista analyst ingeniero ingeniera
        engineer arquitecto arquitecta architect tester testing qa quality assurance soporte support tecnico tecnica
        technician administrador administradora administrator consultor consultora consultant gerente manager jefe
        lider leader lead coordinador coordinadora coordinator director directora supervisor especialista specialist
        asistente assistant operario operaria operador operadora estudiante student pasante practicante trainee junior
        senior semi ssr sr jr scrum master product owner project data science scientist cientifico fullstack full stack
        frontend backend front back end web software sistemas systems informatica informatico computacion devops cloud
        infrastructure infraestructura seguridad security redes network business intelligence bi etl dba base bases
        datos database freelance freelancer independiente emprendedor docente profesor profesora tutor disenador
        disenadora designer ux ui marketing ventas comercial administrativo administrativa contable contador recepcion
        atencion cliente clientes customer service help desk mesa ayuda automation automatizacion manual funcional
        functional it ti tic hr rrhh people recursos humanos
        python java javascript typescript sql mysql postgresql oracle mongodb react angular vue node nodejs php laravel
        django fastapi spring docker kubernetes aws azure gcp git gitlab jira postman cypress selenium excel word
        powerpoint office ms microsoft windows linux unix android ios html css bootstrap api apis rest sap abap cobol
        power tableau qlik looker figma agile agil kanban metodologias metodologia
        argentina argentine argentino arg buenos aires caba capital federal ciudad autonoma city provincia pcia gran gba
        universidad university instituto institute escuela school colegio facultad college academy academia coderhouse
        udemy coursera banco bank empresa company sa srl llc inc ltd group grupo solutions consulting consultoria
        technologies servicios services nacional tecnologica regional agencia
        actualidad actual presente present now hasta desde since from year years anos meses months mes con sin para
        por que como donde the and of in at for with an un una el en es my mis your
        enero febrero marzo abril mayo junio julio agosto septiembre setiembre octubre noviembre diciembre january
        february march april june july august september october november december
        decision decisions making taking solving problem problems teamwork leadership communication thinking critical
        liderazgo comunicacion equipo resolucion problemas pensamiento gestion management
        pro labs lab studio studios tech soft devs corp corporation partners hub digital global ventures
        utn uba unc unlp uns unr unt unsa uade itba
    """.split()
    )
    # Títulos y tratamientos que preceden al nombre de una persona ("Ing. Sonia Grimau", "LIC. DÁMARIS COHEN"): no son
    # parte del nombre ni del apellido.
    TITULOS_PERSONA = frozenset(
        "ing lic licenciado licenciada dr dra doctor doctora arq cr cra cdor cdora cpn mg mgtr mag mba sr sra srta prof profe tec tecn mr mrs ms miss phd".split()
    )
    # Partículas que pueden ir dentro de un apellido o nombre compuesto ("de la", "di", "van")
    PARTICULAS_NOMBRE = frozenset(
        {"de", "del", "la", "las", "los", "da", "das", "do", "dos", "di", "du", "le", "van", "von", "der", "y"}
    )

    @staticmethod
    def _clave_nombre(texto: Optional[str]) -> str:
        """Clave de comparación de un nombre: solo letras a-z, sin tildes ni mayúsculas."""
        import re

        sin_tildes = "".join(c for c in unicodedata.normalize("NFKD", texto or "") if not unicodedata.combining(c))
        return re.sub(r"[^a-z]", "", sin_tildes.casefold())

    @staticmethod
    def _tokens_de_nombre(segmento: str, minimo: int = 2, maximo: int = 5) -> Optional[List[str]]:
        """
        Devuelve las palabras de `segmento` si tiene forma de nombre de persona, o None si no la tiene.
        Forma de nombre: entre `minimo` y `maximo` palabras formadas por letras (admite tildes, apóstrofes, guiones
        internos e iniciales con punto), cada una con inicial mayúscula (salvo partículas como "de" o "di" en el medio),
        sin dígitos ni símbolos, y sin palabras propias de secciones, puestos, idiomas, tecnologías o ubicaciones.
        """
        import re

        limpio = re.sub(r"[​-‏⁠﻿‪-‮]", "", segmento or "")
        limpio = limpio.strip(" \t\"'*_.,;:()[]“”‘’")
        palabras = limpio.split()
        while len(palabras) > 1 and CandidatoService._clave_nombre(palabras[0]) in CandidatoService.TITULOS_PERSONA:
            palabras = palabras[1:]
        if not minimo <= len(palabras) <= maximo:
            return None
        patron = re.compile(r"^[^\W\d_]+(?:['’\-][^\W\d_]+)*\.?$")
        significativas = 0
        for i, palabra in enumerate(palabras):
            if not patron.match(palabra):
                return None
            clave = CandidatoService._clave_nombre(palabra)
            if not clave or clave in CandidatoService.TITULOS_PERSONA:
                return None
            if len(clave) == 1 and palabra[0].isupper() and 0 < i < len(palabras) - 1:
                continue  # Inicial intermedia ("Carlos I Madrigal", "Juan P. Pérez"): no cuenta como nombre ni apellido
            if clave in CandidatoService.PARTICULAS_NOMBRE and palabra.islower():
                if i == 0 or i == len(palabras) - 1:
                    return None
                continue
            if clave in CandidatoService.PALABRAS_NO_NOMBRE and not (
                i == 0 and clave in CandidatoService.NOMBRES_DE_PILA
            ):
                # Salvo un nombre de pila que también es palabra de vocabulario ("German" idioma / nombre) al inicio
                return None
            if not palabra[0].isupper():
                return None
            if len(clave) >= 2:
                significativas += 1
        if significativas < minimo:
            return None
        return palabras

    # Nombres de pila frecuentes (sin tildes). Solo se usan para detectar un nombre escrito como "Apellido Nombre"
    # ("Moreira Rodrigo"); un nombre que no figura acá nunca se descarta por eso.
    NOMBRES_DE_PILA = frozenset(
        """
        adrian adriana agostina agustin agustina alan alberto alejandra alejandro alexis alfredo alicia alma ana andrea
        andres angel angela angeles antonella antonio ariel armando augusto aurora axel barbara beatriz belen benjamin
        bianca brenda bruno camila candela carina carla carlos carmen carolina catalina cecilia celeste cesar clara
        claudia claudio cristian cristina dalma damian daniel daniela dante dario david debora diana diego eduardo elena
        elias eliana emanuel emilia emiliano emilio enrique enzo eric erica ernesto esteban eugenia evelyn ezequiel
        facundo fabian fabiana federico felipe fernanda fernando flavia florencia franco francisco gabriel gabriela
        gaston gerardo german gisel gisela gonzalo graciela guadalupe guido guillermo gustavo hector hernan horacio hugo
        ignacio ines ivan ivana jazmin javier jesica jessica joaquin joel jonathan jorge jose josefina juan julia julian
        juliana julieta karen karina laura leandro leonardo leonel lorena lorenzo lourdes lucas lucia luciana luciano
        lucio luis luisa luz macarena magali malena manuel marcela marcelo marcos maria mariana mariano marina mario
        marisol martin martina matias mauricio mauro maximiliano mayra melina melisa mercedes micaela miguel milagros
        mirko misael monica nadia nahuel natalia nataniel nazarena nazareno nancy nicolas noelia norberto oscar pablo
        paola patricia paula pedro pilar rafael ramiro ramon raul ricardo roberto rocio rodolfo rodrigo romina rosa
        rosario ruben ruth sabrina salvador samuel santiago santino sara sebastian sergio silvia silvina sofia soledad
        sonia susana tamara tatiana teresa tobias tomas valentin valentina valeria vanesa veronica vicente victor
        victoria virginia walter ximena yamila yanina yesica
        julio abril
    """.split()
    )

    @staticmethod
    def _ordenar_nombre_apellido(palabras: List[str], contexto: Optional[Dict[str, Any]] = None) -> List[str]:
        """
        Corrige un nombre escrito como "Apellido(s) Nombre(s)" ("Moreira Rodrigo", "Navarro Agustin"): solo rota cuando
        la primera palabra no es un nombre de pila conocido y todas las palabras finales sí lo son. Ante cualquier duda
        (nombres poco comunes, "Nexxys Carolina Herrera") se respeta el orden en que figura en el CV. No se usa el orden
        de un email sin separadores: muchos empiezan por el apellido ("acostanancy", "martinezmauro"). Con `contexto`,
        solo las fuentes con las palabras separadas (email con puntos o guiones, LinkedIn por defecto) pueden respaldar el
        orden del encabezado o fijar el orden "nombre-apellido".
        """
        claves = [CandidatoService._clave_nombre(p) for p in palabras]

        # Fuentes con las palabras separadas (email con puntos o guiones, LinkedIn por defecto): si una escribe exactamente
        # estas palabras en este orden, el orden está respaldado y la lista de nombres no lo gira; si el LinkedIn por
        # defecto las escribe en otro orden ("nombre-apellido"), ese orden se respeta
        separadas = (contexto or {}).get("separadas") or {}
        if separadas and all(claves) and len(set(claves)) == len(claves):
            if any(v == claves for v in separadas.values()):
                return palabras
            linkedin = separadas.get("linkedin")
            if linkedin and sorted(linkedin) == sorted(claves):
                por_clave = dict(zip(claves, palabras))
                return [por_clave[c] for c in linkedin]

        def conocido(clave: str) -> bool:
            return clave in CandidatoService.NOMBRES_DE_PILA or len(clave) == 1

        if len(palabras) < 2 or conocido(claves[0]):
            return palabras
        # Una inicial al final ("Jaan Carlos Jorge R") suele ser la inicial de un apellido: no prueba que el bloque final
        # sea de nombres de pila y no se gira
        if len(claves[-1]) < 2:
            return palabras
        for k in range(1, len(palabras)):
            if len(claves[k]) > 1 and all(conocido(c) for c in claves[k:]):
                return palabras[k:] + palabras[:k]
        return palabras

    @staticmethod
    def _contexto_nombre(texto: str, nombre_archivo: str = "", email: str = "") -> Dict[str, Any]:
        """
        Fuentes del propio CV con las que se puede corroborar cómo se escribe el nombre de la persona: el email, el perfil
        de LinkedIn y el nombre del archivo (texto sin separadores) y las palabras del documento (en el orden en que figuran).
        """
        import os
        import re

        compacto = re.sub(r"\s*-\s*", "-", re.sub(r"-\s*\n\s*", "-", (texto or "").replace("\r", "")))
        m_linkedin = re.search(r"linkedin\.com/in/([^\s/?#]+)", compacto, re.IGNORECASE)
        base_archivo = os.path.splitext(nombre_archivo or "")[0]
        # Cada parte del archivo ("Resume - Ana Pérez") se considera por separado: unirlas inventaría coincidencias
        segmentos = [sg for sg in re.split(r"\s+-\s+", base_archivo) if sg.strip()]
        unidos = [
            CandidatoService._clave_nombre(valor)
            for valor in [(email or "").split("@")[0], m_linkedin.group(1) if m_linkedin else ""] + segmentos
            if valor
        ]
        palabras = " ".join(c for c in (CandidatoService._clave_nombre(p) for p in (texto or "").split()) if c)
        # Formato explícito "Apellido(s), Nombre(s)" en una parte del archivo: la parte previa a la coma es el apellido
        apellido_explicito: List[str] = []
        for sg in segmentos:
            m_coma = re.match(r"^\s*([^,\d]+?)\s*,\s*([^,\d]+)$", sg)
            if m_coma:
                izquierda = [CandidatoService._clave_nombre(w) for w in m_coma.group(1).split()]
                if (
                    1 <= len(izquierda) <= 3
                    and all(izquierda)
                    and not any(w in CandidatoService.PALABRAS_NO_NOMBRE for w in izquierda)
                ):
                    apellido_explicito = izquierda
                    break

        # Email con separadores ("abel.angel1996") y LinkedIn por defecto ("maria-trinidad-navarro-436004199"): las palabras
        # figuran en el orden en que la persona las escribió. Los slugs sin guiones son personalizados y no prueban nada
        def trozos(valor: str) -> List[str]:
            return [
                c for c in (CandidatoService._clave_nombre(x) for x in re.split(r"[^A-Za-zÀ-ɏ]+", valor)) if len(c) >= 2
            ]

        separadas: Dict[str, List[str]] = {}
        local_email = (email or "").split("@")[0]
        if re.search(r"[._\-]", local_email) and len(trozos(local_email)) >= 2:
            separadas["email"] = trozos(local_email)
        if m_linkedin and "-" in m_linkedin.group(1) and len(trozos(m_linkedin.group(1))) >= 2:
            separadas["linkedin"] = trozos(m_linkedin.group(1))
        return {
            "unidos": [u for u in unidos if u],
            "palabras": f" {palabras} ",
            "apellido_explicito": apellido_explicito,
            "separadas": separadas,
        }

    @staticmethod
    def _dividir_nombre_apellido(
        palabras: List[str], contexto: Optional[Dict[str, Any]] = None
    ) -> Tuple[List[str], List[str]]:
        """
        Separa las palabras de un nombre completo (ya en el orden "Nombre(s) Apellido(s)") en nombres y apellidos.
        Se parte de que la primera palabra es un nombre y de que siempre debe quedar al menos una palabra para el
        apellido. Las palabras siguientes pasan a ser nombres solo con evidencia:
        - corroboración del propio CV: otra fuente (email, LinkedIn, archivo o una mención en el texto) escribe la primera
          palabra seguida directamente de otra posterior, sin las intermedias ("Brian Wolkomirski" frente a "Brian Ezequiel
          Wolkomirski"): las palabras omitidas son segundos nombres y no parte del apellido;
        - una fuente que escribe el apellido antes del nombre ("villarrealnexxo", "toufardiegom") sin las palabras
          intermedias, siempre que no figuren pegadas al apellido en esa misma fuente ("garcialopezana" no prueba que
          "García" sea un nombre);
        - dos nombres de pila conocidos seguidos, cuando no hay otra evidencia.
        Si hay varias lecturas se toma la que menos palabras omite. Una fuente que solo contiene las primeras palabras
        ("melanyjofre") no prueba nada: suele ser el nombre de uso (nombre y primer apellido) y no el bloque de nombres.
        Una partícula ("de", "di", "del", "lo") abre el apellido compuesto y nunca se toma como nombre. Sin evidencia el
        resto queda como apellido (el comportamiento histórico) antes que inventar un nombre compuesto.
        """
        if len(palabras) < 3:
            return palabras[:1], palabras[1:]
        claves = [CandidatoService._clave_nombre(p) for p in palabras]

        def es_particula(i: int) -> bool:
            return claves[i] in CandidatoService.PARTICULAS_NOMBRE

        # Apellido explícito en el nombre del archivo ("Burgener, Maricel del Milagro"): lo que antecede a la coma es el
        # apellido y el resto, aunque tenga partículas, son los nombres
        explicito = (contexto or {}).get("apellido_explicito") or []
        if explicito and len(explicito) < len(palabras) and claves[-len(explicito) :] == explicito:
            return palabras[: -len(explicito)], palabras[-len(explicito) :]

        # Corroboración: la primera palabra y la palabra j figuran juntas, sin las intermedias, en otra fuente del CV.
        # Si hay más de una lectura posible se toma la que menos palabras mueve a los nombres.
        omitidas = 1
        if contexto and claves[0]:
            for j in range(2, len(palabras)):
                if not claves[j] or claves[j] in claves[1:j]:
                    continue
                # Lo que sigue a la primera palabra: solo el resto del apellido (cubre apellidos que empiezan con partícula,
                # "Lo Cascio") o su primera palabra
                resto = claves[j:]
                siguientes = [resto]
                if not es_particula(j) and len(claves[j]) >= 3:
                    siguientes.append(claves[j : j + 1])
                menciones = [" " + claves[0] + " " + " ".join(sig) + " " for sig in siguientes]
                if any(
                    (claves[0] + "".join(sig)) in u for sig in siguientes for u in contexto.get("unidos", [])
                ) or any(m in contexto.get("palabras", "") for m in menciones):
                    omitidas = j
                    break
                # Iniciales de los nombres que anteceden al apellido, pegadas a él ("jcperez" para Juan Carlos Pérez;
                # "mauroemartinez" para Mauro Ezequiel Martínez): las palabras intermedias son nombres y no apellido
                if len(claves[j]) >= 4:
                    intermedias = "".join(c[0] for c in claves[1:j])
                    patrones = (claves[0][0] + intermedias + claves[j], claves[0] + intermedias + claves[j])
                    if any(pt in u for pt in patrones for u in contexto.get("unidos", [])):
                        omitidas = j
                        break
                # Fuente con el apellido antes del nombre ("villarrealnexxo", "toufardiegom"): las palabras intermedias no son
                # parte del apellido, salvo que esa misma fuente las pegue a él
                cola = "".join(claves[j:])
                if len(cola) >= 4:
                    iniciales = "".join(c[0] for c in claves[1:j])
                    previo = claves[j - 1] + cola
                    if any(
                        (cola + claves[0] in u or cola + claves[0] + iniciales in u) and previo not in u
                        for u in contexto.get("unidos", [])
                    ):
                        omitidas = j
                        break
        if omitidas > 1:
            return palabras[:omitidas], palabras[omitidas:]
        # Dos nombres de pila seguidos: con una primera palabra desconocida podría ser "Apellido Nombre ..." y no se mueve
        if (
            claves[0] in CandidatoService.NOMBRES_DE_PILA
            and claves[1] in CandidatoService.NOMBRES_DE_PILA
            and not es_particula(1)
        ):
            return palabras[:2], palabras[2:]
        return palabras[:1], palabras[1:]

    @staticmethod
    def _candidatos_nombre(lineas: List[str], limite: int = 80) -> List[Dict[str, Any]]:
        """
        Posibles nombres dentro de las primeras `limite` líneas del CV (ya sin líneas vacías). Cada línea se divide en
        segmentos (los símbolos, viñetas y separadores no cuentan como parte de un nombre) y se consideran: el segmento
        completo, el formato "Apellido, Nombre", el comienzo de un segmento más largo y los nombres partidos en varias
        líneas de una sola palabra ("TAMARA" / "SAMANA"), habituales cuando el PDF tiene el nombre en un encabezado.
        """
        import re

        def limpiar(linea: str) -> str:
            salida = []
            for c in linea:
                categoria = unicodedata.category(c)
                if c == "\t":
                    salida.append(" | ")
                elif categoria in ("Cf", "Cc"):
                    continue
                elif categoria in ("So", "Sm") or c in "|•·":
                    salida.append(" | ")
                else:
                    salida.append(c)
            return re.sub(r"\s[–—]\s", " | ", "".join(salida))

        candidatos: List[Dict[str, Any]] = []
        cortas: List[
            Tuple[int, List[str]]
        ] = []  # (línea, palabras) de las líneas de 1 a 3 palabras con forma de nombre
        for idx, linea in enumerate(lineas[:limite]):
            segmentos = [s.strip() for s in limpiar(linea).split("|") if s.strip()]
            if len(segmentos) == 1:
                corta = CandidatoService._tokens_de_nombre(segmentos[0], 1, 3)
                if corta:
                    cortas.append((idx, corta))
            for segmento in segmentos:
                directa = CandidatoService._tokens_de_nombre(segmento)
                if directa:
                    candidatos.append({"idx": idx, "nombre": directa[:1], "apellido": directa[1:], "forma": "directa"})
                if segmento.count(",") == 1:
                    izquierda, derecha = segmento.split(",")
                    apellidos = CandidatoService._tokens_de_nombre(izquierda, 1, 3)
                    nombres = CandidatoService._tokens_de_nombre(derecha, 1, 3)
                    if apellidos and nombres:
                        candidatos.append({"idx": idx, "nombre": nombres, "apellido": apellidos, "forma": "coma"})
                palabras = segmento.split()
                if not directa:
                    for cantidad in (4, 3, 2):
                        if cantidad < len(palabras):
                            prefijo = CandidatoService._tokens_de_nombre(" ".join(palabras[:cantidad]))
                            if prefijo:
                                candidatos.append(
                                    {"idx": idx, "nombre": prefijo[:1], "apellido": prefijo[1:], "forma": "prefijo"}
                                )
        # Nombres partidos en líneas consecutivas cortas ("Wenceslao Aguirre" / "Cernadas", "SOFÍA BELÉN" / "GÓMEZ BELIS")
        for pos in range(len(cortas)):
            for cantidad in (2, 3):
                grupo = cortas[pos : pos + cantidad]
                if len(grupo) == cantidad and all(grupo[k + 1][0] == grupo[k][0] + 1 for k in range(cantidad - 1)):
                    palabras = [p for g in grupo for p in g[1]]
                    if len(palabras) <= 5:
                        candidatos.append(
                            {"idx": grupo[0][0], "nombre": palabras[:1], "apellido": palabras[1:], "forma": "partido"}
                        )
        return candidatos

    @staticmethod
    def _detectar_nombre_cv(
        texto: str, nombre_archivo: str = "", email: str = "", texto_completo: str = ""
    ) -> Optional[Tuple[str, str]]:
        """
        Identifica el nombre y apellido del candidato a partir del texto del CV. Devuelve (nombre, apellido) o None si no
        hay información suficiente para identificarlo con confianza (en ese caso se aplica el comportamiento alternativo).

        No se toma la primera línea "con aspecto de nombre": en los PDF con columnas laterales o encabezados con imagen el
        texto llega desordenado y antes del nombre aparecen secciones ("Aptitudes principales", "Sobre mí"), idiomas
        ("Español - Nativo") o puestos. Por eso un candidato debe:
        - tener forma de nombre de persona y no contener vocabulario de secciones, puestos, idiomas, etc.
        - estar respaldado por el contexto: sus palabras figuran en el email, en el perfil de LinkedIn o en el nombre del
          archivo, o bien encabezan el documento (primeras líneas) sin ninguna señal en contra.
        """
        import os
        import re

        lineas = [lin.strip() for lin in (texto or "").replace("\r", "").splitlines() if lin.strip()]
        if not lineas:
            return None
        # Cuando se analiza solo el encabezado visual, el LinkedIn y las menciones del resto del CV siguen siendo evidencia
        texto_contexto = texto_completo or texto

        def formatear(nombres: List[str], apellidos: List[str], explicito: bool = False) -> Tuple[str, str]:
            palabras = nombres + apellidos
            contexto = CandidatoService._contexto_nombre(texto_contexto, nombre_archivo, email)
            ordenadas = CandidatoService._ordenar_nombre_apellido(palabras, None if explicito else contexto)
            if ordenadas != palabras:
                nombres, apellidos = ordenadas[:1], ordenadas[1:]
            if not explicito:
                # Nombre completo sin separación explícita: se reparte entre nombres y apellidos según la evidencia
                nombres, apellidos = CandidatoService._dividir_nombre_apellido(nombres + apellidos, contexto)
            # Las iniciales que siguen al nombre ("Carlos I Madrigal") son del nombre, no del apellido
            while len(apellidos) > 1 and len(CandidatoService._clave_nombre(apellidos[0])) == 1:
                nombres, apellidos = nombres + apellidos[:1], apellidos[1:]
            nombre = " ".join(nombres).strip(" .,;:")
            apellido = " ".join(apellidos).strip(" .,;:")
            if len(nombres) > 1 or not apellido:
                return nombre.title(), apellido.title()
            return nombre.capitalize(), apellido.title()

        # 1. Fuentes que corroboran un nombre: email, LinkedIn y nombre del archivo (peso, texto sin separadores, partes)
        fuentes: List[Tuple[float, str, List[str]]] = []
        local_email = (email or "").split("@")[0]
        compacto = re.sub(r"-\s*\n\s*", "-", (texto_contexto or "").replace("\r", ""))
        compacto = re.sub(r"\s*-\s*", "-", compacto)
        m_linkedin = re.search(r"linkedin\.com/in/([^\s/?#]+)", compacto, re.IGNORECASE)
        base_archivo = os.path.splitext(nombre_archivo or "")[0]
        for peso, valor in (
            (3.0, local_email),
            (2.0, m_linkedin.group(1) if m_linkedin else ""),
            (1.5, base_archivo),
        ):
            if not valor:
                continue
            unido = CandidatoService._clave_nombre(valor)
            partes = [CandidatoService._clave_nombre(p) for p in re.split(r"[^A-Za-zÀ-ɏ]+", valor) if p]
            fuentes.append((peso, unido, partes))

        # 2a. Campos separados ("Nombre: Facundo" / "Apellido: Rosende"): se combinan solo si ambos valores tienen forma
        #     de nombre; con uno solo (o con valores que no son un nombre) se sigue con la etiqueta explícita.
        campo_nombre = re.compile(r"^(?:nombres?|first name|given name)\s*[:\-]\s*(.+)$", re.IGNORECASE)
        campo_apellido = re.compile(r"^(?:apellidos?|last name|surname|family name)\s*[:\-]\s*(.+)$", re.IGNORECASE)
        valor_nombre: Optional[List[str]] = None
        valor_apellido: Optional[List[str]] = None
        for linea in lineas[:60]:
            limpia = re.sub(r"^[\W_]+", "", linea)
            m_nom, m_ape = campo_nombre.match(limpia), campo_apellido.match(limpia)
            if m_nom and valor_nombre is None:
                valor_nombre = CandidatoService._tokens_de_nombre(m_nom.group(1), 1, 3)
            elif m_ape and valor_apellido is None:
                valor_apellido = CandidatoService._tokens_de_nombre(m_ape.group(1), 1, 3)
        if valor_nombre and valor_apellido:
            return formatear(valor_nombre, valor_apellido, explicito=True)

        # 2a'. "Apellido y nombres: Pérez, Juan Carlos": el valor ya separa el apellido de los nombres con una coma
        etiqueta_apellido_nombres = re.compile(r"^apellidos?\s*(?:y|,|/)\s*nombres?\s*[:\-]\s*(.+)$", re.IGNORECASE)
        for linea in lineas[:40]:
            m_an = etiqueta_apellido_nombres.match(re.sub(r"^[\W_]+", "", linea))
            if m_an and m_an.group(1).count(",") == 1:
                izquierda, derecha = m_an.group(1).split(",")
                apellidos_et = CandidatoService._tokens_de_nombre(izquierda, 1, 3)
                nombres_et = CandidatoService._tokens_de_nombre(derecha, 1, 3)
                if apellidos_et and nombres_et:
                    return formatear(nombres_et, apellidos_et, explicito=True)

        # 2b. Etiqueta explícita ("Nombre completo: Juan Pérez", también precedida de viñetas, o "Nombre" seguido del
        #     valor en la línea siguiente). Si el valor no es un nombre plausible se sigue buscando en el resto del CV.
        etiqueta = re.compile(
            r"^(?:name|nombre(?: completo)?|full name|candidato|candidate)\b\s*[:\-]?\s*(.*)$", re.IGNORECASE
        )
        for idx, linea in enumerate(lineas[:40]):
            m = etiqueta.match(re.sub(r"^[\W_]+", "", linea))
            if not m:
                continue
            valor = m.group(1).strip() or (lineas[idx + 1] if idx + 1 < len(lineas) else "")
            tokens = CandidatoService._tokens_de_nombre(valor)
            if tokens:
                return formatear(tokens[:1], tokens[1:])

        def claves_de(candidato: Dict[str, Any]) -> List[str]:
            palabras = candidato["nombre"] + candidato["apellido"]
            claves = [CandidatoService._clave_nombre(p) for p in palabras]
            return [c for c in claves if len(c) >= 3 and c not in CandidatoService.PARTICULAS_NOMBRE]

        def evidencia(claves: List[str]) -> float:
            total = 0.0
            for peso, unido, partes in fuentes:
                for clave in set(claves):
                    if len(clave) >= 4 and clave in unido:
                        total += peso
                    elif len(clave) == 3 and clave in partes:
                        total += peso
            return total

        def orden_coherente(claves: List[str]) -> bool:
            # El email o el perfil de LinkedIn contienen todas las palabras en el mismo orden que el candidato
            if len(claves) < 2 or len(set(claves)) != len(claves):
                return False
            for peso, unido, _ in fuentes:
                if peso >= 2.0:
                    posiciones = [unido.find(c) for c in claves]
                    if all(p >= 0 for p in posiciones) and posiciones == sorted(posiciones):
                        return True
            return False

        # Otro nombre (el del archivo) corroborado por el email: un encabezado sin ningún respaldo no puede desplazarlo
        # (típico de CVs que empiezan con el nombre de una empresa o una institución).
        alterno = CandidatoService._nombre_desde_archivo(nombre_archivo, email) if nombre_archivo else None
        email_alterno = CandidatoService._clave_nombre(local_email)
        alterno_corroborado = (
            bool(alterno)
            and sum(
                1
                for p in (alterno[0] + " " + alterno[1]).split()
                if len(CandidatoService._clave_nombre(p)) >= 4 and CandidatoService._clave_nombre(p) in email_alterno
            )
            >= 2
        )

        mejor = None
        for candidato in CandidatoService._candidatos_nombre(lineas):
            claves = claves_de(candidato)
            if not claves:
                continue
            ev = evidencia(claves)
            idx = candidato["idx"]
            cantidad = len(claves)
            if candidato["forma"] in ("prefijo", "partido"):
                aceptable = ev >= 3
            else:
                # Sin respaldo del contexto solo se acepta una línea completa que encabeza el documento
                aceptable = (
                    ev >= 3
                    or (ev > 0 and idx < 15)
                    or (
                        ev == 0
                        and idx < 3
                        and 2 <= cantidad <= 3
                        and candidato["forma"] == "directa"
                        and not alterno_corroborado
                    )
                )
            if not aceptable:
                continue
            puntaje = ev + max(0, 4 - idx) * 0.5 + (0.5 if 2 <= cantidad <= 3 else 0.0)
            # Entre lecturas del mismo nombre ("Testa Octavio" / "Octavio Testa") se prefiere el orden que respaldan el email o LinkedIn
            if orden_coherente(claves):
                puntaje += 3.0
            if mejor is None or (puntaje, -idx) > (mejor[0], -mejor[1]["idx"]):
                mejor = (puntaje, candidato)
        if not mejor:
            # Diseños con nombre y apellido en bloques separados, cada uno solo en su línea ("Gonzalez" al inicio y
            # "Nahuel" varias líneas después): se aceptan solo si uno encabeza el documento y el otro es un nombre de pila
            sueltas = [
                (i, lin)
                for i, lin in enumerate(lineas[:12])
                if re.fullmatch(r"[A-Za-zÀ-ɏ]{3,}", lin)
                and CandidatoService._clave_nombre(lin) not in CandidatoService.PALABRAS_NO_NOMBRE
            ]
            pilas = [
                (i, lin)
                for i, lin in sueltas
                if CandidatoService._clave_nombre(lin) in CandidatoService.NOMBRES_DE_PILA
            ]
            if len(pilas) == 1 and sueltas and sueltas[0][0] <= 1:
                otras = [(i, lin) for i, lin in sueltas if (i, lin) != pilas[0]]
                if otras and otras[0] == sueltas[0]:
                    return pilas[0][1].capitalize(), otras[0][1].capitalize()
            return None

        return formatear(list(mejor[1]["nombre"]), list(mejor[1]["apellido"]), explicito=mejor[1]["forma"] == "coma")

    @staticmethod
    def _elegir_nombre_cv(
        candidatos: List[Optional[Tuple[str, str]]], contexto: Dict[str, Any]
    ) -> Optional[Tuple[str, str]]:
        """
        Elige entre el nombre detectado en el texto y los del encabezado visual (el título de mayor tamaño de la primera
        página). Se conserva el primero (el del texto) salvo que otro lo complete o tenga más respaldo:
        - lo completa: contiene todas sus palabras en el mismo orden y las que agrega van después de la primera palabra
          (segundos nombres o segundo apellido), o bien todas las que agrega figuran en el email, LinkedIn o archivo;
        - tiene más respaldo: no comparte ninguna palabra con el primero y más de sus palabras figuran en esas fuentes.
        Un encabezado con una palabra extra y sin respaldo al comienzo ("Cofundador Vinícius Rebouças") no desplaza al texto.
        """
        candidatos = [c for c in candidatos if c]
        if not candidatos:
            return None

        def claves(c: Tuple[str, str]) -> List[str]:
            return [k for k in (CandidatoService._clave_nombre(x) for x in f"{c[0]} {c[1]}".split()) if k]

        def respaldo(ks: List[str]) -> int:
            return sum(1 for k in set(ks) if len(k) >= 4 and any(k in u for u in contexto.get("unidos", [])))

        def subsecuencia(corta: List[str], larga: List[str]) -> bool:
            it = iter(larga)
            return all(k in it for k in corta)

        mejor = candidatos[0]
        for otro in candidatos[1:]:
            km, ko = claves(mejor), claves(otro)
            if ko == km or not km or not ko:
                continue
            if set(km) < set(ko) and subsecuencia(km, ko):
                extras = [k for k in ko if k not in km]
                despues_de_la_primera = ko[0] == km[0]
                respaldadas = all(len(k) >= 4 and any(k in u for u in contexto.get("unidos", [])) for k in extras)
                # Una sigla o inicial agregada ("Madrigal Cm") no completa un nombre
                if all(len(k) >= 3 for k in extras) and (despues_de_la_primera or respaldadas):
                    mejor = otro
            elif set(km).isdisjoint(ko) and respaldo(ko) > respaldo(km):
                mejor = otro
        return mejor

    @staticmethod
    def _nombre_desde_encabezado_visual(
        encabezado: str, contexto: Optional[Dict[str, Any]] = None
    ) -> Optional[Tuple[str, str]]:
        """
        Nombre a partir del encabezado visual cuando el nombre y el apellido van en líneas distintas y con tamaños de
        fuente diferentes ("Soledad" en letra cursiva grande y "ARGÜELLO" más chico debajo): las líneas contiguas de 1 a 3
        palabras con forma de nombre se unen. Aplica las mismas exclusiones de vocabulario que el resto de la detección y
        exige entre 2 y 4 palabras en total, de modo que una palabra suelta nunca se toma como nombre.
        """
        lineas = [lin.strip() for lin in (encabezado or "").splitlines() if lin.strip()]
        for inicio in range(len(lineas)):
            palabras: List[str] = []
            for linea in lineas[inicio : inicio + 2]:
                tokens = CandidatoService._tokens_de_nombre(linea, 1, 3)
                if not tokens:
                    break
                palabras.extend(tokens)
            if 2 <= len(palabras) <= 4:
                ordenadas = CandidatoService._ordenar_nombre_apellido(palabras, contexto)
                nombres, apellidos = CandidatoService._dividir_nombre_apellido(ordenadas, contexto)
                return " ".join(nombres).title(), " ".join(apellidos).title()
        return None

    @staticmethod
    def _nombre_desde_archivo(nombre_archivo: str, email: str = "", texto: str = "") -> Optional[Tuple[str, str]]:
        """
        Alternativa cuando el texto no permite identificar el nombre: palabras del nombre del archivo sin dígitos, sin
        vocabulario de secciones/puestos/idiomas, sin siglas de una o dos letras y sin repetir. El archivo puede tener
        varias partes separadas por " - " ("NH Data analyst-S - Nexxys Herrera"); se usa la que más coincide con el
        email. Exige al menos nombre y apellido: una palabra suelta ("My Resume" → "My") no identifica a nadie y devuelve
        None para que se aplique el valor por defecto.
        """
        import os
        import re

        base, _ = os.path.splitext(nombre_archivo or "")
        local_email = CandidatoService._clave_nombre((email or "").split("@")[0])
        mejor: Optional[Tuple[int, List[str]]] = None
        for segmento in re.split(r"\s+-\s+", base):
            partes: List[str] = []
            vistas = set()
            # Separa también palabras pegadas en CamelCase ("NancyAcosta_CV")
            for palabra in re.split(r"[\s_\-.()\[\]&]+", re.sub(r"(?<=[a-zà-ÿ])(?=[A-ZÀ-Þ])", " ", segmento)):
                clave = CandidatoService._clave_nombre(palabra)
                if not palabra or any(c.isdigit() for c in palabra) or len(clave) < 2:
                    continue
                if (
                    clave in CandidatoService.PALABRAS_NO_NOMBRE
                    and not (not partes and clave in CandidatoService.NOMBRES_DE_PILA)
                ) or clave in vistas:
                    continue
                vistas.add(clave)
                partes.append(palabra)
            # Una parte de dos letras ("Re", "Li") es un apellido corto solo si el email la muestra pegada a otra parte del
            # nombre ("regonzalom"); sin eso es una sigla ("NH") y se descarta
            partes = [
                p_
                for p_ in partes
                if len(CandidatoService._clave_nombre(p_)) >= 3
                or any(
                    (CandidatoService._clave_nombre(p_) + CandidatoService._clave_nombre(o_)) in local_email
                    or (CandidatoService._clave_nombre(o_) + CandidatoService._clave_nombre(p_)) in local_email
                    for o_ in partes
                    if o_ is not p_ and len(CandidatoService._clave_nombre(o_)) >= 3
                )
            ]
            partes = partes[:4]
            if len(partes) < 2:
                continue
            coincidencias = sum(1 for p in partes if local_email and CandidatoService._clave_nombre(p) in local_email)
            if mejor is None or coincidencias > mejor[0]:
                mejor = (coincidencias, partes)
        if not mejor:
            return None
        partes = CandidatoService._ordenar_nombre_apellido(mejor[1])
        nombres, apellidos = CandidatoService._dividir_nombre_apellido(
            partes, CandidatoService._contexto_nombre(texto, "", email)
        )
        return " ".join(nombres).title(), " ".join(apellidos).title()

    # Palabras que suelen ir solas en una línea antes de un email ("Email" / "@gmail.com"): no son parte de la dirección
    ETIQUETAS_CONTACTO = frozenset(
        "email mail correo contacto contactar telefono tel cel celular whatsapp linkedin github web direccion".split()
    )

    @staticmethod
    def _unir_email_partido(texto: str) -> str:
        """
        Reconstruye emails que la extracción del PDF partió en dos líneas ("oscaraguirre4" / "@gmail.com",
        "juan@" / "gmail.com", "juan@gmai" / "l.com"). Solo une un salto de línea pegado al "@" o a un dominio
        incompleto, y únicamente si el resultado tiene forma de email (dominio con un TLD de 2 a 6 letras en minúscula).
        Un email completo, o texto cercano que no completa un dominio, no se modifica; nunca se agregan caracteres.
        """
        import re

        t = re.sub(r"[​-‏⁠﻿]", "", (texto or "").replace("\r", ""))
        if "@" not in t:
            return texto or ""

        # a) Parte local sola en su línea y "@..." al comienzo de la siguiente. La línea anterior debe contener únicamente
        #    ese fragmento: con texto adicional ("Contacto: Oscar") no hay un corte claro y no se une. Tampoco se une una
        #    etiqueta ("Email") ni una sola palabra con aspecto de nombre propio ("Oscar").
        def unir_local(m: "re.Match") -> str:
            local = m.group("local")
            if local.lower().strip(".") in CandidatoService.ETIQUETAS_CONTACTO:
                return m.group(0)
            if local.isalpha() and local[0].isupper():
                return m.group(0)
            return local

        t = re.sub(r"(?m)^[ \t]*(?P<local>[A-Za-z0-9_.+-]+)[ \t]*\n[ \t]*(?=@[A-Za-z0-9])", unir_local, t)
        # b) "@" al final de la línea (pegado a su parte local) y a continuación una línea que empieza con un dominio completo
        t = re.sub(
            r"(?<=[A-Za-z0-9_.+-]@)[ \t]*\n[ \t]*(?=[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,6}(?![A-Za-z0-9]))",
            "",
            t,
        )

        # c) Dominio incompleto al final de la línea y su continuación en la siguiente
        def unir_dominio(m: "re.Match") -> str:
            dominio, resto = m.group("dominio"), m.group("resto")
            if re.search(r"\.[A-Za-z]{2,6}$", dominio):
                return m.group(0)  # el dominio ya está completo
            if re.match(r"(?:www\.|https?:)", resto):
                return m.group(0)  # una URL (sitio web, LinkedIn) no completa un email
            if re.fullmatch(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[a-z]{2,6}", dominio + resto):
                return dominio + resto
            return m.group(0)

        return re.sub(
            r"(?P<dominio>(?<=[A-Za-z0-9_.+-]@)[A-Za-z0-9.-]+)[ \t]*\n[ \t]*(?P<resto>[a-z0-9.-]+)(?=[ \t]*(?:\n|\Z))",
            unir_dominio,
            t,
        )

    # Skills: un término genérico (práctica, disciplina, palabra común o una herramienta distinta) no prueba una tecnología,
    # así que no se acepta como sinónimo aunque el catálogo lo declare ("pipelines" no es CI/CD; "bash" no es Linux).
    _SKILL_TERMINOS_GENERICOS = frozenset({"pipeline", "pipelines", "testing", "qa", "shell", "bash"})
    # Términos cortos o de uso común (también son palabras, empresas o disciplinas): solo cuentan si la misma línea o
    # las contiguas nombran otra tecnología del catálogo (una lista de herramientas, no una frase o un nombre propio).
    _SKILL_TERMINOS_AMBIGUOS = frozenset(
        {
            "go",
            "js",
            "ts",
            "pbi",
            "adf",
            "node",
            "elastic",
            "synapse",
            "spring",
            "spark",
            "excel",
            "oracle",
            "express",
            "xray",
            "hive",
        }
    )
    # Los ambiguos que además son palabras comunes deben estar delimitados como elemento de una lista o enumeración: sin
    # palabras de frase a los lados ("Synapse Business Analysis", "go to market", "Oracle Argentina").
    _SKILL_TERMINOS_DELIMITADOS = frozenset(
        {"go", "node", "elastic", "synapse", "spring", "spark", "oracle", "express", "hive"}
    )
    # (skill contenedora, skill contenida) cuya mención conjunta sí es evidencia de ambas
    _SKILL_CONTENIDAS_VALIDAS = frozenset({("sql server", "sql")})
    _SKILL_PALABRAS_ANTES = frozenset(
        {"y", "e", "and", "&", "con", "with", "en", "in", "de", "of", "using", "usando", "manejo", "uso"}
    )
    _SKILL_PALABRAS_DESPUES = frozenset(
        {
            "y",
            "e",
            "and",
            "&",
            "avanzado",
            "avanzada",
            "intermedio",
            "intermedia",
            "basico",
            "básico",
            "basica",
            "básica",
            "advanced",
            "intermediate",
            "basic",
            "nivel",
            "level",
        }
    )

    @staticmethod
    def _termino_delimitado(t: str, inicio: int, fin: int) -> bool:
        """True si la mención está entre separadores de lista (o inicio/fin de línea) o unida por conjunciones o niveles."""
        import re

        antes = re.search(r"([^\s]*)[ \t]*$", t[max(0, inicio - 40) : inicio]).group(1)
        despues = re.match(r"[ \t]*([^\s]*)", t[fin : fin + 40]).group(1)
        # el texto previo/posterior inmediato en la misma línea
        linea_antes = t[:inicio].rsplit("\n", 1)[-1].strip()
        linea_despues = t[fin:].split("\n", 1)[0].strip()
        if (
            linea_antes
            and not re.search(r"[,;|/•·●▪(:\-–—&]$", linea_antes)
            and antes.lower().strip(",;:") not in CandidatoService._SKILL_PALABRAS_ANTES
        ):
            return False
        if (
            linea_despues
            and not re.match(r"[,;|/•·●▪()\.:\-–—&]", linea_despues)
            and despues.lower().strip(",;:.") not in CandidatoService._SKILL_PALABRAS_DESPUES
            and not re.match(r"\d", despues)
        ):
            return False
        return True

    @staticmethod
    def _normalizar_texto_skills(texto: str) -> str:
        """Texto en minúsculas sin lo que no demuestra conocimientos: URLs, dominios, emails y etiquetas de perfil."""
        import re

        t = unicodedata.normalize("NFKC", texto or "")
        t = re.sub(r"[​-‏⁠﻿­]", "", t)
        t = re.sub(r"(?i)\b(?:https?://|www\.)\S+", " ", t)
        t = re.sub(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", " ", t)
        t = re.sub(r"(?i)\b[\w-]+(?:\.[\w-]+)*\.(?:com|org|dev|ar)(?:\.[a-z]{2})?/\S*", " ", t)
        # "GitHub: usuario" o "mi GitHub" enlazan un perfil; no son una herramienta usada
        t = re.sub(r"(?i)\b(?:github|gitlab|bitbucket)\s*:", " ", t)
        t = re.sub(r"(?i)\b(?:mi|mí|my)\s+(?:github|gitlab|bitbucket)\b", " ", t)
        return t.lower()

    @staticmethod
    def _patron_skill(termino: str) -> "re.Pattern":
        """Regex de un término de skill: tolera guiones, puntos, barras y espacios entre sus partes (power bi, power-bi,
        powerbi; node.js, node js, nodejs) y no coincide dentro de otra palabra ni de un nombre con punto
        (react.js no es js); un guion sí separa elementos de una lista (trello-jira-git). Un nombre de una sola
        letra (R) solo cuenta como elemento de una lista: entre separadores (coma, barra, viñeta, paréntesis) o solo en su línea; nunca como letra suelta de una frase
        o de un título espaciado (P R O F I L E)."""
        import re

        t = " ".join((termino or "").lower().split())
        if len(t) == 1 and t.isalnum():
            sep = r"[,;|/•·●▪(:]"
            return re.compile(
                r"(?:^|(?<=" + sep + r")|(?<=" + sep + r" ))[ \t]*" + re.escape(t) + r"[ \t]*(?=$|[,;|/•·●▪()])",
                re.M,
            )
        partes = re.split(r"(?<=[a-z0-9])[ \-_./](?=[a-z0-9])", t)
        cuerpo = r"[ \-_./]?".join(re.escape(p) for p in partes)
        return re.compile(r"(?<![a-z0-9_])(?<![a-z0-9_]\.)" + cuerpo + r"(?![a-z0-9_])")

    @staticmethod
    def detectar_skills_cv(texto: str, catalogo: List[Dict[str, Any]]) -> List[str]:
        """Skills del catálogo que el texto del CV respalda, ordenadas alfabéticamente.

        Reglas: se busca el nombre y los sinónimos de cada skill; un término genérico o que es el nombre de otra skill
        no cuenta como sinónimo; los términos ambiguos exigen contexto técnico (otra skill en su línea o las contiguas);
        las URLs, emails y etiquetas de perfil se ignoran; una mención contenida en otra más larga de otra skill no
        cuenta. No se infiere ninguna skill a partir de otra.
        """
        import bisect

        t = CandidatoService._normalizar_texto_skills(texto)
        if not t.strip():
            return []
        inicios = [0]
        for i, c in enumerate(t):
            if c == "\n":
                inicios.append(i + 1)

        def _norm(s: Any) -> str:
            return " ".join(str(s or "").lower().split())

        nombres_catalogo = {_norm(it.get("nombre")) for it in catalogo}
        coincidencias: List[Tuple[str, int, int, bool]] = []  # (skill, inicio, fin, ambigua)
        for item in catalogo:
            nombre = str(item.get("nombre") or "").strip()
            nombre_n = _norm(nombre)
            if not nombre_n:
                continue
            terminos = [nombre_n]
            for sin in item.get("sinonimos") or []:
                sin_n = _norm(sin)
                if (
                    sin_n
                    and sin_n != nombre_n
                    and sin_n not in CandidatoService._SKILL_TERMINOS_GENERICOS
                    and sin_n not in nombres_catalogo
                ):
                    terminos.append(sin_n)
            for termino in dict.fromkeys(terminos):
                ambiguo = termino in CandidatoService._SKILL_TERMINOS_AMBIGUOS or len(termino) == 1
                for m in CandidatoService._patron_skill(termino).finditer(t):
                    if (
                        termino in CandidatoService._SKILL_TERMINOS_DELIMITADOS
                        and not CandidatoService._termino_delimitado(t, m.start(), m.end())
                    ):
                        continue
                    coincidencias.append((nombre, m.start(), m.end(), ambiguo))

        # Una mención dentro de otra más larga de otra skill (Azure en "Azure DevOps", Oracle en "Oracle PL/SQL") no
        # es evidencia propia: nombra un producto distinto, no la tecnología más corta. Excepción: un motor de SQL
        # (SQL Server) es SQL, así que su mención también respalda esa skill.
        coincidencias = [
            c
            for c in coincidencias
            if not any(
                o[0] != c[0]
                and o[1] <= c[1]
                and o[2] >= c[2]
                and o[2] - o[1] > c[2] - c[1]
                and (o[0].lower(), c[0].lower()) not in CandidatoService._SKILL_CONTENIDAS_VALIDAS
                for o in coincidencias
            )
        ]

        firmes: Dict[int, set] = {}
        dudosos: List[Tuple[str, int]] = []
        encontradas = set()
        for nombre, inicio, _fin, ambiguo in coincidencias:
            linea = bisect.bisect_right(inicios, inicio) - 1
            if ambiguo:
                dudosos.append((nombre, linea))
            else:
                encontradas.add(nombre)
                firmes.setdefault(linea, set()).add(nombre)
        for nombre, linea in dudosos:
            if nombre in encontradas:
                continue
            vecinas = set().union(*(firmes.get(n, set()) for n in (linea - 1, linea, linea + 1)))
            if vecinas - {nombre}:
                encontradas.add(nombre)
        return sorted(encontradas)

    # Teléfono del CV: secuencia de dígitos con separadores habituales (espacios, guiones, puntos, paréntesis y "+"),
    # dentro de una misma línea, que empieza y termina en un límite de palabra para no tomar un número a medias.
    PATRON_TELEFONO_CV = r"(?<![\w+(])(?:\+|\(\+?)?\d[\d \t().\-]{5,}\d(?!\w)"
    # Cantidad de dígitos de un teléfono: 8 (local sin característica) a 15 (máximo internacional E.164)
    DIGITOS_TELEFONO_CV = (8, 15)
    # Formatos con dígitos suficientes que no son teléfonos: rangos de años, fechas y DNI con puntos
    NO_TELEFONO_CV = (
        r"(?:19|20)\d{2}\s*-\s*(?:19|20)\d{2}",
        r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}",
        r"\d{4}-\d{2}-\d{2}",
        r"\d{1,2}\.\d{3}\.\d{3}",
    )
    # Rótulos que anuncian otro dato numérico justo antes del número (documento, CUIT, código postal, cuenta)
    ROTULO_NO_TELEFONO_CV = (
        r"(?:dni|d\.n\.i\.?|documento|pasaporte|cuit|cuil|legajo|cbu|cvu|c\.?p\.?|codigo postal)\s*[:#nº°.]*\s*$"
    )

    @staticmethod
    def _extraer_telefono_cv(texto: Optional[str]) -> Optional[str]:
        """
        Primer teléfono válido del CV, completo y con el formato original ("+54 (3548) 15572263", "+54 3534 267338").
        Se busca línea por línea (un número nunca se arma con dígitos de dos líneas), sin URLs ni emails, y se descartan
        las secuencias que no tienen entre 8 y 15 dígitos, los rangos de años, las fechas, el DNI y los números precedidos
        por un rótulo de otro dato (DNI, CUIT, CP...). Sin un número válido devuelve None: nunca un número truncado.
        """
        import re

        minimo, maximo = CandidatoService.DIGITOS_TELEFONO_CV
        patron = re.compile(CandidatoService.PATRON_TELEFONO_CV)
        no_telefono = re.compile(r"^(?:" + "|".join(CandidatoService.NO_TELEFONO_CV) + r")$")
        rotulo_otro_dato = re.compile(CandidatoService.ROTULO_NO_TELEFONO_CV, re.IGNORECASE)
        for linea in (texto or "").splitlines():
            linea = re.sub(
                r"\S+@\S+|(?:https?://|www\.)\S+|\S*linkedin\S*|\S*github\S*", " | ", linea, flags=re.IGNORECASE
            )
            for m in patron.finditer(linea):
                valor = " ".join(m.group(0).split())
                if valor.count("(") != valor.count(")"):
                    valor = valor.lstrip("(").rstrip(")").strip()
                digitos = re.sub(r"\D", "", valor)
                if not (minimo <= len(digitos) <= maximo) or len(valor) > 30:
                    continue
                if no_telefono.match(valor) or rotulo_otro_dato.search(linea[max(0, m.start() - 25) : m.start()]):
                    continue
                return valor
        return None

    @staticmethod
    def parsear_cv_texto(
        texto: str, nombre_original: str = "", db: Optional[Session] = None, encabezado_visual: str = ""
    ) -> Dict[str, Any]:
        """Extrae heurísticamente los datos principales del candidato desde el texto del CV."""
        import re

        datos = {
            "nombre": "",
            "apellido": "",
            "email": "",
            "telefono": None,
            "ubicacion": None,
            "provincia_id": None,
            "ciudad_id": None,
            "dni": None,
            "fecha_nacimiento": None,
            "headline": None,
            "seniority": None,
            "skills": [],
            "modalidad": None,
            "pretension_salarial": None,
            "linkedin_url": None,
        }

        # 1. Email (validación de patrón estricto)
        # Se prueba primero el texto con los emails partidos reconstruidos y despues el texto original; se usa el primer
        # email que cumple el formato valido (EmailStr). Si ninguno lo cumple, se conserva el primero para el diagnostico.
        patron_email = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
        primero_invalido = ""
        for fuente_email in (CandidatoService._unir_email_partido(texto or ""), texto or ""):
            email_match = re.search(patron_email, fuente_email)
            if not email_match:
                continue
            cand_email = email_match.group(0).lower().strip().rstrip(".")
            if len(cand_email) > 5 and "@" in cand_email and "." in cand_email.split("@")[-1]:
                if CandidatoService._email_valido_cv(cand_email):
                    datos["email"] = cand_email
                    break
                primero_invalido = primero_invalido or cand_email
        if not datos["email"]:
            datos["email"] = primero_invalido

        # 2. Teléfono: número completo tal como figura en el CV (opcional)
        datos["telefono"] = CandidatoService._extraer_telefono_cv(texto)

        # 3. DNI
        if texto:
            dni_match = re.search(
                r"(?:DNI|Documento|D\.N\.I\.?)[:\s]*([0-9]{1,2}\.?[0-9]{3}\.?[0-9]{3})", texto, re.IGNORECASE
            )
            if dni_match:
                datos["dni"] = re.sub(r"\D", "", dni_match.group(1))

        # 4. Fecha de nacimiento
        if texto:
            from datetime import datetime as _dt

            meses_map = {
                "enero": 1,
                "febrero": 2,
                "marzo": 3,
                "abril": 4,
                "mayo": 5,
                "junio": 6,
                "julio": 7,
                "agosto": 8,
                "septiembre": 9,
                "setiembre": 9,
                "octubre": 10,
                "noviembre": 11,
                "diciembre": 12,
                "january": 1,
                "february": 2,
                "march": 3,
                "april": 4,
                "may": 5,
                "june": 6,
                "july": 7,
                "august": 8,
                "september": 9,
                "october": 10,
                "november": 11,
                "december": 12,
            }
            patron_prefijo = r"(?:fecha\s*(?:de)?\s*nacimiento|nacimiento|f\.?\s*nac(?:imiento)?\.?|birth\s*date|date\s*(?:of)?\s*birth|born)[:\s]*"

            # Opción A: DD/MM/YYYY o DD-MM-YYYY o DD.MM.YYYY
            match_fn = re.search(
                patron_prefijo + r"([0-9]{1,2})[/\-\.]([0-9]{1,2})[/\-\.]([0-9]{4})", texto, re.IGNORECASE
            )
            if match_fn:
                dia_n, mes_n, anio_n = int(match_fn.group(1)), int(match_fn.group(2)), int(match_fn.group(3))
                if 1900 <= anio_n <= 2010 and 1 <= mes_n <= 12 and 1 <= dia_n <= 31:
                    try:
                        datos["fecha_nacimiento"] = _dt(anio_n, mes_n, dia_n).date()
                    except Exception:
                        pass

            # Opción B: YYYY-MM-DD
            if not datos["fecha_nacimiento"]:
                match_iso = re.search(
                    patron_prefijo + r"([0-9]{4})[/\-\.]([0-9]{1,2})[/\-\.]([0-9]{1,2})", texto, re.IGNORECASE
                )
                if match_iso:
                    anio_n, mes_n, dia_n = int(match_iso.group(1)), int(match_iso.group(2)), int(match_iso.group(3))
                    if 1900 <= anio_n <= 2010 and 1 <= mes_n <= 12 and 1 <= dia_n <= 31:
                        try:
                            datos["fecha_nacimiento"] = _dt(anio_n, mes_n, dia_n).date()
                        except Exception:
                            pass

            # Opción C: 25 de mayo de 1995
            if not datos["fecha_nacimiento"]:
                match_txt = re.search(
                    patron_prefijo + r"([0-9]{1,2})\s+(?:de\s+)?([a-záéíóú]+)\s+(?:de\s+)?([0-9]{4})",
                    texto,
                    re.IGNORECASE,
                )
                if match_txt:
                    dia_n = int(match_txt.group(1))
                    mes_nombre = match_txt.group(2).lower()
                    anio_n = int(match_txt.group(3))
                    if mes_nombre in meses_map and 1900 <= anio_n <= 2010 and 1 <= dia_n <= 31:
                        try:
                            datos["fecha_nacimiento"] = _dt(anio_n, meses_map[mes_nombre], dia_n).date()
                        except Exception:
                            pass

        # 5. LinkedIn (URLs visibles, hipervinculos embebidos y variantes sin esquema)
        if texto:
            datos["linkedin_url"] = extraer_linkedin_url(texto)

        # 6. Nombre y apellido
        candidato_nom = ""
        candidato_ape = ""

        # Identificación contextual: forma de nombre + respaldo del email, LinkedIn, archivo o posición en el documento
        nombre_cv = CandidatoService._detectar_nombre_cv(texto, nombre_original, datos["email"])
        if encabezado_visual:
            # Si el texto lineal no lo identificó (columnas laterales o encabezado gráfico que altera el orden de lectura) o
            # lo dejó incompleto, se prueba con el título más destacado de la primera página, con las mismas validaciones
            contexto_nombre = CandidatoService._contexto_nombre(texto, nombre_original, datos["email"])
            nombre_cv = CandidatoService._elegir_nombre_cv(
                [
                    nombre_cv,
                    CandidatoService._detectar_nombre_cv(
                        encabezado_visual, nombre_original, datos["email"], texto_completo=texto
                    ),
                    CandidatoService._nombre_desde_encabezado_visual(encabezado_visual, contexto_nombre),
                ],
                contexto_nombre,
            )
        if nombre_cv:
            candidato_nom, candidato_ape = nombre_cv
        else:
            # Sin información suficiente en el texto: se deduce del nombre del archivo (nunca de una lista de habilidades)
            nombre_archivo_cv = CandidatoService._nombre_desde_archivo(nombre_original, datos["email"], texto)
            if nombre_archivo_cv:
                candidato_nom, candidato_ape = nombre_archivo_cv

        if not candidato_nom:
            candidato_nom = "Candidato"
            candidato_ape = "Sin Nombre"

        datos["nombre"] = candidato_nom
        datos["apellido"] = candidato_ape

        # 6. Skills respaldadas por el CV, contra el catálogo activo (o el catálogo base si no hay BD)
        texto_lower = (texto or "").lower()
        skills_catalogo_db = []
        if db is not None:
            try:
                skills_catalogo_db = SkillService.obtener_catalogo_activo(db)
            except Exception:
                skills_catalogo_db = []

        datos["skills"] = CandidatoService.detectar_skills_cv(texto, skills_catalogo_db)

        # 7. Headline / Puesto: perfil del catálogo según el CV (puesto más reciente, encabezado, perfil); "Otro" si el rol no tiene
        # perfil propio y None solo si el CV no tiene ningún título ni funciones reconocibles
        datos["headline"] = detectar_headline_cv(texto, encabezado_visual)

        # 8. Seniority (Regla estricta: los únicos valores válidos son Trainee, Junior, Semi Senior, Senior; Líder Técnico -> Senior)
        if any(
            w in texto_lower for w in ["lider tecnico", "líder técnico", "lead", "arquitecto", "principal", "tech lead"]
        ):
            datos["seniority"] = "Senior"
        elif any(w in texto_lower for w in ["senior", "sr.", "sr ", "ssr."]):
            if "semi" in texto_lower or "ssr" in texto_lower:
                datos["seniority"] = "Semi Senior"
            else:
                datos["seniority"] = "Senior"
        elif any(w in texto_lower for w in ["junior", "jr.", "jr "]):
            datos["seniority"] = "Junior"
        elif any(w in texto_lower for w in ["trainee", "pasante", "practicante"]):
            # Solo si es la situación actual: una pasantía anterior a un puesto profesional fechado no define el seniority
            # (queda sin seniority en lugar de inventar uno). Sin fechas en la experiencia se mantiene la regla anterior.
            if puesto_vigente_es_condicion(texto) is not False:
                datos["seniority"] = "Trainee"

        # Garantizar normalización inmediata si algún análisis previo/externo dejó 'Líder Técnico'
        if datos["seniority"] in ("Líder Técnico", "Lider Tecnico"):
            datos["seniority"] = "Senior"

        # 9. Modalidad
        if "remoto" in texto_lower or "remote" in texto_lower:
            datos["modalidad"] = "Remoto"
        elif "hibrido" in texto_lower or "híbrido" in texto_lower or "hybrid" in texto_lower:
            datos["modalidad"] = "Híbrido"
        elif "presencial" in texto_lower:
            datos["modalidad"] = "Presencial"

        # 10. Ubicación geográfica: provincia y ciudad reconocidas contra los catálogos de Parámetros
        ubicacion_detectada = CandidatoService.detectar_ubicacion_catalogo(
            db, texto, nombre_completo=f"{candidato_nom} {candidato_ape}" if nombre_cv else None
        )
        if ubicacion_detectada:
            datos["ubicacion"] = ubicacion_detectada["ubicacion"]
            datos["provincia_id"] = ubicacion_detectada["provincia_id"]
            datos["ciudad_id"] = ubicacion_detectada["ciudad_id"]

        return datos

    MENSAJE_CV_SIN_EMAIL = (
        "No se pudo registrar el candidato porque no se encontró un email válido en el CV. "
        "Verificá el documento e intentá nuevamente."
    )

    @staticmethod
    def _email_valido_cv(email: Optional[str]) -> Optional[str]:
        """Devuelve el email extraído del CV normalizado si cumple la misma regla que CandidatoCreate (EmailStr); si no, None."""
        from pydantic import EmailStr, TypeAdapter, ValidationError

        email_limpio = (email or "").strip().lower()
        if not email_limpio or len(email_limpio) > 255:
            return None
        try:
            TypeAdapter(EmailStr).validate_python(email_limpio)
        except ValidationError:
            return None
        return email_limpio

    @staticmethod
    def _registrar_email_no_detectado(nombre_archivo: str, texto_cv: str, email_extraido: Optional[str]) -> None:
        """Deja trazas para diagnosticar un CV rechazado por falta de email válido (sin registrar el texto completo del CV)."""
        import re

        _log = logging.getLogger(__name__)
        if email_extraido:
            _log.warning(f"CV '{nombre_archivo}' rechazado: el email extraído no es válido ({email_extraido!r}).")
        elif not (texto_cv or "").strip():
            _log.warning(
                f"CV '{nombre_archivo}' rechazado: no se pudo extraer texto del documento para buscar el email."
            )
        elif re.search(r"@|\be-?mail\b|\bcorreo\b", texto_cv, re.IGNORECASE):
            _log.warning(
                f"CV '{nombre_archivo}' rechazado: el documento parece contener un email, pero el parser no lo detectó."
            )
        else:
            _log.info(f"CV '{nombre_archivo}' rechazado: el documento no contiene un email.")

    @staticmethod
    def _cv_almacenado_identico(candidato: Candidato, contenido: bytes) -> bool:
        """True si el CV almacenado del candidato tiene el mismo SHA-256 que el archivo recibido."""
        import hashlib

        from backend.core.storage import cloud_storage

        if not candidato.cv_url:
            return False
        try:
            almacenado = cloud_storage.download(candidato.cv_url)
        except Exception:
            return False
        return hashlib.sha256(almacenado).hexdigest() == hashlib.sha256(contenido).hexdigest()

    @staticmethod
    def _resumen_comparacion_cv(origen: Any, nombre_archivo: Optional[str] = None) -> Dict[str, Any]:
        """Datos visibles en el modal de comparacion; origen es un Candidato o el dict de datos extraidos del CV."""

        def valor(campo: str) -> Any:
            return origen.get(campo) if isinstance(origen, dict) else getattr(origen, campo, None)

        return {
            "nombre": valor("nombre"),
            "apellido": valor("apellido"),
            "email": valor("email"),
            "telefono": valor("telefono"),
            "ubicacion": valor("ubicacion"),
            "dni": valor("dni"),
            "headline": valor("headline"),
            "seniority": valor("seniority"),
            "modalidad": valor("modalidad"),
            "skills": list(valor("skills") or []),
            "archivo": nombre_archivo or (valor("cv_url") or "").split("/")[-1] or None,
            "cv_url": valor("cv_url"),
        }

    @staticmethod
    def _actualizar_desde_cv(
        db: Session,
        candidato: Candidato,
        datos: Dict[str, Any],
        contenido: bytes,
        ext: str,
        usuario: Optional[str],
    ) -> Candidato:
        """Reemplaza el CV y los datos extraidos de la ficha existente (solo pisa los campos que el nuevo CV aporta)."""
        from backend.core.storage import cloud_storage

        mime = {
            ".pdf": "application/pdf",
            ".doc": "application/msword",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }.get(ext, "application/octet-stream")
        clave_anterior = candidato.cv_url
        clave = f"recruiting/cv/{candidato.id}{ext}"
        cv_previo: Optional[bytes] = None  # contenido que ya ocupaba `clave` (se restaura si la actualizacion falla)
        subido = False
        try:
            for campo in (
                "nombre",
                "apellido",
                "telefono",
                "dni",
                "fecha_nacimiento",
                "linkedin_url",
                "headline",
                "seniority",
                "modalidad",
            ):
                if datos.get(campo):
                    setattr(candidato, campo, datos[campo])
            if datos.get("provincia_id"):
                # La ubicación se reemplaza completa: una provincia sin ciudad no conserva la ciudad anterior (de otra provincia)
                candidato.provincia_id = datos["provincia_id"]
                candidato.ciudad_id = datos.get("ciudad_id")
                candidato.ubicacion = datos.get("ubicacion")
            elif datos.get("ubicacion"):
                candidato.ubicacion = datos["ubicacion"]
            if datos.get("skills"):
                candidato.skills = datos["skills"]
            candidato.updated_at = utc_now()
            if usuario:
                candidato.updated_by = usuario
            db.flush()  # la base valida los cambios ANTES de tocar el storage: si los rechaza, el CV vinculado queda intacto
            try:
                if cloud_storage.exists(clave):
                    cv_previo = cloud_storage.download(clave)
            except Exception:
                cv_previo = None
            cloud_storage.upload(clave, contenido, mime)
            subido = True
            candidato.cv_url = clave
            db.commit()
        except Exception as e:
            db.rollback()
            if subido:
                # La ficha no cambio: el storage tampoco (se repone el CV anterior o se elimina el recien subido)
                try:
                    if cv_previo is not None:
                        cloud_storage.upload(clave, cv_previo, mime)
                    else:
                        cloud_storage.delete(clave)
                except Exception:
                    import logging

                    logging.getLogger(__name__).error(
                        f"No se pudo restaurar el CV vinculado {clave} tras una actualizacion fallida"
                    )
            raise CVPersistenciaError(candidato.email, e) from e
        if clave_anterior and clave_anterior != clave:
            try:
                cloud_storage.delete(clave_anterior)
            except Exception:
                pass
        db.refresh(candidato)
        return candidato

    @staticmethod
    def procesar_cv_bytes(
        db: Session,
        empresa_id: uuid.UUID,
        contenido: bytes,
        nombre_archivo: str,
        content_type: Optional[str] = None,
        usuario: Optional[str] = None,
        max_bytes: int = 10 * 1024 * 1024,  # 10 MB por defecto en contexto masivo
        current_user: Optional[Usuario] = None,
        modo_duplicado: str = "omitir",
        validar_permiso_existente: bool = False,
    ) -> Candidato:
        """
        validar_permiso_existente: con "comparar"/"actualizar", exige que current_user pueda acceder a la ficha existente (403 si no).
        modo_duplicado (email ya existente): "omitir" (409), "comparar" (409 si el archivo es identico; CVDuplicadoDistintoError si es distinto)
        o "actualizar" (reemplaza el CV y los datos de la ficha existente).
        Procesa los bytes de un archivo de CV (PDF, DOC, DOCX), extrae sus datos,
        crea el candidato y almacena el archivo en Cloud Storage.
        - NUNCA lanza HTTPException 500: si falla la extracción, usa datos mínimos del nombre de archivo.
        - Si el CV no contiene un email válido, lanza 422 sin persistir nada (nunca se genera un email alternativo).
        - Si el email ya existe (sin distinguir mayúsculas ni espacios), lanza CVEmailDuplicadoError (409) sin modificar la ficha existente.
        - Si falla el guardado, lanza CVPersistenciaError.
        - Usa savepoint para que un error de BD no anule la sesión completa.
        """
        import os

        from backend.core.storage import cloud_storage

        _log = logging.getLogger(__name__)

        if not nombre_archivo:
            raise HTTPException(status_code=400, detail="Nombre de archivo inválido")

        _, ext = os.path.splitext(nombre_archivo.lower())
        ext = ext.lower().strip()

        extensiones_validas = {".pdf", ".doc", ".docx"}
        if ext not in extensiones_validas:
            raise HTTPException(
                status_code=400, detail=f"Formato no admitido '{ext}'. Solo se admiten archivos PDF, DOC y DOCX."
            )

        if len(contenido) > max_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"El archivo excede el tamaño máximo permitido de {max_bytes // (1024 * 1024)} MB.",
            )

        # 1. Extraer texto — cualquier excepción → texto vacío (degradación segura)
        texto_cv = ""
        try:
            texto_cv = CandidatoService._extraer_texto_de_archivo(contenido, ext)
        except Exception as e_extract:
            _log.warning(f"Extracción de texto fallida para {nombre_archivo}: {e_extract}")
            texto_cv = ""

        # 2. Parsear datos del candidato — cualquier excepción → parsear con texto vacío
        try:
            encabezado_visual = CandidatoService._extraer_encabezado_visual_pdf(contenido) if ext == ".pdf" else ""
            datos_extraidos = CandidatoService.parsear_cv_texto(
                texto_cv, nombre_archivo, db=db, encabezado_visual=encabezado_visual
            )
        except Exception as e_parse:
            _log.warning(f"Parseo fallido para {nombre_archivo}: {e_parse}")
            try:
                datos_extraidos = CandidatoService.parsear_cv_texto("", nombre_archivo, db=db)
            except Exception:
                # Fallback absoluto: deducir nombre del archivo
                base, _ = os.path.splitext(nombre_archivo)
                import re as _re

                partes = [
                    p
                    for p in _re.split(r"[\s_\-]+", base)
                    if p and not p.isdigit() and p.lower() not in {"cv", "curriculum", "resume"}
                ]
                datos_extraidos = {
                    "nombre": partes[0].capitalize() if partes else "Candidato",
                    "apellido": " ".join(partes[1:]).title() if len(partes) > 1 else "Sin Nombre",
                    "email": "",
                    "telefono": None,
                    "ubicacion": None,
                    "dni": None,
                    "headline": None,
                    "seniority": None,
                    "skills": [],
                    "modalidad": None,
                    "pretension_salarial": None,
                    "linkedin_url": None,
                }

        # Normalización estricta de Seniority extraído del CV (Líder Técnico -> Senior)
        sen_extraido = datos_extraidos.get("seniority")
        if sen_extraido and sen_extraido.strip().lower() in (
            "líder técnico",
            "lider tecnico",
            "lead",
            "tech lead",
            "arquitecto",
            "principal",
        ):
            datos_extraidos["seniority"] = "Senior"
        elif sen_extraido and sen_extraido not in ("Trainee", "Junior", "Semi Senior", "Senior"):
            # Si no es uno de los 4 valores válidos, verificar si contiene subcadenas conocidas
            sen_lower = sen_extraido.strip().lower()
            if "semi" in sen_lower or "ssr" in sen_lower:
                datos_extraidos["seniority"] = "Semi Senior"
            elif "senior" in sen_lower or "sr" in sen_lower:
                datos_extraidos["seniority"] = "Senior"
            elif "junior" in sen_lower or "jr" in sen_lower:
                datos_extraidos["seniority"] = "Junior"
            elif "trainee" in sen_lower or "pasante" in sen_lower:
                datos_extraidos["seniority"] = "Trainee"

        # 3. Email real obligatorio: sin un email válido en el CV el candidato no se registra (nunca se inventa uno)
        email_candidato = CandidatoService._email_valido_cv(datos_extraidos.get("email"))
        if not email_candidato:
            CandidatoService._registrar_email_no_detectado(nombre_archivo, texto_cv, datos_extraidos.get("email"))
            raise CVSinEmailError(CandidatoService.MENSAJE_CV_SIN_EMAIL)

        # 4. Duplicado por email (sin distinguir mayúsculas ni espacios, sin filtrar por estado): el CV se omite y la ficha existente NO se toca
        try:
            existente = (
                db.query(Candidato)
                .filter(
                    Candidato.empresa_id == empresa_id,
                    func.lower(func.trim(Candidato.email)) == email_candidato,
                )
                .first()
            )
        except Exception as e_query:
            raise CVPersistenciaError(email_candidato, e_query) from e_query
        if existente:
            if modo_duplicado == "omitir" or existente.deleted_at is not None:
                raise CVEmailDuplicadoError(email_candidato)
            if validar_permiso_existente:
                CandidatoService.get_by_id(db, empresa_id, str(existente.id), current_user=current_user)
            if modo_duplicado == "comparar":
                if CandidatoService._cv_almacenado_identico(existente, contenido):
                    raise CVEmailDuplicadoError(email_candidato, existente.id)
                raise CVDuplicadoDistintoError(
                    email_candidato,
                    CandidatoService._resumen_comparacion_cv(existente),
                    CandidatoService._resumen_comparacion_cv(datos_extraidos, nombre_archivo=nombre_archivo),
                    existente.id,
                )
            return CandidatoService._actualizar_desde_cv(db, existente, datos_extraidos, contenido, ext, usuario)

        content_types = {
            ".pdf": "application/pdf",
            ".doc": "application/msword",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        }
        mime_tipo = content_types.get(ext, content_type or "application/octet-stream")

        # 6. Crear nuevo candidato protegido por savepoint
        codigo_nuevo = CandidatoService._generar_siguiente_codigo(db, empresa_id)

        creador_id = current_user.id if current_user else None

        nuevo_candidato = Candidato(
            empresa_id=empresa_id,
            codigo=codigo_nuevo,
            nombre=(datos_extraidos.get("nombre") or "Candidato")[:100],
            apellido=(datos_extraidos.get("apellido") or "")[:100],
            email=email_candidato[:255],
            telefono=datos_extraidos.get("telefono") or None,
            ubicacion=datos_extraidos.get("ubicacion") or CandidatoService.UBICACION_NO_IDENTIFICADA,
            provincia_id=datos_extraidos.get("provincia_id") or CandidatoService._provincia_no_identificada_id(db),
            ciudad_id=datos_extraidos.get("ciudad_id"),
            dni=datos_extraidos.get("dni") or None,
            fecha_nacimiento=datos_extraidos.get("fecha_nacimiento") or None,
            linkedin_url=datos_extraidos.get("linkedin_url") or None,
            headline=datos_extraidos.get("headline") or None,
            seniority=datos_extraidos.get("seniority") or None,
            modalidad=datos_extraidos.get("modalidad") or None,
            skills=datos_extraidos.get("skills") or [],
            pretension_salarial=None,
            moneda_pretension="ARS",
            estado="Activo",
            fuente="Portal Propio",
            creador_id=creador_id,
            updated_by=usuario,
        )

        # Usar context manager begin_nested() para aislar la transacción
        try:
            with db.begin_nested():
                db.add(nuevo_candidato)
                db.flush()

                # Guardar archivo en Storage
                try:
                    key = f"recruiting/cv/{nuevo_candidato.id}{ext}"
                    cloud_storage.upload(key, contenido, mime_tipo)
                    nuevo_candidato.cv_url = key
                except Exception as e_storage:
                    _log.warning(f"Error al subir CV al storage para nuevo candidato: {e_storage}")
                    nuevo_candidato.cv_url = None

                nuevo_candidato.updated_at = utc_now()
                db.flush()

            db.commit()
        except Exception as e_persist:
            raise CVPersistenciaError(email_candidato, e_persist) from e_persist
        try:
            db.refresh(nuevo_candidato)
        except Exception as e_refresh:
            _log.warning(f"Candidato guardado pero no se pudo refrescar: {e_refresh}")
        return nuevo_candidato

    @staticmethod
    async def crear_desde_cv(
        db: Session,
        empresa_id: uuid.UUID,
        archivo: UploadFile,
        usuario: Optional[str] = None,
        current_user: Optional[Usuario] = None,
        modo_duplicado: str = "omitir",
        validar_permiso_existente: bool = False,
    ) -> Candidato:
        """
        Carga individual de CV con auditoria (recruiting_historial_cargas_cv): delega sin alterarla en
        `_crear_desde_cv_sin_auditoria` y registra el intento (creado, duplicado, sin email o rechazado) en una transaccion propia.
        `modo_duplicado="actualizar"` confirma un duplicado ya auditado y no genera otro registro.
        """
        argumentos = dict(
            db=db,
            empresa_id=empresa_id,
            archivo=archivo,
            usuario=usuario,
            current_user=current_user,
            modo_duplicado=modo_duplicado,
            validar_permiso_existente=validar_permiso_existente,
        )
        if modo_duplicado == "actualizar":
            return await CandidatoService._crear_desde_cv_sin_auditoria(**argumentos)
        from backend.modules.recruiting.historial_cargas_services import HistorialCargaCVService

        nombre = os.path.basename(getattr(archivo, "filename", None) or "") or "(sin archivo)"
        usuario_id = getattr(current_user, "id", None)
        usuario_nombre = HistorialCargaCVService.nombre_usuario(current_user)
        resultado, motivo = "creado", None
        try:
            return await CandidatoService._crear_desde_cv_sin_auditoria(**argumentos)
        except CVEmailDuplicadoError:
            resultado, motivo = "duplicado", "Ya existe un candidato con el mismo email."
            raise
        except CVSinEmailError as e_sin:
            resultado, motivo = "sin_email", str(e_sin.detail)
            raise
        except HTTPException as e_http:
            resultado, motivo = "rechazado", str(e_http.detail)
            raise
        except Exception:
            resultado, motivo = "rechazado", MENSAJE_ERROR_INTERNO
            raise
        finally:
            await asyncio.to_thread(
                HistorialCargaCVService.registrar,
                empresa_id,
                usuario_id,
                usuario_nombre,
                "individual",
                nombre,
                [{"nombre": nombre, "resultado": resultado, "motivo": motivo}],
            )

    @staticmethod
    async def _crear_desde_cv_sin_auditoria(
        db: Session,
        empresa_id: uuid.UUID,
        archivo: UploadFile,
        usuario: Optional[str] = None,
        current_user: Optional[Usuario] = None,
        modo_duplicado: str = "omitir",
        validar_permiso_existente: bool = False,
    ) -> Candidato:
        """
        Crea un nuevo candidato procesando y parseando un archivo de CV (PDF, DOCX).
        Aplica validaciones de contingencia para campos faltantes y persiste el archivo.
        """
        if not archivo or not archivo.filename:
            raise HTTPException(status_code=400, detail="No se seleccionó ningún archivo de CV")

        try:
            contenido = await archivo.read()
        except Exception as e_read:
            raise HTTPException(status_code=400, detail=f"Error al leer los datos del archivo: {str(e_read)}")

        # Archivado del original segun el resultado final (mismo helper y CV_STORAGE_DIR que la carga masiva).
        # Solo se archiva lo que llego a procesarse: los rechazos previos (sin archivo, error de lectura) no se archivan.
        try:
            # En un hilo: la extraccion (y el OCR, que puede tardar segundos) no bloquea el event loop del endpoint
            candidato = await asyncio.to_thread(
                CandidatoService.procesar_cv_bytes,
                db=db,
                empresa_id=empresa_id,
                contenido=contenido,
                nombre_archivo=archivo.filename,
                content_type=archivo.content_type,
                usuario=usuario,
                max_bytes=5 * 1024 * 1024,
                current_user=current_user,
                modo_duplicado=modo_duplicado,
                validar_permiso_existente=validar_permiso_existente,
            )
        except CVEmailDuplicadoError:
            CandidatoService._archivar_cv_masivo(archivo.filename, contenido, "duplicado")
            raise
        except Exception as e_carga:
            # Actualizacion confirmada que falla: el original sigue en cv_duplicados y no se agrega otra copia en cv_errores
            if not (
                modo_duplicado == "actualizar"
                and CandidatoService._buscar_cv_en_duplicados(archivo.filename, contenido)
            ):
                # Motivo = el mismo mensaje que ya recibe el usuario (HTTPException) o el mensaje generico de error interno
                motivo = str(e_carga.detail) if isinstance(e_carga, HTTPException) else MENSAJE_ERROR_INTERNO
                CandidatoService._archivar_cv_masivo(archivo.filename, contenido, "error", motivo)
            raise
        if modo_duplicado == "actualizar":
            # Confirmacion de un duplicado: el original ya archivado en cv_duplicados pasa a cv_procesados_ok (sin copia en ambas)
            CandidatoService._mover_cv_duplicado_a_ok(archivo.filename, contenido)
        else:
            CandidatoService._archivar_cv_masivo(archivo.filename, contenido, "creado")
        return candidato

    # Resultado final de cada archivo de una carga masiva (categorías mutuamente excluyentes) -> campo del resumen
    RESULTADOS_CARGA_MASIVA = {
        "creado": "creados",
        "duplicado": "duplicados_omitidos",
        "sin_email": "sin_email",
        "formato_tamano": "rechazados_formato_tamano",
        "error_lectura": "errores_lectura",
        "error_validacion": "errores_validacion",
        "error_persistencia": "errores_persistencia",
        "error_otro": "errores_otros",
    }

    @staticmethod
    def construir_resumen_carga_masiva(resultados: List[Dict[str, Any]], lote_id: str) -> Dict[str, Any]:
        """Cuenta los resultados individuales de UN lote: cada archivo suma en una única categoría."""
        resumen: Dict[str, Any] = {"lote_id": lote_id, "total_archivos": len(resultados)}
        for campo in CandidatoService.RESULTADOS_CARGA_MASIVA.values():
            resumen[campo] = 0
        for r in resultados:
            resumen[CandidatoService.RESULTADOS_CARGA_MASIVA[r["resultado"]]] += 1
        return resumen

    MAX_CVS_INDIVIDUALES_CARGA_MASIVA = 100

    CARPETA_CV_OK = "cv_procesados_ok"
    CARPETA_CV_ERRORES = "cv_errores"
    CARPETA_CV_DUPLICADOS = "cv_duplicados"

    @staticmethod
    def _raiz_cv_storage() -> str:
        import os

        return os.getenv("CV_STORAGE_DIR", "/data/cv")

    @staticmethod
    def _nombre_base_ext_cv(nombre_archivo: str) -> Tuple[str, str]:
        """Nombre saneado (base, extension) con el que se guarda un CV archivado."""
        import os
        import re

        base, ext = os.path.splitext(os.path.basename((nombre_archivo or "").replace("\\", "/")))
        base = re.sub(r"[^\w.\- ]", "_", base).strip(" .") or "cv"
        ext = re.sub(r"[^\w.]", "_", ext)
        return base, ext

    @staticmethod
    def _escribir_cv_exclusivo(carpeta: str, nombre_archivo: str, contenido: bytes) -> str:
        """Escribe el CV en `carpeta` sin sobrescribir nunca (sufijo _1, _2...; modo exclusivo, seguro ante concurrencia). Devuelve el destino."""
        import os

        os.makedirs(carpeta, exist_ok=True)
        base, ext = CandidatoService._nombre_base_ext_cv(nombre_archivo)
        n = 0
        while True:
            destino = os.path.join(carpeta, f"{base}{'' if n == 0 else '_' + str(n)}{ext}")
            try:
                with open(destino, "xb") as f:
                    f.write(contenido)
                    f.flush()
                    os.fsync(f.fileno())
                return destino
            except FileExistsError:
                n += 1

    # Indice oculto (JSON Lines) dentro de cv_errores con el motivo real del rechazo de cada CV archivado.
    # Al ser oculto no aparece en el listado, el conteo, la descarga individual ni el ZIP.
    ARCHIVO_MOTIVOS_ERRORES = ".motivos.jsonl"
    MAX_LARGO_MOTIVO = 500

    @staticmethod
    def _registrar_motivo_error(carpeta: str, nombre_guardado: str, motivo: str) -> None:
        """Agrega (append) una linea {archivo, motivo} al indice de motivos de cv_errores."""
        import json
        import os

        linea = (
            json.dumps(
                {"archivo": nombre_guardado, "motivo": (motivo or "").strip()[: CandidatoService.MAX_LARGO_MOTIVO]},
                ensure_ascii=False,
            )
            + "\n"
        )
        with open(os.path.join(carpeta, CandidatoService.ARCHIVO_MOTIVOS_ERRORES), "a", encoding="utf-8") as f:
            f.write(linea)
            f.flush()
            os.fsync(f.fileno())

    @staticmethod
    def _archivar_cv_masivo(
        nombre_archivo: str, contenido: bytes, resultado: str, motivo: Optional[str] = None
    ) -> None:
        """
        Guarda el CV original segun el resultado final: creado -> cv_procesados_ok, duplicado por email -> cv_duplicados,
        cualquier otro rechazo -> cv_errores. Raiz configurable con CV_STORAGE_DIR. Nunca sobrescribe (sufijo _1, _2...)
        y nunca interrumpe la carga: un fallo de escritura solo se registra en el log.
        Si va a cv_errores y se informa `motivo`, queda registrado (indice oculto) para mostrarlo en Parametros > Archivos de CV.
        """
        import os

        logger = logging.getLogger(__name__)
        if resultado == "creado":
            subcarpeta = CandidatoService.CARPETA_CV_OK
        elif resultado == "duplicado":
            subcarpeta = CandidatoService.CARPETA_CV_DUPLICADOS
        else:
            subcarpeta = CandidatoService.CARPETA_CV_ERRORES
        try:
            destino = CandidatoService._escribir_cv_exclusivo(
                os.path.join(CandidatoService._raiz_cv_storage(), subcarpeta), nombre_archivo, contenido
            )
            logger.info(f"CV masivo {nombre_archivo} guardado en {destino}")
            if subcarpeta == CandidatoService.CARPETA_CV_ERRORES and motivo:
                try:
                    CandidatoService._registrar_motivo_error(
                        os.path.dirname(destino), os.path.basename(destino), motivo
                    )
                except Exception as e_motivo:
                    logger.error(f"No se pudo registrar el motivo del error de {nombre_archivo}: {e_motivo}")
        except Exception as e_arch:
            logger.error(f"No se pudo guardar el CV masivo {nombre_archivo} en {subcarpeta}: {e_arch}")

    @staticmethod
    def _buscar_cv_en_duplicados(nombre_archivo: str, contenido: bytes) -> List[str]:
        """Rutas de cv_duplicados con el mismo nombre base (con o sin sufijo _N) y contenido identico al CV subido."""
        import os
        import re

        carpeta_dup = os.path.join(CandidatoService._raiz_cv_storage(), CandidatoService.CARPETA_CV_DUPLICADOS)
        if not os.path.isdir(carpeta_dup):
            return []
        base, ext = CandidatoService._nombre_base_ext_cv(nombre_archivo)
        patron = re.compile(rf"^{re.escape(base)}(?:_\d+)?{re.escape(ext)}$")
        encontrados = []
        for nombre in sorted(os.listdir(carpeta_dup)):
            ruta = os.path.join(carpeta_dup, nombre)
            if patron.match(nombre) and os.path.isfile(ruta) and os.path.getsize(ruta) == len(contenido):
                with open(ruta, "rb") as f:
                    if f.read() == contenido:
                        encontrados.append(ruta)
        return encontrados

    @staticmethod
    def _mover_cv_duplicado_a_ok(nombre_archivo: str, contenido: bytes) -> None:
        """
        Actualizacion confirmada de un CV duplicado: el original ya archivado en cv_duplicados (mismo nombre base, con o sin sufijo _N,
        y contenido identico) se MUEVE a cv_procesados_ok, sin volver a escribirlo desde el archivo subido. Si no hay copia previa
        (p. ej. fallo el archivado inicial) se archiva como un CV procesado normal. Nunca interrumpe la operacion: los fallos solo se registran.
        Seguridad: el origen se reclama con un rename atomico (si dos confirmaciones compiten, solo una lo mueve), se escribe el destino en
        modo exclusivo y se verifica su contenido; el origen solo se elimina despues de esa verificacion y se restaura si algo falla.
        """
        import os
        import uuid

        logger = logging.getLogger(__name__)
        raiz = CandidatoService._raiz_cv_storage()
        carpeta_dup = os.path.join(raiz, CandidatoService.CARPETA_CV_DUPLICADOS)
        carpeta_ok = os.path.join(raiz, CandidatoService.CARPETA_CV_OK)
        try:
            candidatos = CandidatoService._buscar_cv_en_duplicados(nombre_archivo, contenido)
            if not candidatos:
                CandidatoService._archivar_cv_masivo(nombre_archivo, contenido, "creado")
                return
            for origen in candidatos:
                reclamado = os.path.join(carpeta_dup, f".moviendo-{uuid.uuid4().hex}")
                try:
                    os.rename(origen, reclamado)  # atomico: solo una confirmacion concurrente lo obtiene
                except FileNotFoundError:
                    continue
                destino = None
                try:
                    with open(reclamado, "rb") as f:
                        datos = f.read()
                    destino = CandidatoService._escribir_cv_exclusivo(carpeta_ok, nombre_archivo, datos)
                    with open(destino, "rb") as f:
                        if f.read() != datos:
                            raise OSError("el destino no coincide con el original")
                except Exception as e_mov:
                    logger.error(
                        f"No se pudo mover el CV {nombre_archivo} a {CandidatoService.CARPETA_CV_OK}; permanece en duplicados: {e_mov}"
                    )
                    if destino and os.path.exists(destino):
                        os.remove(destino)  # destino incompleto o no verificado: no se deja una copia dudosa
                    try:
                        # Se restaura el original en duplicados (el nombre original puede haber sido tomado: se usa uno libre)
                        if not os.path.exists(origen):
                            os.rename(reclamado, origen)
                        else:
                            CandidatoService._escribir_cv_exclusivo(carpeta_dup, nombre_archivo, contenido)
                            os.remove(reclamado)
                    except Exception as e_rest:
                        logger.error(f"CV {nombre_archivo} conservado como {reclamado}: {e_rest}")
                    return
                os.remove(reclamado)
                logger.info(f"CV {nombre_archivo} movido de {CandidatoService.CARPETA_CV_DUPLICADOS} a {destino}")
                return
            # Todas las copias coincidentes fueron reclamadas por otra confirmacion concurrente: ya se esta moviendo, no se crea otra copia.
            logger.info(f"CV {nombre_archivo}: otra confirmacion ya esta moviendo la copia de duplicados")
        except Exception as e_arch:
            logger.error(f"No se pudo mover el CV {nombre_archivo} a {CandidatoService.CARPETA_CV_OK}: {e_arch}")

    # Tiempo maximo para procesar un CV de una carga masiva (extraccion, OCR, parseo y guardado) antes de omitirlo
    TIEMPO_MAXIMO_ARCHIVO_SEGUNDOS = 180

    @staticmethod
    async def _ejecutar_con_limite_de_tiempo(funcion, segundos: float, **kwargs):
        """
        Ejecuta `funcion(**kwargs)` en un hilo daemon propio y espera como mucho `segundos` (asyncio.TimeoutError si se pasa).
        No usa el executor por defecto: asyncio.run() esperaria a un hilo trabado al cerrar y el lote nunca terminaria.
        """
        import concurrent.futures
        import threading

        futuro: concurrent.futures.Future = concurrent.futures.Future()

        def _correr() -> None:
            try:
                resultado = funcion(**kwargs)
            except BaseException as e_hilo:  # se reenvia a quien espera (HTTPException, errores de persistencia, etc.)
                if not futuro.cancelled():  # si ya vencio el limite nadie espera: el futuro esta cancelado
                    futuro.set_exception(e_hilo)
                return
            if not futuro.cancelled():
                futuro.set_result(resultado)

        threading.Thread(target=_correr, daemon=True).start()
        return await asyncio.wait_for(asyncio.wrap_future(futuro), timeout=segundos)

    @staticmethod
    async def procesar_carga_masiva_zip_rar(
        db: Session,
        empresa_id: uuid.UUID,
        archivo: Optional[UploadFile] = None,
        usuario: Optional[str] = None,
        current_user: Optional[Usuario] = None,
        archivos: Optional[List[UploadFile]] = None,
        progreso: Optional[Any] = None,
        cancelado: Optional[Any] = None,
        operacion_id: Optional[uuid.UUID] = None,
        resultados_parciales: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Carga masiva con auditoria (recruiting_historial_cargas_cv y _archivos): delega sin alterarla en
        `_procesar_carga_masiva_sin_auditoria` y registra UN solo registro por operacion, con el resultado de cada archivo,
        en una transaccion propia (tambien si la operacion falla antes de procesar).
        """
        from backend.modules.recruiting.historial_cargas_services import HistorialCargaCVService

        recibidos = [
            os.path.basename(a.filename)
            for a in (archivos or ([archivo] if archivo is not None else []))
            if a is not None and getattr(a, "filename", None)
        ]
        nombre_lote = ", ".join(recibidos)[:255] or None
        usuario_id = getattr(current_user, "id", None)
        usuario_nombre = HistorialCargaCVService.nombre_usuario(current_user)
        try:
            resultado = await CandidatoService._procesar_carga_masiva_sin_auditoria(
                db=db,
                empresa_id=empresa_id,
                archivo=archivo,
                usuario=usuario,
                current_user=current_user,
                archivos=archivos,
                progreso=progreso,
                cancelado=cancelado,
                resultados_parciales=resultados_parciales,
            )
        except Exception as e_lote:
            motivo = str(e_lote.detail) if isinstance(e_lote, HTTPException) else MENSAJE_ERROR_INTERNO
            await asyncio.to_thread(
                HistorialCargaCVService.registrar,
                empresa_id,
                usuario_id,
                usuario_nombre,
                "masiva",
                nombre_lote,
                [{"nombre": n, "resultado": "rechazado", "motivo": motivo} for n in (recibidos or ["(sin archivo)"])],
                False,
                operacion_id,
            )
            raise
        await asyncio.to_thread(
            HistorialCargaCVService.registrar,
            empresa_id,
            usuario_id,
            usuario_nombre,
            "masiva",
            nombre_lote,
            [
                {
                    "nombre": r["archivo"],
                    "resultado": r["resultado"],
                    "motivo": None if r["resultado"] == "creado" else r["mensaje"],
                }
                for r in resultado["resultados"]
            ],
            bool(resultado.get("cancelado")),
            operacion_id,
        )
        return resultado

    @staticmethod
    async def _procesar_carga_masiva_sin_auditoria(
        db: Session,
        empresa_id: uuid.UUID,
        archivo: Optional[UploadFile] = None,
        usuario: Optional[str] = None,
        current_user: Optional[Usuario] = None,
        archivos: Optional[List[UploadFile]] = None,
        progreso: Optional[Any] = None,
        cancelado: Optional[Any] = None,
        resultados_parciales: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Procesa una carga masiva compuesta por archivos comprimidos (.zip/.rar) y/o CVs individuales (.pdf/.docx/.doc).
        - Hasta 100 CVs individuales por operación (los CVs dentro de un comprimido no cuentan para el límite).
        - Descomprime sin basura de SO (__MACOSX, archivos ocultos).
        - Procesa uno a uno reutilizando procesar_cv_bytes con aislamiento de errores (un fallo no corta el lote).
        - Un email que ya existe omite el CV: la ficha existente no se modifica (ni su CV, archivos o auditoría).
        - Acumula en memoria un resultado por archivo (propio de esta ejecución, no se comparte entre lotes) y devuelve
          `resultados` (detalle por archivo) y `resumen` (conteos por categoría). Nada se guarda en tablas.
        """
        import io
        import logging
        import os

        logger = logging.getLogger(__name__)

        lista_archivos = [
            a for a in (archivos or ([archivo] if archivo is not None else [])) if a is not None and a.filename
        ]
        if not lista_archivos:
            raise HTTPException(status_code=400, detail="No se seleccionó ningún archivo.")

        extensiones_comprimidos = {".zip", ".rar"}
        extensiones_cv = {".pdf", ".docx", ".doc"}

        individuales_cant = sum(1 for a in lista_archivos if os.path.splitext(a.filename.lower())[1] in extensiones_cv)
        if individuales_cant > CandidatoService.MAX_CVS_INDIVIDUALES_CARGA_MASIVA:
            raise HTTPException(
                status_code=400,
                detail=f"Se superó el límite de {CandidatoService.MAX_CVS_INDIVIDUALES_CARGA_MASIVA} CVs individuales por operación ({individuales_cant} seleccionados).",
            )

        lote_id = str(uuid.uuid4())
        # resultado final de cada archivo de ESTE lote (si quien llama pasa su lista, ve el avance archivo por archivo)
        resultados: List[Dict[str, Any]] = resultados_parciales if resultados_parciales is not None else []
        candidatos_creados: List[Candidato] = []

        def _registrar(
            nombre: str,
            resultado: str,
            mensaje: str,
            candidato: Optional[Candidato] = None,
            email: Optional[str] = None,
        ) -> None:
            resultados.append(
                {
                    "archivo": nombre,
                    "resultado": resultado,
                    "mensaje": mensaje,
                    "email": email or (candidato.email if candidato is not None else None),
                    "candidato_id": str(candidato.id) if candidato is not None else None,
                }
            )

        def _es_ignorable(nom_base: str, nom: str) -> bool:
            return (
                not nom_base
                or nom_base.startswith(".")
                or "__macosx" in nom.lower()
                or nom_base.lower() in {"thumbs.db", "desktop.ini"}
            )

        archivos_a_procesar: List[Tuple[str, bytes]] = []  # (nombre_archivo, bytes_contenido)
        nombres_vistos = (
            set()
        )  # nombres (sin distinguir mayusculas) ya recibidos en ESTA operacion, incluidos los de los comprimidos

        def _archivar_repetido(nombre: str, contenido_rep: bytes) -> None:
            """Segundo archivo (o posterior) con un nombre ya recibido en la misma carga: duplicado por nombre, sin procesar ni comparar contenido."""
            _registrar(
                nombre,
                "duplicado",
                "Archivo con nombre repetido en la misma carga; se archivó en cv_duplicados sin procesarlo.",
            )
            CandidatoService._archivar_cv_masivo(nombre, contenido_rep, "duplicado")

        def _clasificar_entrada(nom: str, leer) -> None:
            nom_base = os.path.basename(nom)
            if _es_ignorable(nom_base, nom):
                return
            _, ext_f = os.path.splitext(nom_base.lower())
            if ext_f not in extensiones_cv:
                _registrar(
                    nom_base,
                    "formato_tamano",
                    f"Formato no admitido '{ext_f or 'sin extensión'}'. Solo se admiten archivos PDF, DOC y DOCX.",
                )
                return
            try:
                clave_entrada = nom_base.lower()
                if clave_entrada in nombres_vistos:
                    _archivar_repetido(nom_base, leer())
                    return
                nombres_vistos.add(clave_entrada)
                archivos_a_procesar.append((nom_base, leer()))
            except Exception as e_leer:
                logger.warning(f"Error al leer entrada comprimida {nom}: {e_leer}")
                _registrar(nom_base, "error_lectura", f"No se pudo leer el archivo dentro del comprimido: {e_leer}")

        def _extraer_comprimido(ext_comprimido: str, contenido_comprimido: bytes) -> None:
            if ext_comprimido == ".zip":
                try:
                    with zipfile.ZipFile(io.BytesIO(contenido_comprimido)) as zf:
                        for info in zf.infolist():
                            if info.is_dir():
                                continue
                            _clasificar_entrada(info.filename, lambda info=info: zf.read(info))
                except zipfile.BadZipFile:
                    raise HTTPException(status_code=400, detail="El archivo ZIP está dañado o no es un formato válido.")
                except Exception as e_zip:
                    raise HTTPException(status_code=400, detail=f"Error al abrir archivo ZIP: {str(e_zip)}")
                return
            # Soporte para RAR mediante rarfile con backend de sistema unrar/unrar-free/bsdtar
            try:
                import shutil

                import rarfile

                herramienta = shutil.which("unrar") or shutil.which("unrar-free") or shutil.which("bsdtar")
                if herramienta:
                    rarfile.UNRAR_TOOL = herramienta

                with rarfile.RarFile(io.BytesIO(contenido_comprimido)) as rf:
                    for info in rf.infolist():
                        if info.isdir():
                            continue
                        _clasificar_entrada(info.filename, lambda info=info: rf.read(info))
            except ImportError:
                raise HTTPException(
                    status_code=400,
                    detail="El servidor no cuenta con la librería rarfile instalada. Por favor, suba los CVs en formato .ZIP.",
                )
            except rarfile.RarCannotExec as e_exec:
                logger.error(f"Herramienta unrar no encontrada en el sistema: {e_exec}")
                raise HTTPException(
                    status_code=400,
                    detail="No se encontró la herramienta 'unrar' en el servidor para descomprimir archivos .RAR. Por favor, use .ZIP.",
                )
            except Exception as e_rar:
                raise HTTPException(status_code=400, detail=f"Error al descomprimir archivo RAR: {str(e_rar)}")

        es_unico = len(lista_archivos) == 1
        for arch in lista_archivos:
            nombre_original = os.path.basename(arch.filename)
            _, ext_arch = os.path.splitext(nombre_original.lower())

            if ext_arch not in extensiones_comprimidos and ext_arch not in extensiones_cv:
                if es_unico:
                    raise HTTPException(
                        status_code=400,
                        detail="Formato de archivo no válido. Solo se admiten archivos .pdf, .doc, .docx, .zip y .rar.",
                    )
                _registrar(
                    nombre_original,
                    "formato_tamano",
                    f"Formato no admitido '{ext_arch or 'sin extensión'}'. Solo se admiten PDF, DOC, DOCX, ZIP y RAR.",
                )
                continue

            clave_nombre = nombre_original.lower()
            if clave_nombre in nombres_vistos:
                if ext_arch in extensiones_cv:
                    # CV con nombre ya recibido en esta carga: duplicado por nombre, se archiva sin procesar
                    try:
                        _archivar_repetido(nombre_original, await arch.read())
                    except Exception as e_read:
                        _registrar(nombre_original, "error_lectura", f"No se pudo leer el archivo: {e_read}")
                else:
                    _registrar(
                        nombre_original, "duplicado", "Archivo repetido dentro de la misma selección; se omitió."
                    )
                continue
            nombres_vistos.add(clave_nombre)

            try:
                contenido_arch = await arch.read()
            except Exception as e_read:
                if es_unico:
                    raise HTTPException(status_code=400, detail=f"Error al leer el archivo: {str(e_read)}")
                _registrar(nombre_original, "error_lectura", f"No se pudo leer el archivo: {e_read}")
                continue

            if not contenido_arch:
                if es_unico:
                    raise HTTPException(status_code=400, detail="El archivo está vacío.")
                _registrar(nombre_original, "error_lectura", "El archivo está vacío.")
                continue

            if ext_arch in extensiones_cv:
                archivos_a_procesar.append((nombre_original, contenido_arch))
                continue

            try:
                _extraer_comprimido(ext_arch, contenido_arch)
            except HTTPException as e_comp:
                if es_unico:
                    raise
                _registrar(nombre_original, "error_lectura", str(e_comp.detail))

        # Avance real: archivos ya resueltos (rechazados al clasificar) + los que se van a procesar
        total_avance = len(resultados) + len(archivos_a_procesar)
        if progreso:
            progreso(len(resultados), total_avance)
        fue_cancelado = False
        for nombre_item, bytes_item in archivos_a_procesar:
            if cancelado and cancelado():
                fue_cancelado = True
                break
            # Cada archivo se procesa aislado: si uno falla no invalida la sesión ni los demás.
            try:
                candidato = await CandidatoService._ejecutar_con_limite_de_tiempo(
                    CandidatoService.procesar_cv_bytes,
                    CandidatoService.TIEMPO_MAXIMO_ARCHIVO_SEGUNDOS,
                    db=db,
                    empresa_id=empresa_id,
                    contenido=bytes_item,
                    nombre_archivo=nombre_item,
                    usuario=usuario,
                    current_user=current_user,
                )
                _registrar(nombre_item, "creado", "Candidato creado correctamente.", candidato)
                candidatos_creados.append(candidato)
            except asyncio.TimeoutError:
                # El hilo del archivo trabado no se puede matar: se lo abandona (sigue con SU sesion) y el lote continua con una sesion nueva
                logger.error(
                    f"CV masivo {nombre_item}: se supero el tiempo maximo de procesamiento ({CandidatoService.TIEMPO_MAXIMO_ARCHIVO_SEGUNDOS}s); se omite y el lote continua"
                )
                if getattr(db, "bind", None) is engine:
                    db = SessionLocal()
                _registrar(
                    nombre_item,
                    "error_otro",
                    "Se superó el tiempo máximo de procesamiento del archivo; se omitió y la carga continuó.",
                )
            except CVEmailDuplicadoError as e_dup:
                # No se escribió nada: la ficha existente queda intacta.
                logger.info(f"CV masivo {nombre_item} omitido: el email {e_dup.email} ya existe")
                _registrar(
                    nombre_item,
                    "duplicado",
                    f"Ya existe un candidato con el email {e_dup.email}; no se modificó la ficha existente.",
                    email=e_dup.email,
                )
            except CVSinEmailError as e_sin:
                logger.warning(f"CV masivo {nombre_item} rechazado: {e_sin.detail}")
                _registrar(nombre_item, "sin_email", str(e_sin.detail))
            except CVPersistenciaError as e_pers:
                logger.error(f"Error de persistencia en CV masivo {nombre_item}: {e_pers.causa}", exc_info=e_pers.causa)
                db.rollback()
                # Antes de contabilizar, se comprueba qué quedó realmente guardado (el email no existía antes del intento).
                persistido = None
                try:
                    persistido = (
                        db.query(Candidato)
                        .filter(
                            Candidato.empresa_id == empresa_id,
                            func.lower(func.trim(Candidato.email)) == e_pers.email,
                        )
                        .first()
                    )
                except Exception:
                    db.rollback()
                if persistido is not None:
                    _registrar(
                        nombre_item,
                        "creado",
                        "Candidato creado correctamente (guardado confirmado tras un error posterior).",
                        persistido,
                    )
                    candidatos_creados.append(persistido)
                else:
                    _registrar(
                        nombre_item,
                        "error_persistencia",
                        "No se pudo guardar el candidato. Intentá nuevamente.",
                        email=e_pers.email,
                    )
            except HTTPException as e_rechazo:
                logger.warning(f"CV masivo {nombre_item} rechazado: {e_rechazo.detail}")
                db.rollback()
                categoria = "formato_tamano" if e_rechazo.status_code == 400 else "error_validacion"
                _registrar(nombre_item, categoria, str(e_rechazo.detail))
            except Exception as e_proc:
                logger.error(f"Error al procesar CV masivo {nombre_item}: {e_proc}", exc_info=True)
                db.rollback()
                _registrar(nombre_item, "error_otro", MENSAJE_ERROR_INTERNO)
            # Clasificacion por resultado final del archivo (no altera el resultado ni el reporte)
            if resultados:
                CandidatoService._archivar_cv_masivo(
                    nombre_item, bytes_item, resultados[-1]["resultado"], resultados[-1]["mensaje"]
                )
            if progreso:
                progreso(len(resultados), total_avance)

        resumen = CandidatoService.construir_resumen_carga_masiva(resultados, lote_id)
        no_exitosos = [
            {"archivo": r["archivo"], "motivo": r["mensaje"]}
            for r in resultados
            if r["resultado"] not in ("creado", "duplicado")
        ]
        return {
            "lote_id": lote_id,
            "resumen": resumen,
            "resultados": resultados,
            # Campos históricos (compatibilidad): "procesados_exitosamente" son los candidatos efectivamente creados.
            "total_archivos_encontrados": resumen["total_archivos"],
            "procesados_exitosamente": resumen["creados"],
            "fallidos": no_exitosos,
            "candidatos_creados": candidatos_creados,
            "cancelado": fue_cancelado,
            "total_avance": total_avance,
        }

    # ------------------------------------------------------------------
    # Carga masiva con avance real: el lote corre en segundo plano y su estado se publica en un archivo JSON
    # dentro del temporal del sistema (dicsys_lotes_cv; compartido entre los workers del backend; sin cambios de esquema).
    # ------------------------------------------------------------------
    ESTADOS_LOTE_FINALES = ("finalizado", "cancelado", "error")

    @staticmethod
    def _ruta_lote(lote_id: str, sufijo: str = ".json") -> str:
        import os

        try:
            lote_id = str(uuid.UUID(str(lote_id)))
        except ValueError:
            raise HTTPException(status_code=404, detail="Carga no encontrada.")
        return os.path.join(tempfile.gettempdir(), "dicsys_lotes_cv", f"{lote_id}{sufijo}")

    @staticmethod
    def _guardar_estado_lote(lote_id: str, estado: Dict[str, Any]) -> None:
        import json
        import os
        import time

        ruta = CandidatoService._ruta_lote(lote_id)
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        estado["actualizado"] = (
            time.time()
        )  # latido: permite detectar un lote cuyo proceso murio (ver obtener_estado_carga_masiva)
        tmp = f"{ruta}.{uuid.uuid4().hex}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(estado, f)
        # En Windows el reemplazo puede fallar un instante si alguien esta leyendo el archivo: se reintenta
        for intento in range(20):
            try:
                os.replace(tmp, ruta)
                return
            except PermissionError:
                if intento == 19:
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
                    raise
                time.sleep(0.05)

    @staticmethod
    def _estado_lote_autorizado(lote_id: str, empresa_id: uuid.UUID, current_user: Usuario) -> Dict[str, Any]:
        import json

        try:
            with open(CandidatoService._ruta_lote(lote_id), "r", encoding="utf-8") as f:
                estado = json.load(f)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Carga no encontrada.")
        if estado.get("empresa_id") != str(empresa_id) or estado.get("usuario_id") != str(current_user.id):
            raise HTTPException(status_code=404, detail="Carga no encontrada.")
        return estado

    @staticmethod
    async def iniciar_carga_masiva_en_segundo_plano(
        empresa_id: uuid.UUID,
        archivos: List[UploadFile],
        usuario: Optional[str],
        current_user: Usuario,
    ) -> Dict[str, Any]:
        """Lee los archivos subidos, registra el lote (estado 'preparando') y lo procesa en un hilo propio con su sesion de BD."""
        import os
        import threading

        lista = [a for a in (archivos or []) if a is not None and a.filename]
        if not lista:
            raise HTTPException(status_code=400, detail="No se seleccionó ningún archivo.")
        individuales = sum(1 for a in lista if os.path.splitext(a.filename.lower())[1] in (".pdf", ".docx", ".doc"))
        if individuales > CandidatoService.MAX_CVS_INDIVIDUALES_CARGA_MASIVA:
            raise HTTPException(
                status_code=400,
                detail=f"Se superó el límite de {CandidatoService.MAX_CVS_INDIVIDUALES_CARGA_MASIVA} CVs individuales por operación ({individuales} seleccionados).",
            )
        from backend.modules.recruiting.historial_cargas_services import HistorialCargaCVService

        en_memoria = [_ArchivoEnMemoria(a.filename, await a.read()) for a in lista]
        lote_id = str(uuid.uuid4())
        usuario_id = current_user.id
        estado = {
            "lote_id": lote_id,
            "empresa_id": str(empresa_id),
            "usuario_id": str(usuario_id),
            "usuario_nombre": HistorialCargaCVService.nombre_usuario(current_user),
            "estado": "preparando",
            "procesados": 0,
            "total": 0,
            "reporte": None,
            "error": None,
        }
        CandidatoService._guardar_estado_lote(lote_id, estado)
        threading.Thread(
            target=CandidatoService._ejecutar_lote_segundo_plano,
            args=(lote_id, empresa_id, usuario_id, en_memoria, usuario, estado),
            daemon=True,
        ).start()
        return {"lote_id": lote_id, "estado": "preparando", "procesados": 0, "total": 0}

    @staticmethod
    def _ejecutar_lote_segundo_plano(lote_id, empresa_id, usuario_id, en_memoria, usuario, estado) -> None:
        import asyncio
        import os
        import threading

        logger = logging.getLogger(__name__)
        ruta_cancel = CandidatoService._ruta_lote(lote_id, ".cancel")

        parciales: List[
            Dict[str, Any]
        ] = []  # resultado por archivo hasta el momento (se publica para poder auditar un lote interrumpido)

        def _progreso(procesados: int, total: int) -> None:
            estado.update(
                {
                    "estado": "procesando",
                    "procesados": procesados,
                    "total": total,
                    "resultados_parciales": [
                        {"archivo": r["archivo"], "resultado": r["resultado"], "mensaje": r["mensaje"]}
                        for r in parciales
                    ],
                }
            )
            try:
                CandidatoService._guardar_estado_lote(lote_id, estado)
            except Exception as e_prog:
                # Publicar el avance nunca debe interrumpir el procesamiento de los CVs
                logger.warning(f"No se pudo publicar el avance del lote {lote_id}: {e_prog}")

        # Latido mientras el lote vive (aunque un CV tarde): si el proceso muere deja de actualizarse y el estado se declara interrumpido
        parar_latido = threading.Event()

        def _latido() -> None:
            while not parar_latido.wait(CandidatoService.LATIDO_LOTE_SEGUNDOS):
                try:
                    CandidatoService._guardar_estado_lote(lote_id, estado)
                except Exception as e_lat:
                    logger.warning(f"No se pudo publicar el latido del lote {lote_id}: {e_lat}")

        threading.Thread(target=_latido, daemon=True).start()
        db = SessionLocal()
        try:
            user = db.get(Usuario, usuario_id)
            resultado = asyncio.run(
                CandidatoService.procesar_carga_masiva_zip_rar(
                    db=db,
                    empresa_id=empresa_id,
                    archivos=en_memoria,
                    usuario=usuario,
                    current_user=user,
                    progreso=_progreso,
                    cancelado=lambda: os.path.exists(ruta_cancel),
                    operacion_id=uuid.UUID(lote_id),
                    resultados_parciales=parciales,
                )
            )
            cancelado = bool(resultado.get("cancelado"))
            estado.update(
                {
                    "estado": "cancelado" if cancelado else "finalizado",
                    "procesados": len(resultado["resultados"]),
                    "total": resultado["total_avance"],
                    "reporte": {
                        "ok": True,
                        "lote_id": lote_id,
                        "resumen": resultado["resumen"],
                        "resultados": resultado["resultados"],
                    },
                }
            )
        except HTTPException as e_http:
            estado.update({"estado": "error", "error": str(e_http.detail)})
        except Exception as e_lote:
            logger.error(f"Error no controlado en carga masiva en segundo plano: {e_lote}", exc_info=True)
            estado.update({"estado": "error", "error": MENSAJE_ERROR_INTERNO})
        finally:
            parar_latido.set()
            db.close()
            estado.pop("resultados_parciales", None)
            try:
                CandidatoService._guardar_estado_lote(lote_id, estado)
                if os.path.exists(ruta_cancel):
                    os.remove(ruta_cancel)
            except Exception as e_fin:
                logger.error(f"No se pudo publicar el estado final del lote {lote_id}: {e_fin}")

    # Latido del lote y tiempo sin latido tras el cual se lo considera interrumpido (proceso reiniciado o muerto)
    LATIDO_LOTE_SEGUNDOS = 5
    CADUCIDAD_LOTE_SEGUNDOS = 60
    MENSAJE_LOTE_INTERRUMPIDO = (
        "La carga se interrumpió antes de terminar (el servidor se reinició o el proceso dejó de responder). "
        "Los CV ya procesados se conservaron. Volvé a cargar el lote: los candidatos ya creados se omiten como duplicados."
    )

    @staticmethod
    def _declarar_lote_interrumpido(lote_id: str, estado: Dict[str, Any]) -> Dict[str, Any]:
        """Marca el lote como error, lo audita con lo procesado hasta el corte y publica el estado final (sin dejar la pantalla cargando)."""
        from backend.modules.recruiting.historial_cargas_services import HistorialCargaCVService

        parciales = estado.get("resultados_parciales") or []
        archivos = [
            {
                "nombre": r["archivo"],
                "resultado": r["resultado"],
                "motivo": None if r["resultado"] == "creado" else r["mensaje"],
            }
            for r in parciales
        ]
        pendientes = max(0, int(estado.get("total") or 0) - len(parciales))
        if pendientes or not archivos:
            archivos.append(
                {
                    "nombre": "(archivos sin procesar)",
                    "resultado": "rechazado",
                    "motivo": f"Carga interrumpida: {pendientes} archivo(s) quedaron sin procesar.",
                }
            )
        try:
            HistorialCargaCVService.registrar(
                uuid.UUID(estado["empresa_id"]),
                uuid.UUID(estado["usuario_id"]),
                estado.get("usuario_nombre") or "Sin identificar",
                "masiva",
                None,
                archivos,
                False,
                uuid.UUID(lote_id),
            )
        except Exception as e_aud:
            logging.getLogger(__name__).error(f"No se pudo auditar el lote interrumpido {lote_id}: {e_aud}")
        estado.update({"estado": "error", "error": CandidatoService.MENSAJE_LOTE_INTERRUMPIDO})
        estado.pop("resultados_parciales", None)
        try:
            CandidatoService._guardar_estado_lote(lote_id, estado)
        except Exception as e_est:
            logging.getLogger(__name__).error(f"No se pudo publicar el estado del lote interrumpido {lote_id}: {e_est}")
        return estado

    @staticmethod
    def obtener_estado_carga_masiva(lote_id: str, empresa_id: uuid.UUID, current_user: Usuario) -> Dict[str, Any]:
        import os
        import time

        estado = CandidatoService._estado_lote_autorizado(lote_id, empresa_id, current_user)
        if estado.get("estado") not in CandidatoService.ESTADOS_LOTE_FINALES:
            try:
                ultimo = estado.get("actualizado") or os.path.getmtime(CandidatoService._ruta_lote(lote_id))
            except OSError:
                ultimo = time.time()
            if time.time() - ultimo > CandidatoService.CADUCIDAD_LOTE_SEGUNDOS:
                estado = CandidatoService._declarar_lote_interrumpido(lote_id, estado)
        return {k: estado.get(k) for k in ("lote_id", "estado", "procesados", "total", "reporte", "error")}

    @staticmethod
    def cancelar_carga_masiva(lote_id: str, empresa_id: uuid.UUID, current_user: Usuario) -> Dict[str, Any]:
        """Solicita detener el lote: se frena antes del proximo CV (los ya procesados quedan guardados)."""
        import os

        estado = CandidatoService._estado_lote_autorizado(lote_id, empresa_id, current_user)
        if estado["estado"] not in CandidatoService.ESTADOS_LOTE_FINALES:
            ruta = CandidatoService._ruta_lote(lote_id, ".cancel")
            os.makedirs(os.path.dirname(ruta), exist_ok=True)
            open(ruta, "a").close()
        return {k: estado.get(k) for k in ("lote_id", "estado", "procesados", "total")}


class _ArchivoEnMemoria:
    """Archivo ya leido, con la interfaz minima de UploadFile (filename, read) para procesar el lote fuera del request."""

    def __init__(self, filename: str, contenido: bytes):
        self.filename = filename
        self._contenido = contenido

    async def read(self) -> bytes:
        return self._contenido


# ---------------------------------------------------------------------------
# Búsquedas (oportunidades): permisos de asignación
# ---------------------------------------------------------------------------

# Roles que pueden asignar o reasignar el reclutador responsable de una búsqueda
ROLES_ASIGNAN_RECLUTADOR = (ROL_ADMIN, ROL_RECRUITER)


def usuario_puede_administrar_externos(
    db: Session, user: Optional[Usuario], empresa_id: Optional[uuid.UUID] = None
) -> bool:
    """True si el usuario es admin o de un grupo de Recruiting: puede asignar y quitar usuarios externos de una
    búsqueda."""
    if not user:
        return False
    if getattr(user, "rol", "") == "admin":
        return True
    return incluye_grupo_recruiting(_nombres_de_grupos(db, user, empresa_id))


def usuario_puede_asignar_reclutador(
    db: Session, user: Optional[Usuario], empresa_id: Optional[uuid.UUID] = None
) -> bool:
    """True si el usuario puede asignar o reasignar el reclutador de una búsqueda; el grupo EXTERNOS nunca."""
    if not user:
        return False
    if getattr(user, "rol", "") == "admin":
        return True
    if usuario_es_grupo_externos(db, user, empresa_id):
        return False
    return obtener_rol_recruiting(db, user, empresa_id) in ROLES_ASIGNAN_RECLUTADOR


def _nombre_completo(usuario: Usuario) -> str:
    return f"{usuario.nombre} {usuario.apellido}".strip() if usuario.apellido else usuario.nombre


class OportunidadService:
    """Búsquedas de Recruiting (recruiting_oportunidades): listado, alta, edición, asignaciones y catálogos de los
    combos del formulario. Origen: SolicitudService del módulo original."""

    ESTADOS_VALIDOS = ("Abierta", "Pre-ingreso", "Suspendida", "Ganada", "Cancelada")
    ESTADO_GANADA = "Ganada"
    ESTADO_CANCELADA = "Cancelada"
    MENSAJE_BUSQUEDA_GANADA = "La búsqueda está Ganada y cerrada: no admite cambios en su proceso de selección."

    # ---- reglas de acceso -------------------------------------------------

    @staticmethod
    def permisos(db: Session, empresa_id: uuid.UUID, current_user: Usuario) -> Dict[str, bool]:
        """Acciones habilitadas en Búsquedas: el grupo EXTERNOS ni crea ni cancela búsquedas, ni asigna candidatos, ni
        ve el líder, el tipo o Smart Matching."""
        no_externo = not usuario_es_grupo_externos(db, current_user, empresa_id)
        return {
            "puede_crear_busquedas": no_externo,
            "puede_eliminar_busquedas": no_externo,
            "puede_ver_lider_tipo_fecha_busqueda": no_externo,
            "puede_ver_smart_matching": no_externo,
            "puede_asignar_candidatos": no_externo,
            "puede_asignar_reclutador": usuario_puede_asignar_reclutador(db, current_user, empresa_id),
            "puede_administrar_externos": usuario_puede_administrar_externos(db, current_user, empresa_id),
            "es_externo": not no_externo,
        }

    @staticmethod
    def exigir_no_externo(db: Session, empresa_id: uuid.UUID, current_user: Usuario, detalle: str) -> None:
        if usuario_es_grupo_externos(db, current_user, empresa_id):
            raise HTTPException(status_code=403, detail=detalle)

    @staticmethod
    def es_ganada(solicitud: Solicitud) -> bool:
        return (solicitud.estado or "").strip().casefold() == OportunidadService.ESTADO_GANADA.casefold()

    @staticmethod
    def validar_no_ganada(solicitud: Solicitud) -> None:
        """Una búsqueda Ganada está cerrada: solo se consulta (409)."""
        if OportunidadService.es_ganada(solicitud):
            raise HTTPException(status_code=409, detail=OportunidadService.MENSAJE_BUSQUEDA_GANADA)

    @staticmethod
    def marcar_ganada(solicitud: Solicitud, usuario: Optional[str] = None) -> None:
        """Cierre automático al llegar un candidato a Ingreso (una sola vacante); el commit lo hace quien llama."""
        solicitud.estado = OportunidadService.ESTADO_GANADA
        solicitud.updated_at = utc_now()
        solicitud.updated_by = usuario

    # ---- consulta ----------------------------------------------------------

    @staticmethod
    def consulta(
        db: Session,
        empresa_id: uuid.UUID,
        busqueda: Optional[str] = None,
        estado: Optional[str] = None,
        cliente: Optional[str] = None,
        tipo: Optional[str] = None,
        current_user: Optional[Usuario] = None,
    ):
        """Búsquedas de la empresa activa que el usuario puede ver (el grupo EXTERNOS, solo las que tiene asignadas),
        con filtros opcionales; el router la pagina con paginar(). Más recientes primero."""
        query = (
            db.query(Solicitud)
            .options(joinedload(Solicitud.externo_rel))
            .filter(Solicitud.empresa_id == empresa_id, Solicitud.deleted_at.is_(None), Solicitud.activo.is_(True))
        )
        alcance = AlcanceRecruiting.de(db, current_user, empresa_id)
        for condicion in alcance.filtro_busquedas():
            query = query.filter(condicion)

        estado_limpio = (estado or "").strip()
        if estado_limpio and estado_limpio.casefold() != "todos":
            query = query.filter(Solicitud.estado == estado_limpio)

        cliente_limpio = (cliente or "").strip()
        if cliente_limpio:
            query = query.filter(Solicitud.cliente == cliente_limpio)

        tipo_limpio = (tipo or "").strip().casefold()
        if tipo_limpio and tipo_limpio not in ("todas", "todos"):
            query = query.filter(func.lower(Solicitud.tipo) == tipo_limpio)

        termino = (busqueda or "").strip()
        if termino:
            patron = f"%{termino}%"
            condiciones = [
                Solicitud.id_busqueda.ilike(patron),
                Solicitud.titulo.ilike(patron),
                Solicitud.cliente.ilike(patron),
                Solicitud.recruiter_nombre.ilike(patron),
            ]
            if not alcance.es_externo:
                condiciones.append(Solicitud.lider_nombre.ilike(patron))
            query = query.filter(or_(*condiciones))

        return query.order_by(Solicitud.created_at.desc())

    @staticmethod
    def get_by_id(
        db: Session, empresa_id: uuid.UUID, id: uuid.UUID, current_user: Optional[Usuario] = None
    ) -> Solicitud:
        """Una búsqueda de la empresa activa (404 si no existe o es de otra empresa). El grupo EXTERNOS solo accede a
        las que tiene asignadas (403). `q_activos` sale de los candidatos vigentes del pipeline."""
        solicitud = (
            db.query(Solicitud)
            .options(joinedload(Solicitud.externo_rel))
            .filter(Solicitud.id == id, Solicitud.empresa_id == empresa_id, Solicitud.deleted_at.is_(None))
            .first()
        )
        if not solicitud:
            raise HTTPException(status_code=404, detail="La búsqueda no existe.")
        if current_user and usuario_es_grupo_externos(db, current_user, empresa_id):
            if solicitud.externo_id != current_user.id:
                raise HTTPException(status_code=403, detail="No tenés acceso a esta búsqueda: no la tenés asignada.")
        # Valor de la respuesta: no se marca como cambio para que un commit posterior no lo guarde
        q_activos = (
            db.query(func.count(GestionBusqueda.id))
            .filter(
                GestionBusqueda.empresa_id == empresa_id,
                GestionBusqueda.oportunidad_id == solicitud.id,
                GestionBusqueda.activo.is_(True),
                GestionBusqueda.deleted_at.is_(None),
                or_(GestionBusqueda.estado != "Descartado", GestionBusqueda.estado.is_(None)),
            )
            .scalar()
            or 0
        )
        set_committed_value(solicitud, "q_activos", q_activos)
        return solicitud

    # ---- alta y edición ----------------------------------------------------

    @staticmethod
    def _validar_puesto(db: Session, puesto: Optional[str], actual: Optional[str] = None) -> Optional[str]:
        """El puesto de una búsqueda es un perfil activo del catálogo (se guarda su nombre canónico). Vacío = sin
        puesto. Si coincide con el valor ya guardado se conserva, para que editar otros datos no rechace un perfil
        histórico (desactivado o ya inexistente)."""
        limpio = " ".join((puesto or "").split())
        if not limpio:
            return None
        if actual and limpio.casefold() == " ".join(actual.split()).casefold():
            return actual
        perfil = (
            db.query(RecruitingPerfilPuesto)
            .filter(
                RecruitingPerfilPuesto.activo.is_(True), func.lower(RecruitingPerfilPuesto.nombre) == limpio.lower()
            )
            .first()
        )
        if not perfil:
            raise HTTPException(
                status_code=400, detail=f"El perfil / puesto «{limpio}» no corresponde a un perfil profesional activo."
            )
        return perfil.nombre

    @staticmethod
    def _validar_estado(estado: str) -> None:
        if estado not in OportunidadService.ESTADOS_VALIDOS:
            raise HTTPException(
                status_code=400,
                detail=f"Estado «{estado}» no válido. Opciones: {', '.join(OportunidadService.ESTADOS_VALIDOS)}.",
            )

    @staticmethod
    def create(
        db: Session,
        empresa_id: uuid.UUID,
        datos: OportunidadCreate,
        usuario: Optional[str] = None,
        current_user: Optional[Usuario] = None,
    ) -> Solicitud:
        """Crea una búsqueda. Quien la crea queda como creador y, según su rol, como líder o reclutador."""
        OportunidadService.exigir_no_externo(
            db, empresa_id, current_user, "Los usuarios del grupo EXTERNOS no pueden crear búsquedas"
        )
        OportunidadService._validar_estado(datos.estado)

        cliente = datos.cliente.strip()
        titulo = datos.titulo.strip()
        existente = (
            db.query(Solicitud.id)
            .filter(
                Solicitud.empresa_id == empresa_id,
                Solicitud.deleted_at.is_(None),
                func.lower(func.trim(Solicitud.cliente)) == cliente.lower(),
                func.lower(func.trim(Solicitud.titulo)) == titulo.lower(),
            )
            .first()
        )
        if existente:
            raise HTTPException(
                status_code=400, detail="Ya existe una búsqueda con este título para el cliente seleccionado"
            )

        rol = obtener_rol_recruiting(db, current_user, empresa_id) if current_user else ROL_RECRUITER
        creador_id = current_user.id if current_user else None
        lider_id = recruiter_id = None
        lider_nombre = (datos.lider_nombre or "").strip() or None
        recruiter_nombre = (datos.recruiter_nombre or "").strip() or None
        if current_user and rol == ROL_LIDER:
            lider_id = creador_id
            lider_nombre = lider_nombre or _nombre_completo(current_user)
        elif current_user and rol == ROL_RECRUITER:
            recruiter_id = creador_id
            recruiter_nombre = recruiter_nombre or _nombre_completo(current_user)

        solicitud = Solicitud(
            empresa_id=empresa_id,
            id_busqueda=(datos.id_busqueda or "").strip() or f"OP-{uuid.uuid4().hex[:6].upper()}",
            cliente=cliente,
            titulo=titulo,
            estado=datos.estado,
            creador_id=creador_id,
            recruiter_id=recruiter_id,
            lider_id=lider_id,
            recruiter_nombre=recruiter_nombre,
            lider_nombre=lider_nombre,
            # La fecha de asignación la fija siempre el backend (la del cliente se ignora)
            fecha_asignacion=utc_now() if (recruiter_nombre or recruiter_id) else None,
            fecha_creacion=fecha_hoy(),
            puesto=OportunidadService._validar_puesto(db, datos.puesto),
            area=(datos.area or "").strip() or "Operaciones / IT",
            seniority=(datos.seniority or "").strip() or "Senior",
            modalidad=(datos.modalidad or "").strip() or "Remoto",
            vacantes=datos.vacantes or 1,
            rango=(datos.rango or "").strip() or None,
            prioridad=(datos.prioridad or "").strip() or "Alta",
            tipo=datos.tipo or "Efectiva",
            skills=datos.skills,
            habilidades=datos.habilidades,
            skills_deseadas=datos.skills_deseadas,
            descripcion=(datos.descripcion or "").strip() or None,
            updated_by=usuario,
        )
        db.add(solicitud)
        db.commit()
        db.refresh(solicitud)
        return solicitud

    @staticmethod
    def update(
        db: Session,
        empresa_id: uuid.UUID,
        id: uuid.UUID,
        datos: OportunidadUpdate,
        usuario: Optional[str] = None,
        current_user: Optional[Usuario] = None,
    ) -> Solicitud:
        """Edita una búsqueda (409 si está Ganada). El reclutador solo cambia con permiso de asignación y nunca se
        borra por esta vía (para eso está desasignar); la fecha de asignación la fija el backend."""
        solicitud = OportunidadService.get_by_id(db, empresa_id, id, current_user=current_user)
        OportunidadService.validar_no_ganada(solicitud)

        cambios = datos.model_dump(exclude_unset=True)
        if "estado" in cambios and cambios["estado"]:
            OportunidadService._validar_estado(cambios["estado"])
            if cambios["estado"] == OportunidadService.ESTADO_CANCELADA:
                OportunidadService.exigir_no_externo(
                    db,
                    empresa_id,
                    current_user,
                    "Los usuarios del grupo EXTERNOS no pueden eliminar ni cancelar búsquedas",
                )
        else:
            cambios.pop("estado", None)
        for obligatorio in ("cliente", "titulo"):
            if obligatorio in cambios:
                cambios[obligatorio] = (cambios[obligatorio] or "").strip() or None
                if not cambios[obligatorio]:
                    cambios.pop(obligatorio)
        # Columnas que no admiten NULL: un valor vacío no las cambia
        for no_nulo in ("tipo", "vacantes"):
            if cambios.get(no_nulo) is None:
                cambios.pop(no_nulo, None)

        if "puesto" in cambios:
            cambios["puesto"] = OportunidadService._validar_puesto(db, cambios["puesto"], actual=solicitud.puesto)
        if "descripcion" in cambios:
            cambios["descripcion"] = (cambios["descripcion"] or "").strip() or None

        if "recruiter_nombre" in cambios:
            nuevo = " ".join((cambios["recruiter_nombre"] or "").split())
            if not nuevo or nuevo.casefold() == (solicitud.recruiter_nombre or "").strip().casefold():
                cambios.pop("recruiter_nombre")
            elif not usuario_puede_asignar_reclutador(db, current_user, empresa_id):
                raise HTTPException(
                    status_code=403, detail="No tenés permisos para cambiar el reclutador de una búsqueda."
                )
            else:
                cambios["recruiter_nombre"] = nuevo
                cambios["fecha_asignacion"] = utc_now()

        for clave, valor in cambios.items():
            setattr(solicitud, clave, valor)
        solicitud.updated_at = utc_now()
        solicitud.updated_by = usuario
        db.commit()
        db.refresh(solicitud)
        return solicitud

    # ---- asignaciones ------------------------------------------------------

    @staticmethod
    def tomar_asignacion(
        db: Session,
        empresa_id: uuid.UUID,
        id: uuid.UUID,
        usuario: Optional[str] = None,
        current_user: Optional[Usuario] = None,
    ) -> Solicitud:
        """El reclutador toma la búsqueda: queda como responsable y se fija la fecha de asignación. Volver a tomarla
        quien ya era el responsable no reinicia la fecha ni los días abiertos."""
        solicitud = OportunidadService.get_by_id(db, empresa_id, id, current_user=current_user)
        OportunidadService.validar_no_ganada(solicitud)

        if obtener_rol_recruiting(db, current_user, empresa_id) != ROL_RECRUITER:
            raise HTTPException(status_code=403, detail="Solo los usuarios con rol Reclutador pueden tomar búsquedas.")
        if solicitud.recruiter_id and solicitud.recruiter_id != current_user.id:
            raise HTTPException(status_code=400, detail="Esta búsqueda ya está asignada a otro reclutador.")

        nombre_anterior = (solicitud.recruiter_nombre or "").strip().casefold()
        solicitud.recruiter_id = current_user.id
        solicitud.recruiter_nombre = _nombre_completo(current_user)
        mismo_responsable = (
            solicitud.fecha_asignacion is not None and solicitud.recruiter_nombre.strip().casefold() == nombre_anterior
        )
        if not mismo_responsable:
            solicitud.fecha_asignacion = utc_now()
        solicitud.updated_at = utc_now()
        solicitud.updated_by = usuario
        db.commit()
        db.refresh(solicitud)
        return solicitud

    @staticmethod
    def asignar_reclutador(
        db: Session,
        empresa_id: uuid.UUID,
        id: uuid.UUID,
        recruiter_nombre: str,
        usuario: Optional[str] = None,
        current_user: Optional[Usuario] = None,
    ) -> Solicitud:
        """Asigna o reasigna el reclutador con una persona activa del catálogo de Reclutadores. Si el nombre no
        cambia no se toca nada (se conserva la asignación y su fecha)."""
        solicitud = OportunidadService.get_by_id(db, empresa_id, id, current_user=current_user)
        OportunidadService.validar_no_ganada(solicitud)
        if not usuario_puede_asignar_reclutador(db, current_user, empresa_id):
            raise HTTPException(status_code=403, detail="No tenés permisos para asignar el reclutador de una búsqueda.")

        nombre = " ".join((recruiter_nombre or "").split())
        if not nombre:
            raise HTTPException(status_code=400, detail="Seleccioná un reclutador del catálogo.")
        reclutador = (
            db.query(RecruitingReclutador)
            .filter(func.lower(RecruitingReclutador.nombre) == nombre.lower(), RecruitingReclutador.activo.is_(True))
            .first()
        )
        if not reclutador:
            raise HTTPException(
                status_code=400, detail="El reclutador seleccionado no existe o está inactivo en Parámetros."
            )
        if (solicitud.recruiter_nombre or "").strip().casefold() == reclutador.nombre.casefold():
            return solicitud

        solicitud.recruiter_nombre = reclutador.nombre
        # El catálogo no está vinculado a usuarios: se limpia el vínculo previo para no dejar un recruiter_id viejo
        solicitud.recruiter_id = None
        solicitud.fecha_asignacion = utc_now()
        solicitud.updated_at = utc_now()
        solicitud.updated_by = usuario
        db.commit()
        db.refresh(solicitud)
        return solicitud

    @staticmethod
    def desasignar(
        db: Session,
        empresa_id: uuid.UUID,
        id: uuid.UUID,
        usuario: Optional[str] = None,
        current_user: Optional[Usuario] = None,
    ) -> Solicitud:
        """Libera la búsqueda para que otro reclutador pueda tomarla. Solo un admin o el reclutador asignado."""
        solicitud = OportunidadService.get_by_id(db, empresa_id, id, current_user=current_user)
        OportunidadService.validar_no_ganada(solicitud)

        rol = obtener_rol_recruiting(db, current_user, empresa_id)
        if rol not in (ROL_RECRUITER, ROL_ADMIN):
            raise HTTPException(
                status_code=403, detail="Solo el reclutador asignado o un administrador pueden desasignar la búsqueda."
            )
        if rol != ROL_ADMIN and solicitud.recruiter_id and solicitud.recruiter_id != current_user.id:
            raise HTTPException(status_code=403, detail="No podés desasignar una búsqueda que no tenés asignada a vos.")

        solicitud.fecha_asignacion = None
        solicitud.recruiter_id = None
        solicitud.recruiter_nombre = None
        solicitud.updated_at = utc_now()
        solicitud.updated_by = usuario
        db.commit()
        db.refresh(solicitud)
        return solicitud

    @staticmethod
    def _exigir_administrar_externos(db: Session, empresa_id: uuid.UUID, current_user: Optional[Usuario]) -> None:
        if not usuario_puede_administrar_externos(db, current_user, empresa_id):
            raise HTTPException(
                status_code=403, detail="No tenés permisos para administrar los usuarios externos de una búsqueda."
            )

    @staticmethod
    def _query_externos(db: Session, empresa_id: uuid.UUID):
        """Usuarios habilitados de la empresa que pertenecen al grupo EXTERNOS."""
        return (
            db.query(Usuario)
            .join(usuario_grupo, usuario_grupo.c.usuario_id == Usuario.id)
            .join(Grupo, Grupo.id == usuario_grupo.c.grupo_id)
            .filter(
                usuario_grupo.c.empresa_id == empresa_id,
                func.upper(func.trim(Grupo.nombre)) == GRUPO_EXTERNOS,
                Grupo.activo.is_(True),
                Grupo.deleted_at.is_(None),
                Usuario.activo.is_(True),
                Usuario.deleted_at.is_(None),
            )
        )

    @staticmethod
    def listar_externos_disponibles(
        db: Session, empresa_id: uuid.UUID, current_user: Optional[Usuario] = None
    ) -> List[Dict[str, Any]]:
        """Usuarios del grupo EXTERNOS que se pueden asignar a una búsqueda (solo para quien administra externos)."""
        OportunidadService._exigir_administrar_externos(db, empresa_id, current_user)
        usuarios = OportunidadService._query_externos(db, empresa_id).order_by(Usuario.nombre, Usuario.apellido).all()
        return [
            {"id": str(u.id), "nombre": " ".join(filter(None, [u.nombre, u.apellido])), "email": u.email}
            for u in usuarios
        ]

    @staticmethod
    def asignar_externo(
        db: Session,
        empresa_id: uuid.UUID,
        id: uuid.UUID,
        externo_id: uuid.UUID,
        usuario: Optional[str] = None,
        current_user: Optional[Usuario] = None,
    ) -> Solicitud:
        """Asigna (o reemplaza) el usuario externo de la búsqueda; solo acepta usuarios habilitados del grupo EXTERNOS."""
        OportunidadService._exigir_administrar_externos(db, empresa_id, current_user)
        solicitud = OportunidadService.get_by_id(db, empresa_id, id, current_user=current_user)
        OportunidadService.validar_no_ganada(solicitud)

        externo = OportunidadService._query_externos(db, empresa_id).filter(Usuario.id == externo_id).first()
        if not externo:
            raise HTTPException(
                status_code=400,
                detail="El usuario seleccionado no existe, está inactivo o no pertenece al grupo Externos.",
            )
        if solicitud.externo_id == externo.id:
            return solicitud
        solicitud.externo_id = externo.id
        solicitud.updated_at = utc_now()
        solicitud.updated_by = usuario
        db.commit()
        db.refresh(solicitud)
        return solicitud

    @staticmethod
    def quitar_externo(
        db: Session,
        empresa_id: uuid.UUID,
        id: uuid.UUID,
        usuario: Optional[str] = None,
        current_user: Optional[Usuario] = None,
    ) -> Solicitud:
        """Quita la asignación del usuario externo; no elimina la búsqueda ni sus candidatos."""
        OportunidadService._exigir_administrar_externos(db, empresa_id, current_user)
        solicitud = OportunidadService.get_by_id(db, empresa_id, id, current_user=current_user)
        OportunidadService.validar_no_ganada(solicitud)
        if solicitud.externo_id is not None:
            solicitud.externo_id = None
            solicitud.updated_at = utc_now()
            solicitud.updated_by = usuario
            db.commit()
            db.refresh(solicitud)
        return solicitud

    # ---- catálogos de solo lectura -----------------------------------------

    @staticmethod
    def personas(db: Session, modelo) -> list:
        """Líderes o reclutadores activos del catálogo, por nombre (su ABM es de Parámetros)."""
        return db.query(modelo).filter(modelo.activo.is_(True)).order_by(func.lower(modelo.nombre)).all()

    @staticmethod
    def lideres(db: Session) -> list:
        return OportunidadService.personas(db, RecruitingLider)

    @staticmethod
    def reclutadores(db: Session) -> list:
        return OportunidadService.personas(db, RecruitingReclutador)

    @staticmethod
    def match_minimo(db: Session, empresa_id: uuid.UUID) -> int:
        """Umbral de Smart Matching de la empresa; 50 si no lo configuró."""
        config = db.query(RecrutingConfig).filter(RecrutingConfig.empresa_id == empresa_id).first()
        return config.match_minimo_porcentaje if config else 50


# ---------------------------------------------------------------------------
# Candidatos de una búsqueda: pipeline, Smart Matching, alta y baja
# ---------------------------------------------------------------------------


def _coincidencias(requeridos: List[str], del_candidato: List[str]) -> List[str]:
    """Del candidato, lo que coincide (igual o contenido, sin distinguir mayúsculas) con cada requerido."""
    por_clave = {s.lower(): s for s in del_candidato}
    encontradas = []
    for requerido in (r.lower() for r in requeridos):
        for clave, original in por_clave.items():
            if requerido == clave or requerido in clave or clave in requerido:
                encontradas.append(original)
                break
    return encontradas


class CandidatosDeBusquedaService:
    """Los candidatos de una búsqueda: los del pipeline (recruiting_gestionBusqueda), los que sugiere Smart Matching,
    y sumar o quitar uno. El cambio de etapa y el kanban son de Pipeline."""

    ETAPAS_INICIALES = ("Coordinando entrevista", "Postulado", "Candidato")

    @staticmethod
    def _filtro_visibilidad(query, db, empresa_id, current_user):
        """El grupo EXTERNOS ve todos los candidatos de sus búsquedas (los que no presentó, anónimos); el resto, la
        visibilidad de Candidatos."""
        if usuario_es_grupo_externos(db, current_user, empresa_id):
            return query
        rol = obtener_rol_recruiting(db, current_user, empresa_id)
        return aplicar_filtro_ownership_candidatos(query, current_user, rol, db, empresa_id)

    @staticmethod
    def listar(
        db: Session,
        empresa_id: uuid.UUID,
        oportunidad_id: uuid.UUID,
        current_user: Optional[Usuario] = None,
        etapa: Optional[str] = None,
        alcance: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Candidatos vigentes de la búsqueda, con su etapa y estado. `etapa` filtra por una etapa ('Todas' o vacío no
        filtra) y `alcance='propios'` deja solo los que cargó el usuario (se suma a la visibilidad, nunca la amplía)."""
        solicitud = OportunidadService.get_by_id(db, empresa_id, oportunidad_id, current_user=current_user)
        query = (
            db.query(GestionBusqueda, Candidato)
            .join(Candidato, GestionBusqueda.candidato_id == Candidato.id)
            .filter(
                GestionBusqueda.empresa_id == empresa_id,
                GestionBusqueda.oportunidad_id == solicitud.id,
                GestionBusqueda.activo.is_(True),
                GestionBusqueda.deleted_at.is_(None),
                Candidato.deleted_at.is_(None),
            )
        )
        query = CandidatosDeBusquedaService._filtro_visibilidad(query, db, empresa_id, current_user)
        if etapa and etapa.strip().lower() != "todas":
            query = query.filter(func.lower(GestionBusqueda.etapa_actual) == etapa.strip().lower())
        if (alcance or "").strip().lower() == "propios":
            query = query.filter(Candidato.creador_id == current_user.id) if current_user else query.filter(false())
        filas = query.order_by(GestionBusqueda.created_at.desc()).all()

        ids_externos = {u.id for u in OportunidadService._query_externos(db, empresa_id).all()}
        ids_creadores = {c.creador_id for _, c in filas if c.creador_id}
        presentadores = {}
        if ids_creadores:
            for u in db.query(Usuario).filter(Usuario.id.in_(ids_creadores)).all():
                presentadores[u.id] = " ".join(f"{u.nombre or ''} {u.apellido or ''}".split()) or u.email
        ocultador = OcultadorCandidatosEnBusqueda(db, empresa_id, current_user)

        resultado = []
        for g, c in filas:
            resultado.append(
                ocultador.aplicar(
                    {
                        "es_externo": c.creador_id in ids_externos,
                        "presentado_por": presentadores.get(c.creador_id, "Sin identificar"),
                        "id": str(c.id),
                        "gestion_id": str(g.id),
                        "candidato_id": str(c.id),
                        "oportunidad_id": str(g.oportunidad_id),
                        "codigo": c.codigo,
                        "nombre": f"{c.nombre} {c.apellido}".strip(),
                        "nombre_pila": c.nombre,
                        "apellido": c.apellido,
                        "email": c.email,
                        "telefono": c.telefono,
                        "ubicacion": c.ubicacion,
                        "headline": c.headline,
                        "seniority": c.seniority or "Senior",
                        "etapa": g.etapa_actual,
                        "etapa_actual": g.etapa_actual,
                        "estado": g.estado,
                        # El grupo EXTERNOS (ya resuelto por el ocultador) no ve el motivo de descarte ni el feedback
                        "motivo_descarte": None if ocultador.activo else g.motivo_descarte,
                        "feedback_etapa": None if ocultador.activo else g.feedback_etapa,
                        "pretension_salarial_bruta_ars": g.pretension_salarial_bruta_ars,
                        "fecha_cambio_etapa": g.fecha_cambio_etapa or g.updated_at,
                        "created_at": g.created_at,
                        "updated_at": g.updated_at,
                        "cv_url": c.cv_url,
                        "linkedin_url": c.linkedin_url,
                    },
                    c,
                    g,
                )
            )
        return resultado

    @staticmethod
    def compatibles(
        db: Session,
        empresa_id: uuid.UUID,
        oportunidad_id: uuid.UUID,
        busqueda: Optional[str] = None,
        limite: int = 15,
        current_user: Optional[Usuario] = None,
    ) -> List[Dict[str, Any]]:
        """Smart Matching: candidatos activos que el usuario ve y que comparten skills o habilidades con la búsqueda
        (nombre, apellido, código o email opcionales), sin los ya asignados; el de mayor coincidencia primero."""
        OportunidadService.exigir_no_externo(
            db, empresa_id, current_user, "Los usuarios del grupo EXTERNOS no tienen acceso a Smart Matching"
        )
        solicitud = OportunidadService.get_by_id(db, empresa_id, oportunidad_id, current_user=current_user)

        asignados = {
            fila[0]
            for fila in db.query(Postulacion.candidato_id).filter(
                Postulacion.empresa_id == empresa_id,
                Postulacion.solicitud_id == solicitud.id,
                Postulacion.deleted_at.is_(None),
            )
        } | {
            fila[0]
            for fila in db.query(GestionBusqueda.candidato_id).filter(
                GestionBusqueda.empresa_id == empresa_id,
                GestionBusqueda.oportunidad_id == solicitud.id,
                GestionBusqueda.activo.is_(True),
                GestionBusqueda.deleted_at.is_(None),
            )
        }

        skills_busqueda = lista_de_textos(solicitud.skills)
        habilidades_busqueda = lista_de_textos(solicitud.habilidades)

        query = db.query(Candidato).filter(
            Candidato.empresa_id == empresa_id, Candidato.activo.is_(True), Candidato.deleted_at.is_(None)
        )
        query = CandidatosDeBusquedaService._filtro_visibilidad(query, db, empresa_id, current_user)
        termino = (busqueda or "").strip()
        if termino:
            patron = f"%{termino}%"
            query = query.filter(
                or_(
                    Candidato.nombre.ilike(patron),
                    Candidato.apellido.ilike(patron),
                    (Candidato.nombre + " " + Candidato.apellido).ilike(patron),
                    (Candidato.apellido + " " + Candidato.nombre).ilike(patron),
                    Candidato.codigo.ilike(patron),
                    Candidato.email.ilike(patron),
                )
            )

        resultados = []
        for candidato in query.order_by(Candidato.created_at.desc()).limit(100).all():
            if candidato.id in asignados:
                continue
            skills = lista_de_textos(candidato.skills)
            habilidades = lista_de_textos(getattr(candidato, "habilidades", None))
            skills_ok = _coincidencias(skills_busqueda, skills)
            habilidades_ok = _coincidencias(habilidades_busqueda, habilidades)
            requeridos = len(skills_busqueda) + len(habilidades_busqueda)
            coincidentes = len(skills_ok) + len(habilidades_ok)
            if requeridos and not coincidentes:
                continue
            porcentaje = int(coincidentes / requeridos * 100) if requeridos else 100
            seniority = candidato.seniority or "Senior"
            resultados.append(
                {
                    "id": str(candidato.id),
                    "codigo": candidato.codigo,
                    "nombre": candidato.nombre,
                    "apellido": candidato.apellido,
                    "nombre_completo": f"{candidato.nombre or ''} {candidato.apellido or ''}".strip() or "Candidato",
                    "email": candidato.email,
                    "headline": candidato.headline or f"{seniority} Developer",
                    "seniority": seniority,
                    "skills": skills,
                    "habilidades": habilidades,
                    "skills_coincidentes": skills_ok,
                    "habilidades_coincidentes": habilidades_ok,
                    "porcentaje_match": porcentaje,
                    "match_porcentaje": porcentaje,
                    "ya_asignado": False,
                }
            )
        resultados.sort(key=lambda r: (-r["porcentaje_match"], r["apellido"] or "", r["nombre"] or ""))
        return resultados[:limite]

    @staticmethod
    def recalcular_metricas(db: Session, solicitud: Solicitud) -> None:
        """Deja en la búsqueda los contadores del embudo (los que muestra el listado), calculados sobre todas sus
        postulaciones vigentes: no dependen de quién consulta."""
        filas = (
            db.query(Postulacion.etapa, Postulacion.estado)
            .join(Candidato, Postulacion.candidato_id == Candidato.id)
            .filter(
                Postulacion.empresa_id == solicitud.empresa_id,
                Postulacion.solicitud_id == solicitud.id,
                Postulacion.deleted_at.is_(None),
                Candidato.deleted_at.is_(None),
            )
            .all()
        )
        contadores = {"coordinando": 0, "rrhh": 0, "lider": 0, "feedback": 0, "cliente": 0, "activos": 0}
        for etapa, estado in filas:
            etapa = (etapa or "").lower()
            if "coordinando" in etapa:
                contadores["coordinando"] += 1
            elif "rrhh" in etapa:
                contadores["rrhh"] += 1
            elif "presentacion lider" in etapa or "presentación líder" in etapa:
                contadores["lider"] += 1
            elif "feedback" in etapa:
                contadores["feedback"] += 1
            elif "cliente" in etapa:
                contadores["cliente"] += 1
            if (estado or "").lower() == "en proceso":
                contadores["activos"] += 1
        solicitud.candidatos_pipeline = len(filas)
        solicitud.coordinando_entrevista = contadores["coordinando"]
        solicitud.entrevistados_rrhh = contadores["rrhh"]
        solicitud.presentacion_lider = contadores["lider"]
        solicitud.feedback_lider = contadores["feedback"]
        solicitud.presentacion_cliente = contadores["cliente"]
        solicitud.q_activos = contadores["activos"]
        db.commit()

    @staticmethod
    def asignar(
        db: Session,
        empresa_id: uuid.UUID,
        oportunidad_id: uuid.UUID,
        datos: AsignarCandidatoRequest,
        usuario: Optional[str] = None,
        current_user: Optional[Usuario] = None,
        desde_busqueda_asignada: bool = False,
    ) -> Postulacion:
        """Suma un candidato a una búsqueda Abierta: crea su postulación y su fila del pipeline, y deja la traza. Sumarlo
        directo en Ingreso cierra la búsqueda (Ganada).

        `desde_busqueda_asignada` es para el alta de un usuario EXTERNOS desde su búsqueda asignada (carga de CV o alta
        manual): el grupo EXTERNOS no asigna desde el listado, pero sí asocia el candidato que presenta, aunque la ficha
        existente sea de otro usuario (la búsqueda sigue validándose contra su asignación)."""
        if not desde_busqueda_asignada:
            OportunidadService.exigir_no_externo(
                db, empresa_id, current_user, "Los usuarios del grupo EXTERNOS no pueden asignar candidatos a búsquedas"
            )
        solicitud = OportunidadService.get_by_id(db, empresa_id, oportunidad_id, current_user=current_user)
        candidato = CandidatoService.get_by_id(
            db,
            empresa_id,
            str(datos.candidato_id),
            current_user=None if desde_busqueda_asignada else current_user,
        )

        if solicitud.estado != ESTADO_BUSQUEDA_ABIERTA:
            raise HTTPException(
                status_code=400,
                detail=f"No se puede asignar el candidato: la búsqueda está en estado «{solicitud.estado}», "
                f"solo se permiten búsquedas en estado «{ESTADO_BUSQUEDA_ABIERTA}».",
            )
        ya_asignado = (
            db.query(Postulacion.id)
            .filter(
                Postulacion.empresa_id == empresa_id,
                Postulacion.solicitud_id == solicitud.id,
                Postulacion.candidato_id == candidato.id,
                Postulacion.deleted_at.is_(None),
            )
            .first()
        )
        if ya_asignado:
            raise HTTPException(
                status_code=400,
                detail=f"El candidato {candidato.nombre} {candidato.apellido} ya está asignado a esta búsqueda.",
            )

        ahora = utc_now()
        etapa = (datos.etapa or "").strip() or CandidatosDeBusquedaService.ETAPAS_INICIALES[0]
        estado = (datos.estado or "").strip() or ESTADO_EN_PROCESO
        observaciones = (datos.observaciones or "").strip() or None
        etapa_pipeline = "Candidato" if etapa in CandidatosDeBusquedaService.ETAPAS_INICIALES else etapa

        postulacion = Postulacion(
            empresa_id=empresa_id,
            candidato_id=candidato.id,
            solicitud_id=solicitud.id,
            solicitud_titulo=solicitud.titulo,
            solicitud_cliente=solicitud.cliente,
            etapa=etapa,
            estado=estado,
            fecha_asignacion=ahora,
            fecha_etapa=ahora,
            observaciones=observaciones,
            activo=True,
            updated_by=usuario,
        )
        db.add(postulacion)

        # Una sola fila por candidato y búsqueda (restricción única): si estuvo desvinculado se reactiva la baja lógica
        gestion = (
            db.query(GestionBusqueda)
            .filter(
                GestionBusqueda.empresa_id == empresa_id,
                GestionBusqueda.oportunidad_id == solicitud.id,
                GestionBusqueda.candidato_id == candidato.id,
            )
            .first()
        )
        if gestion:
            gestion.deleted_at = None
            gestion.activo = True
            gestion.etapa_actual = etapa_pipeline
            gestion.estado = estado
            gestion.fecha_cambio_etapa = ahora
            gestion.updated_at = ahora
            gestion.updated_by = usuario
        else:
            db.add(
                GestionBusqueda(
                    empresa_id=empresa_id,
                    oportunidad_id=solicitud.id,
                    candidato_id=candidato.id,
                    etapa_actual=etapa_pipeline,
                    estado=estado,
                    feedback_etapa=observaciones,
                    fecha_cambio_etapa=ahora,
                    activo=True,
                    updated_by=usuario,
                )
            )
        if etapa_pipeline.casefold() == "ingreso":
            OportunidadService.marcar_ganada(solicitud, usuario)

        db.flush()
        db.add(
            TransicionEstado(
                empresa_id=empresa_id,
                candidato_id=candidato.id,
                postulacion_id=postulacion.id,
                estado_anterior=None,
                estado_nuevo=f"{estado} ({etapa})",
                observaciones=observaciones,
                usuario=usuario,
            )
        )
        db.commit()
        db.refresh(postulacion)
        CandidatosDeBusquedaService.recalcular_metricas(db, solicitud)
        return postulacion

    @staticmethod
    def desvincular(
        db: Session,
        empresa_id: uuid.UUID,
        oportunidad_id: uuid.UUID,
        candidato_id: uuid.UUID,
        usuario: Optional[str] = None,
        current_user: Optional[Usuario] = None,
    ) -> Dict[str, Any]:
        """Quita al candidato de la búsqueda (baja lógica de su postulación y de su fila del pipeline) sin tocar su ficha
        del Banco de Talentos."""
        solicitud = OportunidadService.get_by_id(db, empresa_id, oportunidad_id, current_user=current_user)
        OportunidadService.validar_no_ganada(solicitud)
        candidato = CandidatoService.validar_operable(db, empresa_id, str(candidato_id), current_user=current_user)

        postulaciones = (
            db.query(Postulacion)
            .filter(
                Postulacion.empresa_id == empresa_id,
                Postulacion.solicitud_id == solicitud.id,
                Postulacion.candidato_id == candidato.id,
                Postulacion.deleted_at.is_(None),
            )
            .all()
        )
        if not postulaciones:
            raise HTTPException(status_code=404, detail="El candidato no se encuentra asignado a esta búsqueda")

        ahora = utc_now()
        for p in postulaciones:
            db.add(
                TransicionEstado(
                    empresa_id=empresa_id,
                    candidato_id=candidato.id,
                    postulacion_id=p.id,
                    estado_anterior=f"{p.estado} ({p.etapa})",
                    estado_nuevo="Desvinculado de la búsqueda",
                    observaciones=f"Desvinculado de la búsqueda {solicitud.titulo}",
                    usuario=usuario,
                    created_at=ahora,
                )
            )
            p.deleted_at = ahora
            p.activo = False
            p.updated_at = ahora
            p.updated_by = usuario
        gestiones = (
            db.query(GestionBusqueda)
            .filter(
                GestionBusqueda.empresa_id == empresa_id,
                GestionBusqueda.oportunidad_id == solicitud.id,
                GestionBusqueda.candidato_id == candidato.id,
                GestionBusqueda.deleted_at.is_(None),
            )
            .all()
        )
        for g in gestiones:
            g.deleted_at = ahora
            g.activo = False
            g.updated_at = ahora
            g.updated_by = usuario
        db.commit()
        CandidatosDeBusquedaService.recalcular_metricas(db, solicitud)
        return {
            "ok": True,
            "mensaje": f"Candidato {candidato.nombre} {candidato.apellido} desvinculado de la búsqueda.",
            "candidato_id": str(candidato.id),
            "oportunidad_id": str(solicitud.id),
        }
