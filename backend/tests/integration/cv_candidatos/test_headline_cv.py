"""Headline (puesto) del candidato al parsear un CV: surge del perfil que el CV declara, no de tecnologías aisladas.

Los textos son ficticios; reproducen la forma de los CVs reales que fallaban en la carga masiva de 1124 archivos (analista
funcional clasificado como desarrollador, QA como Frontend, PHP como Cloud/DevOps, Python/Django como .NET, analista de datos
como .NET, etc.).
"""

import pytest

from backend.modules.recruiting import headline_cv as hl
from backend.modules.recruiting.headline_cv import analizar_headline_cv, detectar_headline_cv
from backend.modules.recruiting.services import CandidatoService

CATALOGO = {
    hl.DATA_ENGINEER,
    hl.DATA_ARCHITECT,
    hl.CLOUD_DEVOPS,
    hl.DOTNET,
    hl.FRONTEND,
    hl.BACKEND,
    hl.FULL_STACK,
    hl.QA,
    hl.ANALISTA_FUNCIONAL,
    hl.PROJECT_MANAGER,
    hl.SCRUM_MASTER,
    hl.LIDER_TECNICO,
    hl.RECRUITER,
    hl.DBA,
    hl.DEVOPS,
    hl.OTRO,
    hl.DATA_ANALYST,
    hl.ANALYTICS_ENGINEER,
    hl.SOPORTE,
}

# Habilidades técnicas comunes a perfiles distintos: por sí solas no definen la profesión
SKILLS_COMPARTIDAS = (
    "Habilidades técnicas\nPython, SQL, Java, JavaScript, React, Angular, Docker, AWS, Azure DevOps, Kubernetes, Jenkins, Git, "
    "Selenium, Cypress, Postman, .NET, C#, Power BI, Jira"
)


def _cv(titulo: str, perfil: str, experiencia: str, extra: str = SKILLS_COMPARTIDAS) -> str:
    return (
        f"Ana Pérez\n{titulo}\nana.perez@example.com | +54 351 555 1234 | Córdoba, Argentina\n\n"
        f"Perfil profesional\n{perfil}\n\nExperiencia laboral\n{experiencia}\n\n{extra}\n\nEducación\nUniversidad Tecnológica Nacional"
    )


# --- Casos reportados: la profesión no se infiere de coincidencias genéricas ----------------------------------------------


def test_analista_funcional_no_se_clasifica_como_desarrollador():
    texto = _cv(
        "Analista Funcional",
        "Analista Funcional con experiencia en relevamiento de requerimientos y documentación funcional.",
        "Analista Funcional | Banco Ejemplo | 2021 - Actualidad\n- Relevamiento de requerimientos y casos de uso con SQL, Java y APIs REST.\n"
        "Analista de Calidad | Empresa Uno | 2019 - 2021",
    )
    assert detectar_headline_cv(texto) == hl.ANALISTA_FUNCIONAL


def test_qa_no_se_clasifica_como_frontend_aunque_use_react_y_javascript():
    texto = _cv(
        "QA Automation Engineer",
        "QA con experiencia en pruebas automatizadas de aplicaciones React y Angular.",
        "QA Automation Engineer | Empresa Web | 2020 - Actualidad\n- Automatización con Cypress y JavaScript sobre interfaces React.",
    )
    assert detectar_headline_cv(texto) == hl.QA


def test_desarrolladora_php_no_es_cloud_devops_por_mencionar_docker_y_aws():
    texto = _cv(
        "Desarrolladora PHP",
        "Desarrolladora con experiencia en Laravel, despliegues con Docker y servicios de AWS.",
        "Desarrolladora PHP | Agencia Web | 2019 - Actualidad\n- Mantenimiento de aplicaciones Laravel y despliegue en AWS con Docker.",
    )
    assert detectar_headline_cv(texto) == hl.BACKEND


def test_desarrollador_python_django_no_es_dotnet_aunque_conozca_c_sharp():
    texto = _cv(
        "Desarrollador Python / Django",
        "Desarrollador con experiencia en Python y Django; conocimientos básicos de .NET y C#.",
        "Desarrollador Python | Software Factory | 2020 - Actualidad\n- APIs con Django REST Framework.",
    )
    assert detectar_headline_cv(texto) == hl.BACKEND


def test_analista_de_datos_rpa_no_se_clasifica_como_dotnet_ni_desarrollador():
    texto = _cv(
        "Analista de Datos y Desarrollador RPA",
        "Analista de Datos con experiencia en automatización de procesos con C# y Python.",
        "Analista de Datos y Desarrollador RPA | Consultora | 2022 - Actualidad\n- Automatizaciones en C# y reportes en Power BI.",
    )
    headline = detectar_headline_cv(texto)
    assert headline == hl.DATA_ANALYST  # perfil del catálogo v2
    assert headline not in (hl.DOTNET, hl.BACKEND, hl.FRONTEND, hl.FULL_STACK)


def test_backend_developer_no_es_frontend_por_conocer_react():
    texto = _cv(
        "Backend Developer",
        "Backend Developer con experiencia en Node.js. Conocimientos de React y Angular.",
        "Backend Developer | Empresa API | 2020 - Actualidad\n- Servicios con Node.js. Soporte de interfaces React.",
    )
    assert detectar_headline_cv(texto) == hl.BACKEND


# --- Prioridad de la evidencia -------------------------------------------------------------------------------------------


def test_el_titulo_explicito_prima_sobre_las_tecnologias_mas_mencionadas():
    # Muchas menciones de React/Angular/Docker, pero el título declarado es Backend
    texto = _cv(
        "Desarrollador Backend",
        "Desarrollo de servicios. Uso React, Angular, Vue, Docker, Kubernetes y Terraform en varios proyectos.",
        "React, Angular, Vue, Docker, Kubernetes, Terraform, AWS, Azure",
    )
    assert analizar_headline_cv(texto) == (hl.BACKEND, "encabezado")


def test_con_varios_titulos_en_el_encabezado_se_usa_el_primero_declarado():
    assert (
        detectar_headline_cv(_cv("Desarrollador Backend | Analista Funcional", "Perfil", "Experiencia")) == hl.BACKEND
    )
    assert detectar_headline_cv(_cv("Analista Funcional / QA", "Perfil", "Experiencia")) == hl.ANALISTA_FUNCIONAL


def test_el_perfil_declarado_se_usa_cuando_el_encabezado_no_tiene_titulo():
    texto = (
        "Ana Pérez\nana.perez@example.com\n\nPerfil profesional\nSoy Analista QA con más de 5 años de experiencia en testing.\n\n"
        "Experiencia laboral\nEmpresa Uno | 2019 - Actualidad\n" + SKILLS_COMPARTIDAS
    )
    assert analizar_headline_cv(texto) == (hl.QA, "resumen")


def test_el_puesto_de_la_experiencia_se_usa_si_no_hay_titulo_ni_perfil_declarado():
    texto = (
        "Ana Pérez\nana.perez@example.com\n\nExperiencia laboral\nAnalista QA Ssr | Banco Ejemplo | 2022 - Actualidad\n"
        "Analista QA | Empresa Dos | 2019 - 2022\n\nHabilidades\nReact, Docker, AWS\nEducación\nUTN"
    )
    assert analizar_headline_cv(texto) == (hl.QA, "experiencia_fechada")


def test_un_titulo_generico_deja_decidir_a_la_experiencia():
    texto = (
        "Ana Pérez\nSenior Software Developer\nana.perez@example.com\n\nExperiencia laboral\nSenior Full Stack Developer | Empresa | 2022 - Actualidad\n"
        "Backend Developer | Otra | 2019 - 2022\n\nHabilidades\nDocker, AWS"
    )
    assert detectar_headline_cv(texto) == hl.FULL_STACK


def test_el_texto_destacado_de_la_primera_pagina_se_usa_como_titulo():
    texto = "Contacto\nana.perez@example.com\nHabilidades\nPython"
    assert detectar_headline_cv(texto, encabezado_visual="ANA PÉREZ\nData Engineer") == hl.DATA_ENGINEER


def test_titulo_con_letras_espaciadas_se_reconoce():
    texto = "Ana Pérez\nA N A L I S T A F U N C I O N A L\nana.perez@example.com\nPerfil\nHabilidades\nSQL"
    assert detectar_headline_cv(texto) == hl.ANALISTA_FUNCIONAL


def test_titulo_partido_en_dos_renglones_se_reconoce():
    texto = "ANA PÉREZ\nANALISTA\nFUNCIONAL\nana.perez@example.com\nHabilidades\nSQL"
    assert detectar_headline_cv(texto) == hl.ANALISTA_FUNCIONAL


# --- Sin evidencia suficiente: no se inventa una profesión --------------------------------------------------------------


@pytest.mark.parametrize(
    "texto",
    [
        # tecnologías sin ningún rol
        "Ana Pérez\nana.perez@example.com\n" + SKILLS_COMPARTIDAS,
        # perfil administrativo
        "Ana Pérez\nana.perez@example.com\nPerfil\nProfesional administrativa con experiencia en facturación y atención al cliente.\n"
        "Experiencia laboral\nAsistente administrativa | Comercio | 2020 - Actualidad\nHabilidades\nExcel, Word",
        # estudiante con herramientas de nube
        "Ana Pérez\nEstudiante de la Tecnicatura en Programación\nana.perez@example.com\nHabilidades\nDocker, AWS, React, Python",
        # documento vacío
        "",
    ],
)
def test_sin_evidencia_suficiente_el_headline_queda_vacio(texto):
    assert detectar_headline_cv(texto) is None


def test_roles_sin_equivalente_en_el_catalogo_se_asignan_a_otro_y_no_a_otro_perfil():
    for titulo in ("Product Owner", "Científico de Datos", "Business Analytics Translator"):
        assert detectar_headline_cv(_cv(titulo, "Perfil", "Experiencia")) == hl.OTRO, titulo


def test_roles_con_perfil_propio_en_el_catalogo_v2():
    for titulo, esperado in (
        ("Data Analyst", hl.DATA_ANALYST),
        ("Analista de Datos", hl.DATA_ANALYST),
        ("Analista de Soporte Técnico", hl.SOPORTE),
        ("Analytics Engineer", hl.ANALYTICS_ENGINEER),
    ):
        assert detectar_headline_cv(_cv(titulo, "Perfil", "Experiencia")) == esperado, titulo


@pytest.mark.parametrize(
    "linea",
    [
        "Pipelines con Azure DevOps y Jenkins",  # herramienta, no rol
        "Implementación en QA/PROD de los desarrollos",  # ambientes, no rol
        "Experiencia en AWS, Docker y Kubernetes",
    ],
)
def test_menciones_de_herramientas_o_ambientes_no_son_un_rol(linea):
    texto = (
        f"Ana Pérez\nana.perez@example.com\nExperiencia laboral\nEmpresa | 2020 - Actualidad\n{linea}\nHabilidades\nSQL"
    )
    assert detectar_headline_cv(texto) is None


def test_cursos_y_formacion_no_cuentan_como_puesto():
    texto = (
        "Ana Pérez\nana.perez@example.com\nExperiencia laboral\nAsistente administrativa | Comercio | 2020 - Actualidad\n"
        "Educación\nCurso de Desarrollador Full Stack - Bootcamp 700hs\nTecnicatura Universitaria en QA\n"
    )
    assert detectar_headline_cv(texto) is None


# --- Variedad de perfiles: la solución no corrige unos casos a costa de otros ------------------------------------------


@pytest.mark.parametrize(
    "titulo,esperado",
    [
        ("Data Engineer", hl.DATA_ENGINEER),
        ("Ingeniera de Datos", hl.DATA_ENGINEER),
        ("Data Architect", hl.DATA_ARCHITECT),
        ("DevOps Engineer", hl.DEVOPS),
        ("SRE", hl.DEVOPS),
        ("Cloud Engineer", hl.CLOUD_DEVOPS),
        ("Desarrollador .NET", hl.DOTNET),
        ("C# Developer", hl.DOTNET),
        ("Desarrollador Frontend", hl.FRONTEND),
        ("React Developer", hl.FRONTEND),
        ("Desarrolladora Backend", hl.BACKEND),
        ("Java Developer", hl.BACKEND),
        ("Desarrollador Full Stack", hl.FULL_STACK),
        ("Fullstack Developer", hl.FULL_STACK),
        ("Tester QA", hl.QA),
        ("Analista de Testing", hl.QA),
        ("Analista Funcional", hl.ANALISTA_FUNCIONAL),
        ("Business Analyst", hl.ANALISTA_FUNCIONAL),
        ("Project Manager", hl.PROJECT_MANAGER),
        ("Líder de Proyectos", hl.PROJECT_MANAGER),
        ("Scrum Master", hl.SCRUM_MASTER),
        ("Tech Lead", hl.LIDER_TECNICO),
        ("Recruiter IT", hl.RECRUITER),
        ("Administrador de Bases de Datos", hl.DBA),
    ],
)
def test_titulos_explicitos_de_perfiles_distintos(titulo, esperado):
    assert detectar_headline_cv(_cv(titulo, "Perfil profesional.", "Experiencia.")) == esperado


def test_el_resultado_siempre_es_un_nombre_del_catalogo_o_none():
    textos = [
        _cv(t, "Perfil", "Experiencia")
        for t in (
            "Data Engineer",
            "Desarrollador Backend",
            "Analista QA",
            "Scrum Master",
            "Tech Lead",
            "Analista de Datos",
            "Recruiter",
            "DBA",
        )
    ] + ["", "Texto sin sentido\n\n", SKILLS_COMPARTIDAS]
    for t in textos:
        assert detectar_headline_cv(t) in CATALOGO | {None}


def test_el_nombre_del_lider_tecnico_coincide_con_el_catalogo_sin_caracteres_rotos():
    assert hl.LIDER_TECNICO == "Líder Técnico"
    assert detectar_headline_cv(_cv("Tech Lead", "Perfil", "Experiencia")) == "Líder Técnico"


# --- Integración con el parser del CV ---------------------------------------------------------------------------------------


def test_el_parser_del_cv_asigna_el_headline_con_la_nueva_logica():
    texto = _cv(
        "Analista Funcional",
        "Analista Funcional con experiencia en relevamiento de requerimientos.",
        "Analista Funcional | Banco Ejemplo | 2021 - Actualidad",
    )
    assert CandidatoService.parsear_cv_texto(texto, "Ana Perez.pdf")["headline"] == hl.ANALISTA_FUNCIONAL


def test_el_parser_deja_el_headline_vacio_sin_evidencia():
    datos = CandidatoService.parsear_cv_texto(
        "Ana Pérez\nana.perez@example.com\n" + SKILLS_COMPARTIDAS, "Ana Perez.pdf"
    )
    assert datos["headline"] is None
    assert datos["email"] == "ana.perez@example.com"


# --- Prioridad por fechas (D4/D5): decide el puesto más reciente, no el primero del texto -----------------------------------


def test_el_puesto_mas_reciente_por_fecha_prima_sobre_el_primero_del_texto():
    texto = (
        "Ana Pérez\nana.perez@example.com\nExperiencia laboral\n"
        "Project Manager | Empresa Uno | Ago. 2023 - May. 2024\n"
        "Data Engineer | Empresa Dos | Jun, 2025 - Actualidad\n"
        "Habilidades\nSQL"
    )
    assert analizar_headline_cv(texto) == (hl.DATA_ENGINEER, "experiencia_fechada")


def test_fecha_encima_del_cargo_se_asocia_al_cargo_siguiente():
    # Diseño "empresa y período" arriba y cargo debajo (CVs de Canva ordenados por posición)
    texto = (
        "Ana Pérez\nana.perez@example.com\nExperiencia profesional\n"
        "Empresa Uno, Buenos Aires, Argentina      Jun, 2025 - Actualidad\nData Engineer\n- Modelado de datos.\n- ETL.\n"
        "Empresa Dos, Buenos Aires, Argentina      May. 2024 - Jun, 2025\nProject Manager\n- Gestión de proyectos.\n"
        "Educación\nUBA"
    )
    assert detectar_headline_cv(texto) == hl.DATA_ENGINEER


def test_fecha_debajo_de_la_descripcion_se_asocia_al_cargo_anterior():
    texto = (
        "Ana Pérez\nana.perez@example.com\nExperiencia Laboral\n"
        "Analista Funcional:\nRelevamiento de requerimientos.\nDocumentación funcional.\nEmpresa Uno - Junio 2024 – Actualidad\n"
        "Desarrolladora Backend:\nServicios Java.\nEmpresa Dos - Julio 2020 – Mayo 2024\nFormación\nUTN"
    )
    assert detectar_headline_cv(texto) == hl.ANALISTA_FUNCIONAL


def test_periodo_partido_en_dos_renglones_y_fechas_numericas():
    partido = "Ana Pérez\nana@example.com\nExperiencia profesional\nQA Tester - Empresa\nMar 2026 -\nPresente\nDesarrolladora Backend - Otra\nOct 2021 -\nDic 2025\nCursos\nX"
    numerico = "Ana Pérez\nana@example.com\nExperiencia laboral\nDesarrollador Backend | Empresa | 03/2019 - 12/2022\nQA Tester | Otra | 01/2023 - 06/2025\nEducación\nUTN"
    assert detectar_headline_cv(partido) == hl.QA
    assert detectar_headline_cv(numerico) == hl.QA


def test_el_puesto_reciente_sin_equivalente_no_se_reemplaza_por_uno_anterior():
    texto = (
        "Ana Pérez\nana@example.com\nExperiencia laboral\n"
        "Product Owner | Empresa | Jun 2025 - Actualidad\nData Engineer | Otra | 2020 - 2025\nEducación\nUBA"
    )
    assert analizar_headline_cv(texto) == (hl.OTRO, "experiencia_fechada")


def test_el_puesto_reciente_con_perfil_propio_prima_sobre_el_anterior():
    texto = (
        "Ana Pérez\nana@example.com\nExperiencia laboral\n"
        "Analytics Engineer | Empresa | Jun 2025 - Actualidad\nData Engineer | Otra | 2020 - 2025\nEducación\nUBA"
    )
    assert analizar_headline_cv(texto) == (hl.ANALYTICS_ENGINEER, "experiencia_fechada")


def test_pasante_no_es_el_puesto_actual_si_hay_uno_posterior():
    texto = (
        "EDUCACIÓN\nUniversidad | 2020 - 2024\nEXPERIENCIA LABORAL\nSOBRE MÍ\n"
        "Pasante en Proyectos y Aplicaciones TI - Empresa\nSEPT 2022 - FEB 2024\nApoyé al Product Owner.\n"
        "Analista Ingeniero de Datos y BI - Empresa\nJUN 2025 - SEPT 2026\nModelos de datos."
    )
    assert detectar_headline_cv(texto) == hl.DATA_ENGINEER


def test_pasante_vigente_toma_el_rol_de_la_misma_linea():
    texto = "Ana Pérez\nana@example.com\nExperiencia laboral\nPasante QA | Empresa | 2025 - Actualidad\nEducación\nUTN"
    assert detectar_headline_cv(texto) == hl.QA


# --- "Otro" como respaldo real: no interrumpe la búsqueda ---------------------------------------------------------------------


def test_un_rol_sin_equivalente_en_el_encabezado_no_interrumpe_la_busqueda():
    texto = (
        "Ana Pérez\nProduct Owner\nana@example.com\nPerfil profesional\nMe gustan los productos.\n"
        "Experiencia laboral\nAnalista Funcional - Banco\nRelevamiento.\nHabilidades\nSQL"
    )
    assert analizar_headline_cv(texto) == (hl.ANALISTA_FUNCIONAL, "experiencia")


def test_solo_titulos_genericos_o_sin_equivalente_se_asignan_a_otro():
    assert detectar_headline_cv("Ana Pérez\nDesarrolladora de Software\nana@example.com\nHabilidades\nSQL") == hl.OTRO
    assert detectar_headline_cv(_cv("Product Owner", "Perfil", "Experiencia")) == hl.OTRO


@pytest.mark.parametrize(
    "titulo,esperado",
    [
        ("BI Analyst", hl.DATA_ANALYST),
        ("Senior BI Analyst:", hl.DATA_ANALYST),
        ("Data Analyst SSR", hl.DATA_ANALYST),
        ("Analista de Datos y Business Intelligence (BI) Semi Senior", hl.DATA_ANALYST),
        ("Power BI Developer", hl.DATA_ANALYST),
        ("Business Analytics Translator", hl.OTRO),  # no es automáticamente Data Analyst
        ("Analytics Engineer", hl.ANALYTICS_ENGINEER),
        ("Application Analyst Tier II/III", hl.SOPORTE),
        ("Application Support Analyst", hl.SOPORTE),
        ("Support Analyst Level 2", hl.SOPORTE),
        ("Mesa de ayuda - Help desk", hl.SOPORTE),
        ("Service Desk", hl.SOPORTE),
        ("Técnico de Soporte", hl.SOPORTE),
        ("Ingeniera de Datos", hl.DATA_ENGINEER),  # reutiliza el perfil existente
    ],
)
def test_perfiles_habituales_se_reconocen_por_alias(titulo, esperado):
    texto = f"Ana Pérez\nana@example.com\nExperiencia laboral\n{titulo} | Empresa | 2023 - Actualidad\nEducación\nUTN"
    assert detectar_headline_cv(texto) == esperado


# --- Decisión B: el encabezado prima si está respaldado por la experiencia ------------------------------------------------


def _cv_dos_columnas(titulo_encabezado: str, cargo_vigente: str) -> str:
    # Orden de dibujo de un CV a dos columnas: la columna lateral (formación) llega antes que el nombre y su título
    return (
        "EDUCACIÓN\nUniversidad | 2020 - 2024\nEXPERIENCIA LABORAL\nSOBRE MÍ\n"
        "Pasante en Proyectos TI - Empresa\nSEPT 2022 - FEB 2024\nApoyo al equipo.\n"
        f"LUCAS PRUEBA\n{titulo_encabezado}\nProduct Manager, Coderhouse\n"
        f"{cargo_vigente} - Empresa\nJUN 2025 - SEPT 2026\nModelos de datos."
    )


def test_encabezado_coherente_con_el_puesto_vigente_prima_sobre_la_experiencia():
    texto = _cv_dos_columnas("ANALYTICS ENGINEER | DATA PRODUCT SPECIALIST | PM", "Analista Ingeniero de Datos y BI")
    assert analizar_headline_cv(texto, encabezado_visual="LUCAS PRUEBA") == (
        hl.ANALYTICS_ENGINEER,
        "encabezado_respaldado",
    )


def test_encabezado_que_contradice_la_experiencia_no_se_toma_como_vigente():
    texto = _cv_dos_columnas("QA AUTOMATION ENGINEER", "Analista Ingeniero de Datos y BI")
    assert analizar_headline_cv(texto, encabezado_visual="LUCAS PRUEBA") == (hl.DATA_ENGINEER, "experiencia_fechada")


def test_encabezado_no_prima_si_el_puesto_vigente_no_es_del_area():
    texto = _cv_dos_columnas("DATA ENGINEER", "Product Owner")
    assert analizar_headline_cv(texto, encabezado_visual="LUCAS PRUEBA") == (hl.OTRO, "experiencia_fechada")


# --- Etapa 4: período encima de la empresa (orden de lectura de un CV con fechas en el margen) -------------------------


def test_periodo_encima_de_la_empresa_se_asocia_al_cargo_de_abajo():
    texto = (
        "Francisco Prueba\nfrancisco@example.com\nEXPERIENCIA PROFESIONAL\n"
        "Jun, 2025 - Actualidad\nAcid Labs, Santiago, Chile\nAnalytics Engineer\nGestión de stakeholders.\n"
        "May. 2024 - Jun, 2025\nDatalytics, Buenos Aires, Argentina\nBusiness Analytics Translator\nUser stories.\n"
        "Lubee, Buenos Aires, Argentina\nProject Manager | Analista Funcional\nScrum.\nAgo. 2023 - May. 2024\nEDUCACIÓN\nUBA"
    )
    fechados = {linea: periodo for periodo, _, linea in hl._titulos_con_fecha(texto)}
    assert fechados["Analytics Engineer"] == ((9999, 12), (2025, 6))
    assert fechados["Business Analytics Translator"] == ((2025, 6), (2024, 5))
    assert fechados["Project Manager | Analista Funcional"] == ((2024, 5), (2023, 8))
    assert analizar_headline_cv(texto) == (hl.ANALYTICS_ENGINEER, "experiencia_fechada")


def test_periodo_partido_en_el_margen_encima_del_cargo():
    texto = (
        "Luna Prueba\nluna@example.com\nExperiencia profesional\n"
        "Mar 2026 -\nPresente\nIT Recruiter Sr. - Freelance\nBúsqueda de perfiles.\n"
        "Dic 2021 -\nMar 2026\nIT Recruiter Sr. - Consultora\nEntrevistas.\nCursos\nX"
    )
    assert analizar_headline_cv(texto) == (hl.RECRUITER, "experiencia_fechada")


# --- Etapa 6.2: QA como tarea o herramienta no es un cargo ---------------------------------------------------------------


@pytest.mark.parametrize(
    "frase",
    [
        "Manejo de backlog y validación de tareas mediante QA.",
        "Coordinación de entregas con el equipo de QA y desarrollo.",
        "Seguimiento de incidencias junto al área de QA",
    ],
)
def test_qa_dentro_de_una_frase_de_tareas_no_es_un_cargo(frase):
    texto = f"Ana Pérez\nana@example.com\nExperiencia laboral\nProduct Owner | Empresa\n{frase}\nEducación\nUBA"
    assert analizar_headline_cv(texto) == (hl.OTRO, "sin_equivalente")


@pytest.mark.parametrize(
    "titulo", ["QA Analyst", "QA Engineer", "QA Tester", "Analista de QA", "Analista QA Semi Senior", "Líder QA"]
)
def test_cargos_de_qa_se_siguen_reconociendo(titulo):
    texto = f"Ana Pérez\nana@example.com\nExperiencia laboral\n{titulo} | Empresa | 2022 - Actualidad\nEducación\nUTN"
    assert detectar_headline_cv(texto) == hl.QA


# --- Etapa 6.1: una pasantía anterior no define el seniority actual ------------------------------------------------------

_CV_PASANTIA_ANTERIOR = (
    "Lucas Prueba\nANALYTICS ENGINEER\nlucas@example.com\nEXPERIENCIA LABORAL\n"
    "Analista Ingeniero de Datos y BI - Empresa\nJUN 2025 - SEPT 2026\nModelos de datos.\n"
    "Pasante en Proyectos y Aplicaciones TI - Empresa\nSEPT 2022 - FEB 2024\nApoyo al equipo.\nEDUCACIÓN\nUCC"
)


def test_puesto_vigente_es_condicion():
    assert hl.puesto_vigente_es_condicion(_CV_PASANTIA_ANTERIOR) is False
    vigente = "Ana Pérez\nana@example.com\nExperiencia laboral\nPasante de Desarrollo | Empresa | 2025 - Actualidad\nEducación\nUTN"
    assert hl.puesto_vigente_es_condicion(vigente) is True
    assert (
        hl.puesto_vigente_es_condicion(
            "Ana Pérez\nana@example.com\nExperiencia laboral\nPasante en Empresa\nEducación\nUTN"
        )
        is None
    )


def test_pasantia_anterior_no_asigna_trainee():
    datos = CandidatoService.parsear_cv_texto(_CV_PASANTIA_ANTERIOR, "cv.pdf")
    assert datos["headline"] == hl.ANALYTICS_ENGINEER
    assert datos["seniority"] is None  # sin evidencia de seniority no se inventa uno


def test_pasantia_vigente_o_sin_fechas_asigna_trainee():
    vigente = "Ana Pérez\nana@example.com\nExperiencia laboral\nPasante de Desarrollo | Empresa | 2025 - Actualidad\nEducación\nUTN"
    sin_fechas = "Ana Pérez\nana@example.com\nExperiencia laboral\nPracticante en Empresa Uno\nEducación\nUTN"
    assert CandidatoService.parsear_cv_texto(vigente, "cv.pdf")["seniority"] == "Trainee"
    assert CandidatoService.parsear_cv_texto(sin_fechas, "cv.pdf")["seniority"] == "Trainee"
