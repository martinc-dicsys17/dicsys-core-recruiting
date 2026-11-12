"""Detección del nombre cuando el orden del texto del PDF no coincide con el orden de lectura visual.

Los PDF se generan en la prueba con PyMuPDF y datos ficticios, imitando el diseño del CV real que fallaba: columna lateral
(perfil, habilidades) dibujada antes que el encabezado, nombre en tamaño grande (duplicado para simular negrita), cargo
debajo y email que no contiene el nombre. El texto lineal deja el nombre después de decenas de líneas de la columna lateral.
"""

import pytest

fitz = pytest.importorskip("fitz")

from backend.modules.recruiting.services import CandidatoService  # noqa: E402

LATERAL = [
    "PERFIL PERSONAL",
    "Analista con más de 9 años de experiencia",
    "liderando iniciativas de automatización,",
    "desarrollo de software y análisis de datos.",
    "Experiencia en: bases de datos y consultas avanzadas.",
    "Desarrollo de dashboards ejecutivos en Power BI.",
    "Gestión de seguridad informática e infraestructura.",
    "Pensamiento analítico y enfoque en datos.",
    "Comunicación clara con equipos técnicos y gerenciales.",
    "Capacidad de liderazgo técnico en proyectos internos.",
    "Toma de decisiones basada en información.",
    "Organización y gestión eficiente del tiempo.",
    "Proactividad en identificación de mejoras.",
    "Enfoque en automatización y eficiencia operativa.",
    "HABILIDADES",
    "EXPERIENCIA LABORAL",
]


def _pdf(encabezado, lateral=LATERAL, duplicar=True, tamano=35, x=204, extra=()):
    """PDF de una página: primero la columna lateral y el cuerpo, al final el encabezado (orden de dibujo != orden visual)."""
    doc = fitz.open()
    pagina = doc.new_page()
    y = 217
    for linea in lateral:
        pagina.insert_text((20, y), linea, fontsize=9)
        y += 14
    pagina.insert_text((245, 450), "Diseño e implementación de soluciones para automatización de procesos.", fontsize=9)
    for texto, fuente, pos in extra:
        pagina.insert_text(pos, texto, fontsize=fuente)
    for linea, fuente, posicion in encabezado:
        for _ in range(2 if duplicar and fuente == tamano else 1):
            pagina.insert_text(posicion, linea, fontsize=fuente)
    return doc.tobytes()


def _parsear(contenido, archivo="cv.pdf", email="candidata@example.com"):
    texto = CandidatoService._extraer_texto_de_archivo(contenido, ".pdf")
    if email:
        texto += f"\n{email}"
    encabezado = CandidatoService._extraer_encabezado_visual_pdf(contenido)
    datos = CandidatoService.parsear_cv_texto(texto, archivo, encabezado_visual=encabezado)
    return datos["nombre"], datos["apellido"], encabezado


def test_el_orden_de_lectura_ubica_el_nombre_antes_de_la_columna_lateral():
    """Causa original: el texto lineal (orden de dibujo) deja el nombre detrás de la columna lateral. La extracción en
    orden de lectura (por coordenadas) lo ubica primero, aun sin el encabezado visual."""
    contenido = _pdf(
        [("JORGE RODRIGUEZ", 35, (204, 140)), ("ANALISTA DE SISTEMAS | DATA & DESARROLLO", 11, (204, 165))]
    )
    with fitz.open(stream=contenido, filetype="pdf") as doc:
        lineal = [lin for lin in doc[0].get_text().splitlines() if lin.strip()]
    assert lineal.index("JORGE RODRIGUEZ") > 15
    texto = CandidatoService._extraer_texto_de_archivo(contenido, ".pdf")
    lineas = [lin for lin in texto.splitlines() if lin.strip()]
    assert lineas[:3] == ["JORGE RODRIGUEZ", "JORGE RODRIGUEZ", "ANALISTA DE SISTEMAS | DATA & DESARROLLO"]
    sin_encabezado = CandidatoService.parsear_cv_texto(texto + "\njrodri0000@example.com", "CV Jorge R.pdf")
    assert (sin_encabezado["nombre"], sin_encabezado["apellido"]) == ("Jorge", "Rodriguez")


def test_regresion_cv_jorge_rodriguez_encabezado_en_mayusculas_junto_a_columna_lateral():
    contenido = _pdf(
        [("JORGE RODRIGUEZ", 35, (204, 140)), ("ANALISTA DE SISTEMAS | DATA & DESARROLLO", 11, (204, 165))]
    )
    nombre, apellido, encabezado = _parsear(contenido, "CV Jorge R.pdf", "jrodri0000@example.com")
    assert (nombre, apellido) == ("Jorge", "Rodriguez")
    assert encabezado == "JORGE RODRIGUEZ"  # el cargo (tamaño menor) no forma parte del encabezado destacado


def test_nombre_con_letras_espaciadas():
    contenido = _pdf([("M A R C O S   M A R A N G O N I", 24, (180, 140))], duplicar=False, tamano=24)
    nombre, apellido, encabezado = _parsear(contenido, "cv.pdf", "marcos.m@example.com")
    assert (nombre, apellido) == ("Marcos", "Marangoni")
    assert encabezado == "MARCOS MARANGONI"


def test_nombre_en_dos_lineas_de_un_encabezado_grafico():
    contenido = _pdf(
        [("TAMARA", 30, (204, 120)), ("SAMANA", 30, (204, 155)), ("Data Analyst", 12, (204, 180))],
        duplicar=False,
        tamano=30,
    )
    nombre, apellido, _ = _parsear(contenido, "cv.pdf", "tsamana@example.com")
    assert (nombre, apellido) == ("Tamara", "Samana")


def test_dos_columnas_con_el_nombre_en_la_columna_derecha():
    contenido = _pdf(
        [("Lucía Benítez", 26, (300, 90)), ("Contadora Pública", 12, (300, 115))], duplicar=False, tamano=26, x=300
    )
    nombre, apellido, _ = _parsear(contenido, "cv.pdf", "contacto@example.com")
    assert (nombre, apellido) == ("Lucía", "Benítez")


@pytest.mark.parametrize(
    "titulos",
    [
        [("CURRICULUM VITAE", 30, (204, 120))],
        [("ANALISTA DE SISTEMAS", 30, (204, 120)), ("DATA & DESARROLLO", 30, (204, 155))],
        [("Experiencia Laboral", 30, (204, 120))],
        [("PYTHON SQL POWER BI", 30, (204, 120))],
        [("Tecnologías y Herramientas", 30, (204, 120))],
    ],
    ids=["titulo_documento", "cargo", "seccion", "habilidades", "seccion_larga"],
)
def test_un_titulo_destacado_que_no_es_un_nombre_no_se_asigna(titulos):
    contenido = _pdf(titulos, duplicar=False, tamano=30)
    nombre, apellido, _ = _parsear(contenido, "My Resume.pdf", "contacto@example.com")
    assert (nombre, apellido) == ("Candidato", "Sin Nombre")


def test_sin_texto_destacado_no_hay_encabezado_y_no_falla_con_pdf_invalido():
    assert CandidatoService._extraer_encabezado_visual_pdf(b"no es un pdf") == ""
    assert CandidatoService._extraer_encabezado_visual_pdf(b"") == ""


def test_el_encabezado_visual_no_pisa_un_nombre_ya_detectado_en_el_texto():
    texto = "Esteban Quiroga\nAnalista Funcional\nquirogaesteban@example.com"
    datos = CandidatoService.parsear_cv_texto(texto, "cv.pdf", encabezado_visual="OTRA PERSONA")
    assert (datos["nombre"], datos["apellido"]) == ("Esteban", "Quiroga")


def test_regresion_cv_marcos_marangoni_dos_columnas_con_nombre_en_letras_espaciadas():
    """PDF de una página, dos columnas: el nombre llega con una letra por palabra, en la línea 86 del texto lineal, y
    el archivo ("CV-MARCOSAMARANGONI - 2026a.pdf") no separa nombre y apellido, así que no hay otra fuente del nombre."""
    secciones = [
        f"{titulo} {n}"
        for titulo in ("Formación académica", "Herramientas y sistemas", "Cursos y participaciones")
        for n in range(1, 8)
    ]
    contenido = _pdf(
        [("M A R C O S   M A R A N G O N I", 24, (180, 140)), ("Analista de Sistemas", 12, (180, 165))],
        lateral=LATERAL + secciones,
        duplicar=False,
        tamano=24,
    )
    with fitz.open(stream=contenido, filetype="pdf") as doc:
        lineal = [lin for lin in doc[0].get_text().splitlines() if lin.strip()]
    assert (
        next(i for i, lin in enumerate(lineal) if lin.startswith("M A R C O S")) > 15
    )  # el texto lineal no lo deja entre las primeras líneas
    texto = CandidatoService._extraer_texto_de_archivo(contenido, ".pdf")
    assert texto.startswith("M A R C O S")  # el orden de lectura sí
    assert CandidatoService._nombre_desde_archivo("CV-MARCOSAMARANGONI - 2026a.pdf") is None
    nombre, apellido, encabezado = _parsear(contenido, "CV-MARCOSAMARANGONI - 2026a.pdf", "mm@example.com")
    assert (nombre, apellido) == ("Marcos", "Marangoni")
    assert encabezado == "MARCOS MARANGONI"


def test_nombre_y_apellido_en_lineas_y_tamanos_distintos_del_encabezado():
    """ "Soledad" en letra grande (parte superior) y "ARGÜELLO" más chico debajo, con el cargo en un cuerpo menor y el
    texto lineal lleno de la columna lateral: el apellido no puede quedar fuera por ser de menor tamaño que el nombre."""
    contenido = _pdf(
        [("Soledad", 41, (277, 110)), ("ARGÜELLO", 24, (390, 140)), ("ANALISTA DE SISTEMAS", 13, (241, 165))],
        duplicar=False,
        tamano=41,
    )
    nombre, apellido, encabezado = _parsear(contenido, "cv_AnalistaFuncional.pdf", "sol.arg.971@example.com")
    assert (nombre, apellido) == ("Soledad", "Argüello")
    assert encabezado == "Soledad\nARGÜELLO"


def test_una_sola_palabra_destacada_no_se_toma_como_nombre():
    contenido = _pdf([("Soledad", 41, (277, 110)), ("ANALISTA DE SISTEMAS", 13, (241, 165))], duplicar=False, tamano=41)
    nombre, apellido, _ = _parsear(contenido, "cv_AnalistaFuncional.pdf", "sol.arg.971@example.com")
    assert (nombre, apellido) == ("Candidato", "Sin Nombre")


def test_dos_lineas_destacadas_que_no_son_un_nombre_no_se_unen():
    contenido = _pdf([("Python", 36, (204, 110)), ("Developer", 30, (204, 150))], duplicar=False, tamano=36)
    nombre, apellido, _ = _parsear(contenido, "My Resume.pdf", "contacto@example.com")
    assert (nombre, apellido) == ("Candidato", "Sin Nombre")
