"""Calidad del OCR real (RapidOCR + PP-OCRv6) sobre texto en espanol escaneado.

Las paginas se generan en memoria con datos ficticios, se rasterizan a ~144 ppp y se incrustan como imagen (sin capa
de texto), igual que un CV escaneado. Se exige que cada linea vuelva exacta: tildes, ñ y dieresis sin transformar,
espacios entre palabras conservados, sin confundir letras con numeros y telefonos y emails sin alteraciones.
Se omiten si RapidOCR o sus modelos no estan instalados (en la imagen Docker del backend lo estan).
"""

import re

import fitz
import pytest

from backend.core import cv_ocr
from backend.modules.recruiting.services import CandidatoService

pytest.importorskip("rapidocr")
if not all(r.is_file() for r in cv_ocr.rutas_modelos()):
    pytest.skip("modelos OCR no instalados", allow_module_level=True)

PALABRAS = [
    "Córdoba",
    "Buenos Aires",
    "González",
    "Muñoz",
    "Álvarez",
    "Martín",
    "Información",
    "Experiencia laboral",
    "Educación",
    "Desarrollador",
    "Ingeniería",
    "Administración",
]
NOMBRES = ["María José Muñoz Álvarez", "Iñaki Núñez Peña", "Ángela Íñiguez Güemes", "Martín Ávila Úbeda"]
LOCALIDADES = ["Villa Cañás, Córdoba", "Tristán Suárez, Buenos Aires", "Bahía Blanca", "Río Cuarto", "San Martín"]
PUESTOS = ["Desarrolladora Backend Senior", "Analista Funcional", "Analytics Engineer", "Soporte IT / Help Desk"]
INSTITUCIONES = [
    "Grupo Arcor S.A. - Ingeniería de Datos",
    "Universidad Nacional de Córdoba (UNC)",
    "Licenciatura en Administración de Empresas",
]
FECHAS = ["Junio 2022 - Actualidad", "Mar. 2019 - Dic. 2021", "03/2017 - 12/2018"]
DIRECCIONES = ["Av. Colón 1250, 5° piso, depto. B", "Güemes 455, San Martín"]
EMAILS = ["maria.munoz_alvarez@gmail.com", "jose.gonzalez-89@hotmail.com.ar", "otalora.lucas@gmail.com"]
TELEFONOS = [
    "+54 9 351 805-3727",
    "(011) 15-4321-9876",
    "+54 11 2639 0067",
    "(+54) 221 455 5165",
    "+54 (3548) 15572263",
    "11-3088-0023",
]
ESPECIALES = ["ÑANDÚ S.R.L. - ÍNDICE DE GESTIÓN", "Pequeñas empresas: logística, señalización y diseño"]

LINEAS = (
    PALABRAS + NOMBRES + LOCALIDADES + PUESTOS + INSTITUCIONES + FECHAS + DIRECCIONES + EMAILS + TELEFONOS + ESPECIALES
)


@pytest.fixture(scope="module")
def motor_real():
    """Motor real de cv_ocr (otras pruebas lo sustituyen con monkeypatch y lo restauran)."""
    previo = (cv_ocr._motor, cv_ocr._motor_no_disponible)
    cv_ocr._motor, cv_ocr._motor_no_disponible = None, False
    assert cv_ocr._obtener_motor() is not None
    yield
    cv_ocr._motor, cv_ocr._motor_no_disponible = previo


def _escaneado(lineas, tamanos=(10, 12)):
    """PDF escaneado con todas las lineas en cada tamano de letra (repartidas en las paginas necesarias).
    Devuelve (bytes, {tamano: [indices de pagina]})."""
    doc = fitz.open()
    paginas_por_tamano = {}
    for tamano in tamanos:
        interlinea = tamano * 1.6
        por_pagina = int((842 - 100) / interlinea)
        for inicio in range(0, len(lineas), por_pagina):
            origen = fitz.open()
            pagina = origen.new_page()
            for n, linea in enumerate(lineas[inicio : inicio + por_pagina]):
                pagina.insert_text((50, 50 + n * interlinea), linea, fontsize=tamano, fontname="helv")
            png = pagina.get_pixmap(matrix=fitz.Matrix(2, 2)).tobytes("png")
            nueva = doc.new_page(width=pagina.rect.width, height=pagina.rect.height)
            nueva.insert_image(nueva.rect, stream=png)
            paginas_por_tamano.setdefault(tamano, []).append(len(doc) - 1)
    return doc.tobytes(), paginas_por_tamano


@pytest.fixture(scope="module")
def paginas(motor_real):
    """Texto reconocido por tamano de letra (todas las lineas de prueba en cada uno)."""
    from backend.modules.recruiting import pdf_texto_cv

    contenido, por_tamano = _escaneado(LINEAS)
    indices = [i for lista in por_tamano.values() for i in lista]
    assert len(indices) <= cv_ocr.MAX_PAGINAS_OCR
    cajas = cv_ocr.reconocer_cajas_pdf(contenido, indices)
    return ["\n".join(pdf_texto_cv.texto_desde_cajas_ocr(cajas[i]) for i in lista) for lista in por_tamano.values()]


def _lineas(texto):
    return {re.sub(r"\s+", " ", lin).strip() for lin in texto.splitlines()}


@pytest.mark.parametrize(
    "grupo, esperadas",
    [
        ("palabras", PALABRAS),
        ("nombres", NOMBRES),
        ("localidades", LOCALIDADES),
        ("puestos", PUESTOS),
        ("instituciones", INSTITUCIONES),
        ("fechas", FECHAS),
        ("direcciones", DIRECCIONES),
        ("especiales", ESPECIALES),
    ],
)
def test_texto_en_espanol_se_reconoce_exacto(paginas, grupo, esperadas):
    for texto in paginas:
        faltan = [e for e in esperadas if e not in _lineas(texto)]
        assert not faltan, f"{grupo}: no reconocidas exactas {faltan}"


def test_emails_y_telefonos_sin_alteraciones(paginas):
    for texto in paginas:
        lineas = _lineas(texto)
        assert [e for e in EMAILS if e not in lineas] == []
        assert [t for t in TELEFONOS if t not in lineas] == []


def test_no_une_palabras_ni_confunde_letras_con_numeros(paginas):
    for texto in paginas:
        compacto = texto.replace(" ", "")
        for linea in LINEAS:
            if " " in linea:
                # La linea esta, con sus espacios: no aparece solo su version sin espacios
                assert linea in _lineas(texto) or linea.replace(" ", "") not in compacto
        assert not re.search(r"[A-Za-zÁÉÍÓÚáéíóúñÑ][0-9][a-záéíóú]", texto), "digito dentro de una palabra"


def test_cv_escaneado_completo_pasa_por_el_parser(motor_real):
    lineas = [
        "Iñaki Núñez Peña",
        "Analista Funcional",
        "Ubicación: Villa Cañás, Córdoba, Argentina",
        "Teléfono: +54 9 351 805-3727",
        "Email: inaki.nunez@example.com",
        "Experiencia laboral",
        "Analista Funcional - Grupo Arcor S.A. | Junio 2022 - Actualidad",
        "Relevamiento de requerimientos y documentación funcional.",
        "Educación",
        "Universidad Nacional de Córdoba (UNC) - Licenciatura en Administración",
    ]
    texto = CandidatoService._extraer_texto_de_archivo(_escaneado(lineas, tamanos=(11,))[0], ".pdf")
    datos = CandidatoService.parsear_cv_texto(texto, "cv escaneado.pdf")
    assert (datos["nombre"], datos["apellido"]) == ("Iñaki", "Núñez Peña")
    assert datos["email"] == "inaki.nunez@example.com"
    assert datos["telefono"] == "+54 9 351 805-3727"
    assert datos["headline"] == "Analista Funcional"
    assert "Villa Cañás, Córdoba, Argentina" in texto
