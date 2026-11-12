"""Conversion de CV Word (.doc/.docx) a PDF para la vista previa del modal de comparacion."""

import logging
import os
import shutil
import subprocess
import tempfile

logger = logging.getLogger(__name__)

PREFIJOS_CV_PERMITIDOS = ("recruiting/cv/", "recruiting/cv_duplicados/")
EXTENSIONES_WORD = (".doc", ".docx")
TIMEOUT_CONVERSION_SEGUNDOS = 60


class ConversionNoDisponibleError(Exception):
    """LibreOffice no esta instalado o la conversion fallo."""


def ruta_cv_convertible(ruta: str) -> bool:
    """True si la clave es un CV Word dentro de las carpetas de CV (sin saltos de directorio)."""
    if ".." in ruta.split("/") or ruta.startswith("/"):
        return False
    return ruta.startswith(PREFIJOS_CV_PERMITIDOS) and ruta.lower().endswith(EXTENSIONES_WORD)


def convertir_word_a_pdf(contenido: bytes, extension: str) -> bytes:
    """Convierte el contenido Word a PDF con LibreOffice headless. Bloqueante: ejecutar en un hilo."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        logger.warning(
            "Vista previa de CV Word no disponible: LibreOffice (soffice) no esta instalado en el contenedor"
        )
        raise ConversionNoDisponibleError("LibreOffice no esta instalado")

    with tempfile.TemporaryDirectory(prefix="cvprev_") as tmp:
        origen = os.path.join(tmp, f"cv{extension}")
        with open(origen, "wb") as f:
            f.write(contenido)
        perfil = os.path.join(tmp, "perfil")
        try:
            subprocess.run(
                [
                    soffice,
                    f"-env:UserInstallation=file://{perfil}",
                    "--headless",
                    "--norestore",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    tmp,
                    origen,
                ],
                check=True,
                capture_output=True,
                timeout=TIMEOUT_CONVERSION_SEGUNDOS,
                env={**os.environ, "HOME": tmp},
            )
        except subprocess.CalledProcessError as e:
            detalle = (e.stderr or b"").decode("utf-8", errors="replace").strip()[:500]
            logger.warning(f"Fallo la conversion de CV a PDF (codigo {e.returncode}): {detalle}")
            raise ConversionNoDisponibleError(str(e)) from e
        except (subprocess.SubprocessError, OSError) as e:
            logger.warning(f"Fallo la conversion de CV a PDF: {e}")
            raise ConversionNoDisponibleError(str(e)) from e
        destino = os.path.join(tmp, "cv.pdf")
        if not os.path.exists(destino):
            logger.warning("Fallo la conversion de CV a PDF: LibreOffice no genero el archivo de salida")
            raise ConversionNoDisponibleError("LibreOffice no genero el PDF")
        with open(destino, "rb") as f:
            return f.read()
