"""Orden de lectura del texto de un PDF (pdf_texto_cv.texto_pagina_ordenado) con PDFs sinteticos generados en memoria.

Cada PDF se dibuja en un orden distinto del de lectura, como hacen los editores de CVs disenados; se comprueba que el
texto extraido respeta columnas, margenes de fechas y encabezados de ancho completo, y que sin estructura el resultado
es el mismo que get_text().
"""

import fitz

from backend.modules.recruiting import pdf_texto_cv
from backend.modules.recruiting.headline_cv import analizar_headline_cv


def _pagina(elementos):
    """elementos: [(x, y, texto, tamano)] en el orden de dibujo."""
    doc = fitz.open()
    pagina = doc.new_page()
    for x, y, texto, tamano in elementos:
        pagina.insert_text((x, y), texto, fontsize=tamano)
    return doc


def _lineas(doc):
    return [lin for lin in pdf_texto_cv.texto_pagina_ordenado(doc[0]).splitlines() if lin.strip()]


def test_documento_simple_queda_igual_que_get_text():
    doc = _pagina(
        [
            (60, 80, "Ana Lopez", 20),
            (60, 110, "Analista Funcional", 12),
            (60, 140, "ana@example.com", 10),
            (60, 170, "Experiencia en relevamiento de requerimientos.", 10),
        ]
    )
    assert pdf_texto_cv.texto_pagina_ordenado(doc[0]).split() == doc[0].get_text().split()


def test_dos_columnas_no_se_intercalan_y_el_encabezado_de_ancho_completo_va_primero():
    # Dibujado: cuerpo derecho, columna izquierda y por ultimo el encabezado
    doc = _pagina(
        [
            (300, 160, "EXPERIENCIA LABORAL", 11),
            (300, 180, "Analytics Engineer - Empresa Uno", 10),
            (300, 195, "Junio 2025 - Actualidad", 10),
            (300, 210, "Modelado de datos y tableros.", 10),
            (40, 160, "CONTACTO", 11),
            (40, 180, "ana@example.com", 10),
            (40, 195, "Cordoba, Argentina", 10),
            (40, 210, "HABILIDADES", 11),
            (40, 225, "SQL y Python", 10),
            (40, 60, "ANA LOPEZ - ANALYTICS ENGINEER | DATA PRODUCT SPECIALIST", 16),
        ]
    )
    lineas = _lineas(doc)
    assert lineas[0].startswith("ANA LOPEZ")
    assert lineas.index("SQL y Python") < lineas.index("EXPERIENCIA LABORAL")
    assert lineas[lineas.index("Analytics Engineer - Empresa Uno") + 1] == "Junio 2025 - Actualidad"


def test_margen_izquierdo_de_fechas_queda_antes_de_su_cargo():
    doc = _pagina(
        [
            (130, 100, "IT Recruiter Sr. - Freelance", 11),
            (130, 115, "Busqueda de perfiles tecnologicos.", 10),
            (130, 200, "IT Recruiter Jr. - Consultora", 11),
            (130, 215, "Entrevistas y seguimiento.", 10),
            (30, 100, "Mar 2026 -", 9),
            (30, 112, "Presente", 9),
            (30, 200, "Dic 2021 -", 9),
            (30, 212, "Mar 2026", 9),
        ]
    )
    assert _lineas(doc) == [
        "Mar 2026 -",
        "Presente",
        "IT Recruiter Sr. - Freelance",
        "Busqueda de perfiles tecnologicos.",
        "Dic 2021 -",
        "Mar 2026",
        "IT Recruiter Jr. - Consultora",
        "Entrevistas y seguimiento.",
    ]


def test_margen_derecho_de_fechas_queda_despues_de_su_renglon():
    doc = _pagina(
        [
            (40, 100, "Acid Labs, Santiago, Chile", 10),
            (40, 115, "Analytics Engineer", 10),
            (40, 200, "Datalytics, Buenos Aires", 10),
            (40, 215, "Business Analytics Translator", 10),
            (460, 100, "Jun 2025 - Actualidad", 10),
            (460, 200, "May 2024 - Jun 2025", 10),
        ]
    )
    assert _lineas(doc) == [
        "Acid Labs, Santiago, Chile",
        "Jun 2025 - Actualidad",
        "Analytics Engineer",
        "Datalytics, Buenos Aires",
        "May 2024 - Jun 2025",
        "Business Analytics Translator",
    ]


def test_cv_con_el_puesto_actual_dibujado_al_final_conserva_su_prioridad():
    """El puesto actual y las fechas se dibujan al final del documento; el orden de lectura los vuelve a su lugar y cada
    cargo queda con su periodo. La mencion de QA dentro de una tarea no es un cargo."""
    doc = _pagina(
        [
            (40, 40, "FRANCISCO PRUEBA", 18),
            (40, 60, "francisco@example.com", 10),
            (40, 90, "EXPERIENCIA PROFESIONAL", 12),
            (40, 170, "Datalytics, Buenos Aires, Argentina", 10),
            (40, 185, "Business Analytics Translator", 10),
            (40, 200, "Manejo de backlog y validacion de tareas mediante QA.", 10),
            (40, 230, "Lubee, Buenos Aires, Argentina", 10),
            (40, 245, "Project Manager | Analista Funcional", 10),
            (40, 260, "Coordinacion de proyectos.", 10),
            (460, 170, "May. 2024 - Jun, 2025", 10),
            (460, 260, "Ago. 2023 - May. 2024", 10),
            (40, 110, "Acid Labs, Santiago, Chile", 10),
            (40, 125, "Analytics Engineer", 10),
            (40, 140, "Actuando como puente entre negocio y datos.", 10),
            (460, 110, "Jun, 2025 - Actualidad", 10),
        ]
    )
    lineal = doc[0].get_text()
    assert lineal.index("Analytics Engineer") > lineal.index("Project Manager")  # orden de dibujo
    texto = pdf_texto_cv.texto_pagina_ordenado(doc[0])
    lineas = [lin for lin in texto.splitlines() if lin.strip()]
    assert lineas[3:6] == ["Acid Labs, Santiago, Chile", "Jun, 2025 - Actualidad", "Analytics Engineer"]
    assert analizar_headline_cv(texto) == ("Analytics Engineer", "experiencia_fechada")


def test_texto_girado_usa_la_extraccion_lineal():
    doc = fitz.open()
    pagina = doc.new_page()
    pagina.insert_text((60, 100), "Linea uno", fontsize=10)
    pagina.insert_text((60, 120), "Linea dos", fontsize=10)
    pagina.insert_text((300, 400), "Texto vertical", fontsize=10, rotate=90)
    assert pdf_texto_cv.texto_pagina_ordenado(pagina) == pagina.get_text()


def test_el_texto_ordenado_conserva_todos_los_caracteres():
    doc = _pagina(
        [
            (300, 100, "Columna derecha uno", 10),
            (40, 100, "Columna izquierda uno", 10),
            (300, 115, "Columna derecha dos", 10),
            (40, 115, "Columna izquierda dos", 10),
        ]
    )
    ordenado = pdf_texto_cv.texto_pagina_ordenado(doc[0])
    assert sorted(ordenado.split()) == sorted(doc[0].get_text().split())
