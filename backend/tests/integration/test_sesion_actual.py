"""GET /auth/me (F07-P02): la sesión actual en una sola llamada para el shell de la SPA."""

import pytest

from backend.core import registry
from backend.tests.helpers.auth import auth_headers

ME = "/api/v1/auth/me"
pytestmark = [pytest.mark.integration, pytest.mark.deploy_gate]


@pytest.fixture
def modulo_de_prueba(monkeypatch):
    modulos = dict(registry._MODULOS_REGISTRY)
    modulos["mod_me"] = {
        "codigo": "mod_me",
        "nombre": "Módulo me",
        "icono": "box",
        "orden": 999,
        "items": [
            {"codigo": "visible", "nombre": "Visible", "ruta": "x.visible", "orden": 1},
            {"codigo": "oculto", "nombre": "Oculto", "ruta": "x.oculto", "orden": 2},
        ],
    }
    monkeypatch.setattr(registry, "_MODULOS_REGISTRY", modulos)


@pytest.fixture
def persona(data_factory):
    """Una cuenta con ficha en su empresa (se unen por DNI) y un grupo con mod_me y mod_me.visible."""
    empresa = data_factory.empresa(nombre_fantasia="Empresa Me")
    usuario = data_factory.usuario(dni=30_111_222)
    empleado = data_factory.empleado(empresa, dni=30_111_222)
    grupo = data_factory.grupo()
    data_factory.asignar_empresa(usuario, empresa)
    data_factory.asignar_grupo(usuario, grupo, empresa)
    data_factory.permisos(grupo, ["mod_me", "mod_me.visible"])
    return usuario, empresa, empleado


def test_con_empresa_trae_empresa_ficha_permisos_y_menu(client, modulo_de_prueba, persona):
    usuario, empresa, empleado = persona
    headers = auth_headers(usuario, empresa)

    r = client.get(ME, headers=headers)

    assert r.status_code == 200, r.text
    sesion = r.json()
    assert sesion["email"] == usuario.email and sesion["dni"] == 30_111_222 and sesion["rol"] == "usuario"
    assert sesion["empresa"]["id"] == str(empresa.id) and sesion["empresa"]["nombre_fantasia"] == "Empresa Me"
    assert [e["id"] for e in sesion["empresas"]] == [str(empresa.id)]
    assert sesion["empleado"]["id"] == str(empleado.id)
    # los mismos permisos y el mismo menú que las llamadas sueltas
    assert sesion["permisos"] == client.get("/api/v1/permisos/mis-permisos", headers=headers).json()["permisos"]
    assert sesion["permisos"] == {"mod_me": True, "mod_me.visible": True}
    assert sesion["menu"] == client.get("/api/v1/menus", headers=headers).json()["items"]
    modulo = next(m for m in sesion["menu"] if m["codigo"] == "mod_me")
    assert [i["codigo"] for i in modulo["items"]] == ["visible"]


def test_sin_empresa_en_el_token_trae_sus_empresas_y_nada_de_la_empresa(client, modulo_de_prueba, persona):
    usuario, empresa, _ = persona

    r = client.get(ME, headers=auth_headers(usuario))

    assert r.status_code == 200, r.text
    sesion = r.json()
    assert [e["id"] for e in sesion["empresas"]] == [str(empresa.id)]
    assert sesion["empresa"] is None and sesion["empleado"] is None
    assert sesion["permisos"] == {} and sesion["menu"] == []


def test_con_una_empresa_a_la_que_no_pertenece_no_trae_nada_de_esa_empresa(client, data_factory, persona):
    usuario, _, _ = persona
    ajena = data_factory.empresa()

    r = client.get(ME, headers=auth_headers(usuario, ajena))

    assert r.status_code == 200, r.text
    sesion = r.json()
    assert sesion["empresa"] is None and sesion["permisos"] == {} and sesion["menu"] == []


def test_admin_ve_el_menu_completo_y_sin_ficha(client, data_factory):
    admin = data_factory.usuario(rol="admin")
    empresa = data_factory.empresa()
    data_factory.asignar_empresa(admin, empresa)
    headers = auth_headers(admin, empresa)

    sesion = client.get(ME, headers=headers).json()

    assert sesion["rol"] == "admin" and sesion["empleado"] is None
    assert sesion["menu"] == client.get("/api/v1/menus", headers=headers).json()["items"]
    assert {m["codigo"] for m in sesion["menu"]} == {m["codigo"] for m in registry.obtener_modulos()}
