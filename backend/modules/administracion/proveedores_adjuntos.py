"""
Archivos de un proveedor: el adjunto de política/NDA (D-84) y los documentos de la
pestaña Documentos.

- NDA: pdf, jpg, png, doc y docx.
- Documentos: lo mismo y además xlsx.

Hasta 10 MB cada uno, mientras D-56 (tipos y tamaño de subidas de todo el sistema)
siga abierta. El tipo se valida por contenido (firma del archivo), no solo por la
extensión.

Los archivos van al storage con una clave aleatoria y se descargan solo por los
endpoints del módulo, que validan el permiso.
"""

import io
import uuid
import zipfile
from typing import Tuple

TAMANO_MAXIMO = 10 * 1024 * 1024

# extensión → (tipo MIME, firma al inicio del archivo)
TIPOS = {
    ".pdf": ("application/pdf", b"%PDF-"),
    ".jpg": ("image/jpeg", b"\xff\xd8\xff"),
    ".jpeg": ("image/jpeg", b"\xff\xd8\xff"),
    ".png": ("image/png", b"\x89PNG\r\n\x1a\n"),
    ".doc": ("application/msword", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"),
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", b"PK\x03\x04"),
    ".xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", b"PK\x03\x04"),
}
EXTENSIONES_NDA = (".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx")
EXTENSIONES_DOCUMENTOS = (*EXTENSIONES_NDA, ".xlsx")
# Un docx y un xlsx son zip: se reconocen por la parte principal que tienen adentro
PARTE_PRINCIPAL = {".docx": "word/document.xml", ".xlsx": "xl/workbook.xml"}


class AdjuntoInvalido(ValueError):
    """El archivo no es de un tipo aceptado o es demasiado grande (422)."""


def _extension(nombre: str) -> str:
    punto = nombre.rfind(".")
    return nombre[punto:].lower() if punto >= 0 else ""


def _tiene_parte(contenido: bytes, parte: str) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(contenido)) as archivo:
            return parte in archivo.namelist()
    except zipfile.BadZipFile:
        return False


def _nombres(extensiones) -> str:
    """«PDF, JPG, PNG, DOC o DOCX» (jpeg va con jpg)."""
    nombres = [e[1:].upper() for e in extensiones if e != ".jpeg"]
    return ", ".join(nombres[:-1]) + f" o {nombres[-1]}"


def validar(nombre: str, contenido: bytes, extensiones=EXTENSIONES_NDA) -> Tuple[str, str]:
    """Devuelve (extensión, tipo MIME) o AdjuntoInvalido."""
    if not contenido:
        raise AdjuntoInvalido("El archivo está vacío")
    if len(contenido) > TAMANO_MAXIMO:
        raise AdjuntoInvalido("El archivo supera los 10 MB")
    extension = _extension(nombre or "")
    if extension not in extensiones:
        raise AdjuntoInvalido(f"Solo se aceptan archivos {_nombres(extensiones)}")
    tipo, firma = TIPOS[extension]
    parte = PARTE_PRINCIPAL.get(extension)
    if not contenido.startswith(firma) or (parte and not _tiene_parte(contenido, parte)):
        raise AdjuntoInvalido("El contenido del archivo no coincide con su extensión")
    return extension, tipo


def clave_storage(empresa_id: uuid.UUID, extension: str) -> str:
    """Clave aleatoria: no se puede adivinar a partir del proveedor ni del contenido."""
    return f"proveedores/{empresa_id}/nda/{uuid.uuid4().hex}{extension}"


def clave_documento(empresa_id: uuid.UUID, proveedor_id: uuid.UUID, documento_id: uuid.UUID, extension: str) -> str:
    """{empresa_id}/proveedores/{proveedor_id}/{uuid}{ext}: el nombre original queda en la base."""
    return f"{empresa_id}/proveedores/{proveedor_id}/{documento_id.hex}{extension}"


def clave_miniatura(clave: str) -> str:
    """La miniatura PNG, al lado del documento."""
    return f"{clave.rsplit('.', 1)[0]}-miniatura.png"


def tipo_por_nombre(clave: str) -> str:
    return TIPOS.get(_extension(clave), ("application/octet-stream", b""))[0]
