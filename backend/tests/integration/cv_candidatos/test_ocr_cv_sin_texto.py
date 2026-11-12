"""OCR de respaldo para CV en PDF: se activa solo en las paginas sin texto digital legible.

Los PDF se generan en memoria con datos ficticios. El motor RapidOCR se sustituye por uno simulado (salvo en la prueba
con el motor real, que se omite si no esta instalado), para comprobar cuando se ejecuta, sobre que paginas y como se
combina su texto con el digital. Cualquier falla del OCR debe degradar sin romper la importacion ni perder el texto
digital ya extraido.
"""

from types import SimpleNamespace

import fitz
import pytest

from backend.core import cv_ocr
from backend.modules.recruiting import pdf_texto_cv
from backend.modules.recruiting.services import CandidatoService

EMAIL = "damian.e.gomez@hotmail.com"
TELEFONO = "+54 1163069535"


def _pagina_con_texto(doc, email: str = EMAIL):
    pagina = doc.new_page()
    pagina.insert_text((60, 120), "Damian Gomez", fontsize=20)
    pagina.insert_text((60, 150), "ANALISTA DE DATOS", fontsize=14)
    pagina.insert_text((60, 200), TELEFONO, fontsize=14)
    pagina.insert_text((60, 230), email, fontsize=14)
    pagina.insert_text((60, 260), "https://www.linkedin.com/in/damiiangomez/", fontsize=14)
    pagina.insert_text(
        (60, 300), "Experiencia en analisis de datos, reportes y tableros para la toma de decisiones.", fontsize=11
    )
    return pagina


def _pdf_con_texto(email: str = EMAIL) -> bytes:
    doc = fitz.open()
    _pagina_con_texto(doc, email)
    return doc.tobytes()


def _png_de_pagina_con_texto(email: str = EMAIL) -> bytes:
    origen = fitz.open(stream=_pdf_con_texto(email), filetype="pdf")
    return origen[0].get_pixmap(matrix=fitz.Matrix(2, 2)).tobytes("png")


def _pagina_escaneada(doc, email: str = EMAIL, texto_digital: str = "", enlace: bool = False):
    """Pagina cuyo contenido es una imagen (escaneo); opcionalmente con una capa de texto minima o un enlace."""
    pagina = doc.new_page()
    pagina.insert_image(pagina.rect, stream=_png_de_pagina_con_texto(email))
    if texto_digital:
        pagina.insert_text((60, 820), texto_digital, fontsize=8)
    if enlace:
        pagina.insert_link(
            {
                "kind": fitz.LINK_URI,
                "from": fitz.Rect(60, 245, 300, 265),
                "uri": "https://www.linkedin.com/in/damiiangomez/",
            }
        )
    return pagina


def _pdf_texto_como_imagen(email: str = EMAIL, **kwargs) -> bytes:
    doc = fitz.open()
    _pagina_escaneada(doc, email, **kwargs)
    return doc.tobytes()


def _salida(items):
    """Resultado con la forma de RapidOCR 3.x (RapidOCROutput): boxes, txts y scores."""
    import numpy as np

    if not items:
        return SimpleNamespace(boxes=None, txts=None, scores=None)
    return SimpleNamespace(
        boxes=np.array([c for c, _, _ in items], dtype=float),
        txts=tuple(t for _, t, _ in items),
        scores=tuple(s for _, _, s in items),
    )


class MotorSimulado:
    """Devuelve siempre las mismas cajas (en pixeles de la imagen) y registra cuantas paginas recibio."""

    def __init__(self, lineas=("Damian Gomez", "ANALISTA DE DATOS", TELEFONO, EMAIL)):
        self.lineas = lineas
        self.llamadas = 0

    def __call__(self, imagen, **_k):
        self.llamadas += 1
        return _salida(
            [
                ([[100, 100 + 40 * i], [600, 100 + 40 * i], [600, 130 + 40 * i], [100, 130 + 40 * i]], lin, 0.95)
                for i, lin in enumerate(self.lineas)
            ]
        )


@pytest.fixture
def motor(monkeypatch):
    simulado = MotorSimulado()
    monkeypatch.setattr(cv_ocr, "_motor", simulado)
    monkeypatch.setattr(cv_ocr, "_motor_no_disponible", False)
    return simulado


@pytest.fixture
def paginas_ocr(monkeypatch):
    """Registra las paginas que se mandan a OCR (sin ejecutarlo)."""
    pedidas = []

    def _registrar(contenido, indices):
        pedidas.extend(indices)
        return {}

    monkeypatch.setattr("backend.core.cv_ocr.reconocer_cajas_pdf", _registrar)
    monkeypatch.setattr("backend.core.cv_ocr.extraer_texto_pdf_por_ocr", lambda c: pedidas.append("documento") or "")
    return pedidas


# --- 1. PDF digital normal ----------------------------------------------------------------------------------------


def test_pdf_digital_no_usa_ocr(paginas_ocr):
    texto = CandidatoService._extraer_texto_de_archivo(_pdf_con_texto(), ".pdf")
    assert paginas_ocr == []
    assert CandidatoService.parsear_cv_texto(texto, "cv.pdf")["email"] == EMAIL


def test_docx_no_usa_ocr(paginas_ocr):
    assert CandidatoService._extraer_texto_de_archivo(b"no es un docx", ".docx") == ""
    assert paginas_ocr == []


# --- 2. PDF escaneado sin texto -----------------------------------------------------------------------------------


def test_pdf_escaneado_no_tiene_texto_digital():
    with fitz.open(stream=_pdf_texto_como_imagen(), filetype="pdf") as doc:
        assert doc[0].get_text().strip() == ""
        assert pdf_texto_cv.pagina_necesita_ocr(doc[0])


def test_pdf_escaneado_usa_ocr_y_el_parser_existente_detecta_los_datos(motor):
    texto = CandidatoService._extraer_texto_de_archivo(_pdf_texto_como_imagen(), ".pdf")
    assert motor.llamadas == 1
    datos = CandidatoService.parsear_cv_texto(texto, "cv.pdf")
    assert datos["email"] == EMAIL
    assert datos["telefono"] == TELEFONO


def test_pdf_escaneado_con_rapidocr_real_detecta_el_email():
    pytest.importorskip("rapidocr")
    if not all(r.is_file() for r in cv_ocr.rutas_modelos()):
        pytest.skip("modelos OCR no instalados")
    texto = CandidatoService._extraer_texto_de_archivo(_pdf_texto_como_imagen(), ".pdf")
    assert CandidatoService.parsear_cv_texto(texto, "cv.pdf")["email"] == EMAIL


# --- 3. PDF escaneado con enlace clickeable -----------------------------------------------------------------------


def test_pdf_escaneado_con_enlace_usa_ocr_y_conserva_la_uri(motor):
    texto = CandidatoService._extraer_texto_de_archivo(_pdf_texto_como_imagen(enlace=True), ".pdf")
    assert motor.llamadas == 1  # la URI del enlace no cuenta como texto de la pagina
    assert EMAIL in texto
    assert texto.rstrip().endswith("https://www.linkedin.com/in/damiiangomez/")


# --- 4. PDF mixto ---------------------------------------------------------------------------------------------------


def _pdf_mixto() -> bytes:
    doc = fitz.open()
    _pagina_con_texto(doc)  # pagina 1: digital
    _pagina_escaneada(doc, "otro.mail@example.com")  # pagina 2: escaneada
    pagina = doc.new_page()  # pagina 3: digital
    pagina.insert_text((60, 120), "Referencias laborales disponibles a pedido del entrevistador.", fontsize=12)
    pagina.insert_text((60, 150), "Disponibilidad inmediata para trabajar de forma remota o hibrida.", fontsize=12)
    return doc.tobytes()


def test_pdf_mixto_solo_hace_ocr_de_la_pagina_escaneada(paginas_ocr):
    CandidatoService._extraer_texto_de_archivo(_pdf_mixto(), ".pdf")
    assert paginas_ocr == [1]


def test_pdf_mixto_mantiene_el_orden_de_las_paginas(monkeypatch):
    monkeypatch.setattr(cv_ocr, "_motor", MotorSimulado(("TEXTO DE LA PAGINA ESCANEADA",)))
    monkeypatch.setattr(cv_ocr, "_motor_no_disponible", False)
    texto = CandidatoService._extraer_texto_de_archivo(_pdf_mixto(), ".pdf")
    posiciones = [texto.index(t) for t in (EMAIL, "TEXTO DE LA PAGINA ESCANEADA", "Referencias laborales")]
    assert posiciones == sorted(posiciones)


# --- 5. PDF digital con dos columnas ------------------------------------------------------------------------------


def test_pdf_a_dos_columnas_no_usa_ocr_para_ordenar(paginas_ocr):
    doc = fitz.open()
    pagina = doc.new_page()
    pagina.insert_text((40, 60), "Laura Perez", fontsize=24)
    izquierda = ["CONTACTO", "laura.perez@example.com", "+54 11 5555 1234", "HABILIDADES", "SQL", "Power BI"]
    derecha = [
        "EXPERIENCIA LABORAL",
        "Data Analyst - Empresa Uno",
        "Marzo 2023 - Actualidad",
        "Reportes y tableros",
        "Analista Funcional - Empresa Dos",
        "Enero 2020 - Febrero 2023",
    ]
    # Se dibuja intercalado (como muchos editores): fila por fila, izquierda y derecha
    for i, (a, b) in enumerate(zip(izquierda, derecha)):
        pagina.insert_text((40, 120 + 20 * i), a, fontsize=10)
        pagina.insert_text((300, 120 + 20 * i), b, fontsize=10)
    texto = CandidatoService._extraer_texto_de_archivo(doc.tobytes(), ".pdf")
    assert paginas_ocr == []
    lineas = texto.splitlines()
    assert lineas.index("Power BI") < lineas.index("EXPERIENCIA LABORAL")  # columna izquierda completa primero
    assert lineas[lineas.index("Data Analyst - Empresa Uno") + 1] == "Marzo 2023 - Actualidad"


# --- 6. Fotografias con texto digital suficiente ------------------------------------------------------------------


def test_pdf_con_foto_y_texto_suficiente_no_usa_ocr(paginas_ocr):
    doc = fitz.open()
    pagina = _pagina_con_texto(doc)
    pagina.insert_image(fitz.Rect(400, 40, 540, 180), stream=_png_de_pagina_con_texto())  # foto de perfil
    CandidatoService._extraer_texto_de_archivo(doc.tobytes(), ".pdf")
    assert paginas_ocr == []


def test_pdf_con_imagen_de_fondo_y_texto_suficiente_no_usa_ocr(paginas_ocr):
    doc = fitz.open()
    pagina = doc.new_page()
    pagina.insert_image(pagina.rect, stream=_png_de_pagina_con_texto("fondo@example.com"))
    pagina.insert_text(
        (60, 500), "Damian Gomez - Analista de datos con experiencia en reportes, tableros y SQL.", fontsize=11
    )
    pagina.insert_text((60, 520), f"{EMAIL} | {TELEFONO} | Buenos Aires, Argentina", fontsize=11)
    CandidatoService._extraer_texto_de_archivo(doc.tobytes(), ".pdf")
    assert paginas_ocr == []


def test_pagina_vacia_o_portada_con_foto_chica_no_usa_ocr(paginas_ocr):
    doc = fitz.open()
    _pagina_con_texto(doc)
    doc.new_page()  # pagina en blanco
    portada = doc.new_page()
    portada.insert_image(fitz.Rect(200, 300, 330, 430), stream=_png_de_pagina_con_texto())
    CandidatoService._extraer_texto_de_archivo(doc.tobytes(), ".pdf")
    assert paginas_ocr == []


# --- 7. Capa de texto insuficiente o ilegible ---------------------------------------------------------------------


def test_capa_de_texto_minima_sobre_un_escaneo_usa_ocr_sin_duplicar_datos(motor):
    """El escaneo tiene una capa digital minima (pie de pagina con el email): se hace OCR y el email no se repite."""
    contenido = _pdf_texto_como_imagen(texto_digital=EMAIL)
    with fitz.open(stream=contenido, filetype="pdf") as doc:
        assert pdf_texto_cv.pagina_necesita_ocr(doc[0])
    texto = CandidatoService._extraer_texto_de_archivo(contenido, ".pdf")
    assert motor.llamadas == 1
    assert texto.count(EMAIL) == 1
    assert texto.count(TELEFONO) == 1
    assert texto.count("Damian Gomez") == 1


def test_capa_de_texto_ilegible_sobre_un_escaneo_usa_ocr(motor):
    contenido = _pdf_texto_como_imagen(
        texto_digital="@@@@ #### %%%% &&&& **** ++++ //// ==== ~~~~ ^^^^ |||| ;;;; :::: ????"
    )
    texto = CandidatoService._extraer_texto_de_archivo(contenido, ".pdf")
    assert motor.llamadas == 1
    assert CandidatoService.parsear_cv_texto(texto, "cv.pdf")["email"] == EMAIL


def test_texto_con_simbolos_sin_mapa_unicode_es_ilegible():
    assert pdf_texto_cv._proporcion_legible("  ��") < pdf_texto_cv.PROPORCION_MIN_LEGIBLE
    assert pdf_texto_cv._proporcion_legible("Analista Funcional - Córdoba, Argentina (2024)") == 1.0


def test_combinar_agrega_solo_las_lineas_digitales_que_el_ocr_no_tiene():
    digital = f"{EMAIL}\nPagina 1 de 2"
    ocr = f"Damian Gomez\n{TELEFONO.replace(' ', '')}\n{EMAIL.upper()}"
    assert pdf_texto_cv.combinar_texto_pagina(digital, ocr) == f"{ocr}\nPagina 1 de 2"
    assert pdf_texto_cv.combinar_texto_pagina(digital, "") == digital  # sin OCR se conserva lo digital


def test_ocr_une_las_cajas_de_un_mismo_renglon():
    cajas = [
        (60, 100, 120, 112, "Celular:"),
        (126, 100, 240, 112, "+54 9 351 805 3727"),
        (60, 130, 200, 142, "Correo:"),
    ]
    assert pdf_texto_cv.texto_desde_cajas_ocr(cajas) == "Celular: +54 9 351 805 3727\nCorreo:"


# --- 8. Errores del motor -----------------------------------------------------------------------------------------


def test_error_al_iniciar_rapidocr_conserva_el_texto_digital_de_las_otras_paginas(monkeypatch):
    import sys

    monkeypatch.setattr(cv_ocr, "_motor", None)
    monkeypatch.setattr(cv_ocr, "_motor_no_disponible", False)
    monkeypatch.setitem(sys.modules, "rapidocr", None)  # la importacion falla
    texto = CandidatoService._extraer_texto_de_archivo(_pdf_mixto(), ".pdf")
    assert cv_ocr._motor_no_disponible is True
    assert CandidatoService.parsear_cv_texto(texto, "cv.pdf")["email"] == EMAIL
    assert "Referencias laborales" in texto


def test_falla_del_motor_ocr_devuelve_vacio_sin_excepcion(monkeypatch):
    class MotorRoto:
        def __call__(self, *_a, **_k):
            raise RuntimeError("falla simulada del OCR")

    monkeypatch.setattr(cv_ocr, "_motor", MotorRoto())
    assert cv_ocr.extraer_texto_pdf_por_ocr(_pdf_texto_como_imagen()) == ""
    assert cv_ocr.reconocer_cajas_pdf(_pdf_texto_como_imagen(), [0]) == {}
    assert CandidatoService._extraer_texto_de_archivo(_pdf_texto_como_imagen(), ".pdf") == ""


def test_ocr_no_disponible_devuelve_vacio_sin_excepcion(monkeypatch):
    monkeypatch.setattr(cv_ocr, "_motor", None)
    monkeypatch.setattr(cv_ocr, "_motor_no_disponible", True)
    assert cv_ocr.extraer_texto_pdf_por_ocr(_pdf_texto_como_imagen()) == ""
    assert cv_ocr.reconocer_cajas_pdf(_pdf_texto_como_imagen(), [0]) == {}


def test_pdf_invalido_devuelve_vacio_sin_excepcion():
    assert cv_ocr.extraer_texto_pdf_por_ocr(b"esto no es un pdf") == ""
    assert CandidatoService._extraer_texto_de_archivo(b"esto no es un pdf", ".pdf") == ""


def test_se_limita_la_cantidad_de_paginas_leidas(monkeypatch):
    paginas = []

    class MotorContador:
        def __call__(self, imagen, **_k):
            paginas.append(imagen.shape)
            return _salida([([[0, 0], [10, 0], [10, 10], [0, 10]], "texto", 0.99)])

    doc = fitz.open()
    for _ in range(cv_ocr.MAX_PAGINAS_OCR + 4):
        doc.new_page()
    monkeypatch.setattr(cv_ocr, "_motor", MotorContador())
    assert cv_ocr.extraer_texto_pdf_por_ocr(doc.tobytes()) == "\n".join(["texto"] * cv_ocr.MAX_PAGINAS_OCR)
    assert len(paginas) == cv_ocr.MAX_PAGINAS_OCR
    assert max(max(s[0], s[1]) for s in paginas) <= cv_ocr.LADO_MAXIMO_PIXELES + 1


def test_pdf_escaneado_de_varias_paginas_respeta_el_limite(motor):
    doc = fitz.open()
    for _ in range(cv_ocr.MAX_PAGINAS_OCR + 2):
        _pagina_escaneada(doc)
    CandidatoService._extraer_texto_de_archivo(doc.tobytes(), ".pdf")
    assert motor.llamadas == cv_ocr.MAX_PAGINAS_OCR


def test_carga_individual_no_bloquea_el_event_loop(monkeypatch):
    """procesar_cv_bytes (extraccion y OCR) corre en un hilo: el event loop sigue atendiendo mientras tanto."""
    import asyncio
    import io
    import threading

    from fastapi import UploadFile

    hilos = []
    monkeypatch.setattr(
        CandidatoService, "procesar_cv_bytes", staticmethod(lambda **_k: hilos.append(threading.get_ident()) or "ok")
    )

    async def _probar():
        archivo = UploadFile(filename="cv.pdf", file=io.BytesIO(_pdf_con_texto()))
        return await CandidatoService.crear_desde_cv(None, None, archivo)

    assert asyncio.run(_probar()) == "ok"
    assert hilos and hilos[0] != threading.get_ident()


def test_modelo_ausente_deja_el_ocr_no_disponible_sin_descargar(monkeypatch, tmp_path):
    """Si falta un archivo de modelo no se intenta descargarlo: el OCR queda no disponible y el texto digital sigue."""
    monkeypatch.setattr(cv_ocr, "_motor", None)
    monkeypatch.setattr(cv_ocr, "_motor_no_disponible", False)
    monkeypatch.setattr(cv_ocr, "rutas_modelos", lambda: (tmp_path / "det.onnx", tmp_path / "rec.onnx"))
    assert cv_ocr._obtener_motor() is None
    assert cv_ocr._motor_no_disponible is True
    assert list(tmp_path.iterdir()) == []
    texto = CandidatoService._extraer_texto_de_archivo(_pdf_mixto(), ".pdf")
    assert CandidatoService.parsear_cv_texto(texto, "cv.pdf")["email"] == EMAIL


def test_ocr_descarta_iconos_de_contacto_leidos_como_letras():
    """El OCR lee el pin de ubicacion como "O" y el icono de LinkedIn como "in": no deben pegarse al dato."""
    cajas = [
        (58, 114, 82, 138, "U"),
        (81, 121, 178, 133, "+54 (3548) 15572263"),
        (66, 143, 81, 159, "O"),
        (84, 147, 176, 163, "Córdoba, Argentina"),
        (254, 148, 296, 164, "27 años"),
        (152, 175, 172, 192, "in"),
        (175, 178, 235, 191, "Luna del Rio"),
    ]
    lineas = pdf_texto_cv.texto_desde_cajas_ocr(cajas).splitlines()
    assert "Córdoba, Argentina" in lineas
    assert "+54 (3548) 15572263" in lineas
    assert not any(lin in ("U", "O", "in") or lin.startswith(("O ", "in ")) for lin in lineas)


def test_ocr_conserva_palabras_cortas_que_no_son_iconos():
    cajas = [
        (60, 100, 75, 112, "R"),
        (160, 100, 220, 112, "Python"),
        (60, 130, 200, 142, "Ingles B1"),
        (60, 160, 70, 172, "y"),
    ]
    texto = pdf_texto_cv.texto_desde_cajas_ocr(cajas)
    assert "R" in texto.split() and "y" in texto.split()
