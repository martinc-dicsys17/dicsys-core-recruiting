"""
Detección del headline (puesto o perfil profesional) de un CV a partir de evidencia explícita del documento.

El headline es el "Puesto" de la ficha del candidato y debe coincidir con un nombre del catálogo
`recruiting_perfiles_puesto` (el combo "Perfil de puesto" filtra por coincidencia exacta). Nunca se deduce de la mera mención
de una tecnología. Orden de decisión (ver analizar_headline_cv):

1. Experiencia con fechas: decide el puesto MÁS RECIENTE (vigente primero). Si no tiene equivalente en el catálogo se asigna
   "Otro"; nunca se reemplaza por un puesto anterior.
   Excepción: el título profesional del encabezado (el perfil declarado) prima cuando es coherente con ese puesto más reciente
   (misma área: "Analytics Engineer" en el encabezado con "Ingeniero de Datos y BI" como cargo vigente). Si lo contradice
   (otra área), decide la experiencia.
2. Sin fechas: título del encabezado (primeras líneas, líneas que siguen al nombre y texto destacado de la primera página),
   luego perfil / resumen ("Soy Analista QA") y luego títulos de la experiencia por orden (el primero pesa más).
3. Funciones descritas (relevamiento de requerimientos, casos de prueba...), solo si no hay ningún título y con evidencia
   abundante y dominante de una única familia.

Un rol reconocido sin perfil propio en el catálogo (Product Owner, Data Scientist, Business Analytics Translator...) o un
título solo genérico se asigna a "Otro" y no interrumpe la búsqueda: si una etapa posterior da un perfil del catálogo, gana
ese. El resultado es None únicamente cuando el CV no tiene ningún título ni funciones reconocibles. Un título genérico
("Software Developer", "Programador") no define el perfil y deja decidir a la evidencia siguiente. Pasante / Practicante /
Estudiante / Intern es una condición laboral, no un perfil: solo cuenta según su fecha y con el rol de la misma línea.
"""

import re
import unicodedata
from typing import Dict, List, Optional, Tuple

# Nombres del catálogo recruiting_perfiles_puesto
DATA_ENGINEER = "Data Engineer"
DATA_ARCHITECT = "Data Architect"
CLOUD_DEVOPS = "Cloud Engineer / DevOps"
DOTNET = "Desarrollador .NET / C#"
FRONTEND = "Desarrollador Frontend"
BACKEND = "Desarrollador Backend"
FULL_STACK = "Desarrollador Full Stack"
QA = "QA Tester / Automation"
ANALISTA_FUNCIONAL = "Analista Funcional"
PROJECT_MANAGER = "Project Manager"
SCRUM_MASTER = "Project Manager / Scrum Master"
LIDER_TECNICO = "Líder Técnico"
RECRUITER = "Recruiter / HRBP"
DBA = "Administrador de Base de Datos (DBA)"
DEVOPS = "DevOps Engineer"
DATA_ANALYST = "Data Analyst / BI Analyst"
ANALYTICS_ENGINEER = "Analytics Engineer"
SOPORTE = "Soporte IT / Help Desk"
OTRO = "Otro"

# Roles explícitos sin equivalente en el catálogo: se reconocen para no asignar otro perfil por inferencia (resultado "Otro")
_OTRO = "__otro__"
# Título genérico de desarrollador: no define el perfil, deja decidir a la evidencia siguiente
_GENERICO = "__generico__"
# Condición laboral (pasante, practicante, estudiante): no es un perfil; solo cuenta como puesto según su fecha y contexto
_CONDICION = "__condicion__"
# Familias internas que no son por sí mismas un nombre del catálogo: se asignan a "Otro"
PERFIL_DE_FAMILIA: Dict[str, str] = {_OTRO: OTRO, _CONDICION: OTRO, _GENERICO: OTRO}

# Áreas de perfiles afines: un título del encabezado es coherente con el puesto más reciente si ambos son de la misma área
_AREAS: List[set] = [
    {DATA_ENGINEER, DATA_ARCHITECT, ANALYTICS_ENGINEER, DATA_ANALYST, DBA},
    {DOTNET, FRONTEND, BACKEND, FULL_STACK, LIDER_TECNICO},
    {CLOUD_DEVOPS, DEVOPS},
    {PROJECT_MANAGER, SCRUM_MASTER},
]

_L = r"(?<![a-z0-9])"
_R = r"(?![a-z0-9])"
_DEV = r"(?:desarrollador[a]?|developer|programador[a]?|engineer|ingenier[oa])"
_LENG_BACK = r"(?:java|python|php|node(?:\.?js)?|ruby|golang|spring(?:\s*boot)?|django|laravel|kotlin|scala)"

# (familia, expresiones) sobre texto en minúsculas y sin tildes
_ROLES: List[Tuple[str, List[str]]] = [
    (DATA_ARCHITECT, [r"data\s+architect", r"arquitect[oa]\s+de\s+datos"]),
    (
        DATA_ENGINEER,
        [r"data\s+engin+e+r(?:ing)?", r"ingenier[oa]\s+de\s+datos", r"big\s+data\s+(?:engineer|developer)"],
    ),
    (
        CLOUD_DEVOPS,
        [
            r"cloud\s+(?:engineer|architect|consultant)",
            r"consultor[a]?\s+cloud",
            r"ingenier[oa]\s+(?:de\s+)?cloud",
        ],
    ),
    (
        DEVOPS,
        [
            r"(?<!azure )devops(?:\s+engineer)?",
            r"ingenier[oa]\s+devops",
            r"sre",
            r"site\s+reliability",
            r"platform\s+engineer",
        ],
    ),
    (
        DOTNET,
        [
            _DEV + r"\s+(?:de\s+)?(?:\.net|dotnet|c#|c\s*sharp|asp\.?net)",
            r"(?:\.net|dotnet|c#)\s+(?:developer|engineer)",
        ],
    ),
    (FULL_STACK, [r"full[\s-]?stack"]),
    (
        FRONTEND,
        [
            r"front[\s-]?end\s+(?:web\s+)?(?:developer|engineer)",
            _DEV + r"\s+(?:web\s+)?front[\s-]?end",
            r"(?:desarrollador[a]?|developer)\s+(?:de\s+)?(?:react|angular|vue)(?:\.?js)?",
            r"(?:react|angular|vue)(?:\.?js)?\s+developer",
            r"ui\s+developer",
        ],
    ),
    (
        BACKEND,
        [
            r"back[\s-]?end\s+(?:web\s+)?(?:developer|engineer)",
            _DEV + r"\s+(?:web\s+)?back[\s-]?end",
            r"(?:desarrollador[a]?|programador[a]?|developer|engineer)\s+(?:de\s+)?" + _LENG_BACK,
            _LENG_BACK + r"\s+(?:developer|engineer)",
        ],
    ),
    (
        QA,
        [
            r"qa(?!\s*/\s*(?:prod|dev|uat))(?!\s+(?:environments?|env|ambiente|servers?))",
            r"tester[a]?",
            r"quality\s+assurance",
            r"sdet",
            r"(?:analista|ingenier[oa]|engineer|lead|lider|consultor[a]?)\s+(?:de\s+)?(?:calidad|testing|pruebas)",
            r"test\s+(?:engineer|analyst|lead)",
            r"analista\s+tester",
            r"(?:analista|ingenier[oa]|lider|lead|especialista|consultor[a]?)\s+(?:de\s+|en\s+)?qa",
        ],
    ),
    (
        ANALISTA_FUNCIONAL,
        [
            r"analista\s+(?:tecnic[oa]\s+)?funcional",
            r"functional\s+analyst",
            r"consultor[a]?\s+funcional",
            r"business\s+analyst",
            r"analista\s+(?:de\s+)?(?:negocios?|requerimientos)",
        ],
    ),
    (SCRUM_MASTER, [r"scrum\s+master", r"agile\s+coach"]),
    (
        PROJECT_MANAGER,
        [
            r"project\s+manager",
            r"(?:lider|jefe|gerente|coordinador[a]?)\s+de\s+proyectos?",
            r"pmo",
            r"delivery\s+manager",
        ],
    ),
    (
        LIDER_TECNICO,
        [
            r"tech(?:nical)?\s+lead",
            r"lider\s+tecnic[oa]",
            r"arquitect[oa]\s+(?:de\s+)?(?:software|soluciones|sistemas|aplicaciones)",
            r"(?:solutions?|software)\s+architect",
        ],
    ),
    (
        RECRUITER,
        [
            r"recruiter",
            r"reclutador[a]?",
            r"talent\s+acquisition",
            r"hrbp",
            r"(?:analista|generalista|especialista|gerente|consultor[a]?)\s+(?:de\s+)?(?:rr\.?\s?hh|recursos\s+humanos|seleccion|reclutamiento)",
        ],
    ),
    (DBA, [r"dba", r"administrador[a]?\s+de\s+bases?\s+de\s+datos", r"database\s+administrator"]),
    (ANALYTICS_ENGINEER, [r"analytics\s+engineer"]),
    (
        DATA_ANALYST,
        [
            r"data\s+analy(?:st|tics)",
            r"analista\s+(?:senior\s+|sr\.?\s+|ssr\s+|jr\.?\s+)?(?:de\s+)?datos",
            r"business\s+intelligence\s+(?:analyst|developer|consultant|engineer|specialist|analista)",
            r"(?:analista|consultor[a]?|desarrollador[a]?)\s+(?:de\s+)?business\s+intelligence",
            r"consultor[a]?\s+bi",
            r"bi\s+(?:analyst|developer|consultant|analista)",
            r"analista\s+bi",
            r"power\s+bi\s+developer",
        ],
    ),
    (
        SOPORTE,
        [
            r"(?:analista|tecnic[oa]|especialista|ingenier[oa]|agente)\s+(?:de\s+|en\s+)?soporte",
            r"help\s*desk",
            r"service\s+desk",
            r"it\s+support",
            r"mesa\s+de\s+ayuda",
            r"(?:application|technical|it)?\s*support\s+(?:analyst|engineer|specialist|technician)",
            r"application\s+(?:support\s+)?analyst",
        ],
    ),
    (
        _OTRO,
        [
            r"data\s+(?:scientist|specialist)",
            r"cientific[oa]\s+de\s+datos",
            r"machine\s+learning\s+engineer",
            r"product\s+(?:owner|manager)",
            r"analista\s+(?:programador|desarrollador)[a]?",
            r"(?:business\s+)?analytics\s+translator",
            r"analista\s+gis",
            r"(?:specialist|analyst|engineer|especialista|analista|ingenier[oa]|consultor[a]?)\s+(?:de\s+|en\s+)?(?:cyber\s*security|ciberseguridad|seguridad\s+informatica)",
            r"cyber\s*security\s+(?:specialist|analyst|engineer)",
            r"analista\s+de\s+procesos",
            r"analista\s+(?:de\s+)?inteligencia",
        ],
    ),
    (_CONDICION, [r"estudiante", r"pasante", r"practicante", r"intern(?:ship)?"]),
    (
        _GENERICO,
        [
            r"software\s+(?:developer|engineer)",
            r"desarrollador[a]?\s+(?:de\s+software|web)",
            r"programador[a]?",
            r"desarrollador[a]?",
            r"web\s+developer",
            r"developer",
            r"analista\s+(?:de\s+|en\s+)?(?:sistemas|informatica)",
        ],
    ),
]

_ROLES_RE: List[Tuple[str, "re.Pattern[str]"]] = [
    (fam, re.compile(_L + "(?:" + "|".join(pats) + ")" + _R)) for fam, pats in _ROLES
]

# Versión compacta (sin espacios) para encabezados con letras espaciadas ("A N A L I S T A F U N C I O N A L")
_COMPACTOS: List[Tuple[str, str]] = [
    ("analistafuncional", ANALISTA_FUNCIONAL),
    ("dataengineer", DATA_ENGINEER),
    ("qualityassurance", QA),
    ("fullstack", FULL_STACK),
    ("frontend", FRONTEND),
    ("backend", BACKEND),
    ("devops", DEVOPS),
    ("projectmanager", PROJECT_MANAGER),
    ("scrummaster", SCRUM_MASTER),
    ("tester", QA),
    ("dataanalyst", DATA_ANALYST),
    ("datascientist", _OTRO),
    ("dataspecialist", _OTRO),
    ("analistadedatos", DATA_ANALYST),
    ("analyticsengineer", ANALYTICS_ENGINEER),
    ("softwaredeveloper", _GENERICO),
    ("developer", _GENERICO),
    ("desarrollador", _GENERICO),
    ("programador", _GENERICO),
]

_TITULOS_SECCION = {
    "experiencia": "exp",
    "experiencia laboral": "exp",
    "experiencia profesional": "exp",
    "work experience": "exp",
    "experience": "exp",
    "professional experience": "exp",
    "antecedentes laborales": "exp",
    "trayectoria profesional": "exp",
    "trayectoria laboral": "exp",
    "experiencia laboral relevante": "exp",
    "historial laboral": "exp",
    "educacion": "otra",
    "formacion": "otra",
    "formacion academica": "otra",
    "education": "otra",
    "estudios": "otra",
    "habilidades": "otra",
    "skills": "otra",
    "habilidades tecnicas": "otra",
    "competencias": "otra",
    "idiomas": "otra",
    "languages": "otra",
    "cursos": "otra",
    "certificaciones": "otra",
    "certifications": "otra",
    "proyectos": "otra",
    "referencias": "otra",
    "contacto": "otra",
    "datos personales": "otra",
    "aptitudes principales": "otra",
    "top skills": "otra",
    "conocimientos": "otra",
    "herramientas": "otra",
    "tecnologias": "otra",
    "perfil": "res",
    "perfil profesional": "res",
    "resumen": "res",
    "resumen profesional": "res",
    "summary": "res",
    "professional summary": "res",
    "professional profile": "res",
    "profile": "res",
    "extracto": "res",
    "sobre mi": "res",
    "acerca de mi": "res",
    "about me": "res",
    "about": "res",
    "objetivo": "res",
    "objetivo profesional": "res",
    "presentacion": "res",
    "resumen curricular": "res",
    "perfil profesional / professional profile": "res",
}

_EDUCACION = re.compile(
    r"universidad|facultad|instituto|colegio|licenciatura|lic\.|tecnicatura|carrera|curso|certificacion|bootcamp|coderhouse|"
    r"egresad|diplomatura|posgrado|master|secundario|bachiller|escuela|capacitacion|formacion|cursad|certificad|\d\s*hs\b|horas de|\bhenry\b|\b(?:utn|frre|frc|uba|unc|unlp)\b"
)
_VINETA = re.compile(r"^\s*[•●▪■□◦·\-\*–—✓✔►>]\s+")
_CUE_DECLARATIVO = re.compile(
    r"(?:\bsoy\b|\bcomo\b|perfil\s+de|rol(?:es)?\s+de|puesto\s+de|\bprofesional\b|desempen\w+|experiencia\s+(?:como|en\s+el\s+rol)|"
    r"\bi\s+am\b|working\s+as|years\s+as|recibid[oa]\s+de|especializad[oa]\s+en|\d\s*\+?\s*anos?\s+(?:de\s+experiencia\s+)?(?:como|en))\s*(?:un[a]?\s+)?[\w\s,/&]{0,25}$"
)

# Funciones que describen un perfil (solo se usan si no hay ningún título): frases, no tecnologías
_FUNCIONES: Dict[str, List[str]] = {
    QA: [
        r"casos? de prueba",
        r"pruebas? (?:funcionales?|de regresion|automatizadas?|manuales?|exploratorias?)",
        r"testing (?:manual|funcional)",
        r"plan(?:es)? de pruebas?",
        r"reporte? (?:de )?(?:bugs|defectos)",
        r"(?:bugs|defectos|incidencias) (?:y|e) ",
        r"smoke test",
        r"test cases?",
        r"regression testing",
        r"ejecucion de pruebas",
    ],
    ANALISTA_FUNCIONAL: [
        r"relevamiento de (?:requerimientos|requisitos|procesos)",
        r"documentacion funcional",
        r"casos? de uso",
        r"analisis funcional",
        r"levantamiento de requerimientos",
        r"historias? de usuario",
        r"especificaciones? funcionales?",
        r"requerimientos funcionales",
    ],
    PROJECT_MANAGER: [
        r"gestion de proyectos",
        r"cronograma",
        r"planificacion del proyecto",
        r"seguimiento de proyectos",
        r"gestion de stakeholders",
        r"project management",
    ],
    RECRUITER: [
        r"reclutamiento",
        r"busqueda de talentos?",
        r"entrevistas? (?:a )?candidatos",
        r"sourcing",
        r"seleccion de personal",
        r"talent acquisition",
    ],
}


def _normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return t.lower().replace(" ", " ").replace("​", "")


def _es_letras_espaciadas(linea: str) -> bool:
    tokens = linea.split()
    if len(tokens) < 6:
        return False
    return sum(1 for t in tokens if len(t) == 1) / len(tokens) >= 0.6


def _roles_en_linea(linea: str) -> List[Tuple[int, str]]:
    """Todos los roles reconocidos en una línea normalizada, como (posición, familia), ordenados por posición."""
    hallazgos: List[Tuple[int, str]] = []
    if _es_letras_espaciadas(linea):
        compacto = re.sub(r"\s+", "", linea)
        for clave, fam in _COMPACTOS:
            for m in re.finditer(re.escape(clave), compacto):
                hallazgos.append((m.start(), fam))
    for fam, rx in _ROLES_RE:
        for m in rx.finditer(linea):
            hallazgos.append((m.start(), fam))
    hallazgos.sort(key=lambda h: h[0])
    # En la misma posición, el rol específico gana sobre el genérico ("desarrollador full stack" no es solo "desarrollador")
    vistos: Dict[int, str] = {}
    for pos, fam in hallazgos:
        previo = vistos.get(pos)
        if previo is None or (previo == _GENERICO and fam != _GENERICO):
            vistos[pos] = fam
    # Un genérico seguido, en la misma línea, de su especialidad ("desarrollador" + "full stack") queda cubierto por el específico
    resultado = sorted(vistos.items())
    return [(p, f) for p, f in resultado]


def _primera_familia(linea: str) -> Optional[Tuple[int, str]]:
    """Primer rol de la línea; entre varios genéricos y específicos, el específico más a la izquierda."""
    roles = _roles_en_linea(linea)
    if not roles:
        return None
    for pos, fam in roles:
        if fam not in (_GENERICO, _CONDICION):
            # un genérico inmediatamente anterior ("Desarrollador" + "Fullstack") lo absorbe el específico; una condición
            # ("Pasante en ...") cede ante el rol de la misma línea
            return pos, fam
    return next(((p, f) for p, f in roles if f == _CONDICION), roles[0])


# Palabras que, justo antes de un rol y en medio de una frase, indican una tarea o herramienta y no un cargo:
# "Manejo de backlog y validacion de tareas mediante QA", "Coordinacion con el equipo de QA"
_CONECTORES_TAREA = {
    "mediante",
    "con",
    "via",
    "utilizando",
    "usando",
    "para",
    "sobre",
    "por",
    "de",
    "del",
    "al",
    "a",
    "en",
    "y",
    "e",
    "entre",
    "el",
    "la",
    "los",
    "las",
}


def _mencion_en_frase(linea: str, pos_rol: int) -> bool:
    """El rol aparece dentro de una frase de tareas (al menos tres palabras antes y un conector inmediato): no es un cargo."""
    previas = re.findall(r"[a-z0-9]+", linea[:pos_rol])
    return len(previas) >= 3 and previas[-1] in _CONECTORES_TAREA


def _lineas(texto: str) -> List[str]:
    return [re.sub(r"\s+", " ", lin).strip() for lin in (texto or "").splitlines() if lin and lin.strip()]


def _es_formacion(linea: str, pos_rol: int) -> bool:
    """La línea es de formación académica o cursos si la mención educativa aparece antes del rol ("Curso de Desarrollador...")."""
    m = _EDUCACION.search(linea)
    return bool(m and m.start() <= pos_rol)


def _con_pares(lineas: List[str]) -> List[str]:
    """Cada línea seguida de su unión con la siguiente cuando ambas son cortas (títulos partidos en dos renglones)."""
    resultado: List[str] = []
    for i, lin in enumerate(lineas):
        resultado.append(lin)
        if i + 1 < len(lineas) and len(lin) <= 40 and len(lineas[i + 1]) <= 40:
            resultado.append(lin + " " + lineas[i + 1])
    return resultado


def _es_contacto(linea: str) -> bool:
    return bool("@" in linea or "http" in linea or "www." in linea or len(re.sub(r"\D", "", linea)) >= 9)


def _seccion(linea: str) -> Optional[str]:
    if _es_letras_espaciadas(linea):
        # Encabezados con letras espaciadas ("E X P E R I E N C I A  L A B O R A L"): se comparan sin espacios
        compacta = re.sub(r"[^a-z]", "", linea)
        for titulo, tipo in _TITULOS_SECCION.items():
            if re.sub(r"[^a-z]", "", titulo) == compacta:
                return tipo
        return None
    limpia = re.sub(r"[^a-z/ ]", " ", linea)
    limpia = re.sub(r"\s+", " ", limpia).strip()
    if len(limpia) > 45:
        return None
    return _TITULOS_SECCION.get(limpia)


def _lineas_tras_nombre(texto: str, encabezado_visual: str, cantidad: int = 2) -> List[str]:
    """
    Líneas del texto que siguen al nombre destacado de la primera página (primera línea del encabezado visual). En los CV a
    dos columnas el bloque "nombre + título profesional" puede quedar lejos del comienzo del texto lineal.
    """
    visuales = _lineas(encabezado_visual)
    if not visuales:
        return []
    nombre = re.sub(r"[^a-z]", "", _normalizar(visuales[0]))
    lineas = _lineas(texto)
    for i, lin in enumerate(lineas):
        if nombre and re.sub(r"[^a-z]", "", _normalizar(lin)) == nombre:
            siguientes = []
            for s in lineas[i + 1 : i + 1 + cantidad]:
                if _seccion(_normalizar(s)):
                    break
                siguientes.append(s)
            return siguientes
    return []


def _evidencia_encabezado(texto: str, encabezado_visual: str) -> Optional[str]:
    # El texto destacado de la primera página y las líneas que siguen al nombre no se cortan por secciones; el texto lineal sí
    # (termina donde empieza la experiencia)
    lineas = (
        [(lin, False) for lin in _con_pares(_lineas(encabezado_visual))]
        + [(lin, False) for lin in _lineas_tras_nombre(texto, encabezado_visual)]
        + [(lin, True) for lin in _con_pares(_lineas(texto)[:40])]
    )
    for bruta, lineal in lineas:
        linea = _normalizar(bruta)
        if lineal and _seccion(linea) in ("exp", "res"):
            break
        if len(linea) > 140 or _es_contacto(linea) or _VINETA.match(bruta):
            continue
        roles = _roles_en_linea(linea)
        if not roles or _es_formacion(linea, roles[0][0]):
            continue
        primero = _primera_familia(linea)
        if primero and primero[1] == _CONDICION:
            # "Estudiante de ...", "Pasante": una condición no es el perfil; se sigue buscando un título
            continue
        if primero and primero[1] != _GENERICO:
            return primero[1]
        # El primer título declarado es genérico ("Senior Software Developer"): no se buscan roles sueltos en el resto del
        # encabezado (listas de habilidades, categorías) y decide la evidencia siguiente
        return _GENERICO
    return None


def _evidencia_resumen(texto: str) -> Optional[str]:
    lineas = _lineas(texto)
    for i, bruta in enumerate(lineas):
        linea = _normalizar(bruta)
        if _seccion(linea) != "res":
            continue
        bloque = " ".join(_normalizar(lin) for lin in lineas[i + 1 : i + 13])
        # el bloque termina donde empieza otra sección
        for j in range(i + 1, min(i + 13, len(lineas))):
            if _seccion(_normalizar(lineas[j])) in ("exp", "otra"):
                bloque = " ".join(_normalizar(lin) for lin in lineas[i + 1 : j])
                break
        for pos, fam in _roles_en_linea(bloque[:1400]):
            if fam in (_GENERICO, _CONDICION):
                continue
            if pos < 25 or _CUE_DECLARATIVO.search(bloque[max(0, pos - 45) : pos]):
                return fam
    # Sin encabezado de sección: frases declarativas al comienzo del documento ("Soy Analista Funcional...")
    inicio = _normalizar(" ".join(lineas[:25]))[:1500]
    for m in re.finditer(
        r"\b(?:soy|me desempeno como|trabajo como|actualmente trabajo como|profesional con \w+ anos de experiencia como)\s+(?:un[a]?\s+)?",
        inicio,
    ):
        roles = _roles_en_linea(inicio[m.end() : m.end() + 60])
        for pos, fam in roles:
            if pos <= 3 and fam not in (_GENERICO, _CONDICION):
                return fam
    return None


def _evidencia_experiencia(texto: str) -> Optional[str]:
    lineas = _lineas(texto)
    inicio = next((i for i, lin in enumerate(lineas) if _seccion(_normalizar(lin)) == "exp"), None)
    zona = lineas[inicio + 1 :] if inicio is not None else lineas[8:]
    titulos: List[str] = []
    for bruta in zona:
        linea = _normalizar(bruta)
        sec = _seccion(linea)
        if sec == "otra" and inicio is not None:
            break
        if sec or len(linea) > 150 or _es_contacto(linea) or _VINETA.match(bruta):
            continue
        primero = _primera_familia(linea)
        if (
            primero
            and primero[0] <= 60
            and primero[1] not in (_GENERICO, _CONDICION)
            and not _es_formacion(linea, primero[0])
            and not _mencion_en_frase(linea, primero[0])
        ):
            titulos.append(primero[1])
    # Sin una sección de experiencia identificable, una mención aislada es evidencia débil: se exigen al menos dos títulos
    if not titulos or (inicio is None and len(titulos) < 2):
        return None
    pesos: Dict[str, int] = {}
    for orden, fam in enumerate(titulos[:5]):
        pesos[fam] = pesos.get(fam, 0) + max(1, 3 - orden)
    mejor = max(pesos.values())
    return next(f for f in titulos if pesos[f] == mejor)


def _evidencia_funciones(texto: str) -> Optional[str]:
    t = _normalizar(texto)
    puntajes: Dict[str, int] = {}
    for fam, frases in _FUNCIONES.items():
        puntajes[fam] = sum(1 for f in frases if re.search(f, t))
    orden = sorted(puntajes.items(), key=lambda kv: kv[1], reverse=True)
    mejor, segundo = orden[0], orden[1]
    if mejor[1] >= 4 and mejor[1] >= 2 * max(segundo[1], 1):
        return mejor[0]
    return None


# Período de un puesto: "Junio 2022 - Actualidad", "May. 2024 - Jun, 2025", "(2025 - Actualidad)", "03/2019 - 12/2022"
_MESES = {
    "ene": 1,
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "abr": 4,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "aug": 8,
    "sep": 9,
    "set": 9,
    "oct": 10,
    "nov": 11,
    "dic": 12,
    "dec": 12,
}
_PUNTO_FECHA = r"(?:(?:([a-z]{3,10})\.?,?\s*(?:de\s+)?)|(?:(\d{1,2})\s*/\s*))?((?:19|20)\d{2})"
_RANGO_FECHAS = re.compile(
    _L
    + _PUNTO_FECHA
    + r"\s*(?:-|–|—|\ba\b|\bal\b|hasta)\s*(?:"
    + _PUNTO_FECHA
    + r"|(actualidad|actual|presente|present|hoy|current|now|la\s+fecha))"
    + _R
)
# Distancia máxima (en líneas) entre un título y el período que se le asocia cuando no están en la misma línea
_LINEAS_HASTA_FECHA = 8


def _mes(nombre: Optional[str], numero: Optional[str], defecto: int) -> int:
    if numero and 1 <= int(numero) <= 12:
        return int(numero)
    return _MESES.get((nombre or "")[:3], defecto)


def _periodo(linea: str) -> Optional[Tuple[Tuple[int, int], Tuple[int, int]]]:
    """(fin, inicio) como (año, mes) del primer rango de fechas de la línea; un puesto vigente termina en (9999, 12)."""
    m = _RANGO_FECHAS.search(linea)
    if not m:
        return None
    inicio = (int(m.group(3)), _mes(m.group(1), m.group(2), 1))
    fin = (9999, 12) if m.group(7) else (int(m.group(6)), _mes(m.group(4), m.group(5), 12))
    return fin, inicio


def _titulos_con_fecha(texto: str) -> List[Tuple[Tuple[Tuple[int, int], Tuple[int, int]], str, str]]:
    """
    Títulos de la experiencia laboral con su período: [((fin, inicio), familia, línea)]. El período se toma de la misma
    línea; si no, de la línea siguiente o la anterior (según el diseño del CV: fecha debajo o encima del cargo), o de dos
    líneas antes si en medio solo está la empresa (fecha encima de la empresa y el cargo); si no, del
    primer período libre antes del próximo título. Cada período se asocia a un único título.
    """
    lineas = _lineas(texto)
    norm = [_normalizar(lin) for lin in lineas]
    inicio = next((i for i, lin in enumerate(norm) if _seccion(lin) == "exp"), None)
    desde = inicio + 1 if inicio is not None else 8
    hasta = len(norm)
    for i in range(desde, len(norm)):
        if inicio is not None and _seccion(norm[i]) == "otra":
            hasta = i
            break
    # Períodos de la zona; un rango partido en dos renglones ("Dic 2021 -" / "Mar 2026") se une
    periodos: Dict[int, Tuple[Tuple[int, int], Tuple[int, int]]] = {}
    for i in range(desde, hasta):
        linea = norm[i]
        if re.search(r"[-–—]\s*$", linea) and i + 1 < hasta:
            linea = f"{linea} {norm[i + 1]}"
        p = _periodo(linea)
        if p:
            periodos[i] = p
    titulos: List[Tuple[int, str]] = []
    for i in range(desde, hasta):
        linea = norm[i]
        if (
            _seccion(linea)
            or len(linea) > 150
            or _VINETA.match(lineas[i])
            or _es_contacto(_RANGO_FECHAS.sub(" ", linea))
        ):
            continue
        primero = _primera_familia(linea)
        if (
            primero
            and primero[0] <= 60
            and not _es_formacion(linea, primero[0])
            and not _mencion_en_frase(linea, primero[0])
        ):
            titulos.append((i, primero[1]))
    indices_titulo = {i for i, _ in titulos}
    usados = set()
    resultado = []
    for k, (i, fam) in enumerate(titulos):
        limite = min(titulos[k + 1][0] if k + 1 < len(titulos) else hasta, i + _LINEAS_HASTA_FECHA + 1)
        opciones = [i, i + 1, i - 1]
        # Período encima de la empresa ("Jun 2025 - Actualidad" / "Acid Labs, Chile" / "Analytics Engineer"), o el
        # rango partido en dos renglones del margen ("Mar 2026 -" / "Presente" / cargo)
        if (
            i - 2 >= desde
            and i - 1 not in indices_titulo
            and len(norm[i - 1]) <= 60
            and not _VINETA.match(lineas[i - 1])
        ):
            opciones.append(i - 2)
        opciones += list(range(i + 2, limite))
        elegido = next(
            (
                j
                for j in opciones
                if j in periodos
                and j not in usados
                and (j == i or j not in indices_titulo)
                and (j != i - 1 or j >= desde)
            ),
            None,
        )
        if elegido is None:
            continue
        usados.add(elegido)
        if fam == _CONDICION:
            # "Pasante en Desarrollo Backend": la condición cede ante el rol que nombra la misma línea
            otro = next((f for _, f in _roles_en_linea(norm[i]) if f not in (_CONDICION, _GENERICO)), None)
            fam = otro or fam
        resultado.append((periodos[elegido], fam, lineas[i]))
    return resultado


def _evidencia_experiencia_fechada(texto: str) -> Optional[str]:
    """
    Familia del puesto MÁS RECIENTE según las fechas de la experiencia (vigente primero; luego el que terminó o empezó
    después). Un título genérico ("Desarrollador de Software") no define el perfil y se pasa al siguiente. Si el puesto más
    reciente no tiene equivalente en el catálogo no se reemplaza por uno anterior: se devuelve su familia (-> "Otro").
    """
    fechados = [t for t in _titulos_con_fecha(texto) if t[1] != _GENERICO]
    if not fechados:
        return None
    return max(fechados, key=lambda t: t[0])[1]


def puesto_vigente_es_condicion(texto: str) -> Optional[bool]:
    """
    Si el CV tiene experiencia con fechas: True cuando el puesto más reciente es una condición (pasante, practicante,
    estudiante, intern, trainee) y False cuando es un puesto profesional. None si no hay puestos fechados.
    Lo usa el seniority: una pasantía anterior no hace Trainee a quien hoy tiene un puesto profesional.
    """
    fechados = _titulos_con_fecha(texto)
    if not fechados:
        return None
    _, _, linea = max(fechados, key=lambda t: t[0])
    return bool(re.search(r"\b(?:trainee|pasante|practicante|estudiante|intern(?:ship)?)\b", _normalizar(linea)))


def _perfil(fam: str) -> str:
    """Nombre del catálogo de una familia: los roles sin perfil propio en el catálogo se asignan a "Otro"."""
    return PERFIL_DE_FAMILIA.get(fam, fam)


def _coherentes(declarado: str, vigente: str) -> bool:
    """El perfil declarado en el encabezado y el puesto más reciente son de la misma área (no se contradicen)."""
    return any(declarado in area and vigente in area for area in _AREAS)


def analizar_headline_cv(texto: str, encabezado_visual: str = "") -> Tuple[Optional[str], str]:
    """
    Devuelve (headline, fuente). La fuente es 'encabezado_respaldado', 'experiencia_fechada', 'encabezado', 'resumen',
    'experiencia', 'funciones', 'sin_equivalente' o 'sin_evidencia'.

    1. Con fechas en la experiencia decide el puesto más reciente (nunca uno anterior), salvo que el título del encabezado
       sea un perfil distinto pero coherente con él (misma área): entonces prima el perfil declarado. Un encabezado de otra
       área no se toma como vigente: decide la experiencia.
    2. Sin fechas: encabezado, perfil/resumen y experiencia por orden. Un rol sin equivalente en el catálogo no interrumpe
       la búsqueda: si ninguna etapa da un perfil del catálogo, el resultado es "Otro".
    3. Funciones descritas (solo si no hay ningún título). Sin ningún título ni función: None.
    """
    fam = _evidencia_experiencia_fechada(texto)
    if fam is not None:
        declarado = _evidencia_encabezado(texto, encabezado_visual)
        if declarado not in (None, _GENERICO, fam) and _coherentes(declarado, fam):
            return _perfil(declarado), "encabezado_respaldado"
        return _perfil(fam), "experiencia_fechada"
    sin_equivalente = False
    etapas = (
        ("encabezado", lambda: _evidencia_encabezado(texto, encabezado_visual)),
        ("resumen", lambda: _evidencia_resumen(texto)),
        ("experiencia", lambda: _evidencia_experiencia(texto)),
    )
    for fuente, buscar in etapas:
        fam = buscar()
        if fam is None:
            continue
        if fam in PERFIL_DE_FAMILIA:
            sin_equivalente = True  # se sigue buscando un perfil del catálogo en las etapas siguientes
            continue
        return fam, fuente
    if sin_equivalente:
        return OTRO, "sin_equivalente"
    fam = _evidencia_funciones(texto)
    if fam is not None:
        return fam, "funciones"
    return None, "sin_evidencia"


def detectar_headline_cv(texto: str, encabezado_visual: str = "") -> Optional[str]:
    """Headline del catálogo de perfiles de puesto respaldado por el CV, o None si no hay evidencia suficiente."""
    return analizar_headline_cv(texto, encabezado_visual)[0]
