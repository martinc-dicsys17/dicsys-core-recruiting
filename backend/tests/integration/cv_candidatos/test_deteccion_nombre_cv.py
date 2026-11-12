"""Detección de nombre y apellido en CVs: nunca se guarda una palabra suelta, un título o una sección como nombre.

Los datos son ficticios; reproducen la forma de los CVs reales que fallaban (título "My Resume", sigla "NH" en el archivo,
nombre con viñeta y etiqueta, nombre escrito como "Apellido Nombre").
"""

import pytest

from backend.modules.recruiting.services import CandidatoService


def _nombre(texto: str, archivo: str = "cv.pdf") -> tuple:
    datos = CandidatoService.parsear_cv_texto(texto, archivo)
    return datos["nombre"], datos["apellido"]


@pytest.mark.parametrize(
    "texto,archivo,esperado",
    [
        # Título de documento en el archivo + nombre en mayúsculas con inicial intermedia en el encabezado
        (
            "LUCIANO R BERTOLI\nSalta\nArgentina\n3870000000\nlbx77@example.com\nH A B I L I D A D E S\nJava & Angular",
            "My Resume.pdf",
            ("Luciano R", "Bertoli"),
        ),
        # Nombre completo con viñeta y etiqueta; el archivo empieza con una sigla y un puesto. CONVENCIÓN, no un CV real validado:
        # dato ficticio; "Lucía" se toma como segundo nombre por ser nombre de pila conocido y porque el archivo ("Ximena Paredes") la omite
        (
            "CV2025\n1\nSoy Ximena, analista de datos.\nhttps://github.com/xparedes\n01 - DATOS PERSONALES\n"
            " Nombre completo: Ximena Lucía Paredes Ortiz\n Edad: 30\nxparedes@example.com",
            "XP Data analyst-S - Ximena Paredes.pdf",
            ("Ximena Lucía", "Paredes Ortiz"),
        ),
        # Encabezado escrito "Apellido Nombre"
        (
            "Quiroga Esteban​\nAnalista de Datos | Ingeniero Industrial\nNeuquén, Argentina\nequiroga@example.com",
            "Quiroga_Esteban_Analista_de_Datos.pdf",
            ("Esteban", "Quiroga"),
        ),
        # Un email que empieza por el apellido no invierte un nombre bien escrito
        ("Esteban Quiroga\nAnalista Funcional\nquirogaesteban@example.com", "cv.pdf", ("Esteban", "Quiroga")),
        # Nombres poco comunes: se respeta el orden del CV
        ("Nexxo Villarreal\nDesarrollador Backend\nnexxo@example.com", "cv.pdf", ("Nexxo", "Villarreal")),
        # Nombres y apellidos compuestos, partículas, apóstrofes y guiones. "Juan Pablo" / "Di Marco" es CONVENCIÓN, no un CV real
        # validado: dato ficticio; "Pablo" se toma como segundo nombre solo porque "Juan" y "Pablo" son nombres de pila conocidos
        (
            "María de los Ángeles Fernández\nContadora\nmafernandez@example.com",
            "cv.pdf",
            ("María", "De Los Ángeles Fernández"),
        ),
        ("Juan Pablo Di Marco\nTester QA\njpdimarco@example.com", "cv.pdf", ("Juan Pablo", "Di Marco")),
        ("Lucía Pérez-Gil\nDiseñadora UX\nlperezgil@example.com", "cv.pdf", ("Lucía", "Pérez-Gil")),
        ("Ana O'Neil\nProduct Owner\naoneil@example.com", "cv.pdf", ("Ana", "O'Neil")),
        # Secciones y títulos antes del nombre: se descartan y se sigue buscando
        (
            "Curriculum Vitae\nExperiencia Laboral\nSobre mí\nRocío Benítez\nrbenitez@example.com",
            "cv.pdf",
            ("Rocío", "Benítez"),
        ),
    ],
    ids=[
        "inicial_y_titulo_my_resume",
        "etiqueta_con_vineta",
        "apellido_nombre",
        "email_apellido_primero",
        "nombre_poco_comun",
        "particulas",
        "nombre_compuesto",
        "apellido_con_guion",
        "apostrofe",
        "secciones_previas",
    ],
)
def test_detecta_nombre_y_apellido_plausibles(texto, archivo, esperado):
    assert _nombre(texto, archivo) == esperado


@pytest.mark.parametrize(
    "texto,archivo",
    [
        ("Experiencia\nDesarrollador Java\nSpring Boot", "My Resume.pdf"),
        ("Resume\nIgnacio\nDesarrollador Java", "CV.pdf"),
        ("", "NH Data analyst.pdf"),
        ("Habilidades\nPython SQL", "Curriculum Vitae 2025.pdf"),
    ],
    ids=["titulo_documento", "palabra_suelta_en_texto", "sigla_y_puesto", "solo_secciones"],
)
def test_sin_nombre_confiable_usa_el_valor_por_defecto(texto, archivo):
    assert _nombre(texto, archivo) == ("Candidato", "Sin Nombre")


def test_nombre_desde_archivo_en_orden_apellido_nombre():
    assert _nombre("Trayectoria profesional\nAnalista funcional\nanavarrete@example.com", "Navarrete Agustin.pdf") == (
        "Agustin",
        "Navarrete",
    )


@pytest.mark.parametrize(
    "archivo,esperado",
    [
        ("My Resume.pdf", None),
        ("MirkoCV.pdf", None),
        ("NH Data analyst-S - Ximena Paredes.pdf", ("Ximena", "Paredes")),
        ("Paredes_Ximena_CV - Ximena.pdf", ("Ximena", "Paredes")),
        ("Mauro-E-Ibarra-CV-English.pdf", ("Mauro", "Ibarra")),
    ],
    ids=["titulo", "una_sola_palabra", "sigla_y_parte_con_nombre", "apellido_nombre", "inicial"],
)
def test_nombre_desde_archivo_exige_nombre_y_apellido(archivo, esperado):
    assert CandidatoService._nombre_desde_archivo(archivo) == esperado


@pytest.mark.parametrize(
    "segmento,esperado",
    [
        ("Carlos I Madrigal", ["Carlos", "I", "Madrigal"]),
        ("Juan P. Pérez", ["Juan", "P.", "Pérez"]),
        ("My", None),
        ("Resume", None),
        ("I Madrigal", None),
        ("Experiencia Laboral", None),
    ],
)
def test_tokens_de_nombre_admite_iniciales_y_rechaza_palabras_sueltas(segmento, esperado):
    assert CandidatoService._tokens_de_nombre(segmento) == esperado


@pytest.mark.parametrize(
    "palabras,esperado",
    [
        (["Moreira", "Rodrigo"], ["Rodrigo", "Moreira"]),
        (["Gómez", "Belis", "Sofía", "Belén"], ["Sofía", "Belén", "Gómez", "Belis"]),
        (["Rodrigo", "Moreira"], ["Rodrigo", "Moreira"]),
        (["Nexxo", "Carolina", "Herrera"], ["Nexxo", "Carolina", "Herrera"]),
        (["Martin", "Lucas"], ["Martin", "Lucas"]),
    ],
)
def test_ordenar_nombre_apellido_solo_rota_con_evidencia(palabras, esperado):
    assert CandidatoService._ordenar_nombre_apellido(palabras) == esperado


def test_nombre_y_apellido_en_bloques_separados_del_encabezado():
    # El PDF entrega el apellido al inicio y el nombre de pila varias líneas después, cada uno solo en su línea
    texto = (
        "Gonzalez\nAspiro a formar una sólida \nexperiencia laboral.\nObjetivo Profesional\nContacto\n"
        "     3510000000\n     Córdoba, Argentina\nNahuel\nTécnico en Sistemas de Información\nnahjuivan@example.com\n"
        "Habilidades Técnicas\nPython, SQL"
    )
    assert _nombre(texto, "cv.pdf") == ("Nahuel", "Gonzalez")


@pytest.mark.parametrize(
    "texto",
    [
        "Gonzalez\nObjetivo Profesional\nTécnico en Sistemas\nPython\nSQL",  # sin nombre de pila
        "Resumen\nExperiencia\nNahuel\nPython\nSQL",  # ninguna palabra suelta encabeza el documento
    ],
)
def test_palabras_sueltas_sin_nombre_y_apellido_claros_no_forman_nombre(texto):
    assert _nombre(texto, "cv.pdf") == ("Candidato", "Sin Nombre")


def test_nombre_de_pila_que_tambien_es_idioma_no_se_descarta():
    # "German" figura como idioma en el vocabulario; al inicio de "German Lara" es el nombre de pila
    texto = (
        "Responsable Seguridad SAP\nAnalista Seguridad SAP\nCorreo  : german-lara@example.com\n"
        "Linkedin : German Lara | LinkedIn\nIdiomas\nINGLES\nGERMAN LARA\nTarjeta Shopping"
    )
    assert _nombre(texto, "cv.pdf") == ("German", "Lara")
    assert _nombre("Experiencia\nAnalista", "German Lara - Copy.pdf") == ("German", "Lara")


@pytest.mark.parametrize(
    "texto",
    [
        "Idiomas\nGerman\nEnglish\nPython",  # el idioma solo
        "Idiomas\nGerman Spanish\nEnglish",  # idiomas en la misma línea
    ],
)
def test_idiomas_no_se_confunden_con_un_nombre(texto):
    assert _nombre(texto, "cv.pdf") == ("Candidato", "Sin Nombre")


@pytest.mark.parametrize(
    "texto,esperado",
    [
        # Campos "Nombre:" y "Apellido:" en líneas separadas, dentro de un bloque de contacto
        (
            "Instituto CEBA.\nInicio: Agosto 2013.\nCONTACTO\nNombre: Facundo\nApellido: Rosende\nDNI: 36.510.767\n"
            "Correo: frosende@example.com",
            ("Facundo", "Rosende"),
        ),
        # Con viñetas, en mayúsculas y con varios nombres/apellidos
        (
            "DATOS PERSONALES\n• NOMBRES: MARÍA LAURA\n• APELLIDOS: FUENTE MARTÍNEZ\nfuente@example.com",
            ("María Laura", "Fuente Martínez"),
        ),
        # Etiquetas en inglés y en distinto orden
        ("Contact\nLast name: Benítez\nFirst name: Lucía\nlbenitez@example.com", ("Lucía", "Benítez")),
    ],
    ids=["nombre_y_apellido_separados", "con_viñetas_y_mayusculas", "etiquetas_en_ingles"],
)
def test_campos_nombre_y_apellido_en_lineas_separadas(texto, esperado):
    assert _nombre(texto) == esperado


@pytest.mark.parametrize(
    "texto",
    [
        "CONTACTO\nNombre: Facundo\nDNI: 36.510.767\nfacu@example.com",  # falta el apellido
        "CONTACTO\nApellido: Rosende\nDNI: 36.510.767\nrosende@example.com",  # falta el nombre
        "CONTACTO\nNombre: Python\nApellido: SQL\nx@example.com",  # los valores no son un nombre
        "Skills\nNombre: Responsable\nApellido: Analista\nx@example.com",
    ],
    ids=["sin_apellido", "sin_nombre", "valores_tecnicos", "valores_de_puesto"],
)
def test_campos_etiquetados_incompletos_o_no_nombres_no_se_asignan(texto):
    assert _nombre(texto) == ("Candidato", "Sin Nombre")
