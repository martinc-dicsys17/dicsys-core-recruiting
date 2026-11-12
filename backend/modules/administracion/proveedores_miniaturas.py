"""
Miniaturas de los documentos de proveedores: un PNG de 320 px de ancho que la pestaña
Documentos muestra como thumbnail.

- Imágenes (jpg, jpeg, png): se achican con Pillow.
- PDF: la primera página, con PyMuPDF.
- Excel (xlsx): las primeras filas de la primera hoja, leídas con openpyxl y dibujadas
  como una grilla con Pillow.
- Word (docx): los títulos y párrafos del documento, leídos del XML del zip con la
  biblioteca estándar y dibujados como una página con Pillow.
- Word 97 (doc): sin miniatura (no hay forma confiable de leerlo en Python puro).

Las de Word y Excel son una vista previa del contenido (textos y celdas), no la página
tal como la muestra Office. Si algo falla, el documento queda sin miniatura y la
pantalla muestra el tipo: subir nunca falla por la miniatura.
"""

import io
import logging
import zipfile
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import List, Optional
from xml.etree import ElementTree

from PIL import Image, ImageDraw, ImageFont, ImageOps

logger = logging.getLogger(__name__)

ANCHO = 320
ALTO_MAXIMO = 480
ALTO_PAGINA = 452  # proporción A4
MARGEN = 18
IMAGENES = (".jpg", ".jpeg", ".png")
# Un docx o un xlsx de 10 MB puede descomprimir mucho más: tope para no leer una bomba zip
DESCOMPRIMIDO_MAXIMO = 50 * 1024 * 1024
FILAS_EXCEL = 18
COLUMNAS_EXCEL = 5

# La fuente de los banners de Innovación (Inter, variable: el peso se elige por nombre)
FUENTE = Path(__file__).resolve().parents[1] / "innovacion" / "og_assets" / "fonts" / "Inter.ttf"
TINTA = (30, 41, 59)
TINTA_SUAVE = (100, 116, 139)
LINEA = (226, 232, 240)
FONDO_ENCABEZADO = (241, 245, 249)

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def generar(contenido: bytes, extension: str) -> Optional[bytes]:
    """El PNG de la miniatura, o None si no hay (la pantalla muestra el tipo)."""
    try:
        if extension in IMAGENES:
            return _de_imagen(contenido)
        if extension == ".pdf":
            return _de_pdf(contenido)
        if extension == ".xlsx":
            return _de_xlsx(contenido)
        if extension == ".docx":
            return _de_docx(contenido)
    except Exception as exc:  # noqa: BLE001 - la miniatura es accesoria: el documento se sube igual
        logger.warning(f"No se pudo generar la miniatura de un {extension}: {exc}")
    return None


# ─── Imágenes y PDF ─────────────────────────────────────────────────────────────


def _de_imagen(contenido: bytes) -> bytes:
    with Image.open(io.BytesIO(contenido)) as original:
        imagen = ImageOps.exif_transpose(original)  # las fotos del celular, derechas
        imagen.thumbnail((ANCHO, ALTO_MAXIMO))
        if imagen.mode not in ("RGB", "RGBA"):
            imagen = imagen.convert("RGBA")
        return _png(imagen)


def _de_pdf(contenido: bytes) -> Optional[bytes]:
    import pymupdf

    with pymupdf.open(stream=contenido, filetype="pdf") as documento:
        if documento.page_count == 0:
            return None
        pagina = documento.load_page(0)
        escala = ANCHO / pagina.rect.width if pagina.rect.width else 1
        return pagina.get_pixmap(matrix=pymupdf.Matrix(escala, escala), alpha=False).tobytes("png")


# ─── Excel ──────────────────────────────────────────────────────────────────────


def _texto_de_celda(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, datetime):
        return valor.strftime("%d/%m/%Y %H:%M") if (valor.hour or valor.minute) else valor.strftime("%d/%m/%Y")
    if isinstance(valor, date):
        return valor.strftime("%d/%m/%Y")
    if isinstance(valor, float):
        return f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".").removesuffix(",00")
    return str(valor).strip()


def _de_xlsx(contenido: bytes) -> Optional[bytes]:
    from openpyxl import load_workbook

    _controlar_zip(contenido)
    libro = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
    try:
        hoja = libro.worksheets[0]
        filas = [
            [_texto_de_celda(v) for v in fila]
            for fila in hoja.iter_rows(max_row=FILAS_EXCEL, max_col=COLUMNAS_EXCEL * 2, values_only=True)
        ]
        nombre_hoja = hoja.title
    finally:
        libro.close()
    # Solo las columnas que tienen algo, hasta COLUMNAS_EXCEL
    columnas = [c for c in range(max((len(f) for f in filas), default=0)) if any(c < len(f) and f[c] for f in filas)]
    columnas = columnas[:COLUMNAS_EXCEL]
    filas = [[f[c] if c < len(f) else "" for c in columnas] for f in filas]
    while filas and not any(filas[-1]):
        filas.pop()
    if not filas or not columnas:
        return None

    imagen, dibujo = _pagina()
    chica, chica_negrita = _fuente(9), _fuente(9, negrita=True)
    dibujo.text(
        (MARGEN, MARGEN - 4),
        _recortar(nombre_hoja, _fuente(10, negrita=True), ANCHO - 2 * MARGEN),
        font=_fuente(10, negrita=True),
        fill=TINTA_SUAVE,
    )
    anchos = _anchos_de_columnas(filas, chica_negrita, ANCHO - 2 * MARGEN)
    alto_fila = 18
    y = MARGEN + 16
    for numero, fila in enumerate(filas):
        if y + alto_fila > ALTO_PAGINA - MARGEN:
            break
        fuente = chica_negrita if numero == 0 else chica
        if numero == 0:
            dibujo.rectangle([MARGEN, y, ANCHO - MARGEN, y + alto_fila], fill=FONDO_ENCABEZADO)
        x = MARGEN
        for texto, ancho in zip(fila, anchos):
            texto = _recortar(texto, fuente, ancho - 6)
            numerico = texto.replace(".", "").replace(",", "").replace("-", "").isdigit()
            posicion = x + ancho - 3 - fuente.getlength(texto) if numerico and numero else x + 3
            dibujo.text((posicion, y + 4), texto, font=fuente, fill=TINTA)
            x += ancho
        dibujo.line([MARGEN, y + alto_fila, ANCHO - MARGEN, y + alto_fila], fill=LINEA)
        y += alto_fila
    # Bordes de las columnas
    x = MARGEN
    for ancho in [0, *anchos]:
        x += ancho
        dibujo.line([x, MARGEN + 16, x, y], fill=LINEA)
    dibujo.line([MARGEN, MARGEN + 16, ANCHO - MARGEN, MARGEN + 16], fill=LINEA)
    return _png(imagen)


def _anchos_de_columnas(filas: List[List[str]], fuente, disponible: float) -> List[float]:
    """
    Las columnas cortas (fechas, importes) se llevan su ancho completo; el resto se reparte
    en partes iguales entre las largas, que se cortan con «…». Si todo entra, lo que sobra
    se reparte en proporción.
    """
    naturales = [max(fuente.getlength(f[i]) for f in filas) + 8 for i in range(len(filas[0]))]
    anchos = [0.0] * len(naturales)
    pendientes, libre = list(range(len(naturales))), disponible
    while pendientes:
        parte = libre / len(pendientes)
        cortas = [i for i in pendientes if naturales[i] <= parte]
        if not cortas:
            for i in pendientes:
                anchos[i] = parte
            return anchos
        for i in cortas:
            anchos[i] = naturales[i]
            libre -= naturales[i]
            pendientes.remove(i)
    return [ancho * disponible / sum(anchos) for ancho in anchos]


# ─── Word ───────────────────────────────────────────────────────────────────────


def _parrafos_docx(contenido: bytes) -> List[tuple]:
    """[(es_titulo, texto)] del cuerpo del documento, en orden (las tablas, celda por celda)."""
    _controlar_zip(contenido)
    with zipfile.ZipFile(io.BytesIO(contenido)) as archivo:
        xml = archivo.read("word/document.xml")
    if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:  # un docx de Word no los usa: no se procesa
        raise ValueError("el documento trae declaraciones XML que no se procesan")
    cuerpo = ElementTree.fromstring(xml).find(f"{W}body")
    if cuerpo is None:
        return []
    parrafos = []
    for parrafo in cuerpo.iter(f"{W}p"):
        texto = "".join(t.text or "" for t in parrafo.iter(f"{W}t")).strip()
        estilo = parrafo.find(f"{W}pPr/{W}pStyle")
        nombre_estilo = (estilo.get(f"{W}val") or "").lower() if estilo is not None else ""
        es_titulo = nombre_estilo.startswith(("heading", "titulo", "título", "title", "ttulo"))
        parrafos.append((es_titulo, texto))
    return parrafos


def _de_docx(contenido: bytes) -> Optional[bytes]:
    parrafos = _parrafos_docx(contenido)
    if not any(texto for _, texto in parrafos):
        return None
    imagen, dibujo = _pagina()
    titulo, cuerpo = _fuente(13, negrita=True), _fuente(8)
    disponible = ANCHO - 2 * MARGEN
    y = MARGEN
    for es_titulo, texto in parrafos:
        if not texto:
            y += 5
            continue
        fuente = titulo if es_titulo else cuerpo
        alto_linea = 17 if es_titulo else 11
        for linea in _envolver(texto, fuente, disponible):
            if y + alto_linea > ALTO_PAGINA - MARGEN:
                return _png(imagen)
            dibujo.text((MARGEN, y), linea, font=fuente, fill=TINTA)
            y += alto_linea
        y += 6 if es_titulo else 3
    return _png(imagen)


# ─── Dibujo ─────────────────────────────────────────────────────────────────────


@lru_cache(maxsize=8)
def _fuente(tamano: int, negrita: bool = False):
    if FUENTE.exists():
        fuente = ImageFont.truetype(str(FUENTE), tamano)
        try:
            fuente.set_variation_by_name("Bold" if negrita else "Regular")
        except Exception:  # noqa: BLE001 - si no es variable, queda el peso que trae
            pass
        return fuente
    return ImageFont.load_default(size=tamano)


def _pagina():
    imagen = Image.new("RGB", (ANCHO, ALTO_PAGINA), "white")
    return imagen, ImageDraw.Draw(imagen)


def _recortar(texto: str, fuente, ancho: float) -> str:
    """El texto entero si entra; si no, cortado con «…»."""
    if fuente.getlength(texto) <= ancho:
        return texto
    while texto and fuente.getlength(texto + "…") > ancho:
        texto = texto[:-1]
    return texto + "…" if texto else ""


def _envolver(texto: str, fuente, ancho: float) -> List[str]:
    """Las líneas del párrafo en el ancho dado (una palabra que no entra, se corta)."""
    lineas, actual = [], ""
    for palabra in texto.split():
        prueba = f"{actual} {palabra}" if actual else palabra
        if fuente.getlength(prueba) <= ancho:
            actual = prueba
            continue
        if actual:
            lineas.append(actual)
        actual = palabra if fuente.getlength(palabra) <= ancho else _recortar(palabra, fuente, ancho)
    if actual:
        lineas.append(actual)
    return lineas


def _controlar_zip(contenido: bytes) -> None:
    with zipfile.ZipFile(io.BytesIO(contenido)) as archivo:
        if sum(info.file_size for info in archivo.infolist()) > DESCOMPRIMIDO_MAXIMO:
            raise ValueError("descomprimido es demasiado grande")


def _png(imagen: Image.Image) -> bytes:
    salida = io.BytesIO()
    imagen.save(salida, "PNG", optimize=True)
    return salida.getvalue()
