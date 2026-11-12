"""Límite de intentos del ingreso (F07-P07): login, 2FA, recuperación de contraseña y magic link."""

import pyotp
import pytest
from fastapi.testclient import TestClient

from backend.core import limites
from backend.core.config import settings

pytestmark = [pytest.mark.integration, pytest.mark.deploy_gate]

LOGIN = "/api/v1/auth/login"
PASSWORD = "clave-de-prueba-larga"


@pytest.fixture
def topes(monkeypatch):
    """Topes chicos para no repetir decenas de pedidos."""
    for nombre, valor in {
        "limite_login_por_cuenta": 3,
        "limite_2fa_por_cuenta": 2,
        "limite_correos_por_cuenta": 2,
        "limite_intentos_por_ip": 6,
    }.items():
        monkeypatch.setattr(settings, nombre, valor)


@pytest.fixture
def persona(data_factory):
    usuario = data_factory.usuario(password=PASSWORD)
    data_factory.asignar_empresa(usuario, data_factory.empresa())
    return usuario


def _desde(app, ip: str) -> TestClient:
    return TestClient(app, client=(ip, 50000))


def _login(client, email, password="incorrecta", **headers):
    return client.post(LOGIN, json={"email": email, "password": password}, headers=headers)


def _es_429(r):
    assert r.status_code == 429, r.text
    assert r.json()["detail"].startswith("Demasiados intentos. Probá de nuevo en ")
    assert 0 < int(r.headers["retry-after"]) <= limites.VENTANA


def test_el_login_frena_a_la_cuenta_despues_de_sus_fallos_aunque_la_clave_sea_buena(
    client, persona, data_factory, topes
):
    for _ in range(3):
        assert _login(client, persona.email).status_code == 401

    _es_429(_login(client, persona.email, PASSWORD))
    otra = data_factory.usuario(password=PASSWORD)
    data_factory.asignar_empresa(otra, data_factory.empresa())
    assert _login(client, otra.email, PASSWORD).status_code == 200, "las otras cuentas siguen entrando"


def test_un_ingreso_bueno_borra_los_fallos_de_la_cuenta(client, persona, topes):
    for _ in range(2):
        assert _login(client, persona.email).status_code == 401
    assert _login(client, persona.email, PASSWORD).status_code == 200
    for _ in range(2):
        assert _login(client, persona.email).status_code == 401

    assert _login(client, persona.email, PASSWORD).status_code == 200


def test_los_emails_desconocidos_cuentan_por_email_sin_distinguir_mayusculas(client, topes):
    for email in ("nadie@example.com", "NADIE@example.com", "Nadie@Example.com"):
        assert _login(client, email).status_code == 401

    _es_429(_login(client, "nadie@example.com"))
    assert _login(client, "otro@example.com").status_code == 401


def test_la_ip_se_frena_con_los_fallos_de_varias_cuentas_y_las_otras_ips_no(app, topes):
    atacante, vecino = _desde(app, "203.0.113.7"), _desde(app, "198.51.100.4")
    for i in range(6):
        assert _login(atacante, f"cuenta-{i}@example.com").status_code == 401

    _es_429(_login(atacante, "cuenta-nueva@example.com"))
    assert _login(vecino, "cuenta-nueva@example.com").status_code == 401


def test_x_cliente_ip_se_cree_solo_desde_una_ip_confiable(app, topes):
    flask, externo = _desde(app, "172.18.0.5"), _desde(app, "203.0.113.7")
    for i in range(6):
        assert _login(flask, f"a-{i}@example.com", **{"X-Cliente-IP": "190.0.0.1"}).status_code == 401
        assert _login(externo, f"b-{i}@example.com", **{"X-Cliente-IP": f"190.0.1.{i}"}).status_code == 401

    # Flask manda la IP de cada navegador: la que falló está frenada y otra no
    _es_429(_login(flask, "a-nueva@example.com", **{"X-Cliente-IP": "190.0.0.1"}))
    assert _login(flask, "a-nueva@example.com", **{"X-Cliente-IP": "190.0.0.2"}).status_code == 401
    # desde afuera la cabecera no cuenta: cambiarla no esquiva el límite de su IP
    _es_429(_login(externo, "b-nueva@example.com", **{"X-Cliente-IP": "190.0.1.99"}))


def test_el_2fa_frena_a_la_cuenta_despues_de_sus_codigos_incorrectos(client, persona, db_session, topes):
    persona.totp_secret = pyotp.random_base32()
    persona.totp_enabled = True
    db_session.flush()
    r = _login(client, persona.email, PASSWORD)
    temp = r.json()["temp_token"]

    def verificar(codigo):
        return client.post("/api/v1/auth/verify-2fa", json={"temp_token": temp, "code": codigo})

    for _ in range(2):
        assert verificar("000000").status_code == 401
    _es_429(verificar(pyotp.TOTP(persona.totp_secret).now()))


def test_un_codigo_bueno_borra_los_fallos_del_2fa(client, persona, db_session, topes):
    persona.totp_secret = pyotp.random_base32()
    persona.totp_enabled = True
    db_session.flush()

    def verificar(codigo):
        temp = _login(client, persona.email, PASSWORD).json()["temp_token"]
        return client.post("/api/v1/auth/verify-2fa", json={"temp_token": temp, "code": codigo})

    assert verificar("000000").status_code == 401
    assert verificar(pyotp.TOTP(persona.totp_secret).now()).status_code == 200
    assert verificar("000000").status_code == 401
    assert verificar(pyotp.TOTP(persona.totp_secret).now()).status_code == 200


def test_forgot_password_cuenta_cada_pedido_por_email_exista_o_no(client, persona, fake_email, topes):
    for email in (persona.email, persona.email.upper()):
        assert client.post("/api/v1/auth/forgot-password", json={"email": email}).status_code == 200
    assert len(fake_email.messages) == 2

    _es_429(client.post("/api/v1/auth/forgot-password", json={"email": persona.email}))
    assert len(fake_email.messages) == 2, "frenado no manda el correo"
    assert client.post("/api/v1/auth/forgot-password", json={"email": "nadie@example.com"}).status_code == 200


def test_los_enlaces_invalidos_cuentan_como_fallos_de_la_ip(client, topes):
    for _ in range(2):
        assert (
            client.post("/api/v1/auth/reset-password", json={"token": "no-es", "password": PASSWORD}).status_code == 400
        )
        assert client.get("/api/v1/usuarios/magic-link/validar/no-es").status_code == 400
        r = client.post(
            "/api/v1/usuarios/magic-link/set-password",
            json={"token": "no-es", "password": PASSWORD, "confirmar_password": PASSWORD},
        )
        assert r.status_code == 400, r.text

    _es_429(client.get("/api/v1/usuarios/magic-link/validar/otro"))
    _es_429(client.post("/api/v1/auth/reset-password", json={"token": "otro", "password": PASSWORD}))
    _es_429(_login(client, "nadie@example.com"))


def test_el_limitador_es_una_ventana_deslizante_y_barre_lo_vencido():
    ahora = [1000.0]
    limitador = limites.Limitador(reloj=lambda: ahora[0])
    for paso in (0, 100, 200):
        ahora[0] = 1000.0 + paso
        limitador.sumar("x")

    assert limitador.espera("x", 3) == limites.VENTANA - 200  # libera cuando vence el primero
    assert limitador.espera("x", 4) == 0
    ahora[0] = 1000.0 + limites.VENTANA + 1
    assert limitador.espera("x", 3) == 0
    ahora[0] += limites.VENTANA + limites.BARRIDO
    limitador.sumar("y")
    assert set(limitador._marcas) == {"y"}
