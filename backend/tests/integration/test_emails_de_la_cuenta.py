"""El email vive en la cuenta (F22): secundario en el CRUD de Usuarios, la ficha de nómina copia el email de la cuenta
(solo lectura), control de email corporativo en el login, migración, Odoo y Webex."""

import json
import uuid

import pytest
from sqlalchemy import text

from backend.core.webex import email_de_persona
from backend.modules.parametros.models import Parametro
from backend.modules.sincronizacion.services import SincronizacionService
from backend.modules.tareas import cola
from backend.modules.usuarios import emails_corporativos
from backend.tests.helpers.auth import auth_headers

pytestmark = [pytest.mark.integration]

USUARIOS = "/api/v1/usuarios"
EMPLEADOS = "/api/v1/nomina/empleados"
LOGIN = "/api/v1/auth/login"


def _local():
    return f"qa{uuid.uuid4().hex[:8]}"


def _dni():
    return uuid.uuid4().int % 89_999_999 + 10_000_000


@pytest.fixture
def admin(data_factory, db_session):
    empresa = data_factory.empresa()
    usuario = data_factory.usuario(rol="admin")
    data_factory.asignar_empresa(usuario, empresa)
    db_session.commit()  # como la API: el rollback de un alta rechazada no lo borra
    return empresa, auth_headers(usuario, empresa)


def _alta_usuario(**cambios):
    return {
        "email": f"{_local()}@dicsys.com",
        "nombre": "Juan",
        "apellido": "Pérez",
        "password": "clave-123",
        "rol": "usuario",
        **cambios,
    }


def _alta_ficha(**cambios):
    valor = uuid.uuid4().int
    return {
        "codigo": f"EMP-{uuid.uuid4().hex[:8]}",
        "cuil": 20_000_000_000 + valor % 9_999_999_999,
        "apellido": "Pérez",
        "nombre": "Juan",
        "dni": _dni(),
        **cambios,
    }


# ─── Secundario en el CRUD de Usuarios ────────────────────────────────────


def test_alta_y_edicion_del_secundario(client, admin):
    empresa, headers = admin
    local = _local()
    r = client.post(
        USUARIOS,
        json=_alta_usuario(email=f"{local}@dicsys.ai", email_secundario=f"{local.upper()}@DICSYS.com"),
        headers=headers,
    )
    assert r.status_code == 201, r.text
    assert r.json()["email_secundario"] == f"{local}@dicsys.com"
    usuario_id = r.json()["id"]

    r = client.put(f"{USUARIOS}/{usuario_id}", json={"email_secundario": f"otro{local}@dicsys.com"}, headers=headers)
    assert r.status_code == 200 and r.json()["email_secundario"] == f"otro{local}@dicsys.com", r.text
    r = client.put(f"{USUARIOS}/{usuario_id}", json={"email_secundario": None}, headers=headers)
    assert r.status_code == 200 and r.json()["email_secundario"] is None, r.text


def test_secundario_igual_al_email_o_de_otra_cuenta(client, admin, data_factory):
    empresa, headers = admin
    local = _local()
    data_factory.usuario(email=f"{local}@dicsys.ai", email_secundario=f"{local}@dicsys.com")
    data_factory.session.commit()  # como la API: el rollback de un alta rechazada no la borra

    r = client.post(
        USUARIOS,
        json=_alta_usuario(email=f"x{local}@dicsys.ai", email_secundario=f"X{local}@dicsys.ai"),
        headers=headers,
    )
    assert r.status_code == 422 and "distinto del email" in r.json()["detail"], r.text
    r = client.post(
        USUARIOS,
        json=_alta_usuario(email=f"y{local}@dicsys.ai", email_secundario=f"{local}@dicsys.ai"),
        headers=headers,
    )
    assert r.status_code == 409 and "ya es de otra cuenta" in r.json()["detail"], r.text
    r = client.post(USUARIOS, json=_alta_usuario(email=f"{local}@dicsys.com"), headers=headers)
    assert r.status_code == 409 and r.json()["detail"] == "El email ya está registrado", r.text


def test_con_ficha_los_dos_tienen_que_ser_de_la_empresa(client, admin, data_factory):
    empresa, headers = admin
    dni = _dni()
    data_factory.empleado(empresa, dni=dni)
    data_factory.session.commit()  # como la API: el rollback de un alta rechazada no la borra
    for cambios, campo in (
        ({"email": "juan@gmail.com"}, "El email"),
        ({"email_secundario": "juan@gmail.com"}, "El email secundario"),
    ):
        r = client.post(USUARIOS, json=_alta_usuario(dni=dni, **cambios), headers=headers)
        assert r.status_code == 422, r.text
        assert r.json()["detail"].startswith(f"{campo} tiene que ser de un dominio de la empresa"), r.json()
        assert "ficha de nómina" in r.json()["detail"]
    # Sin ficha no se exige el dominio (cuentas de sistema o externas)
    assert (
        client.post(
            USUARIOS, json=_alta_usuario(email=f"{_local()}@gmail.com", dni=_dni()), headers=headers
        ).status_code
        == 201
    )


def test_la_persona_no_cambia_su_email(client, data_factory):
    usuario = data_factory.usuario(email=f"{_local()}@dicsys.com")
    r = client.put(
        "/api/v1/auth/me", json={"email": "otro@gmail.com", "nombre": "Juana"}, headers=auth_headers(usuario)
    )
    assert r.status_code == 200, r.text
    assert r.json()["email"] == usuario.email and r.json()["nombre"] == "Juana"


def test_la_persona_no_cambia_su_dni_ni_queda_con_una_ficha_ajena(client, db_session, data_factory):
    """PG-25: con el DNI de una ficha sin cuenta, la persona la veía y la editaba como propia."""
    empresa = data_factory.empresa()
    ficha = data_factory.empleado(empresa, dni=_dni(), email_corporativo=None)
    usuario = data_factory.usuario(email=f"{_local()}@dicsys.ai")
    con_dni = data_factory.usuario(email=f"{_local()}@dicsys.ai", dni=_dni())
    db_session.commit()

    r = client.put(
        "/api/v1/auth/me", json={"dni": ficha.dni, "nombre": "Juana"}, headers=auth_headers(usuario, empresa)
    )
    assert r.status_code == 200, r.text
    assert r.json()["dni"] is None and r.json()["nombre"] == "Juana"
    assert client.get("/api/v1/auth/me/perfil", headers=auth_headers(usuario, empresa)).json()["empleado"] is None
    db_session.expire_all()
    assert db_session.get(type(ficha), ficha.id).email_corporativo is None

    r = client.put("/api/v1/auth/me", json={"dni": None, "nombre": "Juana"}, headers=auth_headers(con_dni, empresa))
    assert r.status_code == 200 and r.json()["dni"] == con_dni.dni


def test_mi_perfil_de_nomina_no_cambia_el_email_de_la_cuenta(client, data_factory):
    empresa = data_factory.empresa()
    usuario = data_factory.usuario(email=f"{_local()}@dicsys.com", dni=_dni())
    data_factory.asignar_empresa(usuario, empresa)
    ficha = data_factory.empleado(empresa, dni=usuario.dni, email_corporativo=usuario.email)
    r = client.put(
        f"{EMPLEADOS}/{ficha.id}/mi-perfil",
        json={"email_personal": "personal@gmail.com"},
        headers=auth_headers(usuario, empresa),
    )
    assert r.status_code == 200, r.text
    r = client.get("/api/v1/auth/me", headers=auth_headers(usuario, empresa))
    assert r.json()["email"] == usuario.email


def test_mi_perfil_trae_el_secundario_de_la_cuenta(client, data_factory):
    empresa = data_factory.empresa()
    usuario = data_factory.usuario(email=f"{_local()}@dicsys.ai", email_secundario=f"{_local()}@dicsys.com", dni=_dni())
    data_factory.asignar_empresa(usuario, empresa)
    data_factory.empleado(empresa, dni=usuario.dni, email_corporativo=usuario.email)
    r = client.get("/api/v1/auth/me/perfil", headers=auth_headers(usuario, empresa))
    assert r.status_code == 200, r.text
    assert (r.json()["email_secundario"], r.json()["empleado"]["email_corporativo"]) == (
        usuario.email_secundario,
        usuario.email,
    )


# ─── La ficha copia el email de la cuenta ─────────────────────────────────


def test_la_ficha_copia_el_email_de_la_cuenta(client, admin, data_factory, db_session):
    empresa, headers = admin
    local = _local()
    dni = _dni()
    ficha = data_factory.empleado(empresa, dni=dni, email_corporativo="viejo@dicsys.com")

    r = client.post(USUARIOS, json=_alta_usuario(email=f"{local}@dicsys.com", dni=dni), headers=headers)
    assert r.status_code == 201, r.text
    db_session.refresh(ficha)
    assert ficha.email_corporativo == f"{local}@dicsys.com"

    r = client.put(f"{USUARIOS}/{r.json()['id']}", json={"email": f"{local}@dicsys.ai"}, headers=headers)
    assert r.status_code == 200, r.text
    db_session.refresh(ficha)
    assert ficha.email_corporativo == f"{local}@dicsys.ai"

    # Nómina no lo edita: el campo se ignora
    r = client.put(
        f"{EMPLEADOS}/{ficha.id}", json={"email_corporativo": "otro@dicsys.ai", "puesto": "QA"}, headers=headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["email_corporativo"] == f"{local}@dicsys.ai"
    r = client.get(f"{EMPLEADOS}/{ficha.id}", headers=headers)
    assert r.json()["email_secundario"] is None


def test_alta_de_ficha_copia_de_la_cuenta_y_sin_cuenta_queda_vacia(client, admin, data_factory):
    empresa, headers = admin
    usuario = data_factory.usuario(email=f"{_local()}@dicsys.ai", email_secundario=f"{_local()}@dicsys.com", dni=_dni())
    r = client.post(
        EMPLEADOS, json=_alta_ficha(dni=usuario.dni, email_corporativo="ignorado@dicsys.com"), headers=headers
    )
    assert r.status_code == 201, r.text
    assert r.json()["email_corporativo"] == usuario.email
    r = client.get(f"{EMPLEADOS}/{r.json()['id']}", headers=headers)
    assert r.json()["email_secundario"] == usuario.email_secundario

    r = client.post(EMPLEADOS, json=_alta_ficha(email_corporativo="ignorado@dicsys.com"), headers=headers)
    assert r.status_code == 201 and r.json()["email_corporativo"] is None, r.text


def test_cambio_de_dni_de_la_ficha_copia_de_la_nueva_cuenta(client, admin, data_factory):
    empresa, headers = admin
    usuario = data_factory.usuario(email=f"{_local()}@dicsys.com", dni=_dni())
    ficha = data_factory.empleado(empresa, email_corporativo="de.odoo@dicsys.com")
    r = client.put(f"{EMPLEADOS}/{ficha.id}", json={"dni": usuario.dni}, headers=headers)
    assert r.status_code == 200 and r.json()["email_corporativo"] == usuario.email, r.text


def test_email_de_otro_dominio_no_se_copia(db_session, data_factory):
    empresa = data_factory.empresa()
    empresa.dominios_email = json.dumps(["acme.com"])
    usuario = data_factory.usuario(email=f"{_local()}@dicsys.com", dni=_dni())
    ficha = data_factory.empleado(empresa, dni=usuario.dni, email_corporativo="x@acme.com")
    emails_corporativos.copiar_a_fichas(db_session, usuario)
    assert ficha.email_corporativo is None


# ─── Login ────────────────────────────────────────────────────────────────


def _cuenta_con_ficha(data_factory, email, email_secundario=None, ficha=True, dni=True):
    empresa = data_factory.empresa()
    usuario = data_factory.usuario(
        email=email, email_secundario=email_secundario, password="clave-123", dni=_dni() if dni else None
    )
    data_factory.asignar_empresa(usuario, empresa)
    if ficha and dni:
        data_factory.empleado(empresa, dni=usuario.dni, email_corporativo=email)
    return usuario


def test_login_con_el_email_o_el_secundario(client, data_factory):
    local = _local()
    usuario = _cuenta_con_ficha(data_factory, f"{local}@dicsys.ai", f"{local}@dicsys.com")
    for email in (f"{local}@dicsys.ai", f"{local.upper()}@DICSYS.com"):
        r = client.post(LOGIN, json={"email": email, "password": "clave-123"})
        assert r.status_code == 200, (email, r.text)
        assert r.json()["user"]["id"] == str(usuario.id)
    assert client.post(LOGIN, json={"email": f"{local}@dicsys.com", "password": "otra"}).status_code == 401


@pytest.mark.parametrize(
    "email, secundario, entra",
    [
        ("juan@gmail.com", None, False),
        ("juan@gmail.com", "juan@dicsys.com", True),
        ("juan@dicsys.ai", None, True),
    ],
)
def test_control_de_email_corporativo_con_ficha(client, data_factory, email, secundario, entra):
    local = _local()
    _cuenta_con_ficha(data_factory, email.replace("juan", local), secundario and secundario.replace("juan", local))
    r = client.post(LOGIN, json={"email": email.replace("juan", local), "password": "clave-123"})
    if entra:
        assert r.status_code == 200, r.text
    else:
        assert (r.status_code, r.json()["detail"]) == (403, emails_corporativos.SIN_EMAIL_CORPORATIVO)


@pytest.mark.parametrize("ficha, dni", [(False, True), (False, False)])
def test_sin_ficha_o_sin_dni_no_hay_control(client, data_factory, ficha, dni):
    email = f"{_local()}@gmail.com"
    _cuenta_con_ficha(data_factory, email, ficha=ficha, dni=dni)
    assert client.post(LOGIN, json={"email": email, "password": "clave-123"}).status_code == 200


def test_control_con_ficha_dada_de_baja_y_con_otra_empresa(client, data_factory, db_session):
    local = _local()
    usuario = _cuenta_con_ficha(data_factory, f"{local}@gmail.com", ficha=False)
    empresa = data_factory.empresa()
    data_factory.empleado(empresa, dni=usuario.dni, activo=False)
    r = client.post(LOGIN, json={"email": usuario.email, "password": "clave-123"})
    assert r.status_code == 403
    # Con una segunda ficha en una empresa cuyo dominio es el de la cuenta, alcanza
    otra = data_factory.empresa()
    otra.dominios_email = json.dumps(["gmail.com"])
    data_factory.empleado(otra, dni=usuario.dni)
    db_session.flush()
    assert client.post(LOGIN, json={"email": usuario.email, "password": "clave-123"}).status_code == 200


# ─── Migración ────────────────────────────────────────────────────────────
# La copia a las fichas la hace la revisión 0004 al agregar email_secundario; la cadena se prueba en test_migraciones.


def test_la_migracion_copia_a_las_fichas(db_session, data_factory):
    from backend.tests.integration.test_migraciones import revision

    COPIA_A_FICHAS = revision("0004").COPIA_A_FICHAS
    empresa = data_factory.empresa()
    con_espacio = data_factory.usuario(email=f"{_local()}@dicsys.com", dni=_dni())
    otro_dominio = data_factory.usuario(email=f"{_local()}@dicsys.odoo.com", dni=_dni())
    f1 = data_factory.empleado(empresa, dni=con_espacio.dni, email_corporativo="viejo@dicsys.com")
    f2 = data_factory.empleado(empresa, dni=otro_dominio.dni, email_corporativo=otro_dominio.email)
    f3 = data_factory.empleado(empresa, email_corporativo="sin.cuenta@dicsys.com")
    db_session.execute(text("UPDATE core_usuarios SET email = email || ' ' WHERE id = :id"), {"id": con_espacio.id})
    db_session.execute(text("UPDATE core_usuarios SET email = trim(email) WHERE email <> trim(email)"))
    db_session.execute(text(COPIA_A_FICHAS))
    for objeto in (con_espacio, f1, f2, f3):
        db_session.refresh(objeto)
    assert con_espacio.email == con_espacio.email.strip()
    assert f1.email_corporativo == con_espacio.email
    assert f2.email_corporativo is None
    assert f3.email_corporativo == "sin.cuenta@dicsys.com"


# ─── Webex: el email de la cuenta de la persona ───────────────────────────


def test_webex_prueba_primero_el_principal_y_despues_el_secundario(fake_webex):
    assert email_de_persona(["a@dicsys.ai"]) == "a@dicsys.ai"
    assert fake_webex.busquedas == []  # con un solo email no se consulta
    fake_webex.personas = {"a@dicsys.com"}
    assert email_de_persona(["a@dicsys.ai", "a@dicsys.com"]) == "a@dicsys.com"
    fake_webex.personas = set()
    assert email_de_persona(["a@dicsys.ai", "a@dicsys.com"]) == "a@dicsys.ai"


def test_mensaje_personal_de_webex_va_a_la_cuenta_de_la_persona(db_session, data_factory, fake_webex):
    local = _local()
    usuario = _cuenta_con_ficha(data_factory, f"{local}@dicsys.ai", f"{local}@dicsys.com")
    fake_webex.personas = {f"{local}@dicsys.com"}
    # El aviso sale al email de la ficha (la copia); Webex lo resuelve por la cuenta
    assert cola.mandar("webex_personal", usuario.email, "Aviso", {"texto": "hola"}, db=db_session) is None
    assert fake_webex.messages[-1]["person_email"] == f"{local}@dicsys.com"
    assert cola.mandar("webex_personal", usuario.email, "Aviso", {"texto": "hola"}) is None
    assert fake_webex.messages[-1]["person_email"] == usuario.email


def test_sync_de_webex_usa_el_secundario_de_la_cuenta(db_session, data_factory, fake_webex):
    from backend.modules.nomina.models import Empleado

    empresa = data_factory.empresa()
    db_session.query(Empleado).filter(Empleado.empresa_id != empresa.id).update({"activo": False})
    esta, nueva, sin_cuenta = _local(), _local(), _local()
    for local in (esta, nueva):
        usuario = data_factory.usuario(email=f"{local}@dicsys.ai", email_secundario=f"{local}@dicsys.com", dni=_dni())
        data_factory.empleado(empresa, dni=usuario.dni, email_corporativo=usuario.email)
    data_factory.empleado(empresa, email_corporativo=f"{sin_cuenta}@dicsys.ai")
    for key, valor in (("webex_team_dicsys_id", "team-1"), ("webex_sync_sleep_segundos", "0")):
        db_session.add(Parametro(categoria="Sincronización", subcategoria="Webex", nombre=key, key=key, valor=valor))
    db_session.flush()
    fake_webex.personas = {f"{nueva}@dicsys.com"}
    fake_webex.list_team_member_emails = lambda team_id, timeout=15.0: {
        "success": True,
        "emails": {f"{esta}@dicsys.com"},
    }

    resultado = SincronizacionService._sync_webex_membresias(db_session, None)

    agregados = sorted(m["person_email"] for m in fake_webex.messages if m["kind"] == "team_membership")
    assert agregados == sorted([f"{nueva}@dicsys.com", f"{sin_cuenta}@dicsys.ai"]), resultado
    assert resultado["registros_procesados"] == 3
