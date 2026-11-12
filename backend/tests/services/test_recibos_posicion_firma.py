"""Cálculo de dónde estampar la firma del empleado.

En los recibos sin duplicado el bloque de firmas se corre verticalmente según la
cantidad de conceptos, así que la posición se lee del PDF en vez de hardcodearla.
"""

import pytest

try:
    import pymupdf
except ImportError:  # pragma: no cover
    pymupdf = None

from backend.modules.recibos.pdf_service import PDFService

pytestmark = pytest.mark.services

ANCHO, ALTO = 612, 792


def recibo_sin_duplicado(y_linea):
    """Arma una hoja con el bloque de firmas a la altura pedida."""
    doc = pymupdf.open()
    page = doc.new_page(width=ANCHO, height=ALTO)
    for x0, x1, etiqueta, ex in (
        (295.44, 404.16, "Firma Empleador", 324.72),
        (431.16, 540.72, "Firma Empleado", 453.0),
    ):
        page.draw_line(pymupdf.Point(x0, y_linea), pymupdf.Point(x1, y_linea))
        page.insert_text((ex, y_linea + 9), etiqueta, fontsize=7)
    return doc.tobytes()


def recibo_con_duplicado():
    """Recibo con duplicado: pie a altura fija, sin la etiqueta del bloque."""
    doc = pymupdf.open()
    page = doc.new_page(width=ANCHO, height=ALTO)
    page.insert_text((60, 740), "Recibí el importe de mis haberes", fontsize=7)
    page.insert_text((190, 752), "FIRMA", fontsize=7)
    return doc.tobytes()


needs_pymupdf = pytest.mark.skipif(pymupdf is None, reason="PyMuPDF no disponible")


@needs_pymupdf
def test_sin_la_etiqueta_no_devuelve_posicion():
    # El front cae a su posición por defecto, que para ese layout es correcta.
    assert PDFService.calcular_posicion_firma(recibo_con_duplicado()) is None


@needs_pymupdf
def test_la_firma_va_arriba_de_la_linea_con_lugar_para_el_texto():
    y_linea = 556.2
    pos = PDFService.calcular_posicion_firma(recibo_sin_duplicado(y_linea))

    # pdf-lib mide desde abajo: y es el borde inferior de la imagen. La firma se
    # levanta para dejar los dos renglones de texto entre ella y la línea.
    base = ALTO - y_linea
    assert pos["y"] > base
    assert pos["y"] == pytest.approx(base + PDFService.FIRMA_SEPARACION_TEXTO, abs=0.5)


@needs_pymupdf
def test_la_firma_entra_en_la_linea_y_queda_centrada():
    pos = PDFService.calcular_posicion_firma(recibo_sin_duplicado(556.2))

    assert pos["ancho"] <= 540.72 - 431.16
    assert pos["x"] >= 431.16
    assert pos["x"] + pos["ancho"] <= 540.72
    izquierda = pos["x"] - 431.16
    derecha = 540.72 - (pos["x"] + pos["ancho"])
    assert izquierda == pytest.approx(derecha, abs=1.0)


@needs_pymupdf
def test_el_texto_va_entre_la_firma_y_la_linea():
    y_linea = 556.2
    pos = PDFService.calcular_posicion_firma(recibo_sin_duplicado(y_linea))

    base = ALTO - y_linea
    nombre_y = pos["texto_y"] - 9  # el segundo renglón, el más bajo

    # Los dos renglones quedan sobre la línea...
    assert nombre_y > base
    # ...y por debajo de la firma.
    assert pos["texto_y"] < pos["y"]


@needs_pymupdf
def test_el_texto_se_centra_sobre_la_linea():
    pos = PDFService.calcular_posicion_firma(recibo_sin_duplicado(556.2))

    assert pos["centro_x"] == pytest.approx((431.16 + 540.72) / 2, abs=1.0)
    # La firma comparte ese centro.
    assert pos["x"] + pos["ancho"] / 2 == pytest.approx(pos["centro_x"], abs=0.5)


@needs_pymupdf
@pytest.mark.parametrize("y_linea", [533.8, 556.2, 581.8, 605.8, 629.8])
def test_la_posicion_sigue_al_bloque_de_firmas(y_linea):
    # Las alturas del test son las que aparecen en un lote real: 96 pt de
    # diferencia entre el recibo más corto y el más largo.
    pos = PDFService.calcular_posicion_firma(recibo_sin_duplicado(y_linea))

    base = ALTO - y_linea
    assert pos["y"] == pytest.approx(base + PDFService.FIRMA_SEPARACION_TEXTO, abs=0.5)
    assert pos["texto_y"] - 9 > base  # el texto no baja de la línea
    assert pos["texto_y"] < pos["y"]  # y queda bajo la firma


@needs_pymupdf
def test_el_pie_no_depende_del_bloque():
    arriba = PDFService.calcular_posicion_firma(recibo_sin_duplicado(533.8))
    abajo = PDFService.calcular_posicion_firma(recibo_sin_duplicado(629.8))

    assert arriba["pie_y"] == abajo["pie_y"]
    # Por debajo del texto de la firma en los dos casos.
    assert arriba["pie_y"] < abajo["texto_y"]


@needs_pymupdf
def test_pagina_en_blanco_no_explota():
    doc = pymupdf.open()
    doc.new_page(width=ANCHO, height=ALTO)

    assert PDFService.calcular_posicion_firma(doc.tobytes()) is None
