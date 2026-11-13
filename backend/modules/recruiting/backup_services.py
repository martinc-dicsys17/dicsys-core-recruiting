"""
Backup completo de Recruiting (Parametros > Archivos de CV > "Backup").

Genera un unico ZIP con:
  - database/: exportacion restaurable (CSV por tabla + restore.sql) de TODAS las tablas recruiting_* y de las filas
    indispensables de las tablas compartidas (core_empresas, core_usuarios sin secretos, notificaciones de Recruiting).
  - cv_procesados_ok/, cv_duplicados/, cv_errores/: los archivos fisicos de CV_STORAGE_DIR (mismos criterios que la pantalla).
  - manifest.json: version, fecha, conteos, tamanos y SHA-256 de cada pieza.

Garantias:
  - Solo lectura: la base se lee en una transaccion REPEATABLE READ + READ ONLY (instantanea consistente; cualquier escritura falla) y
    los CV originales solo se abren para leer. Nunca se mueve, modifica ni elimina nada fuera del directorio privado del backup.
  - Memoria acotada: COPY y archivos se escriben al ZIP por bloques; el ZIP se arma en disco como ".partial" y solo se publica
    (renombra) despues de verificar CRC y SHA-256 de todas sus piezas.
  - Se ejecuta en un hilo propio; el estado vive en archivos del directorio privado para que cualquier worker lo consulte.
"""
import hashlib
import json
import logging
import os
import re
import tempfile
import threading
import time
import uuid
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from backend.modules.recruiting.parametros_services import ArchivoCVService
from backend.modules.recruiting.services import MENSAJE_ERROR_INTERNO, CandidatoService
from backend.modules.usuarios.models import Usuario

logger = logging.getLogger(__name__)

TAMANO_BLOQUE = 1024 * 1024
_EXTENSIONES_YA_COMPRIMIDAS = (".docx", ".zip", ".rar", ".png", ".jpg", ".jpeg")


class _EscritorConHash:
    """Archivo de escritura (para COPY) que calcula el SHA-256 y el tamano de lo escrito sin guardarlo en memoria."""

    def __init__(self, destino):
        self._destino = destino
        self.sha256 = hashlib.sha256()
        self.bytes = 0

    def write(self, datos) -> int:
        if isinstance(datos, str):
            datos = datos.encode("utf-8")
        self.sha256.update(datos)
        self.bytes += len(datos)
        self._destino.write(datos)
        return len(datos)


def _ident(nombre: str) -> str:
    """Identificador SQL entre comillas (los nombres salen del catalogo de la base, nunca de la entrada del usuario)."""
    return '"' + nombre.replace('"', '""') + '"'


class BackupRecruitingService:
    VERSION_BACKUP = "1.2"  # 1.1: core_usuarios incluye dni, telefono y avatar_url; 1.2: incluye los archivos del storage (storage/)
    FORMATO = "RECLUIT_BACKUP"
    PREFIJO_TABLAS = "recruiting_"
    ESTADOS_ACTIVOS = ("preparando", "generando", "verificando")
    RETENCION_SEGUNDOS = 24 * 3600          # los ZIP y estados se conservan 24 h para poder volver a descargarlos
    RETENCION_PARCIAL_SEGUNDOS = 2 * 3600   # un ".partial" de un proceso interrumpido se descarta pasadas 2 h
    CADUCIDAD_LATIDO_SEGUNDOS = 120         # sin latido en este tiempo el backup en curso se considera interrumpido
    PATRON_ZIP = re.compile(r"^RECLUIT_BACKUP_\d{8}_\d{6}(_\d+)?\.zip$")

    # Tablas compartidas: solo se exportan las filas referenciadas por Recruiting y nunca contrasenas, tokens, secretos TOTP ni credenciales
    PATRON_COLUMNA_SENSIBLE = re.compile(
        r"(password_hash|token|secret|totp|backup_codes|api_key|credential)", re.IGNORECASE
    )
    # Archivos del storage de Recruiting (cloud_storage: local, GCS o S3) referenciados por la base: (tabla, columna)
    COLUMNAS_STORAGE = (
        ("recruiting_candidatos", "cv_url"),
        ("recruiting_etapa_archivos", "ruta_archivo"),
        ("recruiting_candidatos_duplicados", "archivo_temp_key"),
    )
    PREFIJO_STORAGE = "recruiting/"
    TABLA_NOTIFICACIONES = "core_notificaciones_internas"
    FILTRO_NOTIFICACIONES = "(origen ILIKE 'recruiting%' OR enlace ILIKE '/recruiting%')"
    # Valores con los que restore.sql completa las columnas obligatorias que no se respaldan (usuarios sin credenciales)
    VALORES_COLUMNAS_OMITIDAS = {
        "password_hash": "'!sin-credenciales'",
        "requiere_password_change": "true",
        "totp_enabled": "false",
        "totp_required": "false",
    }

    # ------------------------------------------------------------------ acceso y directorio privado

    @staticmethod
    def verificar_acceso(current_user: Optional[Usuario]) -> None:
        """Mismo criterio que "Limpiar BD": solo el administrador (rol admin); el boton del frontend solo orienta la interfaz."""
        if getattr(current_user, "rol", None) != "admin":
            raise HTTPException(status_code=403, detail="No tenés permiso para generar ni descargar backups de Recruiting")

    @staticmethod
    def _directorio() -> str:
        """Directorio privado (0700) fuera de CV_STORAGE_DIR; configurable con BACKUP_RECRUITING_DIR."""
        base = os.getenv("BACKUP_RECRUITING_DIR") or os.path.join(tempfile.gettempdir(), "dicsys_backups_recruiting")
        ruta = os.path.abspath(base)
        raiz_cv = os.path.abspath(CandidatoService._raiz_cv_storage())
        try:
            dentro_de_cv = os.path.commonpath([ruta, raiz_cv]) == raiz_cv
        except ValueError:  # unidades distintas (Windows): no pueden estar una dentro de la otra
            dentro_de_cv = False
        if dentro_de_cv:
            raise RuntimeError("El directorio de backups no puede estar dentro de CV_STORAGE_DIR")
        os.makedirs(ruta, mode=0o700, exist_ok=True)
        return ruta

    @staticmethod
    def _id_valido(backup_id: str) -> str:
        try:
            return str(uuid.UUID(str(backup_id)))
        except ValueError:
            raise HTTPException(status_code=404, detail="Backup no encontrado.")

    @classmethod
    def _ruta_estado(cls, backup_id: str) -> str:
        return os.path.join(cls._directorio(), f"{cls._id_valido(backup_id)}.json")

    @classmethod
    def _guardar_estado(cls, estado: Dict[str, Any]) -> None:
        ruta = cls._ruta_estado(estado["backup_id"])
        estado["actualizado_ts"] = time.time()
        tmp = f"{ruta}.{uuid.uuid4().hex}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({k: v for k, v in estado.items() if not k.startswith("_")}, f)  # las claves "_x" son solo de memoria
        for intento in range(20):  # en Windows el reemplazo puede fallar un instante si alguien lee el archivo
            try:
                os.replace(tmp, ruta)
                break
            except PermissionError:
                if intento == 19:
                    os.remove(tmp)
                    raise
                time.sleep(0.05)
        try:  # latido del bloqueo: mientras se actualice, el backup en curso se considera vivo
            os.utime(os.path.join(cls._directorio(), "activo.lock"))
        except OSError:
            pass

    @classmethod
    def _leer_estado(cls, backup_id: str) -> Dict[str, Any]:
        try:
            with open(cls._ruta_estado(backup_id), "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Backup no encontrado.")

    @staticmethod
    def _publico(estado: Dict[str, Any]) -> Dict[str, Any]:
        claves = (
            "backup_id", "estado", "fase", "porcentaje", "mensaje", "tablas_total", "tablas_procesadas", "archivos_total",
            "archivos_procesados", "bytes_total", "bytes_procesados", "nombre_archivo", "tamano_bytes", "tamano", "sha256",
            "error", "iniciado_at", "finalizado_at",
        )
        return {k: estado.get(k) for k in claves}

    # ------------------------------------------------------------------ limpieza de temporales propios

    @classmethod
    def _limpiar_temporales(cls) -> None:
        """Elimina solo archivos propios del directorio privado: backups vencidos, parciales abandonados y estados viejos."""
        directorio = cls._directorio()
        ahora = time.time()
        for nombre in os.listdir(directorio):
            ruta = os.path.join(directorio, nombre)
            propio = (
                cls.PATRON_ZIP.match(nombre)
                or nombre.endswith(".zip.partial")
                or re.match(r"^[0-9a-f-]{36}\.json$", nombre)
                or nombre.endswith(".tmp")
            )
            if not propio or not os.path.isfile(ruta) or os.path.islink(ruta):
                continue
            limite = cls.RETENCION_PARCIAL_SEGUNDOS if nombre.endswith((".partial", ".tmp")) else cls.RETENCION_SEGUNDOS
            try:
                if ahora - os.path.getmtime(ruta) > limite:
                    os.remove(ruta)
            except OSError as e:
                logger.warning(f"No se pudo eliminar el temporal de backup {nombre}: {e}")

    @classmethod
    def _tomar_bloqueo(cls) -> Optional[str]:
        """Un solo backup a la vez (entre todos los workers). Devuelve None si se obtuvo; si no, el id del backup en curso."""
        ruta = os.path.join(cls._directorio(), "activo.lock")
        for _ in range(2):
            try:
                fd = os.open(ruta, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(fd)
                return None
            except FileExistsError:
                try:
                    if time.time() - os.path.getmtime(ruta) <= cls.CADUCIDAD_LATIDO_SEGUNDOS:
                        return cls._backup_en_curso() or "en-curso"
                    os.remove(ruta)  # bloqueo abandonado por un proceso interrumpido
                except OSError:
                    pass
        return "en-curso"

    @classmethod
    def _backup_en_curso(cls) -> Optional[str]:
        directorio = cls._directorio()
        for nombre in os.listdir(directorio):
            if re.match(r"^[0-9a-f-]{36}\.json$", nombre):
                try:
                    with open(os.path.join(directorio, nombre), "r", encoding="utf-8") as f:
                        estado = json.load(f)
                except (OSError, ValueError):
                    continue
                if estado.get("estado") in cls.ESTADOS_ACTIVOS:
                    return estado.get("backup_id")
        return None

    @classmethod
    def _soltar_bloqueo(cls) -> None:
        try:
            os.remove(os.path.join(cls._directorio(), "activo.lock"))
        except OSError:
            pass

    # ------------------------------------------------------------------ API del servicio

    @classmethod
    def iniciar(cls, current_user: Usuario) -> Dict[str, Any]:
        """Registra el backup (estado 'preparando') y lo genera en un hilo propio. Un segundo pedido simultaneo recibe 409."""
        cls.verificar_acceso(current_user)
        cls._limpiar_temporales()
        en_curso = cls._tomar_bloqueo()
        if en_curso:
            raise HTTPException(status_code=409, detail="Ya hay un backup de Recruiting en curso. Esperá a que termine.")
        estado = cls._estado_inicial(current_user.email)
        try:
            cls._guardar_estado(estado)
            cls._lanzar(lambda: cls._ejecutar(estado))
        except Exception:
            cls._soltar_bloqueo()
            logger.error("No se pudo iniciar el backup de Recruiting", exc_info=True)
            raise HTTPException(status_code=500, detail=MENSAJE_ERROR_INTERNO)
        return cls._publico(estado)

    @staticmethod
    def _estado_inicial(email: Optional[str]) -> Dict[str, Any]:
        return {
            "backup_id": str(uuid.uuid4()), "estado": "preparando", "fase": "preparando", "porcentaje": 0,
            "mensaje": "Preparando el backup...", "tablas_total": 0, "tablas_procesadas": 0, "archivos_total": 0,
            "archivos_procesados": 0, "bytes_total": 0, "bytes_procesados": 0, "nombre_archivo": None, "tamano_bytes": None,
            "tamano": None, "sha256": None, "error": None, "iniciado_at": datetime.now(timezone.utc).isoformat(),
            "finalizado_at": None, "usuario": email,
        }

    @classmethod
    def generar_bloqueante(cls, email: Optional[str], estado: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Genera y verifica un backup en el hilo actual (lo usa la importacion para el backup de seguridad previo).

        El llamador debe tener tomado el bloqueo global (`_tomar_bloqueo`). Si algo falla elimina solo el temporal incompleto y propaga el error.
        """
        estado = estado or cls._estado_inicial(email)
        cls._guardar_estado(estado)
        parcial = None
        try:
            with cls._sesion_de_lectura() as db:
                parcial, final = cls._rutas_zip()
                cls._generar(db, estado, parcial)
            cls._verificar_y_publicar(estado, parcial, final)
        except Exception:
            if parcial:
                try:
                    os.remove(parcial)
                except OSError:
                    pass
            estado.update({"estado": "error", "fase": "error", "mensaje": "No se pudo generar el backup.", "error": MENSAJE_ERROR_INTERNO})
            try:
                cls._guardar_estado(estado)
            except Exception:
                pass
            raise
        return estado

    @staticmethod
    def _lanzar(funcion) -> None:
        threading.Thread(target=funcion, daemon=True).start()

    @classmethod
    def obtener_estado(cls, current_user: Usuario, backup_id: str) -> Dict[str, Any]:
        cls.verificar_acceso(current_user)
        estado = cls._leer_estado(backup_id)
        if estado.get("estado") in cls.ESTADOS_ACTIVOS and time.time() - estado.get("actualizado_ts", 0) > cls.CADUCIDAD_LATIDO_SEGUNDOS:
            estado.update({"estado": "error", "mensaje": "El backup se interrumpió. Intentá nuevamente.", "error": "interrumpido"})
        return cls._publico(estado)

    @classmethod
    def ruta_descarga(cls, current_user: Usuario, backup_id: str) -> Tuple[str, str]:
        """(ruta, nombre) del ZIP de un backup finalizado y verificado. La ruta se reconstruye aqui: nunca viene del cliente."""
        cls.verificar_acceso(current_user)
        estado = cls._leer_estado(backup_id)
        nombre = estado.get("nombre_archivo") or ""
        if estado.get("estado") != "finalizado" or not cls.PATRON_ZIP.match(nombre):
            raise HTTPException(status_code=409, detail="El backup todavía no está listo para descargar.")
        ruta = os.path.join(cls._directorio(), nombre)
        if not os.path.isfile(ruta) or os.path.islink(ruta):
            raise HTTPException(status_code=404, detail="El backup ya no está disponible. Generá uno nuevo.")
        return ruta, nombre

    # ------------------------------------------------------------------ generacion (hilo en segundo plano)

    @classmethod
    @contextmanager
    def _sesion_de_lectura(cls) -> Iterator[Session]:
        """Sesion propia con instantanea consistente y solo lectura (se sustituye en las pruebas por la sesion de prueba)."""
        from backend.database import SessionLocal

        db = SessionLocal()
        try:
            db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            yield db
        finally:
            db.rollback()
            db.close()

    @staticmethod
    def _liberar_instantanea(db: Session) -> None:
        """Cierra la transaccion de solo lectura (no hay nada que confirmar)."""
        db.rollback()

    @classmethod
    def _ejecutar(cls, estado: Dict[str, Any]) -> None:
        parcial = None
        try:
            with cls._sesion_de_lectura() as db:
                parcial, final = cls._rutas_zip()
                cls._generar(db, estado, parcial)
            cls._verificar_y_publicar(estado, parcial, final)
        except Exception:
            logger.error("Fallo la generación del backup de Recruiting", exc_info=True)
            if parcial:
                try:
                    os.remove(parcial)  # solo el temporal incompleto
                except OSError:
                    pass
            estado.update({
                "estado": "error", "fase": "error", "mensaje": "No se pudo generar el backup. Intentá nuevamente.",
                "error": MENSAJE_ERROR_INTERNO, "finalizado_at": datetime.now(timezone.utc).isoformat(),
            })
            try:
                cls._guardar_estado(estado)
            except Exception:
                logger.error("No se pudo publicar el error del backup", exc_info=True)
        finally:
            cls._soltar_bloqueo()

    @classmethod
    def _rutas_zip(cls) -> Tuple[str, str]:
        nombre = f"RECLUIT_BACKUP_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.zip"
        final = os.path.join(cls._directorio(), nombre)
        n = 0
        while os.path.exists(final) or os.path.exists(final + ".partial"):
            n += 1
            final = os.path.join(cls._directorio(), nombre.replace(".zip", f"_{n}.zip"))
        return final + ".partial", final

    @classmethod
    def _actualizar(cls, st: Dict[str, Any], forzar: bool = False, **campos) -> None:
        """Actualiza el estado y lo publica (el avance fino se limita a ~2 publicaciones por segundo para no saturar el disco)."""
        st.update(campos)
        ahora = time.monotonic()
        if forzar or ahora - st.get("_ultima_publicacion", 0) >= 0.5:
            st["_ultima_publicacion"] = ahora
            cls._guardar_estado(st)

    @classmethod
    def _porcentaje(cls, estado: Dict[str, Any]) -> int:
        """Base de datos 0-10 %, archivos 10-90 %, verificacion 90-99 %, finalizado 100 %."""
        fase = estado.get("fase")
        if fase == "base_de_datos":
            total = max(estado.get("tablas_total", 0), 1)
            return int(10 * estado.get("tablas_procesadas", 0) / total)
        if fase == "archivos":
            total = estado.get("bytes_total", 0)
            avance = (estado.get("bytes_procesados", 0) / total) if total else 1
            return 10 + int(80 * min(avance, 1))
        if fase == "verificando":
            total = max(estado.get("bytes_zip_total", 0), 1)
            return 90 + int(9 * min(estado.get("bytes_zip_leidos", 0) / total, 1))
        return estado.get("porcentaje", 0)

    # -- descubrimiento de tablas

    @classmethod
    def _descubrir(cls, db: Session) -> Dict[str, Any]:
        """Tablas recruiting_* del esquema real (en orden de dependencias) y las tablas compartidas que referencian."""
        insp = inspect(db.connection())
        nombres = sorted(t for t in insp.get_table_names() if t.startswith(cls.PREFIJO_TABLAS))
        columnas = {t: [c["name"] for c in insp.get_columns(t)] for t in nombres}
        dependencias: Dict[str, set] = {t: set() for t in nombres}
        referencias: List[Tuple[str, str, str, str, Optional[str]]] = []  # (tabla, columna, tabla_ref, columna_ref, filtro)
        for t in nombres:
            for fk in insp.get_foreign_keys(t):
                destino = fk["referred_table"]
                if destino in dependencias:
                    if destino != t:
                        dependencias[t].add(destino)
                else:
                    for col, col_ref in zip(fk["constrained_columns"], fk["referred_columns"]):
                        referencias.append((t, col, destino, col_ref, None))
        orden: List[str] = []
        pendientes = dict(dependencias)
        while pendientes:
            listas = sorted(t for t, deps in pendientes.items() if deps <= set(orden))
            if not listas:  # ciclo: se agregan las restantes igualmente (restore.sql las carga sin depender del orden)
                listas = sorted(pendientes)
            for t in listas:
                orden.append(t)
                pendientes.pop(t)

        compartidas: Dict[str, Dict[str, Any]] = {}
        notif_cols: List[str] = []
        if cls.TABLA_NOTIFICACIONES in insp.get_table_names():
            notif_cols = [c["name"] for c in insp.get_columns(cls.TABLA_NOTIFICACIONES)]
            for col in ("empresa_id", "usuario_id"):
                if col in notif_cols:
                    destino = "core_empresas" if col == "empresa_id" else "core_usuarios"
                    referencias.append((cls.TABLA_NOTIFICACIONES, col, destino, "id", cls.FILTRO_NOTIFICACIONES))
        for destino in sorted({r[2] for r in referencias}):
            cols_db = [c["name"] for c in insp.get_columns(destino)]
            cols_nulas = {c["name"]: (not c["nullable"] and c.get("default") is None) for c in insp.get_columns(destino)}
            omitidas = [c for c in cols_db if cls.PATRON_COLUMNA_SENSIBLE.search(c)]
            compartidas[destino] = {
                "columnas": [c for c in cols_db if c not in omitidas],
                "omitidas": omitidas,
                "omitidas_obligatorias": [c for c in omitidas if cols_nulas[c]],
                "referencias": [r for r in referencias if r[2] == destino],
                "clave": (insp.get_pk_constraint(destino).get("constrained_columns") or ["id"])[0],
            }
        # Tablas ajenas al prefijo de las que se respaldan solo las filas de Recruiting (notificaciones internas)
        filtradas = {cls.TABLA_NOTIFICACIONES: {"columnas": notif_cols, "omitidas_obligatorias": [], "filtro": cls.FILTRO_NOTIFICACIONES}} if notif_cols else {}
        return {"orden": orden, "columnas": columnas, "compartidas": compartidas, "filtradas": filtradas, "insp": insp}

    @classmethod
    def _consulta_compartida(cls, tabla: str, info: Dict[str, Any]) -> str:
        subconsultas = []
        for t, col, _destino, _col_ref, filtro in info["referencias"]:
            donde = f"{_ident(col)} IS NOT NULL" + (f" AND {filtro}" if filtro else "")
            subconsultas.append(f"SELECT {_ident(col)} FROM {_ident(t)} WHERE {donde}")
        columnas = ", ".join(_ident(c) for c in info["columnas"])
        return f"SELECT {columnas} FROM {_ident(tabla)} WHERE {_ident(info['clave'])} IN ({' UNION '.join(subconsultas)}) ORDER BY {_ident(info['clave'])}"

    @classmethod
    def _consulta_recruiting(cls, tabla: str, columnas: List[str]) -> str:
        return f"SELECT {', '.join(_ident(c) for c in columnas)} FROM {_ident(tabla)}"

    # -- generacion

    @classmethod
    def _generar(cls, db: Session, estado: Dict[str, Any], ruta_parcial: str) -> None:
        inicio = datetime.now(timezone.utc)
        db.execute(text("SELECT 1"))  # fija la instantanea: base y listado de archivos corresponden al mismo instante
        snapshot_utc = datetime.now(timezone.utc)
        desc = cls._descubrir(db)

        # Archivos de CV (mismo criterio que la pantalla: solo archivos regulares, no ocultos, sin enlaces simbolicos)
        listado: List[Tuple[str, str, int, float]] = []  # (carpeta, nombre, bytes, mtime)
        for carpeta in ArchivoCVService.CARPETAS:
            for a in sorted(ArchivoCVService._inspeccionar(carpeta), key=lambda x: x["nombre"]):
                listado.append((carpeta, a["nombre"], a["bytes"], a["mtime"], a["ruta"]))
        indice_motivos = os.path.join(ArchivoCVService._ruta_carpeta(CandidatoService.CARPETA_CV_ERRORES), CandidatoService.ARCHIVO_MOTIVOS_ERRORES)
        if os.path.isfile(indice_motivos) and not os.path.islink(indice_motivos):
            st = os.stat(indice_motivos)
            listado.append((CandidatoService.CARPETA_CV_ERRORES, CandidatoService.ARCHIVO_MOTIVOS_ERRORES, st.st_size, st.st_mtime, indice_motivos))

        tablas_total = len(desc["orden"]) + len(desc["compartidas"]) + len(desc["filtradas"])
        cls._actualizar(
            estado, forzar=True, estado="generando", fase="base_de_datos", tablas_total=tablas_total, tablas_procesadas=0,
            archivos_total=len(listado), archivos_procesados=0, bytes_total=sum(x[2] for x in listado), bytes_procesados=0,
            mensaje=f"Exportando la base de datos (0 de {tablas_total} tablas)...",
        )

        manifest_tablas: Dict[str, Any] = {}
        advertencias: List[str] = []
        piezas: Dict[str, Tuple[str, int]] = {}  # ruta en el ZIP -> (sha256, bytes): lo que la verificacion debe encontrar

        with zipfile.ZipFile(ruta_parcial, "w", allowZip64=True) as zf:
            cursor = db.connection().connection.cursor()
            try:
                # --- A. Base de datos
                def exportar(tabla: str, consulta: str, columnas: List[str], alcance: str) -> None:
                    nombre_zip = f"database/{tabla}.csv"
                    zinfo = zipfile.ZipInfo(nombre_zip, date_time=snapshot_utc.timetuple()[:6])
                    zinfo.compress_type = zipfile.ZIP_DEFLATED
                    zinfo.external_attr = 0o600 << 16
                    with zf.open(zinfo, "w", force_zip64=True) as destino:
                        escritor = _EscritorConHash(destino)
                        cursor.copy_expert(f"COPY ({consulta}) TO STDOUT WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')", escritor)
                    registros = cursor.rowcount
                    contados = db.execute(text(f"SELECT count(*) FROM ({consulta}) AS q")).scalar()
                    if registros != contados:
                        raise RuntimeError(f"Inconsistencia al exportar {tabla}: COPY={registros} count={contados}")
                    manifest_tablas[tabla] = {
                        "registros": registros, "archivo": nombre_zip, "bytes": escritor.bytes, "sha256": escritor.sha256.hexdigest(),
                        "columnas": columnas, "alcance": alcance,
                    }
                    piezas[nombre_zip] = (escritor.sha256.hexdigest(), escritor.bytes)
                    cls._actualizar(
                        estado, tablas_procesadas=estado["tablas_procesadas"] + 1,
                        mensaje=f"Exportando la base de datos ({estado['tablas_procesadas'] + 1} de {tablas_total} tablas)...",
                    )
                    estado["porcentaje"] = cls._porcentaje(estado)

                for tabla in desc["compartidas"]:
                    info = desc["compartidas"][tabla]
                    exportar(tabla, cls._consulta_compartida(tabla, info), info["columnas"],
                             "filas referenciadas por Recruiting" + (f"; columnas no respaldadas: {', '.join(info['omitidas'])}" if info["omitidas"] else ""))
                for tabla, info in desc["filtradas"].items():
                    exportar(tabla, f"{cls._consulta_recruiting(tabla, info['columnas'])} WHERE {info['filtro']}", info["columnas"],
                             f"solo filas de Recruiting: {info['filtro']}")
                for tabla in desc["orden"]:
                    exportar(tabla, cls._consulta_recruiting(tabla, desc["columnas"][tabla]), desc["columnas"][tabla], "completa")

                claves_storage = cls._claves_storage(db)
                secuencias = cls._secuencias(db, desc)
                externas = cls._referencias_externas(db)
                script = cls._script_restauracion(desc, secuencias).encode("utf-8")
                zinfo = zipfile.ZipInfo("database/restore.sql", date_time=snapshot_utc.timetuple()[:6])
                zinfo.compress_type = zipfile.ZIP_DEFLATED
                zinfo.external_attr = 0o600 << 16
                zf.writestr(zinfo, script)
                sha_script = hashlib.sha256(script).hexdigest()
                piezas["database/restore.sql"] = (sha_script, len(script))
            finally:
                cursor.close()
            cls._liberar_instantanea(db)  # la base ya no se necesita: no se mantiene abierta durante la copia de archivos

            # --- B. Archivos de CV (por bloques; los originales solo se abren para lectura)
            cls._actualizar(estado, forzar=True, fase="archivos", mensaje=f"Copiando CV (0 de {len(listado)})...")
            estado["porcentaje"] = cls._porcentaje(estado)
            carpetas = {c: {"cantidad": 0, "bytes": 0} for c in ArchivoCVService.CARPETAS}
            archivos_manifest: List[Dict[str, Any]] = []
            for carpeta in ArchivoCVService.CARPETAS:
                zf.writestr(zipfile.ZipInfo(f"{carpeta}/"), b"")  # la estructura de carpetas se conserva aunque esten vacias
            for i, (carpeta, nombre, _tam, _mtime, ruta) in enumerate(listado, start=1):
                try:
                    entrada = cls._copiar_archivo(zf, carpeta, nombre, ruta, estado)
                except FileNotFoundError:
                    advertencias.append(f"{carpeta}/{nombre}: el archivo ya no existía al copiarlo (omitido)")
                    continue
                archivos_manifest.append(entrada)
                piezas[entrada["ruta"]] = (entrada["sha256"], entrada["bytes"])
                if not nombre.startswith("."):
                    carpetas[carpeta]["cantidad"] += 1
                carpetas[carpeta]["bytes"] += entrada["bytes"]
                if entrada.get("modificado_durante_la_copia"):
                    advertencias.append(f"{carpeta}/{nombre}: cambió mientras se copiaba; el hash corresponde a lo copiado")
                cls._actualizar(estado, archivos_procesados=i, mensaje=f"Copiando CV ({i} de {len(listado)})...")
                estado["porcentaje"] = cls._porcentaje(estado)

            # --- B2. Archivos del storage referenciados por la base (cv_url, adjuntos de etapas, duplicados pendientes)
            storage = cls._copiar_storage(zf, claves_storage, estado, piezas, advertencias)

            # --- C. Manifest (ultima pieza: contiene los hashes de todas las demas)
            total_registros = sum(t["registros"] for t in manifest_tablas.values())
            bytes_archivos = sum(c["bytes"] for c in carpetas.values())
            bytes_bd = sum(t["bytes"] for t in manifest_tablas.values()) + len(script)
            manifest = {
                "formato": cls.FORMATO, "version_backup": cls.VERSION_BACKUP, "generado_utc": inicio.isoformat(),
                "instantanea_base_utc": snapshot_utc.isoformat(), "generado_por": estado.get("usuario"),
                "base_de_datos": {
                    "motor": "postgresql", "tablas": manifest_tablas, "total_tablas": len(manifest_tablas), "total_registros": total_registros,
                    "script_restauracion": {"archivo": "database/restore.sql", "bytes": len(script), "sha256": sha_script},
                    "exclusiones": "Las tablas compartidas solo incluyen las filas referenciadas por Recruiting, sin contraseñas, hashes, tokens, secretos TOTP ni credenciales.",
                },
                "archivos_storage": storage,
                "archivos_cv": {
                    "carpetas": carpetas, "total_archivos": sum(c["cantidad"] for c in carpetas.values()),
                    "total_bytes": bytes_archivos, "archivos": archivos_manifest,
                },
                "tamano_total_sin_comprimir_bytes": bytes_archivos + bytes_bd + storage["bytes"],
                "referencias_a_archivos_no_incluidos": externas,
                "advertencias": advertencias,
                "restauracion": (
                    "1) Extraer el ZIP. 2) Con el esquema ya creado, ejecutar desde la carpeta extraida: "
                    "psql \"<DATABASE_URL>\" -v ON_ERROR_STOP=1 -f database/restore.sql (inserta sin pisar registros existentes). "
                    "3) Copiar el contenido de cv_procesados_ok, cv_duplicados y cv_errores a las mismas carpetas dentro de CV_STORAGE_DIR."
                ),
            }
            datos = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
            zinfo = zipfile.ZipInfo("manifest.json", date_time=snapshot_utc.timetuple()[:6])
            zinfo.compress_type = zipfile.ZIP_DEFLATED
            zinfo.external_attr = 0o600 << 16
            zf.writestr(zinfo, datos)
        estado["_piezas"] = piezas
        estado["_manifest"] = manifest

    @classmethod
    def _copiar_archivo(cls, zf: zipfile.ZipFile, carpeta: str, nombre: str, ruta: str, estado: Dict[str, Any]) -> Dict[str, Any]:
        """Agrega un CV al ZIP por bloques conservando nombre, fecha y tamano; devuelve su entrada de manifest."""
        arcname = f"{carpeta}/{nombre}"
        zinfo = zipfile.ZipInfo.from_file(ruta, arcname)
        zinfo.external_attr = 0o600 << 16
        zinfo.compress_type = zipfile.ZIP_STORED if nombre.lower().endswith(_EXTENSIONES_YA_COMPRIMIDAS) else zipfile.ZIP_DEFLATED
        sha = hashlib.sha256()
        copiados = 0
        with open(ruta, "rb") as origen, zf.open(zinfo, "w", force_zip64=zinfo.file_size > (1 << 30)) as destino:
            while True:
                bloque = origen.read(TAMANO_BLOQUE)
                if not bloque:
                    break
                sha.update(bloque)
                destino.write(bloque)
                copiados += len(bloque)
                estado["bytes_procesados"] = estado.get("bytes_procesados", 0) + len(bloque)
                estado["porcentaje"] = cls._porcentaje(estado)
                cls._actualizar(estado)
        entrada = {
            "ruta": arcname, "bytes": copiados, "sha256": sha.hexdigest(),
            "modificado_utc": datetime.fromtimestamp(os.stat(ruta).st_mtime, tz=timezone.utc).isoformat(),
        }
        if copiados != zinfo.file_size:
            entrada["modificado_durante_la_copia"] = True
        return entrada

    @classmethod
    def clave_storage_valida(cls, clave: Any) -> bool:
        """Clave relativa del storage de Recruiting: sin rutas absolutas, '..', barras invertidas ni caracteres de control."""
        return (
            isinstance(clave, str) and clave.startswith(cls.PREFIJO_STORAGE) and len(clave) <= 500 and "\\" not in clave
            and not any(ord(c) < 32 for c in clave) and not any(p in ("", ".", "..") for p in clave.split("/")) and ":" not in clave
        )

    @classmethod
    def _claves_storage(cls, db: Session) -> List[str]:
        """Claves de storage referenciadas por la base (distintas, ordenadas) dentro de la instantanea del backup."""
        claves = set()
        for tabla, columna in cls.COLUMNAS_STORAGE:
            try:
                with db.begin_nested():
                    filas = db.execute(text(f"SELECT DISTINCT {_ident(columna)} FROM {_ident(tabla)} WHERE {_ident(columna)} IS NOT NULL AND {_ident(columna)} <> ''")).fetchall()
            except Exception:
                continue  # tabla inexistente en un esquema anterior
            claves.update(f[0] for f in filas)
        return sorted(claves)

    @classmethod
    def _copiar_storage(cls, zf: zipfile.ZipFile, claves: List[str], estado: Dict[str, Any], piezas: Dict[str, Tuple[str, int]], advertencias: List[str]) -> Dict[str, Any]:
        """Agrega al ZIP (storage/NNNNNN.bin) los archivos del storage referenciados por la base. Solo claves de Recruiting."""
        from backend.core.storage import cloud_storage

        archivos: List[Dict[str, Any]] = []
        faltantes: List[str] = []
        total_bytes = 0
        for i, clave in enumerate(claves, start=1):
            if not cls.clave_storage_valida(clave):
                advertencias.append(f"Clave de storage fuera de Recruiting omitida: {clave[:80]}")
                continue
            try:
                datos = cloud_storage.download(clave)
            except Exception:
                faltantes.append(clave)
                continue
            ruta = f"storage/{len(archivos) + 1:06d}.bin"
            zinfo = zipfile.ZipInfo(ruta, date_time=datetime.now(timezone.utc).timetuple()[:6])
            zinfo.compress_type = zipfile.ZIP_DEFLATED
            zinfo.external_attr = 0o600 << 16
            zf.writestr(zinfo, datos)
            sha = hashlib.sha256(datos).hexdigest()
            archivos.append({"clave": clave, "ruta": ruta, "bytes": len(datos), "sha256": sha})
            piezas[ruta] = (sha, len(datos))
            total_bytes += len(datos)
            cls._actualizar(estado, mensaje=f"Copiando archivos del almacenamiento ({i} de {len(claves)})...")
        if faltantes:
            advertencias.append(f"{len(faltantes)} archivo(s) referenciados por la base no existian en el almacenamiento y no se incluyeron")
        return {"total": len(archivos), "bytes": total_bytes, "archivos": archivos, "faltantes": faltantes}

    @classmethod
    def _secuencias(cls, db: Session, desc: Dict[str, Any]) -> List[Tuple[str, str, str]]:
        """(tabla, columna, secuencia) de las claves enteras autoincrementales de Recruiting, para reajustarlas al restaurar."""
        resultado = []
        for tabla in desc["orden"]:
            pk = desc["insp"].get_pk_constraint(tabla).get("constrained_columns") or []
            if len(pk) != 1:
                continue
            secuencia = db.execute(text("SELECT pg_get_serial_sequence(:t, :c)"), {"t": _ident(tabla), "c": pk[0]}).scalar()
            if secuencia:
                resultado.append((tabla, pk[0], secuencia))
        return resultado

    @classmethod
    def _referencias_externas(cls, db: Session) -> Dict[str, Any]:
        """Cuenta los archivos que la base referencia fuera de las 3 carpetas (almacenamiento de candidatos y adjuntos).

        No se incluyen en este backup: se informa su cantidad para que el alcance quede documentado.
        """
        consultas = {
            "cv_vinculados_a_candidatos": "SELECT count(*) FROM recruiting_candidatos WHERE cv_url IS NOT NULL AND cv_url <> ''",
            "adjuntos_de_etapas": "SELECT count(*) FROM recruiting_etapa_archivos WHERE ruta_archivo IS NOT NULL",
            "cv_de_duplicados_pendientes": "SELECT count(*) FROM recruiting_candidatos_duplicados WHERE archivo_temp_key IS NOT NULL",
        }
        resultado: Dict[str, Any] = {}
        for clave, sql in consultas.items():
            try:
                with db.begin_nested():
                    resultado[clave] = db.execute(text(sql)).scalar()
            except Exception:
                resultado[clave] = None
        resultado["nota"] = "Conteos informativos: estos archivos del almacenamiento se incluyen en storage/ (ver archivos_storage del manifest)."
        return resultado

    @classmethod
    def _script_restauracion(cls, desc: Dict[str, Any], secuencias: List[Tuple[str, str, str]]) -> str:
        """restore.sql: carga cada CSV en una tabla temporal y la inserta sin pisar registros existentes (ON CONFLICT DO NOTHING)."""
        lineas = [
            "-- Restauracion de Recruiting. Ejecutar desde la carpeta donde se extrajo el ZIP:",
            "--   psql \"<DATABASE_URL>\" -v ON_ERROR_STOP=1 -f database/restore.sql",
            "-- Requiere el esquema ya creado (arranque normal de la aplicacion). No elimina ni modifica registros existentes.",
            "BEGIN;",
        ]
        tablas = list(desc["compartidas"]) + list(desc["filtradas"]) + list(desc["orden"])
        for tabla in tablas:
            comp = desc["compartidas"].get(tabla) or desc["filtradas"].get(tabla)
            columnas = comp["columnas"] if comp else desc["columnas"][tabla]
            lista = ", ".join(_ident(c) for c in columnas)
            destino_cols, origen_cols = lista, lista
            if comp and comp["omitidas_obligatorias"]:
                extra = []
                for c in comp["omitidas_obligatorias"]:
                    valor = cls.VALORES_COLUMNAS_OMITIDAS.get(c, "''")
                    extra.append((c, valor))
                destino_cols = lista + ", " + ", ".join(_ident(c) for c, _ in extra)
                origen_cols = lista + ", " + ", ".join(v for _, v in extra)
            lineas += [
                f"-- {tabla}",
                f"CREATE TEMP TABLE _restore AS SELECT {lista} FROM {_ident(tabla)} WITH NO DATA;",
                f"\\copy _restore ({lista}) FROM 'database/{tabla}.csv' WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')",
                f"INSERT INTO {_ident(tabla)} ({destino_cols}) SELECT {origen_cols} FROM _restore ON CONFLICT DO NOTHING;",
                "DROP TABLE _restore;",
            ]
        for tabla, columna, secuencia in secuencias:
            lineas.append(
                f"SELECT setval('{secuencia}', (SELECT MAX({_ident(columna)}) FROM {_ident(tabla)})) "
                f"WHERE EXISTS (SELECT 1 FROM {_ident(tabla)});"
            )
        lineas.append("COMMIT;")
        return "\n".join(lineas) + "\n"

    # ------------------------------------------------------------------ verificacion y publicacion

    @classmethod
    def _verificar_y_publicar(cls, estado: Dict[str, Any], parcial: str, final: str) -> None:
        """Relee el ZIP completo (CRC + SHA-256 de cada pieza contra lo escrito y contra el manifest) y recien entonces lo publica."""
        piezas: Dict[str, Tuple[str, int]] = estado.pop("_piezas")
        manifest: Dict[str, Any] = estado.pop("_manifest")
        tamano_zip = os.path.getsize(parcial)
        cls._actualizar(
            estado, forzar=True, estado="verificando", fase="verificando", bytes_zip_total=tamano_zip, bytes_zip_leidos=0,
            mensaje="Verificando la integridad del backup...",
        )
        with zipfile.ZipFile(parcial, "r") as zf:
            if zf.testzip() is not None:
                raise RuntimeError("El ZIP generado tiene entradas dañadas")
            nombres = {i.filename for i in zf.infolist() if not i.is_dir()}
            if nombres != set(piezas) | {"manifest.json"}:
                raise RuntimeError("El contenido del ZIP no coincide con lo esperado")
            leidos = 0
            for ruta, (sha_esperado, bytes_esperados) in piezas.items():
                sha, n = hashlib.sha256(), 0
                with zf.open(ruta) as f:
                    while True:
                        bloque = f.read(TAMANO_BLOQUE)
                        if not bloque:
                            break
                        sha.update(bloque)
                        n += len(bloque)
                        leidos += len(bloque)
                        estado["bytes_zip_leidos"] = leidos
                        estado["porcentaje"] = cls._porcentaje(estado)
                        cls._actualizar(estado)
                if sha.hexdigest() != sha_esperado or n != bytes_esperados:
                    raise RuntimeError(f"Verificación fallida en {ruta}")
            en_zip = json.loads(zf.read("manifest.json").decode("utf-8"))
            if en_zip != manifest:
                raise RuntimeError("El manifest del ZIP no coincide con el generado")
            for t, datos in en_zip["base_de_datos"]["tablas"].items():
                if piezas[datos["archivo"]][0] != datos["sha256"]:
                    raise RuntimeError(f"Hash del manifest incorrecto para {t}")
            for a in en_zip["archivos_cv"]["archivos"]:
                if piezas[a["ruta"]] != (a["sha256"], a["bytes"]):
                    raise RuntimeError(f"Hash del manifest incorrecto para {a['ruta']}")

        sha_zip = hashlib.sha256()
        with open(parcial, "rb") as f:
            for bloque in iter(lambda: f.read(TAMANO_BLOQUE), b""):
                sha_zip.update(bloque)
        os.replace(parcial, final)  # recien ahora el ZIP queda disponible
        cls._actualizar(
            estado, forzar=True, estado="finalizado", fase="finalizado", porcentaje=100, nombre_archivo=os.path.basename(final),
            tamano_bytes=tamano_zip, tamano=ArchivoCVService.formatear_tamano(tamano_zip), sha256=sha_zip.hexdigest(),
            mensaje="Backup completado y verificado. Ya podés descargarlo.", finalizado_at=datetime.now(timezone.utc).isoformat(),
        )
