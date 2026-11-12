"""Carga de CVs: un candidato solo se registra con el email real del CV; nunca se inventa uno."""

import io
import logging
import zipfile

import fitz
import pytest

from backend.modules.recruiting.models import Candidato
from backend.modules.recruiting.services import CandidatoService
from backend.tests.helpers.auth import auth_headers

URL_INDIVIDUAL = "/api/v1/recruiting/candidatos/cargar-cv"
URL_MASIVO = "/api/v1/recruiting/candidatos/cargar-cv-masivo"


def _pdf(*lineas: str) -> bytes:
    doc = fitz.open()
    pagina = doc.new_page()
    for i, linea in enumerate(lineas):
        pagina.insert_text((72, 72 + i * 18), linea)
    contenido = doc.tobytes()
    doc.close()
    return contenido


CV_VALIDO = _pdf("Laura Gomez", "Analista QA", "laura.gomez@example.com", "Cordoba, Argentina")
CV_SIN_EMAIL = _pdf("Nicolas Marcelo Tosi", "Desarrollador .NET en Accenture Argentina", "Buenos Aires, Argentina")
CV_EMAIL_INVALIDO = _pdf("Pedro Ruiz", "Desarrollador Backend", "pedro..ruiz@example.com")
CV_EMAIL_NO_DETECTABLE = _pdf("Ana Diaz", "Email: ana.diaz@gmail", "Desarrolladora Frontend")


@pytest.fixture
def escenario(data_factory, db_session, fake_storage):  # noqa: F811
    empresa = data_factory.empresa()
    usuario = data_factory.usuario(rol="admin")
    data_factory.asignar_empresa(usuario, empresa)
    db_session.flush()
    return auth_headers(usuario, empresa), empresa


def _subir(client, headers, contenido, nombre="cv.pdf"):  # noqa: F811
    return client.post(URL_INDIVIDUAL, headers=headers, files={"archivo": (nombre, contenido, "application/pdf")})


def _candidatos(db_session, empresa):  # noqa: F811
    return db_session.query(Candidato).filter(Candidato.empresa_id == empresa.id).all()


def _sin_emails_ficticios(db_session):  # noqa: F811
    return db_session.query(Candidato).filter(Candidato.email.ilike("%sindato.com")).count() == 0


@pytest.mark.integration
def test_cv_con_email_valido_registra_el_email_real(client, db_session, escenario, fake_storage):  # noqa: F811
    headers, empresa = escenario
    r = _subir(client, headers, CV_VALIDO, "Laura Gomez.pdf")

    assert r.status_code == 201, r.text
    assert r.json()["ok"] is True
    assert r.json()["candidato"]["email"] == "laura.gomez@example.com"
    candidatos = _candidatos(db_session, empresa)
    assert [c.email for c in candidatos] == ["laura.gomez@example.com"]
    assert candidatos[0].cv_url in fake_storage.files


@pytest.mark.integration
@pytest.mark.parametrize(
    "contenido,nombre",
    [
        (CV_SIN_EMAIL, "Nicolas Tosi .pdf"),
        (CV_EMAIL_INVALIDO, "Pedro Ruiz.pdf"),
        (CV_EMAIL_NO_DETECTABLE, "Ana Diaz.pdf"),
    ],
    ids=["sin_email", "email_invalido", "email_no_detectado"],
)
def test_cv_sin_email_valido_se_rechaza_sin_persistir(client, db_session, escenario, fake_storage, contenido, nombre):  # noqa: F811
    headers, empresa = escenario
    r = _subir(client, headers, contenido, nombre)

    assert r.status_code == 422
    assert r.json() == {"detail": CandidatoService.MENSAJE_CV_SIN_EMAIL}
    assert _candidatos(db_session, empresa) == []
    assert fake_storage.files == {}
    assert _sin_emails_ficticios(db_session)


@pytest.mark.integration
def test_rechazo_no_bloquea_la_carga_del_siguiente_cv(client, db_session, escenario):  # noqa: F811
    headers, empresa = escenario
    assert _subir(client, headers, CV_SIN_EMAIL).status_code == 422
    assert _subir(client, headers, CV_SIN_EMAIL).status_code == 422

    r = _subir(client, headers, CV_VALIDO)
    assert r.status_code == 201, r.text
    assert [c.email for c in _candidatos(db_session, empresa)] == ["laura.gomez@example.com"]
    assert _sin_emails_ficticios(db_session)


@pytest.mark.integration
def test_email_real_duplicado_sigue_rechazandose_con_409(client, db_session, escenario):  # noqa: F811
    headers, empresa = escenario
    assert _subir(client, headers, CV_VALIDO).status_code == 201

    r = _subir(client, headers, CV_VALIDO)
    assert r.status_code == 409
    assert "laura.gomez@example.com" in r.json()["detail"]
    assert len(_candidatos(db_session, empresa)) == 1


@pytest.mark.integration
def test_rechazo_registra_diagnostico_cuando_el_cv_parece_tener_email(client, escenario, caplog):  # noqa: F811
    headers, _ = escenario
    with caplog.at_level(logging.WARNING, logger="backend.modules.recruiting.services"):
        assert _subir(client, headers, CV_EMAIL_NO_DETECTABLE, "Ana Diaz.pdf").status_code == 422
    assert "Ana Diaz.pdf" in caplog.text
    assert "parece contener un email" in caplog.text


@pytest.mark.integration
def test_carga_masiva_informa_cv_sin_email_sin_crear_candidato_ficticio(client, db_session, escenario):  # noqa: F811
    headers, empresa = escenario
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as zf:
        zf.writestr("Laura Gomez.pdf", CV_VALIDO)
        zf.writestr("Nicolas Tosi.pdf", CV_SIN_EMAIL)

    r = client.post(
        URL_MASIVO, headers=headers, files={"archivo": ("cvs.zip", zip_buffer.getvalue(), "application/zip")}
    )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["procesados_exitosamente"] == 1
    assert body["fallidos"] == [{"archivo": "Nicolas Tosi.pdf", "motivo": CandidatoService.MENSAJE_CV_SIN_EMAIL}]
    assert [c.email for c in _candidatos(db_session, empresa)] == ["laura.gomez@example.com"]
    assert _sin_emails_ficticios(db_session)


@pytest.mark.parametrize(
    "email,esperado",
    [
        ("Laura.Gomez@Example.com ", "laura.gomez@example.com"),
        ("", None),
        (None, None),
        ("pedro..ruiz@example.com", None),
        ("ana.diaz@gmail", None),
        ("sin arroba", None),
    ],
)
def test_email_valido_cv_aplica_la_regla_de_emailstr(email, esperado):
    assert CandidatoService._email_valido_cv(email) == esperado


def _cv_de_bytes(total: int) -> bytes:
    base = CV_VALIDO
    return base + b"\n%" + b"0" * (total - len(base) - 2)


@pytest.mark.integration
def test_carga_individual_acepta_cv_de_hasta_5_mb(client, escenario):  # noqa: F811
    headers, _ = escenario
    r = _subir(client, headers, _cv_de_bytes(5 * 1024 * 1024), "Laura Gomez.pdf")
    assert r.status_code == 201, r.text


@pytest.mark.integration
def test_carga_individual_rechaza_cv_mayor_a_5_mb(client, db_session, escenario):  # noqa: F811
    headers, empresa = escenario
    r = _subir(client, headers, _cv_de_bytes(5 * 1024 * 1024 + 1), "Laura Gomez.pdf")
    assert r.status_code == 400
    assert "5 MB" in r.text
    assert _candidatos(db_session, empresa) == []
