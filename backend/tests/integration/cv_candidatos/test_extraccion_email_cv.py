"""Extracción del email del CV: reconstruye direcciones partidas por la extracción del PDF sin inventar caracteres.

Los datos son ficticios; reproducen la forma de los PDFs reales donde el email llega cortado en dos líneas.
"""

import io

import fitz
import pytest

from backend.modules.recruiting.services import CandidatoService
from backend.tests.helpers.auth import auth_headers


def _email(texto: str) -> str:
    return CandidatoService.parsear_cv_texto(texto, "cv.pdf")["email"]


@pytest.mark.parametrize(
    "texto,esperado",
    [
        # Partido antes del "@"
        ("Lucía Pérez\nAnalista\nlucia.perez4\n@gmail.com\nSoy un profesional", "lucia.perez4@gmail.com"),
        ("Contacto\nlucia4\n  @hotmail.com.ar\n", "lucia4@hotmail.com.ar"),
        # Partido después del "@"
        ("lucia.perez@\ngmail.com\nTeléfono 1122334455", "lucia.perez@gmail.com"),
        # Partido dentro del dominio
        ("pablosebastian@gmai\nl.com\nwww.linkedin.com/in/pablo", "pablosebastian@gmail.com"),
        ("juan@empresa.c\nom", "juan@empresa.com"),
        ("juan@gmail\n.com", "juan@gmail.com"),
        # Normales: no se tocan
        ("Email: lucia.perez@gmail.com\nTeléfono: 1122334455", "lucia.perez@gmail.com"),
        ("lucia@gmail.com\nanalista", "lucia@gmail.com"),
        ("lucia@gmail.com\n1122334455", "lucia@gmail.com"),
        ("Mail: Lucia.Perez@Example.com.", "lucia.perez@example.com"),
    ],
    ids=[
        "antes_arroba",
        "antes_arroba_con_sangria",
        "despues_arroba",
        "dominio_cortado",
        "tld_cortado",
        "punto_en_la_linea_siguiente",
        "normal_con_etiqueta",
        "texto_cercano_minuscula",
        "telefono_cercano",
        "mayusculas",
    ],
)
def test_extrae_el_email_completo(texto, esperado):
    assert _email(texto) == esperado


@pytest.mark.parametrize(
    "texto",
    [
        "Lucía Pérez\nAnalista\nlucia4\nTeléfono 1122334455",  # sin arroba
        "Mail\n@gmail.com\nLucía",  # la etiqueta no forma parte de la dirección
        "Email\n@",  # arroba sin dominio
        "lucia@gmail\nTeléfono: 1122334455",  # dominio sin TLD: no se completa con texto ajeno
        "Soy dev\n@ Google\nBuenos Aires",  # "@" suelto
        "",
    ],
    ids=["sin_arroba", "etiqueta", "arroba_sin_dominio", "dominio_sin_tld", "arroba_suelto", "vacio"],
)
def test_no_inventa_emails_cuando_no_hay_uno_valido(texto):
    assert _email(texto) == ""


def test_unir_email_partido_no_modifica_texto_sin_emails_partidos():
    texto = "Lucía Pérez\nAnalista QA\nlucia@gmail.com\nBuenos Aires\nPython | SQL"
    assert CandidatoService._unir_email_partido(texto) == texto


def test_email_partido_valida_con_la_regla_de_emailstr():
    texto = "oscaraguirre4\n@gmail.com"
    assert CandidatoService._email_valido_cv(_email(texto)) == "oscaraguirre4@gmail.com"


def _pdf(*lineas: str) -> bytes:
    doc = fitz.open()
    pagina = doc.new_page()
    for i, linea in enumerate(lineas):
        pagina.insert_text((72, 72 + i * 18), linea)
    contenido = doc.tobytes()
    doc.close()
    return contenido


@pytest.mark.integration
def test_carga_de_cv_con_email_partido_registra_el_candidato(client, db_session, data_factory, fake_storage):  # noqa: F811
    empresa = data_factory.empresa()
    usuario = data_factory.usuario(rol="admin")
    data_factory.asignar_empresa(usuario, empresa)
    db_session.flush()
    headers = auth_headers(usuario, empresa)
    contenido = _pdf("Oscar Aguirre", "Analista de Datos", "oscaraguirre4", "@gmail.com", "Buenos Aires")

    r = client.post(
        "/api/v1/recruiting/candidatos/cargar-cv",
        headers=headers,
        files={"archivo": ("Oscar Aguirre.pdf", io.BytesIO(contenido), "application/pdf")},
    )

    assert r.status_code == 201, r.text
    assert r.json()["candidato"]["email"] == "oscaraguirre4@gmail.com"


def test_dominio_incompleto_no_se_completa_con_texto_ajeno():
    texto = "lucia@empresa.c\nAnalista Senior"
    assert CandidatoService._unir_email_partido(texto) == texto


def test_si_el_email_reconstruido_no_tiene_formato_valido_se_usa_el_original():
    # Unido daria "ana..diaz@gmail.com" (formato invalido); el email original del CV si es valido
    assert _email("ana.\n@gmail.com\nana@gmail.com") == "ana@gmail.com"


@pytest.mark.parametrize(
    "texto",
    [
        "Contacto: Oscar\n@gmail.com",  # la línea anterior tiene texto adicional
        "Email: oscar\n@gmail.com",  # etiqueta + palabra en la misma línea
        "Oscar Aguirre\n@gmail.com",  # un nombre completo no es parte local
        "Oscar\n@gmail.com",  # una palabra con aspecto de nombre propio
        "Teléfono 1122334455 oscar\n@gmail.com",  # número y texto antes de la palabra
        "Analista de datos\n@gmail.com",
    ],
    ids=["contacto_y_nombre", "etiqueta_y_palabra", "nombre_completo", "nombre_solo", "telefono_y_palabra", "cargo"],
)
def test_no_une_texto_de_otra_linea_con_un_fragmento_arroba(texto):
    assert _email(texto) == ""
    assert "Oscar@" not in CandidatoService._unir_email_partido(texto)


@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("Contacto\noscaraguirre4\n@gmail.com", "oscaraguirre4@gmail.com"),  # el fragmento solo en su línea
        ("Contacto\n  oscar_aguirre\n  @hotmail.com\nBuenos Aires", "oscar_aguirre@hotmail.com"),
        ("oscar.aguirre\n@gmail.com", "oscar.aguirre@gmail.com"),
        ("Email: oscaraguirre4@\ngmail.com", "oscaraguirre4@gmail.com"),  # "@" pegado a su parte local
    ],
    ids=["fragmento_solo", "con_sangria", "con_punto", "arroba_al_final"],
)
def test_sigue_reconstruyendo_cortes_claros(texto, esperado):
    assert _email(texto) == esperado


@pytest.mark.parametrize(
    "texto",
    [
        "Email: oscar@\nTeléfono 1122334455",  # lo que sigue al "@" no es un dominio
        "oscar@\nAnalista de datos",
        "usuario@@gmail.com",  # mal formado
        "oscar..aguirre@gmail.com",  # mal formado
        ".oscar@gmail.com",  # mal formado
    ],
    ids=["arroba_y_telefono", "arroba_y_cargo", "doble_arroba", "puntos_dobles", "punto_inicial"],
)
def test_emails_mal_formados_o_fragmentos_ajenos_se_rechazan(texto):
    assert CandidatoService._email_valido_cv(_email(texto)) is None


@pytest.mark.parametrize(
    "texto",
    [
        "ana@gmail\nwww.linkedin.com/in/ana",  # una URL no completa el dominio
        "ana@gmail\nlinkedin.com/in/ana",  # la linea siguiente trae mas que un fragmento de dominio
        "ana@gmail\nhttps://linkedin.com/in/ana",
        "ana@gmail\nlinkedin.com Buenos Aires",  # texto adicional en la linea siguiente
        "ana@gmail\nwww.miweb.com",
    ],
    ids=["www_linkedin", "linkedin_con_ruta", "https", "texto_adicional", "www_sitio"],
)
def test_un_dominio_incompleto_no_se_completa_con_una_url(texto):
    assert "gmailwww" not in CandidatoService._unir_email_partido(texto)
    assert "gmaillinkedin" not in CandidatoService._unir_email_partido(texto)
    assert CandidatoService._unir_email_partido(texto) == texto
    assert _email(texto) == ""


@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("oscaraguirre4\n@gmail.com", "oscaraguirre4@gmail.com"),
        ("pablo@gmai\nl.com\nwww.linkedin.com/in/pablo", "pablo@gmail.com"),  # el fragmento solo en su linea
        ("pablo@gmai\nl.com", "pablo@gmail.com"),
        ("Email: ana@gmail.com\nwww.linkedin.com/in/ana", "ana@gmail.com"),  # normal con URL cercana
    ],
    ids=["antes_arroba", "dominio_partido_con_url_despues", "dominio_partido", "normal_con_url"],
)
def test_la_proteccion_contra_urls_no_rompe_los_emails_partidos_ni_los_normales(texto, esperado):
    assert _email(texto) == esperado
