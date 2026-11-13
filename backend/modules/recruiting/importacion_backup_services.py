"""
Importacion (restauracion) de un backup completo de Recruiting (Parametros > Archivos de CV > "Importar").

Solo acepta ZIP generados por BackupRecruitingService (formato RECLUIT_BACKUP). Nunca ejecuta SQL del ZIP: restore.sql solo se verifica
(hash) y no se usa; la base se restaura con COPY sobre tablas y columnas validadas contra el esquema actual.

Flujo:
  1. subir():      el ZIP se guarda por bloques en un directorio privado y se valida en segundo plano (sin tocar nada del sistema):
                   estructura y nombres seguros, manifest, SHA-256 y tamano de cada pieza, conteos de registros y archivos,
                   version y compatibilidad con el esquema actual. Resultado: vista previa + limitaciones (estado "validado").
  2. confirmar():  requiere confirmacion explicita (texto) y la aceptacion de las limitaciones. Toma el bloqueo global, comprueba que no
                   haya cargas masivas ni otro proceso y que alcance el espacio, y restaura en segundo plano:
                   backup de seguridad -> CV a un directorio temporal verificado -> base en un SAVEPOINT -> intercambio de carpetas
                   -> commit. Cualquier error revierte la base y devuelve las carpetas originales.

Alcance: todas las tablas recruiting_*, mas las filas de core_empresas / core_usuarios que referencian (solo se insertan las que faltan:
nunca se modifican usuarios existentes) y las notificaciones internas de Recruiting. No toca otros modulos ni credenciales.
"""
import codecs
import csv
import hashlib
import json
import logging
import os
import re
import shutil
import stat
import threading
import time
import uuid
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional, Tuple

from fastapi import HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.modules.recruiting.backup_services import BackupRecruitingService, _ident
from backend.modules.recruiting.parametros_services import ArchivoCVService
from backend.modules.recruiting.services import MENSAJE_ERROR_INTERNO, CandidatoService
from backend.modules.usuarios.models import Usuario

logger = logging.getLogger(__name__)

TAMANO_BLOQUE = 1024 * 1024
TEXTO_CONFIRMACION = "REEMPLAZAR"
EXTENSIONES_PROHIBIDAS = (
    ".exe", ".bat", ".cmd", ".com", ".scr", ".ps1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".msi", ".dll", ".jar", ".sh",
    ".py", ".php", ".pl", ".lnk", ".reg", ".hta", ".cpl", ".sys", ".docm", ".xlsm", ".pptm",
)
PATRON_TABLA = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,62}$")
PATRON_SHA256 = re.compile(r"^[0-9a-f]{64}$")
PREFIJO_TRABAJO = ".importacion_"
ARCHIVO_JOURNAL = "journal.json"
COLUMNA_STORAGE_POR_TABLA = dict(BackupRecruitingService.COLUMNAS_STORAGE)


class _Rechazo(Exception):
    """El backup no es valido o no se puede restaurar; el mensaje es apto para mostrar al usuario."""


class _LectorConHash:
    """Lectura por bloques de una pieza del ZIP calculando SHA-256 y tamano (sirve de archivo de origen para COPY)."""

    def __init__(self, origen, progreso=None):
        self._origen = origen
        self._progreso = progreso
        self.sha256 = hashlib.sha256()
        self.bytes = 0

    def read(self, n: int = -1) -> bytes:
        datos = self._origen.read(n if n and n > 0 else TAMANO_BLOQUE)
        if datos:
            self.sha256.update(datos)
            self.bytes += len(datos)
            if self._progreso:
                self._progreso(len(datos))
        return datos


def _lineas(lector: _LectorConHash) -> Iterator[str]:
    """Lineas UTF-8 (separadas por \\n) de una pieza, sin cargarla completa en memoria; los saltos dentro de comillas los resuelve csv."""
    decodificador = codecs.getincrementaldecoder("utf-8")()
    resto = ""
    while True:
        bloque = lector.read(TAMANO_BLOQUE)
        if not bloque:
            break
        resto += decodificador.decode(bloque)
        partes = resto.split("\n")
        resto = partes.pop()
        for p in partes:
            yield p + "\n"
    resto += decodificador.decode(b"", final=True)
    if resto:
        yield resto


class ImportarBackupRecruitingService:
    ESTADOS_ACTIVOS = ("validando", "restaurando")
    CADUCIDAD_LATIDO_SEGUNDOS = 180
    RETENCION_SEGUNDOS = 24 * 3600
    MAX_ENTRADAS = 500_000
    MAX_MANIFEST_BYTES = 64 * 1024 * 1024
    MAX_ZIP_BYTES = int(os.getenv("BACKUP_IMPORT_MAX_BYTES", str(50 * 1024 ** 3)))
    MARGEN_ESPACIO_BYTES = 64 * 1024 * 1024
    VERSIONES_SOPORTADAS = ("1.0", "1.1", "1.2")
    TABLAS_COMPARTIDAS = ("core_empresas", "core_usuarios")
    FRESCURA_LOTE_SEGUNDOS = 30 * 60

    # ------------------------------------------------------------------ directorio, estado y bloqueos

    @classmethod
    def _dir(cls) -> str:
        ruta = os.path.join(BackupRecruitingService._directorio(), "importaciones")
        os.makedirs(ruta, mode=0o700, exist_ok=True)
        return ruta

    @staticmethod
    def _id_valido(importacion_id: str) -> str:
        try:
            return str(uuid.UUID(str(importacion_id)))
        except ValueError:
            raise HTTPException(status_code=404, detail="Importación no encontrada.")

    @classmethod
    def _ruta(cls, importacion_id: str, sufijo: str) -> str:
        return os.path.join(cls._dir(), f"{cls._id_valido(importacion_id)}{sufijo}")

    @classmethod
    def _guardar(cls, st: Dict[str, Any]) -> None:
        ruta = cls._ruta(st["importacion_id"], ".json")
        st["actualizado_ts"] = time.time()
        tmp = f"{ruta}.{uuid.uuid4().hex}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({k: v for k, v in st.items() if not k.startswith("_")}, f)
        for intento in range(20):
            try:
                os.replace(tmp, ruta)
                break
            except PermissionError:
                if intento == 19:
                    os.remove(tmp)
                    raise
                time.sleep(0.05)
        for lock in (os.path.join(cls._dir(), "validacion.lock"), os.path.join(BackupRecruitingService._directorio(), "activo.lock")):
            try:  # latido de los bloqueos que esta importacion tenga tomados
                if os.path.exists(lock):
                    os.utime(lock)
            except OSError:
                pass

    @classmethod
    def _leer(cls, importacion_id: str) -> Dict[str, Any]:
        try:
            with open(cls._ruta(importacion_id, ".json"), "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="Importación no encontrada.")

    @classmethod
    def _actualizar(cls, st: Dict[str, Any], forzar: bool = False, **campos) -> None:
        st.update(campos)
        ahora = time.monotonic()
        if forzar or ahora - st.get("_ultima", 0) >= 0.5:
            st["_ultima"] = ahora
            cls._guardar(st)

    @classmethod
    def _publico(cls, st: Dict[str, Any]) -> Dict[str, Any]:
        claves = (
            "importacion_id", "estado", "fase", "porcentaje", "mensaje", "error", "nombre_original", "tamano_bytes", "tamano",
            "preview", "limitaciones", "avisos", "backup_seguridad", "resultado", "revertido", "iniciado_at", "finalizado_at",
        )
        publico = {k: st.get(k) for k in claves}
        publico["limitaciones"] = publico["limitaciones"] or []
        publico["avisos"] = publico["avisos"] or []
        return publico

    @staticmethod
    def _tomar(ruta: str, caducidad: int) -> bool:
        for _ in range(2):
            try:
                os.close(os.open(ruta, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
                return True
            except FileExistsError:
                try:
                    if time.time() - os.path.getmtime(ruta) <= caducidad:
                        return False
                    os.remove(ruta)  # bloqueo abandonado por un proceso interrumpido
                except OSError:
                    pass
        return False

    @staticmethod
    def _soltar(ruta: str) -> None:
        try:
            os.remove(ruta)
        except OSError:
            pass

    @classmethod
    def _limpiar(cls) -> None:
        """Elimina solo archivos propios de importaciones (ZIP, estados, parciales) vencidos y que no esten en curso."""
        ahora = time.time()
        for nombre in os.listdir(cls._dir()):
            ruta = os.path.join(cls._dir(), nombre)
            if not re.match(r"^[0-9a-f-]{36}\.(json|zip|zip\.partial|json\.[0-9a-f]+\.tmp)$", nombre) or not os.path.isfile(ruta) or os.path.islink(ruta):
                continue
            try:
                if ahora - os.path.getmtime(ruta) > cls.RETENCION_SEGUNDOS:
                    os.remove(ruta)
            except OSError as e:
                logger.warning(f"No se pudo eliminar el temporal de importacion {nombre}: {e}")

    @classmethod
    def restauracion_en_curso(cls) -> bool:
        """True si hay una restauracion en ejecucion (la usa la carga masiva de CV para no escribir mientras se reemplazan las carpetas)."""
        try:
            for nombre in os.listdir(cls._dir()):
                if re.match(r"^[0-9a-f-]{36}\.json$", nombre):
                    with open(os.path.join(cls._dir(), nombre), "r", encoding="utf-8") as f:
                        st = json.load(f)
                    if st.get("estado") == "restaurando" and time.time() - st.get("actualizado_ts", 0) <= cls.CADUCIDAD_LATIDO_SEGUNDOS:
                        return True
        except Exception:
            return False
        return False

    @classmethod
    def _recuperar_sin_fallar(cls) -> None:
        try:
            cls.recuperar_interrumpidas()
        except Exception:
            logger.error("Fallo la revision de restauraciones interrumpidas", exc_info=True)

    @staticmethod
    def _lanzar(funcion) -> None:
        threading.Thread(target=funcion, daemon=True).start()

    # ------------------------------------------------------------------ API: subir y validar

    @classmethod
    def subir(cls, current_user: Usuario, archivo: UploadFile) -> Dict[str, Any]:
        BackupRecruitingService.verificar_acceso(current_user)
        nombre = os.path.basename((archivo.filename or "").replace("\\", "/"))
        if not nombre.lower().endswith(".zip"):
            raise HTTPException(status_code=400, detail="Seleccioná un backup en formato .zip generado por RECLUIT.")
        cls._limpiar()
        cls._recuperar_sin_fallar()
        if not cls._tomar(os.path.join(cls._dir(), "validacion.lock"), cls.CADUCIDAD_LATIDO_SEGUNDOS):
            raise HTTPException(status_code=409, detail="Ya hay una importación en validación. Esperá a que termine.")
        importacion_id = str(uuid.uuid4())
        parcial = cls._ruta(importacion_id, ".zip.partial")
        final = cls._ruta(importacion_id, ".zip")
        try:
            cls._guardar_subida(archivo, parcial)
            os.replace(parcial, final)
            st = {
                "importacion_id": importacion_id, "estado": "validando", "fase": "validando", "porcentaje": 0,
                "mensaje": "Validando el backup...", "error": None, "nombre_original": nombre,
                "tamano_bytes": os.path.getsize(final), "tamano": ArchivoCVService.formatear_tamano(os.path.getsize(final)),
                "preview": None, "limitaciones": [], "avisos": [], "backup_seguridad": None, "resultado": None, "revertido": None,
                "iniciado_at": datetime.now(timezone.utc).isoformat(), "finalizado_at": None, "usuario": current_user.email,
            }
            cls._guardar(st)
            cls._lanzar(lambda: cls._validar_en_segundo_plano(st))
        except HTTPException:
            cls._eliminar_archivos(importacion_id)
            cls._soltar(os.path.join(cls._dir(), "validacion.lock"))
            raise
        except Exception:
            cls._eliminar_archivos(importacion_id)
            cls._soltar(os.path.join(cls._dir(), "validacion.lock"))
            logger.error("No se pudo recibir el backup a importar", exc_info=True)
            raise HTTPException(status_code=500, detail=MENSAJE_ERROR_INTERNO)
        return cls._publico(st)

    @classmethod
    def _guardar_subida(cls, archivo: UploadFile, destino: str) -> None:
        """Guarda el ZIP subido por bloques controlando tamano maximo y espacio libre; solo acepta firma ZIP."""
        escritos = 0
        with open(destino, "xb") as out:
            while True:
                bloque = archivo.file.read(TAMANO_BLOQUE)
                if not bloque:
                    break
                if escritos == 0 and not bloque.startswith((b"PK\x03\x04", b"PK\x05\x06")):
                    raise HTTPException(status_code=400, detail="El archivo no es un ZIP válido.")
                escritos += len(bloque)
                if escritos > cls.MAX_ZIP_BYTES:
                    raise HTTPException(status_code=413, detail="El backup supera el tamaño máximo permitido para importar.")
                if (escritos // TAMANO_BLOQUE) % 32 == 0 and shutil.disk_usage(os.path.dirname(destino)).free < cls.MARGEN_ESPACIO_BYTES:
                    raise HTTPException(status_code=507, detail="No hay espacio suficiente en el servidor para recibir el backup.")
                out.write(bloque)
        if escritos == 0:
            raise HTTPException(status_code=400, detail="El archivo está vacío.")

    @classmethod
    def _eliminar_archivos(cls, importacion_id: str) -> None:
        for sufijo in (".zip.partial", ".zip"):
            try:
                os.remove(cls._ruta(importacion_id, sufijo))
            except (OSError, HTTPException):
                pass

    @classmethod
    def _validar_en_segundo_plano(cls, st: Dict[str, Any]) -> None:
        try:
            ruta = cls._ruta(st["importacion_id"], ".zip")
            with cls._sesion_esquema() as db:
                analisis = cls._analizar(ruta, db, st)
            estado = os.stat(ruta)
            cls._actualizar(
                st, forzar=True, estado="validado", fase="validado", porcentaje=100, preview=analisis["preview"],
                limitaciones=analisis["limitaciones"], avisos=analisis["avisos"], manifest_sha256=analisis["manifest_sha256"],
                zip_size=estado.st_size, zip_mtime_ns=estado.st_mtime_ns, error=None,
                mensaje="Backup validado. Revisá la vista previa antes de restaurar.",
            )
        except _Rechazo as e:
            cls._eliminar_archivos(st["importacion_id"])
            cls._actualizar(st, forzar=True, estado="rechazado", fase="rechazado", mensaje=str(e), error=str(e),
                            finalizado_at=datetime.now(timezone.utc).isoformat())
        except Exception:
            logger.error("Fallo la validacion del backup a importar", exc_info=True)
            cls._eliminar_archivos(st["importacion_id"])
            cls._actualizar(st, forzar=True, estado="error", fase="error", mensaje="No se pudo validar el backup.",
                            error=MENSAJE_ERROR_INTERNO, finalizado_at=datetime.now(timezone.utc).isoformat())
        finally:
            cls._soltar(os.path.join(cls._dir(), "validacion.lock"))

    @classmethod
    @contextmanager
    def _sesion_esquema(cls) -> Iterator[Session]:
        with BackupRecruitingService._sesion_de_lectura() as db:
            yield db

    @classmethod
    def obtener_estado(cls, current_user: Usuario, importacion_id: str) -> Dict[str, Any]:
        BackupRecruitingService.verificar_acceso(current_user)
        st = cls._leer(importacion_id)
        if st.get("estado") in cls.ESTADOS_ACTIVOS and time.time() - st.get("actualizado_ts", 0) > cls.CADUCIDAD_LATIDO_SEGUNDOS:
            st.update({"estado": "error", "mensaje": "La importación se interrumpió. Revisá el estado de Recruiting y reintentá.", "error": "interrumpido"})
        if st.get("estado") == "restaurando" and st.get("fase") == "respaldo_seguridad" and st.get("backup_id_seguridad"):
            try:  # avance real del backup de seguridad (0-30 % de la restauracion)
                b = BackupRecruitingService._leer_estado(st["backup_id_seguridad"])
                st["porcentaje"] = max(st.get("porcentaje", 0), min(30, int(b.get("porcentaje", 0) * 0.3)))
            except HTTPException:
                pass
        return cls._publico(st)

    @classmethod
    def descartar(cls, current_user: Usuario, importacion_id: str) -> Dict[str, Any]:
        """Elimina el ZIP subido de una importacion que todavia no se esta ejecutando."""
        BackupRecruitingService.verificar_acceso(current_user)
        st = cls._leer(importacion_id)
        if st.get("estado") in cls.ESTADOS_ACTIVOS:
            raise HTTPException(status_code=409, detail="La importación está en curso y no se puede descartar.")
        cls._eliminar_archivos(st["importacion_id"])
        cls._soltar(cls._ruta(st["importacion_id"], ".json"))
        return {"ok": True}

    # ------------------------------------------------------------------ validacion

    @classmethod
    def _ruta_permitida(cls, nombre: str) -> Tuple[str, ...]:
        """Clasifica el nombre de una entrada del ZIP; rechaza todo lo que no sea exactamente el formato del backup."""
        if (
            not nombre or len(nombre) > 400 or nombre.startswith(("/", "\\")) or "\\" in nombre or ":" in nombre
            or any(ord(c) < 32 for c in nombre) or any(p in ("..", ".") for p in nombre.split("/"))
        ):
            raise _Rechazo("El backup contiene rutas no permitidas.")
        if nombre == "manifest.json":
            return ("manifest",)
        if nombre == "database/restore.sql":
            return ("sql",)
        partes = nombre.split("/")
        if len(partes) == 2 and partes[0] == "database" and partes[1].endswith(".csv") and PATRON_TABLA.match(partes[1][:-4]):
            return ("csv", partes[1][:-4])
        if len(partes) == 2 and partes[0] == "storage" and re.match(r"^\d{6}\.bin$", partes[1]):
            return ("storage", nombre)
        if len(partes) == 2 and partes[1] == "" and partes[0] in ArchivoCVService.CARPETAS:
            return ("dir", partes[0])
        if len(partes) == 2 and partes[0] in ArchivoCVService.CARPETAS and partes[1]:
            archivo = partes[1]
            indice = partes[0] == CandidatoService.CARPETA_CV_ERRORES and archivo == CandidatoService.ARCHIVO_MOTIVOS_ERRORES
            if not (indice or ArchivoCVService._nombre_valido(archivo)):
                raise _Rechazo("El backup contiene nombres de archivo no permitidos.")
            if os.path.splitext(archivo.lower())[1] in EXTENSIONES_PROHIBIDAS:
                raise _Rechazo("El backup contiene archivos ejecutables o de tipo no permitido.")
            return ("cv", partes[0], archivo)
        raise _Rechazo("El backup contiene archivos que no corresponden al formato de RECLUIT.")

    @classmethod
    def _analizar(cls, ruta_zip: str, db: Session, st: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Valida todo el ZIP sin modificar nada. Devuelve vista previa, limitaciones y avisos o lanza _Rechazo."""
        try:
            zf = zipfile.ZipFile(ruta_zip, "r")
        except zipfile.BadZipFile:
            raise _Rechazo("El archivo no es un ZIP válido o está dañado.")
        with zf:
            infos = zf.infolist()
            if len(infos) > cls.MAX_ENTRADAS:
                raise _Rechazo("El backup contiene demasiadas entradas.")
            entradas: Dict[str, zipfile.ZipInfo] = {}
            vistos = set()
            clases: Dict[str, Tuple[str, ...]] = {}
            for zi in infos:
                clase = cls._ruta_permitida(zi.filename)
                clave = zi.filename.lower()
                if clave in vistos:
                    raise _Rechazo("El backup contiene entradas duplicadas.")
                vistos.add(clave)
                if (zi.flag_bits & 0x1) or ((zi.external_attr >> 16) & 0o170000) == stat.S_IFLNK:
                    raise _Rechazo("El backup contiene archivos cifrados o enlaces simbólicos.")
                if zi.file_size > 50 * 1024 * 1024 and zi.compress_size > 0 and zi.file_size / zi.compress_size > 1000:
                    raise _Rechazo("El backup contiene entradas con una compresión anormal.")
                entradas[zi.filename] = zi
                clases[zi.filename] = clase
            for carpeta in ArchivoCVService.CARPETAS:
                if f"{carpeta}/" not in entradas:
                    raise _Rechazo(f"Falta la carpeta de CV {carpeta} en el backup.")
            if "manifest.json" not in entradas:
                raise _Rechazo("El backup no contiene manifest.json.")
            if "database/restore.sql" not in entradas:
                raise _Rechazo("El backup no contiene los archivos de base de datos (database/restore.sql).")
            if entradas["manifest.json"].file_size > cls.MAX_MANIFEST_BYTES:
                raise _Rechazo("El manifest del backup es demasiado grande.")
            try:
                manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            except (ValueError, zipfile.BadZipFile):
                raise _Rechazo("El manifest.json está dañado o no es válido.")
            manifest_sha = hashlib.sha256(zf.read("manifest.json")).hexdigest()
            info = cls._validar_manifest(manifest)

            tablas = manifest["base_de_datos"]["tablas"]
            archivos = manifest["archivos_cv"]["archivos"]
            csv_en_zip = {c[1] for c in clases.values() if c[0] == "csv"}
            if csv_en_zip != set(tablas):
                raise _Rechazo("Los archivos de base de datos del backup no coinciden con el manifest.")
            cv_en_zip = {n for n, c in clases.items() if c[0] == "cv"}
            if cv_en_zip != {a["ruta"] for a in archivos}:
                raise _Rechazo("Los archivos de CV del backup no coinciden con el manifest.")
            storage = (manifest.get("archivos_storage") or {}).get("archivos") or []
            if {n for n, c in clases.items() if c[0] == "storage"} != {a["ruta"] for a in storage}:
                raise _Rechazo("Los archivos de almacenamiento del backup no coinciden con el manifest.")

            piezas: List[Tuple[str, str, int, Optional[int], Optional[List[str]]]] = []  # (ruta, sha, bytes, registros, columnas)
            sql = manifest["base_de_datos"]["script_restauracion"]
            piezas.append((sql["archivo"], sql["sha256"], sql["bytes"], None, None))
            for t, d in tablas.items():
                piezas.append((d["archivo"], d["sha256"], d["bytes"], d["registros"], d["columnas"]))
            for a in archivos:
                piezas.append((a["ruta"], a["sha256"], a["bytes"], None, None))
            for a in storage:
                piezas.append((a["ruta"], a["sha256"], a["bytes"], None, None))
            referenciadas: set = set()
            total = sum(p[2] for p in piezas) or 1
            leidos = [0]

            def progreso(n: int) -> None:
                leidos[0] += n
                if st is not None:
                    cls._actualizar(st, porcentaje=min(99, int(100 * leidos[0] / total)), mensaje="Verificando la integridad del backup...")

            for ruta, sha, tam, registros, columnas in piezas:
                zi = entradas.get(ruta)
                if zi is None or zi.file_size != tam:
                    raise _Rechazo(f"El tamaño de {ruta} no coincide con el manifest.")
                try:
                    with zf.open(zi) as f:
                        lector = _LectorConHash(f, progreso)
                        if registros is None:
                            while lector.read(TAMANO_BLOQUE):
                                pass
                        else:
                            referenciadas |= cls._contar_registros(lector, ruta, columnas, registros, COLUMNA_STORAGE_POR_TABLA.get(ruta[len("database/"):-len(".csv")]))
                except zipfile.BadZipFile:
                    raise _Rechazo(f"El backup está dañado ({ruta}).")
                if lector.bytes != tam or lector.sha256.hexdigest() != sha:
                    raise _Rechazo(f"El checksum SHA-256 de {ruta} no coincide: el backup fue alterado o está dañado.")

            claves_incluidas = {a["clave"] for a in storage}
            if not claves_incluidas <= referenciadas:
                raise _Rechazo("El backup incluye archivos de almacenamiento que su base de datos no referencia.")
            carpetas = info["carpetas"]
            return cls._armar_resultado(db, manifest, manifest_sha, carpetas, os.path.getsize(ruta_zip), len(referenciadas - claves_incluidas))

    @classmethod
    def _contar_registros(cls, lector: _LectorConHash, ruta: str, columnas: List[str], esperados: int, columna_clave: Optional[str] = None) -> set:
        """Verifica cabecera, columnas por fila y cantidad de registros de un CSV; devuelve los valores de `columna_clave` (claves de storage)."""
        csv.field_size_limit(2 ** 31 - 1)
        claves: set = set()
        try:
            lectura = csv.reader(_lineas(lector), strict=True)
            cabecera = next(lectura, None)
            if cabecera != columnas:
                raise _Rechazo(f"Las columnas de {ruta} no coinciden con el manifest.")
            indice = columnas.index(columna_clave) if columna_clave in columnas else None
            n = 0
            for fila in lectura:
                if len(fila) != len(columnas):
                    raise _Rechazo(f"{ruta} contiene filas con una cantidad de columnas inválida.")
                if indice is not None and fila[indice]:
                    claves.add(fila[indice])
                n += 1
        except (csv.Error, UnicodeDecodeError):
            raise _Rechazo(f"{ruta} no tiene un formato válido.")
        if n != esperados:
            raise _Rechazo(f"La cantidad de registros de {ruta} ({n}) no coincide con el manifest ({esperados}).")
        return claves

    @classmethod
    def _validar_manifest(cls, m: Any) -> Dict[str, Any]:
        """Estructura y coherencia interna del manifest (tipos, version, conteos y rutas)."""
        try:
            if not isinstance(m, dict) or m.get("formato") != BackupRecruitingService.FORMATO:
                raise _Rechazo("El archivo no corresponde a un backup de RECLUIT.")
            if str(m.get("version_backup")) not in cls.VERSIONES_SOPORTADAS:
                raise _Rechazo(f"La versión del backup ({m.get('version_backup')}) no es compatible con esta versión de RECLUIT.")
            bd, cv = m["base_de_datos"], m["archivos_cv"]
            tablas, archivos = bd["tablas"], cv["archivos"]
            if not isinstance(tablas, dict) or not tablas or not isinstance(archivos, list) or not isinstance(cv["carpetas"], dict):
                raise _Rechazo("El manifest no tiene la estructura esperada.")
            if not any(t.startswith(BackupRecruitingService.PREFIJO_TABLAS) for t in tablas):
                raise _Rechazo("El backup no contiene tablas de Recruiting.")
            sql = bd["script_restauracion"]
            if sql.get("archivo") != "database/restore.sql" or not PATRON_SHA256.match(str(sql.get("sha256"))) or not isinstance(sql.get("bytes"), int):
                raise _Rechazo("El manifest no tiene la estructura esperada.")
            total_reg = 0
            for t, d in tablas.items():
                if (
                    not PATRON_TABLA.match(t) or d.get("archivo") != f"database/{t}.csv" or not PATRON_SHA256.match(str(d.get("sha256")))
                    or not isinstance(d.get("bytes"), int) or not isinstance(d.get("registros"), int) or d["registros"] < 0
                    or not isinstance(d.get("columnas"), list) or not d["columnas"]
                    or not all(isinstance(c, str) and PATRON_TABLA.match(c) for c in d["columnas"]) or len(set(d["columnas"])) != len(d["columnas"])
                ):
                    raise _Rechazo(f"El manifest describe de forma inválida la tabla {t}.")
                total_reg += d["registros"]
            if bd.get("total_registros") != total_reg or bd.get("total_tablas") != len(tablas):
                raise _Rechazo("Los totales de base de datos del manifest no coinciden con su contenido.")
            carpetas = {c: {"cantidad": 0, "bytes": 0} for c in ArchivoCVService.CARPETAS}
            rutas = set()
            for a in archivos:
                carpeta, _, nombre = str(a.get("ruta", "")).partition("/")
                if (
                    carpeta not in carpetas or not nombre or "/" in nombre or a["ruta"] in rutas or not PATRON_SHA256.match(str(a.get("sha256")))
                    or not isinstance(a.get("bytes"), int) or a["bytes"] < 0
                ):
                    raise _Rechazo("El manifest describe de forma inválida un archivo de CV.")
                rutas.add(a["ruta"])
                carpetas[carpeta]["bytes"] += a["bytes"]
                if not nombre.startswith("."):
                    carpetas[carpeta]["cantidad"] += 1
            for c, v in carpetas.items():
                declarado = cv["carpetas"].get(c) or {}
                if declarado.get("cantidad") != v["cantidad"] or declarado.get("bytes") != v["bytes"]:
                    raise _Rechazo(f"Los conteos de la carpeta {c} no coinciden con el manifest.")
            if cv.get("total_archivos") != sum(v["cantidad"] for v in carpetas.values()) or cv.get("total_bytes") != sum(v["bytes"] for v in carpetas.values()):
                raise _Rechazo("Los totales de archivos del manifest no coinciden con su contenido.")
            storage = m.get("archivos_storage")
            if storage is not None:
                if not isinstance(storage, dict) or not isinstance(storage.get("archivos"), list):
                    raise _Rechazo("El manifest no tiene la estructura esperada.")
                claves, rutas_storage, bytes_storage = set(), set(), 0
                for a in storage["archivos"]:
                    if (
                        not BackupRecruitingService.clave_storage_valida(a.get("clave")) or a["clave"] in claves
                        or not re.match(r"^storage/\d{6}\.bin$", str(a.get("ruta"))) or a["ruta"] in rutas_storage
                        or not PATRON_SHA256.match(str(a.get("sha256"))) or not isinstance(a.get("bytes"), int) or a["bytes"] < 0
                    ):
                        raise _Rechazo("El manifest describe de forma inválida un archivo de almacenamiento.")
                    claves.add(a["clave"])
                    rutas_storage.add(a["ruta"])
                    bytes_storage += a["bytes"]
                if storage.get("total") != len(storage["archivos"]) or storage.get("bytes") != bytes_storage:
                    raise _Rechazo("Los totales de archivos de almacenamiento del manifest no coinciden con su contenido.")
            return {"carpetas": carpetas}
        except (KeyError, TypeError, AttributeError):
            raise _Rechazo("El manifest no tiene la estructura esperada.")

    # ------------------------------------------------------------------ compatibilidad con el esquema y vista previa

    @classmethod
    def _planificar_esquema(cls, db: Session, manifest: Dict[str, Any]) -> Dict[str, Any]:
        """Compara tablas y columnas del backup con el esquema actual. Devuelve el plan de carga y las limitaciones."""
        desc = BackupRecruitingService._descubrir(db)
        insp = desc["insp"]
        tablas = manifest["base_de_datos"]["tablas"]
        notif = BackupRecruitingService.TABLA_NOTIFICACIONES
        plan: Dict[str, Dict[str, Any]] = {}
        limitaciones: List[str] = []
        for t, d in tablas.items():
            if t.startswith(BackupRecruitingService.PREFIJO_TABLAS):
                if t not in desc["columnas"]:
                    raise _Rechazo(f"El backup incluye la tabla {t}, que no existe en esta versión de RECLUIT.")
                actuales = [c for c in insp.get_columns(t)]
                tipo = "recruiting"
            elif t in cls.TABLAS_COMPARTIDAS or t == notif:
                actuales = [c for c in insp.get_columns(t)]
                tipo = "compartida" if t in cls.TABLAS_COMPARTIDAS else "notificaciones"
            else:
                raise _Rechazo(f"El backup incluye la tabla {t}, que no se puede restaurar.")
            nombres = [c["name"] for c in actuales]
            sobrantes = [c for c in d["columnas"] if c not in nombres]
            if sobrantes:
                raise _Rechazo(f"El backup contiene columnas que no existen en esta versión ({t}: {', '.join(sobrantes)}).")
            extra: List[Tuple[str, str]] = []
            faltantes: List[str] = []
            for c in actuales:
                if c["name"] in d["columnas"]:
                    continue
                obligatoria = (not c["nullable"]) and c.get("default") is None and not c.get("autoincrement") and not c.get("identity")
                if obligatoria:
                    valor = BackupRecruitingService.VALORES_COLUMNAS_OMITIDAS.get(c["name"])
                    if valor is None and BackupRecruitingService.PATRON_COLUMNA_SENSIBLE.search(c["name"]):
                        valor = "''"
                    if valor is None or tipo == "recruiting":
                        raise _Rechazo(f"El backup no es compatible con el esquema actual: falta la columna obligatoria {t}.{c['name']}.")
                    extra.append((c["name"], valor))
                elif not BackupRecruitingService.PATRON_COLUMNA_SENSIBLE.search(c["name"]):
                    faltantes.append(c["name"])
            if faltantes:
                if tipo == "recruiting":
                    limitaciones.append(f"La tabla {t} no incluye las columnas {', '.join(faltantes)} en este backup: quedarán con su valor por defecto (vacío).")
                else:
                    limitaciones.append(
                        f"El backup no incluye las columnas {', '.join(faltantes)} de {t} (backup de una versión anterior): "
                        "los registros que no existan en este servidor se crearán sin esos datos; los existentes no se modifican."
                    )
            plan[t] = {"tipo": tipo, "columnas": d["columnas"], "extra": extra}
        vaciadas = sorted(t for t in desc["orden"] if t not in tablas)
        for t in vaciadas:
            limitaciones.append(f"La tabla {t} no existe en este backup: quedará vacía al restaurar.")
        return {"plan": plan, "limitaciones": limitaciones, "desc": desc, "vaciadas": vaciadas}

    @classmethod
    def _armar_resultado(cls, db: Session, manifest: Dict[str, Any], manifest_sha: str, carpetas: Dict[str, Any], tamano_zip: int, sin_archivo: int = 0) -> Dict[str, Any]:
        esquema = cls._planificar_esquema(db, manifest)
        bd = manifest["base_de_datos"]
        limitaciones: List[str] = list(esquema["limitaciones"])
        avisos: List[str] = [str(a) for a in (manifest.get("advertencias") or [])][:20]
        storage = manifest.get("archivos_storage")
        if storage is None:
            limitaciones.append(
                "El backup no incluye los archivos del almacenamiento de candidatos (CV vinculados, adjuntos de etapas y duplicados pendientes; backup de una versión anterior): "
                "se restauran sus registros, pero esos archivos deben existir ya en el almacenamiento de este servidor."
            )
        elif sin_archivo:
            avisos.append(f"{sin_archivo} archivo(s) del almacenamiento referenciados por la base no estaban en el backup (ya faltaban al generarlo).")
        total_bytes = sum(v["bytes"] for v in carpetas.values())
        bytes_bd = sum(d["bytes"] for d in bd["tablas"].values())
        preview = {
            "version_backup": str(manifest["version_backup"]),
            "generado_utc": manifest.get("generado_utc"),
            "generado_por": manifest.get("generado_por"),
            "tablas": [{"tabla": t, "registros": d["registros"], "alcance": d.get("alcance")} for t, d in bd["tablas"].items()],
            "total_tablas": len(bd["tablas"]),
            "total_registros": bd["total_registros"],
            "carpetas": [
                {"carpeta": c, "cantidad": v["cantidad"], "bytes": v["bytes"], "tamano": ArchivoCVService.formatear_tamano(v["bytes"])}
                for c, v in carpetas.items()
            ],
            "total_archivos": sum(v["cantidad"] for v in carpetas.values()),
            "tamano_total_bytes": total_bytes + bytes_bd,
            "tamano_total": ArchivoCVService.formatear_tamano(total_bytes + bytes_bd),
            "tamano_zip": ArchivoCVService.formatear_tamano(tamano_zip),
            "archivos_storage": {
                "cantidad": (storage or {}).get("total", 0), "bytes": (storage or {}).get("bytes", 0),
                "tamano": ArchivoCVService.formatear_tamano((storage or {}).get("bytes", 0)),
            },
            "tablas_que_se_vaciaran": esquema["vaciadas"],
            "integridad": {
                "estado": "verificada",
                "detalle": "ZIP válido, nombres seguros, SHA-256 y tamaños de todas las piezas, conteos de registros y archivos coinciden con el manifest.",
            },
        }
        return {"preview": preview, "limitaciones": limitaciones, "avisos": avisos, "manifest_sha256": manifest_sha}

    # ------------------------------------------------------------------ API: confirmar y restaurar

    @classmethod
    def confirmar(cls, current_user: Usuario, importacion_id: str, confirmar: bool, texto_confirmacion: str, aceptar_limitaciones: bool) -> Dict[str, Any]:
        BackupRecruitingService.verificar_acceso(current_user)
        cls._recuperar_sin_fallar()
        st = cls._leer(importacion_id)
        if st.get("estado") != "validado":
            raise HTTPException(status_code=409, detail="El backup todavía no está validado o ya fue procesado.")
        if not confirmar or (texto_confirmacion or "").strip() != TEXTO_CONFIRMACION:
            raise HTTPException(status_code=400, detail=f"Confirmá la restauración escribiendo {TEXTO_CONFIRMACION}.")
        if st.get("limitaciones") and not aceptar_limitaciones:
            raise HTTPException(status_code=400, detail="Debés aceptar las limitaciones informadas del backup para continuar.")
        ruta = cls._ruta(importacion_id, ".zip")
        try:
            info = os.stat(ruta)
        except OSError:
            raise HTTPException(status_code=409, detail="El archivo del backup ya no está disponible. Subilo nuevamente.")
        if info.st_size != st.get("zip_size") or info.st_mtime_ns != st.get("zip_mtime_ns"):
            raise HTTPException(status_code=409, detail="El archivo del backup cambió después de validarlo. Subilo nuevamente.")
        if BackupRecruitingService._tomar_bloqueo() is not None:
            raise HTTPException(status_code=409, detail="Hay un backup o una restauración de Recruiting en curso. Esperá a que termine.")
        try:
            cls._comprobar_entorno(st)
        except _Rechazo as e:
            BackupRecruitingService._soltar_bloqueo()
            raise HTTPException(status_code=409, detail=str(e))
        except Exception:
            BackupRecruitingService._soltar_bloqueo()
            logger.error("No se pudo comprobar el entorno para restaurar", exc_info=True)
            raise HTTPException(status_code=500, detail=MENSAJE_ERROR_INTERNO)
        try:
            st.update({
                "estado": "restaurando", "fase": "comprobando", "porcentaje": 0, "mensaje": "Preparando la restauración...",
                "error": None, "revertido": None, "finalizado_at": None, "iniciado_restauracion_at": datetime.now(timezone.utc).isoformat(),
            })
            cls._guardar(st)
            cls._lanzar(lambda: cls._restaurar_en_segundo_plano(st))
        except Exception:
            BackupRecruitingService._soltar_bloqueo()
            logger.error("No se pudo iniciar la restauracion de Recruiting", exc_info=True)
            raise HTTPException(status_code=500, detail=MENSAJE_ERROR_INTERNO)
        return cls._publico(st)

    @classmethod
    def _hay_cargas_masivas(cls) -> bool:
        carpeta = os.path.dirname(CandidatoService._ruta_lote(str(uuid.uuid4())))
        if not os.path.isdir(carpeta):
            return False
        for nombre in os.listdir(carpeta):
            ruta = os.path.join(carpeta, nombre)
            if not nombre.endswith(".json") or time.time() - os.path.getmtime(ruta) > cls.FRESCURA_LOTE_SEGUNDOS:
                continue
            try:
                with open(ruta, "r", encoding="utf-8") as f:
                    if json.load(f).get("estado") not in CandidatoService.ESTADOS_LOTE_FINALES:
                        return True
            except (OSError, ValueError):
                continue
        return False

    @classmethod
    def _bytes_actuales_de_cv(cls) -> int:
        return sum(a["bytes"] for c in ArchivoCVService.CARPETAS for a in ArchivoCVService._inspeccionar(c))

    @classmethod
    def _comprobar_entorno(cls, st: Dict[str, Any]) -> None:
        """Sin cargas masivas en curso y con espacio libre para el backup de seguridad y los CV nuevos."""
        if cls._hay_cargas_masivas():
            raise _Rechazo("Hay una carga masiva de CV en ejecución. Esperá a que termine para restaurar.")
        preview = st.get("preview") or {}
        raiz = CandidatoService._raiz_cv_storage()
        os.makedirs(raiz, exist_ok=True)
        nuevos = sum(c["bytes"] for c in preview.get("carpetas", [])) + (preview.get("archivos_storage") or {}).get("bytes", 0)
        necesario_cv = int(nuevos * 1.05) + cls.MARGEN_ESPACIO_BYTES
        if shutil.disk_usage(raiz).free < necesario_cv:
            raise _Rechazo(f"No hay espacio suficiente en el almacenamiento de CV (se necesitan {ArchivoCVService.formatear_tamano(necesario_cv)}).")
        necesario_backup = int(cls._bytes_actuales_de_cv() * 1.1) + cls.MARGEN_ESPACIO_BYTES
        if shutil.disk_usage(cls._dir()).free < necesario_backup:
            raise _Rechazo(f"No hay espacio suficiente para el backup de seguridad (se necesitan {ArchivoCVService.formatear_tamano(necesario_backup)}).")

    @classmethod
    @contextmanager
    def _sesion_escritura(cls) -> Iterator[Session]:
        """Sesion propia para la restauracion (en las pruebas se sustituye por la sesion de prueba)."""
        from backend.database import SessionLocal

        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    @classmethod
    def _restaurar_en_segundo_plano(cls, st: Dict[str, Any]) -> None:
        raiz = CandidatoService._raiz_cv_storage()
        trabajo = os.path.join(raiz, f"{PREFIJO_TRABAJO}{st['importacion_id']}")
        try:
            cls._restaurar(st, raiz, trabajo)
        except _Rechazo as e:
            cls._fallar(st, str(e), revertido=True, trabajo=trabajo)
        except Exception:
            logger.error("Fallo la restauracion de Recruiting", exc_info=True)
            cls._fallar(st, "La restauración falló. Se recuperó el estado anterior de Recruiting.", revertido=True, trabajo=trabajo)
        finally:
            BackupRecruitingService._soltar_bloqueo()

    @classmethod
    def _fallar(cls, st: Dict[str, Any], mensaje: str, revertido: bool, trabajo: str) -> None:
        if st.get("_critico"):  # no se pudo recuperar algo: se conserva el directorio de trabajo con los originales
            mensaje, revertido = st["_critico"], False
        else:
            shutil.rmtree(trabajo, ignore_errors=True)
        cls._actualizar(st, forzar=True, estado="error", fase="error", mensaje=mensaje, error=mensaje, revertido=revertido,
                        finalizado_at=datetime.now(timezone.utc).isoformat())

    # -- registro persistente de etapas (journal): permite recuperar el estado anterior si el proceso muere a mitad de camino

    @staticmethod
    def _journal(trabajo: str, **datos) -> None:
        os.makedirs(trabajo, exist_ok=True)
        ruta = os.path.join(trabajo, ARCHIVO_JOURNAL)
        actual: Dict[str, Any] = {}
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                actual = json.load(f)
        except (OSError, ValueError):
            pass
        actual.update(datos)
        actual["actualizado_utc"] = datetime.now(timezone.utc).isoformat()
        tmp = f"{ruta}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(actual, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, ruta)

    @classmethod
    def _restaurar(cls, st: Dict[str, Any], raiz: str, trabajo: str) -> None:
        ruta_zip = cls._ruta(st["importacion_id"], ".zip")
        cls._actualizar(st, forzar=True, fase="comprobando", porcentaje=1, mensaje="Comprobando que no haya otros procesos de Recruiting...")
        cls._comprobar_entorno(st)

        # 1) Backup de seguridad del estado actual: si no se puede generar, no se toca nada
        cls._actualizar(st, forzar=True, fase="respaldo_seguridad", porcentaje=2, mensaje="Generando el backup de seguridad del estado actual...")
        previo = BackupRecruitingService._estado_inicial(st.get("usuario"))
        st["backup_id_seguridad"] = previo["backup_id"]
        cls._guardar(st)
        try:
            seguridad = BackupRecruitingService.generar_bloqueante(st.get("usuario"), previo)
        except Exception:
            logger.error("No se pudo generar el backup de seguridad previo a la importacion", exc_info=True)
            raise _Rechazo("No se pudo generar el backup de seguridad del estado actual. La restauración fue cancelada y no se modificó nada.")
        st["backup_seguridad"] = {
            "backup_id": seguridad["backup_id"], "nombre_archivo": seguridad["nombre_archivo"], "tamano": seguridad["tamano"], "sha256": seguridad["sha256"],
        }
        cls._actualizar(st, forzar=True, fase="preparando_archivos", porcentaje=30, mensaje="Verificando y preparando los CV a restaurar...")
        cls._journal(trabajo, importacion_id=st["importacion_id"], etapa="preparando", usuario=st.get("usuario"))

        with zipfile.ZipFile(ruta_zip, "r") as zf:
            manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            if hashlib.sha256(zf.read("manifest.json")).hexdigest() != st.get("manifest_sha256"):
                raise _Rechazo("El backup cambió después de validarlo. La restauración fue cancelada.")
            cls._validar_manifest(manifest)

            # 2) CV y archivos del storage a directorios temporales (CV dentro de CV_STORAGE_DIR: el intercambio es un renombrado)
            cls._preparar_archivos(zf, manifest, os.path.join(trabajo, "nuevo"), st)
            entradas_storage = cls._preparar_storage(zf, manifest, trabajo)

            with cls._sesion_escritura() as db:
                esquema = cls._planificar_esquema(db, manifest)
                # 3) Base de datos dentro de un SAVEPOINT: nada queda confirmado hasta el final
                cls._actualizar(st, forzar=True, fase="base_de_datos", porcentaje=60, mensaje="Restaurando la base de datos...")
                savepoint = db.begin_nested()
                try:
                    registros = cls._restaurar_base(db, zf, manifest, esquema, st)
                    # 4) Intercambio de carpetas (las originales quedan en trabajo/viejo hasta confirmar) y archivos del storage
                    cls._actualizar(st, forzar=True, fase="reemplazando_archivos", porcentaje=90, mensaje="Reemplazando los CV...")
                    cls._journal(trabajo, etapa="intercambiando")
                    cls._reemplazar_carpetas(raiz, trabajo)
                    plan = cls._planificar_storage(entradas_storage, trabajo)
                    cls._aplicar_storage(entradas_storage, plan, trabajo)
                    # 5) Confirmacion: el id de transaccion queda en el journal para saber, tras una caida, si PostgreSQL llego a confirmarla
                    txid = int(db.execute(text("SELECT txid_current()")).scalar())
                    cls._journal(trabajo, etapa="commit_pendiente", txid=txid)
                    db.commit()  # confirma toda la transaccion (incluye el SAVEPOINT)
                except BaseException:
                    try:
                        if savepoint.is_active:
                            savepoint.rollback()
                    except Exception:  # conexion perdida: al cerrar la sesion la base descarta la transaccion sin confirmar
                        logger.error("No se pudo revertir el SAVEPOINT de la restauracion", exc_info=True)
                    cls._deshacer_storage(trabajo, st)
                    cls._deshacer_carpetas(raiz, trabajo, st)
                    raise
        cls._finalizar(st, trabajo, registros, len(entradas_storage))

    @classmethod
    def _finalizar(cls, st: Dict[str, Any], trabajo: str, registros: Dict[str, int], archivos_storage: int) -> None:
        """Despues del commit: ya no hay vuelta atras automatica. Se descartan los originales y se publica el resultado."""
        cls._journal(trabajo, etapa="confirmado")
        shutil.rmtree(trabajo, ignore_errors=True)
        archivos = {c["carpeta"]: c["cantidad"] for c in st["preview"]["carpetas"]}
        usuarios = st.get("usuarios_sin_credenciales") or []
        cls._actualizar(
            st, forzar=True, estado="finalizado", fase="finalizado", porcentaje=100, error=None, revertido=None,
            mensaje="Restauración completada y verificada.", finalizado_at=datetime.now(timezone.utc).isoformat(),
            resultado={
                "tablas": registros, "total_registros": sum(registros.values()), "archivos": archivos,
                "total_archivos": sum(archivos.values()), "archivos_storage": archivos_storage, "backup_seguridad": st["backup_seguridad"],
                "usuarios_sin_credenciales": usuarios,
            },
        )

    @classmethod
    def _preparar_archivos(cls, zf: zipfile.ZipFile, manifest: Dict[str, Any], nuevo: str, st: Dict[str, Any]) -> None:
        for carpeta in ArchivoCVService.CARPETAS:
            os.makedirs(os.path.join(nuevo, carpeta), exist_ok=True)
        archivos = manifest["archivos_cv"]["archivos"]
        total = max(len(archivos), 1)
        base = os.path.realpath(nuevo)
        for i, a in enumerate(archivos, start=1):
            carpeta, _, nombre = a["ruta"].partition("/")
            destino = os.path.join(nuevo, carpeta, nombre)
            if os.path.dirname(os.path.realpath(destino)) != os.path.join(base, carpeta):
                raise _Rechazo("Ruta de archivo no permitida en el backup.")
            cls._extraer(zf, a["ruta"], destino, a["bytes"], a["sha256"])
            try:
                mtime = datetime.fromisoformat(a["modificado_utc"]).timestamp()
                os.utime(destino, (mtime, mtime))
            except (KeyError, ValueError, OSError):
                pass
            cls._actualizar(st, porcentaje=30 + int(30 * i / total), mensaje=f"Preparando los CV ({i} de {total})...")

    @staticmethod
    def _extraer(zf: zipfile.ZipFile, entrada: str, destino: str, bytes_esperados: int, sha_esperado: str) -> None:
        """Extrae una pieza por bloques verificando su tamano y SHA-256."""
        sha = hashlib.sha256()
        n = 0
        with zf.open(entrada) as origen, open(destino, "xb") as out:
            while True:
                bloque = origen.read(TAMANO_BLOQUE)
                if not bloque:
                    break
                sha.update(bloque)
                n += len(bloque)
                out.write(bloque)
            out.flush()
            os.fsync(out.fileno())
        if n != bytes_esperados or sha.hexdigest() != sha_esperado:
            raise _Rechazo(f"El archivo {entrada} no coincide con su checksum al restaurarlo. La restauración fue cancelada.")

    @classmethod
    def _preparar_storage(cls, zf: zipfile.ZipFile, manifest: Dict[str, Any], trabajo: str) -> List[Dict[str, Any]]:
        """Extrae y verifica los archivos del storage (CV vinculados, adjuntos de etapas, duplicados pendientes) a un directorio temporal."""
        entradas = (manifest.get("archivos_storage") or {}).get("archivos") or []
        destino = os.path.join(trabajo, "storage_nuevo")
        os.makedirs(destino, exist_ok=True)
        for a in entradas:
            cls._extraer(zf, a["ruta"], os.path.join(destino, os.path.basename(a["ruta"])), a["bytes"], a["sha256"])
        return entradas

    @classmethod
    def _planificar_storage(cls, entradas: List[Dict[str, Any]], trabajo: str) -> Dict[str, Any]:
        """Distingue claves nuevas de las que ya existen con otro contenido (esas se guardan para poder recuperarlas) y lo registra en el journal."""
        from backend.core.storage import cloud_storage

        viejo = os.path.join(trabajo, "storage_viejo")
        os.makedirs(viejo, exist_ok=True)
        nuevas: List[str] = []
        sobrescritas: List[Dict[str, str]] = []
        for a in entradas:
            if cloud_storage.exists(a["clave"]):
                previo = cloud_storage.download(a["clave"])
                if hashlib.sha256(previo).hexdigest() == a["sha256"]:
                    continue  # mismo contenido: no hay nada que cambiar
                archivo = os.path.basename(a["ruta"])
                with open(os.path.join(viejo, archivo), "wb") as f:
                    f.write(previo)
                sobrescritas.append({"clave": a["clave"], "archivo": archivo})
            else:
                nuevas.append(a["clave"])
        plan = {"nuevas": nuevas, "sobrescritas": sobrescritas}
        cls._journal(trabajo, etapa="storage", storage=plan)
        return plan

    @classmethod
    def _aplicar_storage(cls, entradas: List[Dict[str, Any]], plan: Dict[str, Any], trabajo: str) -> None:
        import mimetypes

        from backend.core.storage import cloud_storage

        a_subir = set(plan["nuevas"]) | {s["clave"] for s in plan["sobrescritas"]}
        for a in entradas:
            if a["clave"] in a_subir:
                with open(os.path.join(trabajo, "storage_nuevo", os.path.basename(a["ruta"])), "rb") as f:
                    cloud_storage.upload(a["clave"], f.read(), mimetypes.guess_type(a["clave"])[0] or "application/octet-stream")

    @classmethod
    def _deshacer_storage(cls, trabajo: str, st: Optional[Dict[str, Any]] = None) -> None:
        """Devuelve el storage a su estado anterior segun el journal (idempotente): borra las claves nuevas y repone las sobrescritas."""
        from backend.core.storage import cloud_storage

        try:
            with open(os.path.join(trabajo, ARCHIVO_JOURNAL), "r", encoding="utf-8") as f:
                plan = json.load(f).get("storage")
        except (OSError, ValueError):
            return
        if not plan:
            return
        try:
            for clave in plan.get("nuevas", []):
                try:
                    cloud_storage.delete(clave)
                except Exception:
                    if cloud_storage.exists(clave):
                        raise
            for s in plan.get("sobrescritas", []):
                with open(os.path.join(trabajo, "storage_viejo", s["archivo"]), "rb") as f:
                    cloud_storage.upload(s["clave"], f.read(), "application/octet-stream")
        except Exception:
            logger.critical("No se pudo recuperar el storage original; los originales quedan en %s", trabajo, exc_info=True)
            if st is not None:
                st["_critico"] = f"ATENCIÓN: la restauración falló y no se pudo recuperar automáticamente el almacenamiento de archivos. Los originales quedan en {trabajo}. Contactá a soporte; hay un backup de seguridad disponible."
            raise

    @classmethod
    def _restaurar_base(cls, db: Session, zf: zipfile.ZipFile, manifest: Dict[str, Any], esquema: Dict[str, Any], st: Dict[str, Any]) -> Dict[str, int]:
        """Reemplaza el contenido de Recruiting por el del backup (en la transaccion/savepoint del llamador)."""
        desc, plan = esquema["desc"], esquema["plan"]
        tablas = manifest["base_de_datos"]["tablas"]
        cursor = db.connection().connection.cursor()
        notif = BackupRecruitingService.TABLA_NOTIFICACIONES
        registros: Dict[str, int] = {}
        try:
            db.execute(text("TRUNCATE " + ", ".join(_ident(t) for t in desc["orden"]) + " RESTART IDENTITY"))
            if notif in tablas:  # notificaciones internas de Recruiting: se reemplazan por las del backup
                db.execute(text(f"DELETE FROM {_ident(notif)} WHERE {BackupRecruitingService.FILTRO_NOTIFICACIONES}"))

            orden = [t for t in cls.TABLAS_COMPARTIDAS if t in tablas] + ([notif] if notif in tablas else []) + [t for t in desc["orden"] if t in tablas]
            for i, tabla in enumerate(orden, start=1):
                d, p = tablas[tabla], plan[tabla]
                lista = ", ".join(_ident(c) for c in p["columnas"])
                copy = f"COPY {{destino}} ({lista}) FROM STDIN WITH (FORMAT csv, HEADER true, ENCODING 'UTF8')"
                with zf.open(d["archivo"]) as f:
                    lector = _LectorConHash(f)
                    if p["tipo"] == "recruiting":
                        cursor.copy_expert(copy.format(destino=_ident(tabla)), lector)
                        cargadas = cursor.rowcount
                    else:  # compartidas: solo se agregan las filas que faltan (nunca se modifican las existentes)
                        cursor.execute(f"CREATE TEMP TABLE _restore AS SELECT {lista} FROM {_ident(tabla)} WITH NO DATA")
                        cursor.copy_expert(copy.format(destino="_restore"), lector)
                        cargadas = cursor.rowcount
                        columnas_destino = lista + "".join(f", {_ident(c)}" for c, _ in p["extra"])
                        columnas_origen = lista + "".join(f", {v}" for _, v in p["extra"])
                        devolver = ""
                        if tabla == "core_usuarios" and {"id", "email"} <= set(p["columnas"]):
                            devolver = ' RETURNING "id"::text, "email"'
                        cursor.execute(f"INSERT INTO {_ident(tabla)} ({columnas_destino}) SELECT {columnas_origen} FROM _restore ON CONFLICT DO NOTHING{devolver}")
                        if devolver:  # cuentas creadas ahora: quedan sin credenciales utilizables y deben restablecerlas
                            creados = [{"id": r[0], "email": r[1]} for r in cursor.fetchall()]
                            st["usuarios_sin_credenciales"] = creados
                            if creados and "requiere_password_change" in set(p["columnas"]) | {c for c, _ in p["extra"]}:
                                cursor.execute('UPDATE core_usuarios SET "requiere_password_change" = true WHERE "id"::text = ANY(%s)', ([u["id"] for u in creados],))
                        cursor.execute("DROP TABLE _restore")
                if cargadas != d["registros"] or lector.bytes != d["bytes"] or lector.sha256.hexdigest() != d["sha256"]:
                    raise RuntimeError(f"Verificación fallida al restaurar {tabla}")
                registros[tabla] = cargadas
                cls._actualizar(st, porcentaje=60 + int(28 * i / len(orden)), mensaje=f"Restaurando la base de datos ({i} de {len(orden)} tablas)...")
            for tabla, columna, secuencia in BackupRecruitingService._secuencias(db, desc):
                db.execute(
                    text(f"SELECT setval(CAST(:s AS regclass), (SELECT MAX({_ident(columna)}) FROM {_ident(tabla)})) WHERE EXISTS (SELECT 1 FROM {_ident(tabla)})"),
                    {"s": secuencia},
                )
            db.flush()
        finally:
            cursor.close()
        return registros

    @classmethod
    def _reemplazar_carpetas(cls, raiz: str, trabajo: str) -> None:
        viejo = os.path.join(trabajo, "viejo")
        os.makedirs(viejo, exist_ok=True)
        for carpeta in ArchivoCVService.CARPETAS:
            actual = os.path.join(raiz, carpeta)
            if os.path.lexists(actual):
                os.rename(actual, os.path.join(viejo, carpeta))
            os.rename(os.path.join(trabajo, "nuevo", carpeta), actual)

    @classmethod
    def _deshacer_carpetas(cls, raiz: str, trabajo: str, st: Dict[str, Any], intercambio_iniciado: bool = True) -> None:
        """Devuelve las carpetas originales a CV_STORAGE_DIR segun lo que realmente hay en disco (sirve igual tras una caida a mitad de renombrado)."""
        try:
            intercambio_iniciado = intercambio_iniciado and os.path.isdir(os.path.join(trabajo, "nuevo"))
            os.makedirs(os.path.join(trabajo, "nuevo"), exist_ok=True)
            for carpeta in ArchivoCVService.CARPETAS:
                actual = os.path.join(raiz, carpeta)
                viejo = os.path.join(trabajo, "viejo", carpeta)
                nuevo = os.path.join(trabajo, "nuevo", carpeta)
                if os.path.lexists(viejo):  # el original fue apartado: se repone y lo restaurado se aparta
                    if os.path.lexists(actual):
                        os.rename(actual, nuevo if not os.path.lexists(nuevo) else os.path.join(trabajo, f"descartado_{carpeta}"))
                    os.rename(viejo, actual)
                elif intercambio_iniciado and not os.path.lexists(nuevo) and os.path.lexists(actual):  # no habia original: lo restaurado se aparta
                    os.rename(actual, nuevo)
        except Exception:
            logger.critical("No se pudieron recuperar las carpetas de CV originales; quedan en %s", trabajo, exc_info=True)
            st["_critico"] = (
                f"ATENCIÓN: la restauración falló y no se pudieron recuperar automáticamente las carpetas de CV originales. "
                f"Quedan resguardadas en {trabajo}. Contactá a soporte; hay un backup de seguridad disponible."
            )
            raise

    # ------------------------------------------------------------------ recuperacion automatica tras una caida

    @classmethod
    def _estado_transaccion(cls, txid: Optional[int]) -> Optional[str]:
        """'committed' | 'aborted' | 'in progress' | None segun PostgreSQL (txid_status)."""
        if txid is None:
            return None  # sin id de transaccion no se puede saber: nunca se decide
        with cls._sesion_escritura() as db:
            return db.execute(text("SELECT txid_status(:t)"), {"t": txid}).scalar()

    @classmethod
    def recuperar_interrumpidas(cls) -> List[Dict[str, Any]]:
        """Revisa los directorios de trabajo de restauraciones que el proceso dejo a medias (por caida o reinicio) y las resuelve:

        - hasta el commit de PostgreSQL (o transaccion abortada): devuelve carpetas y storage originales; la base ya descarto la transaccion;
        - commit confirmado por PostgreSQL (txid_status): la restauracion es valida y solo se descartan los originales;
        - transaccion aun en curso: no se toca nada (se reintenta mas tarde).
        No actua mientras haya una restauracion viva (latido reciente). Se ejecuta al iniciar el backend y al usar los endpoints de importacion.
        """
        resultados: List[Dict[str, Any]] = []
        raiz = CandidatoService._raiz_cv_storage()
        if not os.path.isdir(raiz):
            return resultados
        pendientes = sorted(d for d in os.listdir(raiz) if d.startswith(PREFIJO_TRABAJO) and os.path.isdir(os.path.join(raiz, d)))
        if not pendientes or cls.restauracion_en_curso():
            return resultados
        for nombre in pendientes:
            trabajo = os.path.join(raiz, nombre)
            try:
                resultados.append(cls._recuperar(raiz, trabajo, nombre[len(PREFIJO_TRABAJO):]))
            except Exception:
                logger.critical("No se pudo recuperar la restauracion interrumpida %s", nombre, exc_info=True)
                resultados.append({"importacion_id": nombre[len(PREFIJO_TRABAJO):], "resultado": "error"})
        return resultados

    @classmethod
    def _recuperar(cls, raiz: str, trabajo: str, importacion_id: str) -> Dict[str, Any]:
        try:
            with open(os.path.join(trabajo, ARCHIVO_JOURNAL), "r", encoding="utf-8") as f:
                journal = json.load(f)
        except (OSError, ValueError):
            journal = {}
        etapa = journal.get("etapa")
        if etapa == "commit_pendiente":
            transaccion = cls._estado_transaccion(journal.get("txid"))
            if transaccion == "committed":
                resultado = "confirmada"
            elif transaccion == "aborted":
                resultado = "revertida"
            else:  # 'in progress', NULL (id demasiado antiguo) o cualquier valor desconocido: no se toca nada
                logger.warning("Restauracion %s: estado de transaccion no concluyente (%r); no se modifica nada", importacion_id, transaccion)
                return {"importacion_id": importacion_id, "resultado": "pendiente"}
        elif etapa == "confirmado":
            resultado = "confirmada"
        else:
            resultado = "revertida"  # nunca llego a confirmarse: la base conserva su estado anterior
        st: Dict[str, Any] = {}
        if resultado == "revertida":
            cls._deshacer_storage(trabajo, st)
            cls._deshacer_carpetas(raiz, trabajo, st, intercambio_iniciado=etapa in ("intercambiando", "storage"))
        shutil.rmtree(trabajo, ignore_errors=True)
        logger.warning("Restauracion de Recruiting interrumpida %s: %s", importacion_id, resultado)
        cls._marcar_recuperada(importacion_id, resultado)
        BackupRecruitingService._soltar_bloqueo()
        return {"importacion_id": importacion_id, "resultado": resultado}

    @classmethod
    def _marcar_recuperada(cls, importacion_id: str, resultado: str) -> None:
        try:
            st = cls._leer(importacion_id)
        except HTTPException:
            return
        if st.get("estado") != "restaurando":
            return
        if resultado == "confirmada":
            st.update({"estado": "finalizado", "fase": "finalizado", "porcentaje": 100, "mensaje": "La restauración se había confirmado antes de la interrupción: quedó completa.", "error": None, "revertido": None})
        else:
            st.update({"estado": "error", "fase": "error", "mensaje": "La restauración se interrumpió. Se recuperó automáticamente el estado anterior de Recruiting.", "error": "interrumpida", "revertido": True})
        st["finalizado_at"] = datetime.now(timezone.utc).isoformat()
        cls._guardar(st)
