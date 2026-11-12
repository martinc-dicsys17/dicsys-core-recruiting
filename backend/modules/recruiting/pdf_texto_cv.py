"""Lectura del texto de un CV en PDF: orden de lectura por columnas y deteccion de paginas que necesitan OCR.

Funciones puras sobre paginas de PyMuPDF (sin BD). `CandidatoService._extraer_texto_de_archivo` las usa para:

1. **Orden de lectura** (`texto_pagina_ordenado`): `page.get_text()` devuelve los renglones en el orden en que se
   dibujaron, que en CVs disenados no es el orden en que se leen (columnas laterales, fechas en un margen, bloques
   agregados al final). Se reconstruye con un corte recursivo X/Y sobre los renglones y sus coordenadas:
   - **Corte vertical** (hueco en X que ningun renglon atraviesa y con texto a ambos lados a la misma altura): dos
     columnas reales -> primero la izquierda completa y despues la derecha, sin intercalar experiencias.
   - **Margen de fechas** (columna angosta formada casi solo por fechas, a la izquierda o a la derecha del cuerpo):
     no es una columna de lectura; cada grupo de fechas se ubica antes del renglon del cuerpo a su altura, para
     que el periodo quede junto a su cargo.
   - **Corte horizontal** (el hueco en Y mas grande): separa encabezados que ocupan todo el ancho y secciones.
   Si el texto ordenado no contiene exactamente los mismos caracteres que `get_text()`, o la pagina tiene texto
   girado, se usa `get_text()` sin cambios (alternativa segura). `get_text(sort=True)` no se usa: ordena solo por
   coordenadas e intercala las columnas.

2. **Paginas que necesitan OCR** (`pagina_necesita_ocr`): se evalua cada pagina por separado, sin contar los
   enlaces clickeables (una URI no es texto de la pagina). Se pide OCR cuando la pagina no tiene texto legible
   suficiente **y** tiene una imagen que cubre buena parte de ella (un escaneo); una pagina vacia o con una foto
   chica no se manda a OCR.
"""

import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

# Renglon: (x0, y0, x1, y1, texto)
Renglon = Tuple[float, float, float, float, str]

HUECO_MIN_COLUMNAS = 8.0  # puntos libres en X para considerar dos columnas
SOLAPE_MIN_COLUMNAS = 0.3  # las dos columnas deben compartir al menos esta fraccion de altura
ANCHO_MAX_MARGEN = 0.35  # un margen de fechas ocupa como mucho esta fraccion del ancho de la region
TOLERANCIA_FILA = 4.0  # puntos: una fecha del margen va antes del renglon del cuerpo que empieza a su altura

_PERIODO = re.compile(
    r"\b(?:19|20)\d{2}\b|\b(?:actualidad|presente|actual|hoy|current|present)\b"
    r"|\b(?:ene|feb|mar|abr|may|jun|jul|ago|sep|sept|oct|nov|dic|jan|apr|aug|dec)[a-z]*\.?\b",
    re.IGNORECASE,
)


# ----------------------------------------------------------------------------------------------- orden de lectura


def _renglones(pagina: Any) -> Optional[List[Renglon]]:
    """Renglones de texto de la pagina con su caja; None si hay texto girado (el orden por coordenadas no aplica)."""
    renglones: List[Renglon] = []
    for bloque in pagina.get_text("dict").get("blocks", []):
        if bloque.get("type", 0) != 0:
            continue
        for linea in bloque.get("lines", []):
            direccion = linea.get("dir", (1, 0))
            if abs(direccion[0] - 1) > 0.01 or abs(direccion[1]) > 0.01:
                return None
            texto = "".join(s.get("text", "") for s in linea.get("spans", []))
            if not texto.strip():
                continue
            x0, y0, x1, y1 = (float(v) for v in linea["bbox"])
            renglones.append((x0, y0, x1, y1, texto))
    return renglones


def _corte_vertical(renglones: List[Renglon]) -> Optional[Tuple[List[Renglon], List[Renglon]]]:
    """Hueco en X mas ancho que ningun renglon atraviesa, con texto a ambos lados a una altura compartida."""
    intervalos = sorted((r[0], r[2]) for r in renglones)
    mejor: Optional[Tuple[float, float]] = None
    fin = intervalos[0][1]
    for x0, x1 in intervalos[1:]:
        if x0 - fin >= HUECO_MIN_COLUMNAS and (mejor is None or x0 - fin > mejor[1] - mejor[0]):
            mejor = (fin, x0)
        fin = max(fin, x1)
    if mejor is None:
        return None
    corte = (mejor[0] + mejor[1]) / 2
    izquierda = [r for r in renglones if r[2] <= corte]
    derecha = [r for r in renglones if r[0] >= corte]
    alto_izq = (min(r[1] for r in izquierda), max(r[3] for r in izquierda))
    alto_der = (min(r[1] for r in derecha), max(r[3] for r in derecha))
    solape = min(alto_izq[1], alto_der[1]) - max(alto_izq[0], alto_der[0])
    menor = min(alto_izq[1] - alto_izq[0], alto_der[1] - alto_der[0])
    if solape <= 0 or solape < SOLAPE_MIN_COLUMNAS * menor:
        return None  # no estan una al lado de la otra: es un corte horizontal
    return izquierda, derecha


def _corte_horizontal(renglones: List[Renglon]) -> Optional[Tuple[List[Renglon], List[Renglon]]]:
    """Separa por el hueco en Y mas grande que ningun renglon atraviesa."""
    intervalos = sorted((r[1], r[3]) for r in renglones)
    mejor: Optional[Tuple[float, float]] = None
    fin = intervalos[0][1]
    for y0, y1 in intervalos[1:]:
        if y0 > fin and (mejor is None or y0 - fin > mejor[1] - mejor[0]):
            mejor = (fin, y0)
        fin = max(fin, y1)
    if mejor is None:
        return None
    corte = (mejor[0] + mejor[1]) / 2
    return [r for r in renglones if r[3] <= corte], [r for r in renglones if r[1] >= corte]


def _es_margen_de_fechas(lado: List[Renglon], ancho_region: float) -> bool:
    """Columna angosta cuyos renglones son casi todos fechas o periodos (no es una columna de lectura)."""
    ancho = max(r[2] for r in lado) - min(r[0] for r in lado)
    if ancho > ANCHO_MAX_MARGEN * ancho_region:
        return False
    con_fecha = sum(1 for r in lado if _PERIODO.search(r[4]))
    return con_fecha * 2 >= len(lado) and all(len(r[4].strip()) <= 40 for r in lado)


def _grupos(renglones: List[Renglon]) -> List[List[Renglon]]:
    """Agrupa renglones consecutivos de una columna angosta (un periodo partido en dos renglones queda junto)."""
    grupos: List[List[Renglon]] = []
    for r in sorted(renglones, key=lambda r: (r[1], r[0])):
        if grupos and r[1] - grupos[-1][-1][3] <= (r[3] - r[1]) * 0.6:
            grupos[-1].append(r)
        else:
            grupos.append([r])
    return grupos


def _intercalar_margen(cuerpo: List[Renglon], margen: List[Renglon], a_la_izquierda: bool) -> List[Renglon]:
    """Ubica cada grupo de fechas del margen junto al renglon del cuerpo que esta a su altura: antes de ese renglon
    si el margen esta a la izquierda ("Mar 2026 - Presente" | cargo) y despues si esta a la derecha
    ("Banco Macro" | "07/2023 - Presente"), como se lee."""
    resultado: List[Renglon] = []
    pendientes = _grupos(margen)
    for renglon in cuerpo:
        if a_la_izquierda:
            while pendientes and pendientes[0][0][1] <= renglon[1] + TOLERANCIA_FILA:
                resultado.extend(pendientes.pop(0))
            resultado.append(renglon)
        else:
            resultado.append(renglon)
            while pendientes and pendientes[0][0][1] <= renglon[3]:
                resultado.extend(pendientes.pop(0))
    for grupo in pendientes:
        resultado.extend(grupo)
    return resultado


def _ordenar(renglones: List[Renglon]) -> List[Renglon]:
    if len(renglones) <= 1:
        return list(renglones)
    vertical = _corte_vertical(renglones)
    if vertical:
        izquierda, derecha = vertical
        ancho = max(r[2] for r in renglones) - min(r[0] for r in renglones)
        margen_izq = _es_margen_de_fechas(izquierda, ancho) and not _es_margen_de_fechas(derecha, ancho)
        margen_der = _es_margen_de_fechas(derecha, ancho) and not _es_margen_de_fechas(izquierda, ancho)
        if not (margen_izq or margen_der):
            return _ordenar(izquierda) + _ordenar(derecha)
        margen, cuerpo = (izquierda, derecha) if margen_izq else (derecha, izquierda)
        return _intercalar_margen(_ordenar(cuerpo), margen, margen_izq)
    horizontal = _corte_horizontal(renglones)
    if horizontal:
        arriba, abajo = horizontal
        return _ordenar(arriba) + _ordenar(abajo)
    return sorted(renglones, key=lambda r: (r[1], r[0]))


def _sin_espacios(texto: str) -> List[str]:
    return sorted(c for c in texto if not c.isspace())


def texto_pagina_ordenado(pagina: Any) -> str:
    """Texto de la pagina en orden de lectura (columnas, margen de fechas y secciones); si no es confiable, get_text()."""
    original = pagina.get_text() or ""
    try:
        renglones = _renglones(pagina)
        if not renglones or len(renglones) < 3:
            return original
        ordenado = "\n".join(r[4] for r in _ordenar(renglones))
        # Alternativa segura: el texto ordenado debe tener exactamente los mismos caracteres que la extraccion lineal
        if _sin_espacios(ordenado) != _sin_espacios(original):
            return original
        return ordenado + "\n"
    except Exception:
        return original


# ------------------------------------------------------------------------------------------------ necesidad de OCR

TEXTO_MINIMO_LEGIBLE = 40  # caracteres legibles: por debajo la capa de texto no alcanza para un CV
COBERTURA_MIN_IMAGEN = 0.3  # la imagen debe cubrir al menos esta fraccion de la pagina para tratarse de un escaneo
PROPORCION_MIN_LEGIBLE = 0.6  # fraccion minima de letras, digitos y signos comunes en el texto de la pagina
PALABRAS_MIN = 8
TRAZOS_MIN_TEXTO_DIBUJADO = 150  # texto convertido a contornos: cada letra es un trazo


def _proporcion_legible(texto: str) -> float:
    """Fraccion de caracteres "normales" (letras latinas, digitos, puntuacion comun); texto con fuentes sin mapa
    Unicode aparece como simbolos privados o de control."""
    visibles = [c for c in texto if not c.isspace()]
    if not visibles:
        return 0.0
    normales = 0
    for c in visibles:
        categoria = unicodedata.category(c)
        if c.isascii() and (c.isalnum() or c in ".,;:-_/()+@&%'\"!?|#*"):
            normales += 1
        elif categoria.startswith("L") and unicodedata.name(c, "").startswith("LATIN"):
            normales += 1
        elif categoria in ("Pd", "Ps", "Pe", "Pi", "Pf", "Po") and c != "\ufffd":
            normales += 1
    return normales / len(visibles)


def evaluar_pagina(pagina: Any) -> Dict[str, Any]:
    """Medidas de la pagina para decidir el OCR: texto legible, palabras, bloques y cobertura de imagenes."""
    texto = pagina.get_text() or ""  # sin URIs: los enlaces no son texto de la pagina
    area = float(pagina.rect.width * pagina.rect.height) or 1.0
    cobertura = 0.0
    bloques_texto = 0
    for bloque in pagina.get_text("dict").get("blocks", []):
        if bloque.get("type") == 1:
            x0, y0, x1, y1 = bloque["bbox"]
            cobertura += max(0.0, (x1 - x0)) * max(0.0, (y1 - y0)) / area
        elif any(s.get("text", "").strip() for lin in bloque.get("lines", []) for s in lin.get("spans", [])):
            bloques_texto += 1
    return {
        "caracteres": len("".join(texto.split())),
        "palabras": len(re.findall(r"[^\W\d_]{2,}", texto)),
        "legible": _proporcion_legible(texto),
        "bloques_texto": bloques_texto,
        "cobertura_imagen": min(cobertura, 1.0),
    }


def texto_suficiente(medidas: Dict[str, Any]) -> bool:
    """La capa digital alcanza: bastantes caracteres, palabras reales y mayoria de caracteres legibles."""
    return (
        medidas["caracteres"] >= TEXTO_MINIMO_LEGIBLE
        and medidas["palabras"] >= PALABRAS_MIN
        and medidas["legible"] >= PROPORCION_MIN_LEGIBLE
    )


def pagina_necesita_ocr(pagina: Any) -> bool:
    """True si el contenido de la pagina esta dibujado y no como texto: sin texto legible suficiente y con una
    imagen que cubre buena parte de ella (escaneo) o con muchos trazos vectoriales (texto convertido a contornos).

    - Pagina con texto digital suficiente, aunque tenga fotos o una imagen de fondo: no.
    - Pagina vacia, o con una foto chica y poco texto (portada, foto de perfil): no.
    - Pagina sin capa de texto, o con una capa ilegible (simbolos sin mapa Unicode) o minima, sobre un escaneo: si.
    Los enlaces clickeables no cuentan como texto.
    """
    medidas = evaluar_pagina(pagina)
    if texto_suficiente(medidas):
        return False
    if medidas["cobertura_imagen"] >= COBERTURA_MIN_IMAGEN:
        return True
    try:
        return len(pagina.get_drawings()) >= TRAZOS_MIN_TEXTO_DIBUJADO
    except Exception:
        return False


# --------------------------------------------------------------------------------------- combinacion con el OCR


def _es_icono_ocr(caja: Renglon, cajas: List[Renglon]) -> bool:
    """Icono de contacto leido como letras ("U" del telefono, "O" del pin de ubicacion, "in" de LinkedIn): una caja de
    una o dos letras pegada a la izquierda de otro texto del mismo renglon. Sin filtrarlo, "O Cordoba, Argentina"
    impide reconocer la ubicacion."""
    if not re.fullmatch(r"[^\W\d_]{1,2}", caja[4].strip()):
        return False
    alto = caja[3] - caja[1] or 1.0
    for otra in cajas:
        if otra is caja or len(otra[4].strip()) <= 2:
            continue
        solape = min(caja[3], otra[3]) - max(caja[1], otra[1])
        hueco = otra[0] - caja[2]
        if solape >= 0.4 * min(alto, otra[3] - otra[1]) and -0.3 * alto <= hueco <= 0.6 * alto:
            return True
    return False


def texto_desde_cajas_ocr(cajas: List[Renglon]) -> str:
    """Texto de las cajas del OCR de una pagina con el mismo orden de lectura que el texto digital; las cajas de
    un mismo renglon visual que quedan contiguas se unen con un espacio (el OCR suele partir "Rotulo: valor") y se
    descartan los iconos de contacto leidos como letras."""
    cajas = [c for c in cajas if not _es_icono_ocr(c, cajas)]
    if not cajas:
        return ""
    ordenadas = _ordenar(list(cajas)) if len(cajas) > 1 else list(cajas)
    lineas: List[Renglon] = []
    for caja in ordenadas:
        if lineas:
            x0, y0, x1, y1, texto = lineas[-1]
            alto = min(y1 - y0, caja[3] - caja[1]) or 1.0
            solape = min(y1, caja[3]) - max(y0, caja[1])
            if solape >= 0.5 * alto and 0 <= caja[0] - x1 <= 2.5 * alto:
                lineas[-1] = (x0, min(y0, caja[1]), caja[2], max(y1, caja[3]), f"{texto} {caja[4]}")
                continue
        lineas.append(caja)
    return "\n".join(lin[4] for lin in lineas)


def _clave_linea(texto: str) -> str:
    """Letras y digitos sin tildes ni mayusculas: compara una linea digital con el texto del OCR."""
    sin_tildes = unicodedata.normalize("NFKD", texto)
    return "".join(c.lower() for c in sin_tildes if c.isalnum())


def combinar_texto_pagina(digital: str, ocr: str) -> str:
    """Texto final de una pagina reconocida por OCR.

    Si el OCR no devolvio nada se conserva el texto digital (nunca se pierde lo que ya se habia extraido). Si la
    capa digital es ilegible se descarta. Si es legible pero minima (por ejemplo un pie de pagina sobre un escaneo),
    se agregan al OCR solo las lineas digitales que el OCR no contiene, sin repetir datos.
    """
    if not ocr.strip():
        return digital
    if _proporcion_legible(digital) < PROPORCION_MIN_LEGIBLE:
        return ocr
    clave_ocr = _clave_linea(ocr)
    extra = [lin for lin in digital.splitlines() if _clave_linea(lin) and _clave_linea(lin) not in clave_ocr]
    return "\n".join([ocr, *extra])
