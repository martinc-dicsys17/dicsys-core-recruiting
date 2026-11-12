"""Detección de skills en CVs: solo se guardan tecnologías que el contenido del CV respalda.

Los textos son ficticios; reproducen la forma de los CVs reales que fallaban (sinónimo genérico "pipelines", URLs de GitHub,
"react.js" confundido con "js", nombres de empresa o palabras comunes que coinciden con una tecnología).
"""

import json
from pathlib import Path

import pytest

from backend.modules.recruiting.services import CandidatoService

# El catálogo base de skills es el que carga la revisión 0006 (el original lo tenía además en seed_data.py)
RECRUITING_SKILLS_SEED = [
    s
    for s in json.loads(
        (Path(__file__).resolve().parents[3] / "migraciones" / "datos" / "0006_catalogos_recruiting.json").read_text(
            encoding="utf-8"
        )
    )["recruiting_skills"]
    if s.get("activo", True)
]


def _skills(texto: str, catalogo=None) -> list:
    return CandidatoService.detectar_skills_cv(texto, catalogo if catalogo is not None else RECRUITING_SKILLS_SEED)


# --- Sinónimos genéricos y coincidencias que el CV no respalda -------------------------------------------------------


@pytest.mark.parametrize(
    "texto",
    [
        "Perfil: diseño de pipelines ETL y modelado de datos. Power BI, SQL.",
        "Optimización de data pipelines para el área de ventas.",
        "Herramientas: SQL Server, dataflows, pipelines, Tableau",
    ],
)
def test_pipelines_no_es_ci_cd(texto):
    assert "CI/CD" not in _skills(texto)


def test_ci_cd_se_detecta_cuando_el_cv_lo_nombra():
    assert "CI/CD" in _skills("Arquitectura & DevOps: CI/CD · Docker · Amazon Web Services")
    assert "CI/CD" in _skills("Experiencia con integración continua: continuous integration y continuous delivery")


def test_catalogo_de_bd_con_sinonimo_generico_no_genera_la_skill():
    catalogo = [
        {"nombre": "CI/CD", "sinonimos": ["ci/cd", "pipelines"]},
        {"nombre": "Linux", "sinonimos": ["linux", "bash", "shell"]},
    ]
    assert _skills("Diseño de pipelines de datos. Scripts en bash y shell.", catalogo) == []


@pytest.mark.parametrize(
    "texto",
    [
        "Contacto: https://github.com/usuario-ejemplo https://www.linkedin.com/in/usuario",
        "GitHub: usuario-ejemplo\nLinkedIn: usuario",
        "Mi GitHub y mi portfolio",
        "github.com/usuario\nAnalista funcional",
    ],
)
def test_enlace_o_etiqueta_de_perfil_github_no_es_git(texto):
    assert "Git" not in _skills(texto)


def test_git_solo_con_la_mencion_de_git():
    assert "Git" in _skills("Control de versiones: Git & GitHub")
    assert "Git" in _skills("Flujo de trabajo con Git Flow")


@pytest.mark.parametrize(
    "texto,skill",
    [
        ("Herramientas: Jira | Trello | GitHub | WordPress", "GitHub"),
        ("Administré herramientas Atlassian (Jira, Confluence, Bitbucket, Xray, Zephyr)", "Bitbucket"),
        ("Repositorios en GitLab y despliegues con Docker", "GitLab"),
    ],
)
def test_plataformas_de_repositorios_no_implican_git(texto, skill):
    resultado = _skills(texto)
    assert skill in resultado
    assert "Git" not in resultado


def test_bash_y_shell_no_implican_linux():
    assert "Linux" not in _skills("Scripts en Bash para automatizar procesos. Unix shell scripts en modo eventual.")
    assert "Linux" in _skills("Administración de servidores Linux (Ubuntu)")


def test_shell_como_empresa_no_es_una_skill():
    assert _skills("Soporte técnico a clientes corporativos (Shell, Arcor, Banco Nación)") == []


def test_bash_se_detecta_como_skill_propia():
    assert "Bash" in _skills("Automatización: Bash, Python")


def test_react_js_no_es_javascript():
    assert "JavaScript" not in _skills("Frontend en React.js y Vue.js con diseño responsive")
    assert "JavaScript" in _skills("Lenguajes: JavaScript, TypeScript, React.js")
    assert "JavaScript" in _skills("Lenguajes: JS, HTML, CSS")


def test_nombres_de_archivo_o_url_con_extension_no_son_skills():
    assert "PHP" not in _skills("Ver certificado: https://academy.example.com/mod/verify.php?code=abc123")
    assert "PHP" not in _skills("Publicación en https://revistas.example.edu.ar/index.php/Bitacora/issue/view/3098")
    assert "PHP" in _skills("Desarrollo web en PHP y MySQL")


# --- Términos ambiguos: solo con contexto técnico ---------------------------------------------------------------------


def test_synapse_como_empresa_no_es_la_skill():
    assert "Synapse" not in _skills(
        "Consultor de procesos y sistemas en Synapse Business Analysis.\nAbril 2025 - actualidad"
    )
    assert "Synapse" in _skills("Cloud: Azure Synapse, Databricks, Data Factory")


def test_elastic_como_adjetivo_no_es_elasticsearch():
    texto = "Prediction of the thermodynamic, elastic, electronic, and structural properties of alloys"
    assert "Elasticsearch" not in _skills(texto)
    assert "Elasticsearch" in _skills("Monitoreo de logs (Elasticsearch), Docker")


def test_go_ambiguo_requiere_lista_de_tecnologias():
    assert "Go" not in _skills("Estrategia go to market para nuevos productos")
    assert "Go" in _skills("Backend: Go, Postman, microservicios con Docker")


def test_excel_y_oracle_ambiguos_requieren_contexto_tecnico():
    assert "Excel" not in _skills("Busco un equipo donde pueda excel en mis tareas y crecer.")
    assert {"Excel", "Oracle", "SQL"} <= set(_skills("Herramientas: SQL, Oracle, Excel avanzado"))


# --- Variantes de escritura ------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "texto,esperada",
    [
        ("Dashboards en Power-BI", "Power BI"),
        ("Dashboards en PowerBI", "Power BI"),
        ("Backend con Node JS y MongoDB", "Node.js"),
        ("Backend con node-js", "Node.js"),
        ("Backend con NodeJS", "Node.js"),
        ("Modelos con Scikit Learn", "scikit-learn"),
        ("Modelos con sklearn", "scikit-learn"),
        ("Bases de datos: sqlserver", "SQL Server"),
        ("Frameworks: React JS, Vue.js", "React"),
        ("Pipelines con integración y despliegue: CI CD", "CI/CD"),
    ],
)
def test_variantes_de_escritura(texto, esperada):
    assert esperada in _skills(texto)


def test_no_coincide_dentro_de_otra_palabra():
    assert _skills("Javascripting, sqlalchemy, dockerfile y reactivo") == []


# --- Tecnologías relevantes que antes se omitían -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "texto,esperadas",
    [
        (
            "Business Intelligence: Tableau, MicroStrategy, Qlik Sense, Power BI",
            {"Tableau", "MicroStrategy", "Qlik", "Power BI"},
        ),
        (
            "ETL: SSIS, SSRS, SSAS, Informatica PowerCenter, Teradata",
            {"SSIS", "SSRS", "SSAS", "Informatica", "Teradata"},
        ),
        ("QA: Postman, Swagger, SonarQube, Jenkins, JMeter", {"Postman", "Swagger", "SonarQube", "Jenkins", "JMeter"}),
        (
            "IA: TensorFlow, PyTorch, scikit-learn, LangChain, Pandas, NumPy",
            {"TensorFlow", "PyTorch", "scikit-learn", "LangChain", "Pandas", "NumPy"},
        ),
        (
            "Microsoft: DAX, Power Query, Power Automate, Power Apps, Microsoft Fabric",
            {"DAX", "Power Query", "Power Automate", "Power Apps", "Microsoft Fabric"},
        ),
        ("Herramientas Atlassian: Jira, Confluence, Xray", {"Jira", "Confluence", "Xray"}),
    ],
)
def test_tecnologias_relevantes_se_detectan(texto, esperadas):
    assert esperadas <= set(_skills(texto))


def test_todas_las_skills_del_catalogo_base_tienen_nombre_e_id_unicos():
    nombres = [s["nombre"].lower() for s in RECRUITING_SKILLS_SEED]
    ids = [s["id"] for s in RECRUITING_SKILLS_SEED]
    assert len(nombres) == len(set(nombres))
    assert len(ids) == len(set(ids))


# --- No se inventan conocimientos ------------------------------------------------------------------------------------


def test_una_skill_no_se_infiere_de_otra():
    assert _skills("Experiencia con Docker y Spring Boot") == ["Docker", "Spring Boot"]


def test_texto_vacio_o_sin_tecnologias():
    assert _skills("") == []
    assert _skills("Analista funcional con experiencia en gestión de proyectos y atención al cliente") == []


def test_resultado_ordenado_y_sin_duplicados():
    resultado = _skills("SQL, python, SQL, Python, sql")
    assert resultado == ["Python", "SQL"]


# --- Segunda iteración: evidencia textual estricta -------------------------------------------------------------------


def test_una_mencion_dentro_de_otro_producto_no_es_evidencia_de_la_tecnologia_corta():
    # Azure DevOps y Azure, Oracle PL/SQL y Oracle son productos distintos para el catálogo; SQL Server sí es SQL
    assert "Azure" not in _skills("Herramientas: Azure DevOps (TFS), Jira, Postman")
    assert {"Azure", "Azure DevOps"} <= set(_skills("Cloud: Azure, Azure DevOps, Docker"))
    assert "Oracle" not in _skills("Bases de datos: Oracle PL/SQL, MySQL")
    assert {"SQL", "SQL Server"} <= set(_skills("Bases de datos: SQL Server, MySQL"))
    assert {"SQL", "SQL Server"} <= set(_skills("Bases de datos: SQL, SQL Server, MySQL"))


@pytest.mark.parametrize(
    "texto",
    [
        "Herramientas técnicas: Python, Tableau, SQL, Power BI, R, Excel",
        "Lenguajes de Programación: Python (Pandas, NumPy), R\nETL: NiFi",
        "Jira\nSQL\nPython\nC\nR\nLooker Studio",
        "Python y R Studio\nSQL",
        "Minería de texto y webscrapping. Lenguaje R.\nPython",
        "Stack: R (análisis estadístico y modelado de datos), Python",
    ],
)
def test_r_se_detecta_como_elemento_de_una_lista_o_con_su_nombre_completo(texto):
    assert "R" in _skills(texto)


@pytest.mark.parametrize(
    "texto",
    [
        "P R O F I L E\nAnalista de datos con Python y SQL",
        "Analista de datos en Binamics S.R.L, Python, SQL",
        "JORGE R\nPRODUCT OWNER | PROJECT MANAGER\nPython, SQL",
        "ANALISTA QA SR. | ANALISTA FUNCIONAL\nPython, SQL",
        "I+D en R&D con Python y SQL",
        "Plan A, B, C o R según el caso. Python",
    ],
)
def test_r_no_se_confunde_con_una_letra_suelta(texto):
    assert "R" not in _skills(texto)


@pytest.mark.parametrize(
    "texto,skill",
    [
        ("Consultor de procesos en Synapse Business Analysis\nTrello, Jira", "Synapse"),
        ("Oracle Argentina S.A.\nSQL, Python", "Oracle"),
        ("Estrategia go to market\nPython, SQL", "Go"),
        ("Proyecto Spark de transformación digital\nPython, SQL", "Spark"),
    ],
)
def test_palabra_comun_dentro_de_una_frase_no_es_una_skill(texto, skill):
    assert skill not in _skills(texto)


@pytest.mark.parametrize(
    "texto,skill",
    [
        ("Gestión de bases de datos en SQL, Oracle y Postgres.", "Oracle"),
        ("Oracle 11g - curso\nSQL", "Oracle"),
        ("Herramientas: SQL, Excel avanzado, Power BI", "Excel"),
        ("Backend: Go, Postman, microservicios con Docker", "Go"),
        ("Frameworks: Node.js y Express\nReact", "Express"),
    ],
)
def test_termino_ambiguo_delimitado_en_una_lista_si_se_detecta(texto, skill):
    assert skill in _skills(texto)


def test_formacion_en_una_tecnologia_es_evidencia_de_la_skill():
    # Criterio: una mención en cursos o formación declara conocimiento; no se descarta por antigüedad ni por sección.
    assert ".NET" in _skills("CURSOS EXTRACURRICULARES\nVisual Studio .NET | IES Siglo XXI | 2002")


@pytest.mark.parametrize(
    "texto,esperadas",
    [
        ("Visualización: Matplotlib, Seaborn, Plotly, Streamlit", {"Matplotlib", "Seaborn", "Plotly", "Streamlit"}),
        ("Gestión: Trello, Redmine, TestRail, Zephyr", {"Trello", "Redmine", "TestRail", "Zephyr"}),
        ("Backend: REST APIs, Flask, Firebase, Maven", {"REST API", "Flask", "Firebase", "Maven"}),
        (
            "Frontend: Bootstrap, Tailwind CSS, Vite, Webpack, Sass",
            {"Bootstrap", "Tailwind CSS", "Vite", "Webpack", "Sass"},
        ),
        ("ETL: DataStage, Control-M, Informatica", {"DataStage", "Control-M", "Informatica"}),
    ],
)
def test_tecnologias_agregadas_en_la_segunda_iteracion(texto, esperadas):
    assert esperadas <= set(_skills(texto))


def test_lista_unida_por_guiones_detecta_cada_herramienta():
    assert {"Trello", "Jira", "Postman", "Git"} <= set(_skills("Herramientas: trello-jira-postman-git"))


def test_react_con_guion_no_agrega_javascript():
    resultado = _skills("Frontend: React-JS y Vue\nHTML, CSS")
    assert "React" in resultado and "JavaScript" not in resultado
