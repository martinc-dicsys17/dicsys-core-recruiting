"""
Servicio de manejo de archivos.
"""

import hashlib
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

# Directorio base para archivos
FILES_DIR = Path("/data/files")
PROFILE_DIR = FILES_DIR / "profile"
SUPPORT_IMG_DIR = FILES_DIR / "support-img"

# Extensiones permitidas para imágenes
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
SUPPORT_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".pdf"}
MAX_FILE_SIZE = 2 * 1024 * 1024  # 2MB
MAX_SUPPORT_FILE_SIZE = 5 * 1024 * 1024  # 5MB para soporte


def init_directories():
    """Crea los directorios necesarios si no existen."""
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    SUPPORT_IMG_DIR.mkdir(parents=True, exist_ok=True)


def get_file_hash(content: bytes) -> str:
    """Genera un hash único para el contenido del archivo."""
    return hashlib.sha256(content).hexdigest()[:16]


async def save_profile_image(file: UploadFile) -> str:
    """
    Guarda una imagen de perfil y retorna la URL relativa.
    """
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400, detail=f"Tipo de archivo no permitido. Use: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    content = await file.read()

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="El archivo excede el tamaño máximo de 2MB")

    file_hash = get_file_hash(content)
    unique_id = uuid.uuid4().hex[:8]
    filename = f"{file_hash}_{unique_id}{ext}"

    init_directories()

    file_path = PROFILE_DIR / filename
    with open(file_path, "wb") as f:
        f.write(content)

    return f"/files/profile/{filename}"


def delete_profile_image(url: str) -> bool:
    """Elimina una imagen de perfil dado su URL."""
    if not url or not url.startswith("/files/profile/"):
        return False

    filename = url.split("/")[-1]
    file_path = PROFILE_DIR / filename

    if file_path.exists():
        file_path.unlink()
        return True
    return False


async def save_support_image(file: UploadFile) -> str:
    """Guarda una imagen de soporte y retorna la URL relativa."""
    ext = Path(file.filename).suffix.lower()
    if ext not in SUPPORT_EXTENSIONS:
        raise HTTPException(
            status_code=400, detail=f"Tipo de archivo no permitido. Use: {', '.join(SUPPORT_EXTENSIONS)}"
        )

    content = await file.read()
    if len(content) > MAX_SUPPORT_FILE_SIZE:
        raise HTTPException(status_code=400, detail="El archivo excede el tamaño máximo de 5MB")

    file_hash = get_file_hash(content)
    unique_id = uuid.uuid4().hex[:8]
    filename = f"{file_hash}_{unique_id}{ext}"

    SUPPORT_IMG_DIR.mkdir(parents=True, exist_ok=True)
    file_path = SUPPORT_IMG_DIR / filename
    with open(file_path, "wb") as f:
        f.write(content)

    return f"/files/support-img/{filename}"


async def save_acuerdo_image(file: UploadFile) -> str:
    """Guarda una imagen de acuerdo firmado en subcarpeta dedicada."""
    ext = Path(file.filename).suffix.lower()
    if ext not in SUPPORT_EXTENSIONS:
        raise HTTPException(
            status_code=400, detail=f"Tipo de archivo no permitido. Use: {', '.join(SUPPORT_EXTENSIONS)}"
        )

    content = await file.read()
    if len(content) > MAX_SUPPORT_FILE_SIZE:
        raise HTTPException(status_code=400, detail="El archivo excede el tamaño máximo de 5MB")

    file_hash = get_file_hash(content)
    unique_id = uuid.uuid4().hex[:8]
    filename = f"{file_hash}_{unique_id}{ext}"

    acuerdos_dir = SUPPORT_IMG_DIR / "acuerdos"
    acuerdos_dir.mkdir(parents=True, exist_ok=True)
    file_path = acuerdos_dir / filename
    with open(file_path, "wb") as f:
        f.write(content)

    return f"/files/support-img/acuerdos/{filename}"
