"""
Capa de abstracción de Storage.

Permite usar filesystem local o Google Cloud Storage (GCS)
de forma transparente. Cada módulo trabaja con keys relativas
y el backend resuelve dónde guardar.

Ejemplos de keys:
    profile/{hash}_{uid}.jpg
    support-img/acuerdos/{hash}_{uid}.png

Recibos de sueldo (ver backend/modules/recibos/pdf_service.py, que arma estas
keys con carpeta_lote()). El segmento {slug} es el tipo de liquidación —
mensual, sac, liqfinal, especial — y es lo que evita que dos lotes del mismo
período se pisen los PDF entre sí:
    recibos-{cuit}/{periodo}/{slug}/masivo_{hash}_{uid}.pdf
    recibos-{cuit}/{periodo}/{slug}/{NNN}_original_{cuil}.pdf
    recibos-{cuit}/{periodo}/{slug}/{NNN}_duplicado_{cuil}.pdf
    recibos-{cuit}/{periodo}/{slug}/firmados/{recibo_id}_{hash}_{uid}.pdf
"""

import hashlib
import logging
import uuid
from abc import ABC, abstractmethod
from io import BytesIO
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image

logger = logging.getLogger(__name__)


# ─── Interfaz abstracta ──────────────────────────────────────────────────────


class StorageBackend(ABC):
    """Interfaz que deben implementar todos los backends de storage."""

    @abstractmethod
    def upload(self, key: str, content: bytes, content_type: str = "application/octet-stream") -> str:
        """Sube un archivo. Retorna la key final."""
        ...

    @abstractmethod
    def download(self, key: str) -> bytes:
        """Descarga un archivo. Retorna bytes."""
        ...

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Elimina un archivo. Retorna True si existía."""
        ...

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Verifica si un archivo existe."""
        ...

    @abstractmethod
    def get_url(self, key: str, expires: int = 3600) -> str:
        """Retorna URL de acceso al archivo.
        En local: ruta relativa para servir via endpoint.
        En S3: presigned URL.
        """
        ...


# ─── Backend Local (filesystem) ──────────────────────────────────────────────


class LocalStorageBackend(StorageBackend):
    """Backend que guarda archivos en el filesystem local."""

    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        return self.base_path / key

    def upload(self, key: str, content: bytes, content_type: str = "application/octet-stream") -> str:
        file_path = self._resolve(key)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "wb") as f:
            f.write(content)
        return key

    def download(self, key: str) -> bytes:
        file_path = self._resolve(key)
        if not file_path.exists():
            raise FileNotFoundError(f"Archivo no encontrado: {key}")
        return file_path.read_bytes()

    def delete(self, key: str) -> bool:
        file_path = self._resolve(key)
        if file_path.exists():
            file_path.unlink()
            return True
        return False

    def exists(self, key: str) -> bool:
        return self._resolve(key).exists()

    def get_url(self, key: str, expires: int = 3600) -> str:
        return f"/storage/{key}"

    def get_absolute_path(self, key: str) -> str:
        """Retorna path absoluto en disco. Solo para LocalStorage."""
        return str(self._resolve(key))


# ─── Backend GCS (Google Cloud Storage) ───────────────────────────────────────


class GCSStorageBackend(StorageBackend):
    """Backend que guarda archivos en Google Cloud Storage.

    Identidad (F06-P04): sin GCS_CREDENTIALS_PATH, la del entorno (ADC): en la VM, su service account, sin una clave
    JSON de larga vida en el disco. Con GCS_CREDENTIALS_PATH, la service account de ese JSON (desarrollo local)."""

    def __init__(
        self,
        bucket_name: str,
        credentials_path: str = "",
    ):
        import google.auth
        from google.cloud import storage as gcs_storage
        from google.oauth2 import service_account

        if credentials_path and not Path(credentials_path).is_file():
            logger.warning(f"GCS_CREDENTIALS_PATH={credentials_path} no existe: uso la identidad del entorno (ADC)")
            credentials_path = ""
        if credentials_path:
            self.credenciales = service_account.Credentials.from_service_account_file(credentials_path)
            proyecto = self.credenciales.project_id
        else:
            self.credenciales, proyecto = google.auth.default()
        self.client = gcs_storage.Client(credentials=self.credenciales, project=proyecto)

        self.bucket = self.client.bucket(bucket_name)
        self.bucket_name = bucket_name

    def upload(self, key: str, content: bytes, content_type: str = "application/octet-stream") -> str:
        blob = self.bucket.blob(key)
        blob.upload_from_string(content, content_type=content_type)
        return key

    def download(self, key: str) -> bytes:
        blob = self.bucket.blob(key)
        if not blob.exists():
            raise FileNotFoundError(f"Archivo no encontrado en GCS: {key}")
        return blob.download_as_bytes()

    def delete(self, key: str) -> bool:
        blob = self.bucket.blob(key)
        if not blob.exists():
            return False
        blob.delete()
        return True

    def exists(self, key: str) -> bool:
        return self.bucket.blob(key).exists()

    def get_url(self, key: str, expires: int = 3600) -> str:
        """Genera una signed URL v4 con expiración. Con la clave de una service account (el JSON) firma acá; con la
        identidad de la VM, que no tiene clave privada, firma con IAM signBlob: la cuenta necesita
        roles/iam.serviceAccountTokenCreator sobre sí misma (F06-P03)."""
        import datetime

        blob = self.bucket.blob(key)
        firma = {"version": "v4", "expiration": datetime.timedelta(seconds=expires), "method": "GET"}
        if hasattr(self.credenciales, "sign_bytes"):
            return blob.generate_signed_url(**firma)
        if not self.credenciales.valid or self.credenciales.service_account_email == "default":
            # la identidad de Compute Engine da su email real y el token recién después de refrescar
            from google.auth.transport.requests import Request

            self.credenciales.refresh(Request())
        return blob.generate_signed_url(
            **firma,
            service_account_email=self.credenciales.service_account_email,
            access_token=self.credenciales.token,
        )


# ─── StorageService (API pública) ─────────────────────────────────────────────


class StorageService:
    """
    Servicio principal de storage. Wrapper sobre el backend activo
    con helpers para generar keys, subir imágenes con thumbnail, etc.

    Uso:
        from backend.core.storage import cloud_storage, local_storage
        key = cloud_storage.build_key("profile", content, ext=".jpg")
        cloud_storage.upload(key, content, "image/jpeg")
        cloud_storage.upload_image(key, content, "image/jpeg", thumbnail_size=(200, 200))
    """

    def __init__(self, backend: StorageBackend):
        self.backend = backend

    # ─── Helpers de key ───────────────────────────────────────────────────

    @staticmethod
    def file_hash(content: bytes) -> str:
        """Genera hash corto del contenido para nombres únicos."""
        return hashlib.sha256(content).hexdigest()[:16]

    @staticmethod
    def build_key(folder: str, content: bytes, ext: str, prefix: str = "") -> str:
        """
        Genera una key única para un archivo.

        Args:
            folder: Carpeta destino (ej: "profile", "recibos-{cuit}/{periodo}/{slug}")
            content: Bytes del archivo (para generar hash)
            ext: Extensión con punto (ej: ".jpg", ".pdf")
            prefix: Prefijo opcional (ej: "original", "pag_001")

        Returns:
            Key completa, ej: "profile/a1b2c3d4e5f6_8f9a0b1c.jpg"
        """
        h = hashlib.sha256(content).hexdigest()[:16]
        uid = uuid.uuid4().hex[:8]
        name = f"{prefix}_{h}_{uid}{ext}" if prefix else f"{h}_{uid}{ext}"
        # Normalizar: sin doble slash, sin slash al inicio
        folder = folder.strip("/")
        return f"{folder}/{name}"

    # ─── Operaciones base (delegadas al backend) ─────────────────────────

    def upload(self, key: str, content: bytes, content_type: str = "application/octet-stream") -> str:
        return self.backend.upload(key, content, content_type)

    def download(self, key: str) -> bytes:
        return self.backend.download(key)

    def delete(self, key: str) -> bool:
        return self.backend.delete(key)

    def exists(self, key: str) -> bool:
        return self.backend.exists(key)

    def get_url(self, key: str, expires: int = 3600) -> str:
        return self.backend.get_url(key, expires)

    # ─── Upload de imagen con thumbnail opcional ─────────────────────────

    def upload_image(
        self,
        key: str,
        content: bytes,
        content_type: str = "image/jpeg",
        thumbnail_size: Optional[Tuple[int, int]] = None,
        thumbnail_quality: int = 85,
    ) -> dict:
        """
        Sube una imagen y opcionalmente genera un thumbnail.

        Args:
            key: Key destino de la imagen original
            content: Bytes de la imagen
            content_type: MIME type
            thumbnail_size: Tupla (ancho, alto) para el thumbnail. None = sin thumbnail.
            thumbnail_quality: Calidad JPEG del thumbnail (1-100)

        Returns:
            Dict con:
                - key: key de la imagen original
                - thumbnail_key: key del thumbnail (None si no se generó)
                - size: tamaño en bytes del original
                - thumbnail_size: tamaño en bytes del thumbnail
        """
        # Subir original
        self.backend.upload(key, content, content_type)

        result = {
            "key": key,
            "thumbnail_key": None,
            "size": len(content),
            "thumbnail_size": None,
        }

        # Generar y subir thumbnail si se pidió
        if thumbnail_size:
            try:
                thumb_bytes = self._generate_thumbnail(content, thumbnail_size, thumbnail_quality)
                thumb_key = self._thumbnail_key(key)
                self.backend.upload(thumb_key, thumb_bytes, "image/jpeg")
                result["thumbnail_key"] = thumb_key
                result["thumbnail_size"] = len(thumb_bytes)
            except Exception as e:
                logger.warning(f"No se pudo generar thumbnail para {key}: {e}")

        return result

    def delete_image(self, key: str) -> bool:
        """Elimina una imagen y su thumbnail si existe."""
        thumb_key = self._thumbnail_key(key)
        self.backend.delete(thumb_key)  # No importa si no existe
        return self.backend.delete(key)

    # ─── Helpers internos ─────────────────────────────────────────────────

    @staticmethod
    def _thumbnail_key(key: str) -> str:
        """Genera la key del thumbnail a partir de la key original.
        profile/abc123.jpg → profile/abc123_thumb.jpg
        """
        p = Path(key)
        return str(p.with_name(f"{p.stem}_thumb{p.suffix}"))

    @staticmethod
    def _generate_thumbnail(content: bytes, size: Tuple[int, int], quality: int = 85) -> bytes:
        """Genera un thumbnail JPEG desde bytes de imagen."""
        img = Image.open(BytesIO(content))
        img.thumbnail(size, Image.LANCZOS)

        # Convertir a RGB si tiene alpha (PNG con transparencia)
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGB")

        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=quality, optimize=True)
        return buffer.getvalue()

    # ─── Acceso al path local (solo para LocalStorage) ────────────────────

    def get_absolute_path(self, key: str) -> Optional[str]:
        """Retorna path absoluto. Solo funciona con LocalStorageBackend."""
        if isinstance(self.backend, LocalStorageBackend):
            return self.backend.get_absolute_path(key)
        return None

    def is_local(self) -> bool:
        """Retorna True si el backend es local."""
        return isinstance(self.backend, LocalStorageBackend)


# ─── Factory e instancia global ───────────────────────────────────────────────


def _create_local_storage() -> StorageService:
    """Crea una instancia de StorageService con backend local (filesystem)."""
    from backend.core.config import settings

    base_path = getattr(settings, "storage_local_path", "/data/files")
    backend = LocalStorageBackend(base_path=base_path)
    logger.info(f"Storage local: path={base_path}")
    return StorageService(backend)


def _create_cloud_storage() -> StorageService:
    """Crea una instancia de StorageService con backend GCS.
    Si GCS no está configurado, cae a local como fallback.
    """
    from backend.core.config import settings

    if settings.environment == "testing":
        logger.info("GCS deshabilitado en modo test, cloud_storage usa local")
        return _create_local_storage()

    bucket = getattr(settings, "gcs_bucket_name", "")
    if bucket:
        credentials = getattr(settings, "gcs_credentials_path", "")
        backend = GCSStorageBackend(bucket_name=bucket, credentials_path=credentials)
        logger.info(f"Storage cloud: GCS bucket={bucket}")
        return StorageService(backend)

    # Fallback a local si GCS no está configurado
    logger.warning("GCS no configurado (GCS_BUCKET_NAME vacío), cloud_storage usa local como fallback")
    return _create_local_storage()


# ─── Instancias globales ──────────────────────────────────────────────────────
#
# local_storage: para archivos no críticos (avatares, logos, imágenes CMS)
#   → siempre filesystem local
#
# cloud_storage: para datos críticos (recibos, fotos nómina, certificados, evidencias)
#   → GCS en producción, local como fallback en desarrollo
#
# Uso:
#   from backend.core.storage import cloud_storage, local_storage
#   cloud_storage.upload(key, content)   # recibos, fotos, certificados
#   local_storage.upload(key, content)   # avatares, logos

local_storage = _create_local_storage()
cloud_storage = _create_cloud_storage()
