"""Detección del apellido en CVs: nombres compuestos, apellidos compuestos, títulos y palabras que no son un nombre.

Los datos son ficticios; reproducen los errores de apellido hallados al auditar CVs reales: el segundo nombre quedaba
como parte del apellido ("Ariel" / "Cristian Vizne"), los títulos ("Ing.", "Lic.") se guardaban como nombre y frases o
instituciones se tomaban como encabezado. Un segundo nombre solo se mueve al nombre con evidencia: otra fuente del propio
CV que omita esa palabra, un apellido explícito en el archivo ("Apellido, Nombre") o dos nombres de pila conocidos seguidos.
"""

import pytest

from backend.modules.recruiting.services import CandidatoService


def _nombre(texto: str, archivo: str = "cv.pdf") -> tuple:
    datos = CandidatoService.parsear_cv_texto(texto, archivo)
    return datos["nombre"], datos["apellido"]


@pytest.mark.parametrize(
    "texto,esperado",
    [
        # Dos nombres de pila conocidos seguidos: el segundo es parte del nombre
        ("Ariel Cristian Vizne\nQA Tester\navizne@example.com", ("Ariel Cristian", "Vizne")),
        ("María Belén Guzmán\nAnalista\nmbguzman@example.com", ("María Belén", "Guzmán")),
        ("Jonathan David Leon Rojas\nAnalista\njdleon@example.com", ("Jonathan David", "Leon Rojas")),
        ("Juan Pablo Di Marco\nTester\njpdimarco@example.com", ("Juan Pablo", "Di Marco")),
        # Partícula: abre el apellido compuesto y no se toma como nombre
        ("María de los Ángeles Fernández\nContadora\nmafernandez@example.com", ("María", "De Los Ángeles Fernández")),
        # Nombre y apellido simples: no cambian
        ("Mijal Nuñez\nAnalista de datos\nmnunez@example.com", ("Mijal", "Nuñez")),
        ("Luis Martin\nSoporte\nlmartin@example.com", ("Luis", "Martin")),
    ],
    ids=[
        "ariel_cristian",
        "maria_belen",
        "jonathan_david",
        "juan_pablo_di_marco",
        "de_los_angeles",
        "sin_segundo_nombre",
        "apellido_que_es_nombre",
    ],
)
def test_separa_nombres_y_apellidos_por_evidencia(texto, esperado):
    assert _nombre(texto) == esperado


@pytest.mark.parametrize(
    "texto,archivo,esperado",
    [
        # El archivo menciona a la persona sin su segundo nombre: la palabra omitida es un nombre, no parte del apellido
        (
            "Stella Mary Argüello\nSoporte técnico\nsmarguello@example.com",
            "Stella Argüello.pdf",
            ("Stella Mary", "Argüello"),
        ),
        # El email también omite el segundo nombre; el apellido compuesto se conserva completo
        (
            "Alvaro Rodrigo Vargas Garcia\nDesarrollador\nalvarovargas@example.com",
            "cv.pdf",
            ("Alvaro Rodrigo", "Vargas Garcia"),
        ),
        ("Marco Luciano Lo Cascio\nQA\nmarcolocascio@example.com", "cv.pdf", ("Marco Luciano", "Lo Cascio")),
        # Tres nombres de pila: lo prueba el archivo, que solo conserva el primer nombre y el apellido
        (
            "Reyna Gabriela Elizabeth Lopez\nAnalista\nrgl@example.com",
            "CV_ReynaLopez.pdf",
            ("Reyna Gabriela Elizabeth", "Lopez"),
        ),
        # Nombre compuesto con partícula: el archivo en formato "Apellido, Nombre" fija el apellido
        (
            "MARICEL DEL MILAGRO BURGENER\nQA Tester\nmburgener@example.com",
            "Burgener, Maricel del Milagro.pdf",
            ("Maricel Del Milagro", "Burgener"),
        ),
    ],
    ids=[
        "archivo_sin_segundo_nombre",
        "email_sin_segundo_nombre",
        "apellido_compuesto_corroborado",
        "tres_nombres_corroborados",
        "apellido_explicito_en_archivo",
    ],
)
def test_la_evidencia_del_propio_cv_separa_nombres_compuestos(texto, archivo, esperado):
    assert _nombre(texto, archivo) == esperado


@pytest.mark.parametrize(
    "texto,archivo,esperado",
    [
        # "Orlando" y "Nexxo" no son nombres de pila conocidos y ninguna fuente omite la palabra: no se inventa un nombre compuesto
        ("Nexxo Orlando Villarreal\nDesarrollador\nnexxov@example.com", "cv.pdf", ("Nexxo", "Orlando Villarreal")),
        # Primera palabra desconocida: podría ser "Apellido Nombre ..."; no se mueve nada
        ("Linoska Alejandra Rodríguez\nQA\nlrodriguez@example.com", "cv.pdf", ("Linoska", "Alejandra Rodríguez")),
        # Una repetición ("López López") no es una palabra omitida
        ("Facundo Lopez Lopez\nQA\nflopez@example.com", "Facundo Lopez.pdf", ("Facundo", "Lopez Lopez")),
    ],
    ids=["nombre_desconocido", "primera_palabra_desconocida", "apellido_repetido"],
)
def test_sin_evidencia_no_se_inventa_un_nombre_compuesto(texto, archivo, esperado):
    assert _nombre(texto, archivo) == esperado


@pytest.mark.parametrize(
    "texto,esperado",
    [
        (
            "Ing. Sonia Marcela Grimau\nDNI: 26815585\nEmail: sgrimau@example.com\nSoy proactiva",
            ("Sonia Marcela", "Grimau"),
        ),
        ("LIC. DÁMARIS COHEN\nOBJETIVO\nBusco ser parte de un proyecto\ndcohen@example.com", ("Dámaris", "Cohen")),
        ("Dr. Pablo Quiroga\nMédico\npquiroga@example.com", ("Pablo", "Quiroga")),
        ("Dra. Lucía Pérez-Gil\nMédica\nlperezgil@example.com", ("Lucía", "Pérez-Gil")),
    ],
    ids=["ing", "lic_mayusculas", "dr", "dra"],
)
def test_titulos_profesionales_no_son_nombre(texto, esperado):
    assert _nombre(texto) == esperado


@pytest.mark.parametrize(
    "segmento,esperado",
    [
        ("Ing. Sonia Grimau", ["Sonia", "Grimau"]),
        ("Lic Dámaris Cohen", ["Dámaris", "Cohen"]),
        ("Ing.", None),
        ("Lic.", None),
    ],
)
def test_tokens_de_nombre_descarta_titulos(segmento, esperado):
    assert CandidatoService._tokens_de_nombre(segmento, 1, 3) == esperado


@pytest.mark.parametrize(
    "texto,archivo,esperado",
    [
        # "DECISION MAKING" es una competencia: no aporta "Making" como nombre
        (
            "Habilidades\nDECISION MAKING\nBerenice Villarroel\nData Analyst\nbvillarroel@example.com",
            "cv.pdf",
            ("Berenice", "Villarroel"),
        ),
        # El CV empieza con una empresa; el nombre del archivo, corroborado por el email, identifica a la persona
        (
            "Opendev Pro\nSoftware Studio\nFrontend Developer\nfernandorodriguez@example.com",
            "CV - Fernando Rodriguez.pdf",
            ("Fernando", "Rodriguez"),
        ),
    ],
    ids=["frase_de_competencias", "empresa_en_el_encabezado"],
)
def test_frases_y_empresas_no_se_toman_como_nombre(texto, archivo, esperado):
    assert _nombre(texto, archivo) == esperado


@pytest.mark.parametrize(
    "texto,esperado",
    [
        # Formato con coma: el CV ya separa nombres y apellidos
        ("Pérez, Juan Carlos\nAnalista\njcperez@example.com", ("Juan Carlos", "Pérez")),
        # Campos explícitos: no se redistribuyen las palabras
        ("Datos personales\nNombre: Juan\nApellido: Carlos Pérez\njcperez@example.com", ("Juan", "Carlos Pérez")),
    ],
    ids=["formato_coma", "campos_explicitos"],
)
def test_separadores_explicitos_no_se_redistribuyen(texto, esperado):
    assert _nombre(texto) == esperado


@pytest.mark.parametrize(
    "palabras,contexto,esperado",
    [
        (["Ariel", "Cristian", "Vizne"], None, (["Ariel", "Cristian"], ["Vizne"])),
        (["Marco", "Luciano", "Lo", "Cascio"], None, (["Marco"], ["Luciano", "Lo", "Cascio"])),
        (
            ["Marco", "Luciano", "Lo", "Cascio"],
            {"unidos": ["marcolocascio37"], "palabras": " "},
            (["Marco", "Luciano"], ["Lo", "Cascio"]),
        ),
        (["María", "de", "los", "Ángeles", "Fernández"], None, (["María"], ["de", "los", "Ángeles", "Fernández"])),
        (["Carlos", "Madrigal", "Pérez"], None, (["Carlos"], ["Madrigal", "Pérez"])),
        (["Ana", "García"], None, (["Ana"], ["García"])),
        (["Nahuel"], None, (["Nahuel"], [])),
    ],
)
def test_dividir_nombre_apellido(palabras, contexto, esperado):
    assert CandidatoService._dividir_nombre_apellido(palabras, contexto) == esperado


def test_una_coma_en_el_archivo_que_no_es_apellido_no_confunde():
    # "CV, EDER ZOY": lo previo a la coma es una sigla del documento, no un apellido; el segundo nombre lo prueba la otra parte
    texto = "EDER NAHUEL ZOY\nIngeniero en Sistemas de Información\nederzoy6@example.com"
    assert _nombre(texto, "CV, EDER ZOY - Eder Zoy.pdf") == ("Eder Nahuel", "Zoy")


def test_una_inicial_final_no_gira_el_nombre():
    # "Jaan Carlos Jorge R": "R" es la inicial de un apellido; no prueba que "Carlos Jorge R" sean nombres de pila
    assert CandidatoService._ordenar_nombre_apellido(["Jaan", "Carlos", "Jorge", "R"]) == [
        "Jaan",
        "Carlos",
        "Jorge",
        "R",
    ]
    # El giro "Apellido Nombre" con nombres de pila reales sigue funcionando
    assert CandidatoService._ordenar_nombre_apellido(["Moreira", "Rodrigo"]) == ["Rodrigo", "Moreira"]


def test_encabezado_en_dos_lineas_con_inicial_final_y_linkedin():
    # Caso real simplificado: el encabezado visual parte "JAAN CARLOS" / "JORGE R"; LinkedIn omite el segundo nombre
    texto = (
        "EXPERIENCIA\nPERFIL PROFESIONAL\nPRODUCT OWNER\njorgejaanc@example.com\n"
        "linkedin.com/in/jaan-jorge-rodriguez-6a2539116"
    )
    datos = CandidatoService.parsear_cv_texto(texto, "cv.pdf", encabezado_visual="JAAN   CARLOS\nJORGE R")
    assert (datos["nombre"], datos["apellido"]) == ("Jaan Carlos", "Jorge R")


@pytest.mark.parametrize(
    "texto,archivo,esperado",
    [
        # Iniciales de los nombres pegadas al apellido en el email ("nov..." = Nexxo + Orlando)
        (
            "Nexxo Orlando Villarreal\nDesarrollador\nnovillarreal@example.com",
            "cv.pdf",
            ("Nexxo Orlando", "Villarreal"),
        ),
        # Inicial del segundo nombre entre el primer nombre y el apellido en el archivo
        (
            "Linoska Alejandra Rodríguez Vásquez\nQA\nlrodriguez@example.com",
            "Linoska_A_Rodriguez_V_CV.pdf",
            ("Linoska Alejandra", "Rodríguez Vásquez"),
        ),
        # La inicial del primer nombre sola no prueba un segundo nombre
        ("Nexxo Orlando Villarreal\nDesarrollador\nnvillarreal@example.com", "cv.pdf", ("Nexxo", "Orlando Villarreal")),
    ],
    ids=["iniciales_en_email", "inicial_en_archivo", "solo_inicial_del_primero"],
)
def test_las_iniciales_pegadas_al_apellido_prueban_los_nombres(texto, archivo, esperado):
    assert _nombre(texto, archivo) == esperado


def test_apellido_corto_solo_con_respaldo_del_email():
    # "Re" es un apellido de dos letras: el email "regonzalom" lo muestra pegado al nombre; sin eso sería una sigla
    assert CandidatoService._nombre_desde_archivo("Gonzalo Re.pdf", "regonzalom@example.com") == ("Gonzalo", "Re")
    assert CandidatoService._nombre_desde_archivo("Gonzalo Re.pdf", "gmartinez@example.com") is None
    assert CandidatoService._nombre_desde_archivo(
        "NH Data analyst-S - Nexxys Herrera.pdf", "nexxysherrera@example.com"
    ) == ("Nexxys", "Herrera")


@pytest.mark.parametrize(
    "texto,archivo,esperado",
    [
        # Email con el apellido antes del nombre ("villarrealnexxo"): "Orlando" no queda pegado al apellido, es un nombre
        (
            "Nexxo Orlando Villarreal\nDesarrollador\nvillarrealnexxo@example.com",
            "cv.pdf",
            ("Nexxo Orlando", "Villarreal"),
        ),
        # Apellido, primer nombre e inicial del segundo ("villarrealnexxoo")
        (
            "Nexxo Orlando Villarreal\nDesarrollador\nvillarrealnexxoo@example.com",
            "cv.pdf",
            ("Nexxo Orlando", "Villarreal"),
        ),
        # Apellido compuesto usado solo: "garcialopezana" pega "García" al apellido, no prueba que sea un nombre
        ("Ana García López\nDesarrolladora\ngarcialopezana@example.com", "cv.pdf", ("Ana", "García López")),
    ],
    ids=["email_apellido_primero_sin_intermedia", "email_apellido_nombre_inicial", "apellido_compuesto_no_es_nombre"],
)
def test_fuentes_con_apellido_primero(texto, archivo, esperado):
    assert _nombre(texto, archivo) == esperado


def test_un_archivo_escrito_apellido_primero_no_contradice_el_encabezado():
    # Escribir el archivo como "Apellido Nombre Nombre" es una convención y no contradice al encabezado "Nombre Nombre
    # Apellido": en CV reales (p. ej. "CV_Pilotti Pamela Sol" con encabezado "Pamela Sol Pilotti") la evidencia sigue valiendo
    texto = "Nexxo Orlando Villarreal\nDesarrollador\nvillarrealnexxo@example.com"
    assert _nombre(texto, "Villarreal Nexxo Orlando.pdf") == ("Nexxo Orlando", "Villarreal")


def test_las_etiquetas_explicitas_no_se_desplazan_por_otras_fuentes():
    # "Nombre:" y "Apellido:" separan explícitamente; el email con otro criterio no las redistribuye
    texto = "Datos personales\nNombre: Nexxo\nApellido: Orlando Villarreal\nvillarrealnexxo@example.com"
    assert _nombre(texto, "Nexxo Villarreal.pdf") == ("Nexxo", "Orlando Villarreal")


def test_etiqueta_apellido_y_nombres_con_coma_es_explicita():
    # "Apellido y nombres: Telle, Damián Ismael": el apellido y los nombres ya vienen separados por la coma
    texto = (
        "CURRÍCULUM VITAE\nDATOS PERSONALES:\nApellido y nombres: Telle, Damián Ismael\nDNI: 30111222\n"
        "dtelle@example.com"
    )
    assert _nombre(texto, "Damián Telle - Copy.pdf") == ("Damián Ismael", "Telle")


@pytest.mark.parametrize(
    "texto,esperado",
    [
        # LinkedIn por defecto ("nombre-apellido") frente a un encabezado "Apellido Nombre" con nombres poco comunes
        (
            "Coria Adriel\nEstudiante de Ingeniería\ncoriadriel021@example.com\nlinkedin.com/in/adriel-coria",
            ("Adriel", "Coria"),
        ),
        # Un LinkedIn personalizado (sin guiones) no define el orden
        (
            "Coria Adriel\nEstudiante de Ingeniería\ncoriadriel021@example.com\nlinkedin.com/in/coriadriel",
            ("Coria", "Adriel"),
        ),
    ],
    ids=["linkedin_por_defecto", "linkedin_sin_guiones"],
)
def test_el_linkedin_por_defecto_fija_el_orden_nombre_apellido(texto, esperado):
    assert _nombre(texto) == esperado


def test_email_con_separadores_respalda_el_orden_del_encabezado():
    # "Abel" no es un nombre de pila conocido y "Angel" sí: sin respaldo el orden se giraría a "Angel Abel"; el email
    # "abel.angel" escribe el mismo orden que el encabezado
    texto = "Abel Angel\nQA Engineer\nabel.angel1996@example.com"
    assert _nombre(texto) == ("Abel", "Angel")
    # Sin ese respaldo se mantiene el comportamiento histórico del giro con nombres de pila
    assert _nombre("Moreira Rodrigo\nAnalista\nmoreirar@example.com") == ("Rodrigo", "Moreira")


def test_el_encabezado_visual_completa_el_nombre_del_texto():
    # El texto lineal da "Luis Granada"; el título de la primera página trae el nombre completo
    texto = "Luis Granada\nDiseñador\nlgranada@example.com"
    datos = CandidatoService.parsear_cv_texto(texto, "cv.pdf", encabezado_visual="LUIS CARLOS\nGRANADA CASTAÑO")
    assert (datos["nombre"], datos["apellido"]) == ("Luis Carlos", "Granada Castaño")


@pytest.mark.parametrize(
    "candidatos,email,esperado",
    [
        # Completa el nombre: las palabras agregadas van después de la primera
        (
            [("Tobias", "Federico"), ("Tobias Federico", "Coria Gallegos")],
            "tcoria@example.com",
            ("Tobias Federico", "Coria Gallegos"),
        ),
        # Agrega un nombre al comienzo respaldado por el email o el archivo
        (
            [("Islas", "Neiner"), ("Florencia", "Islas Neiner")],
            "florenciaislasneiner@example.com",
            ("Florencia", "Islas Neiner"),
        ),
        # No comparte palabras con el texto y tiene más respaldo
        ([("María", "Vargas"), ("Mariana", "Yannone")], "marianayannone@example.com", ("Mariana", "Yannone")),
        # Sin respaldo se conserva el del texto
        ([("María", "Vargas"), ("Mariana", "Yannone")], "xyz@example.com", ("María", "Vargas")),
        # Una palabra agregada al comienzo y sin respaldo ("Cofundador") no desplaza al texto
        (
            [("Vinícius", "Rebouças"), ("Cofundador", "Vinícius Rebouças")],
            "vrebouças@example.com",
            ("Vinícius", "Rebouças"),
        ),
        # Una sigla agregada al final ("Cm") no completa el nombre
        ([("Carlos I", "Madrigal"), ("Carlos I", "Madrigal Cm")], "cmadrigal@example.com", ("Carlos I", "Madrigal")),
    ],
    ids=[
        "completa_con_apellido",
        "completa_con_nombre_respaldado",
        "mas_respaldo",
        "sin_respaldo",
        "cofundador",
        "sigla",
    ],
)
def test_elegir_nombre_entre_texto_y_encabezado_visual(candidatos, email, esperado):
    contexto = CandidatoService._contexto_nombre("", "cv.pdf", email)
    assert CandidatoService._elegir_nombre_cv(candidatos, contexto) == esperado
