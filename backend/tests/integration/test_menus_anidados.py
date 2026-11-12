"""Menú de tres niveles: un ítem puede agrupar hijos con clave de permiso plana."""

import pytest

from backend.core import registry
from backend.tests.helpers.auth import auth_headers

MENUS = "/api/v1/menus"
DETALLE = "/api/v1/permisos/modulos/detalle"
pytestmark = [pytest.mark.integration, pytest.mark.deploy_gate]


@pytest.fixture
def modulo_anidado(monkeypatch):
    modulos = dict(registry._MODULOS_REGISTRY)
    modulos["mod_test"] = {
        "codigo": "mod_test",
        "nombre": "Módulo test",
        "icono": "box",
        "orden": 999,
        "items": [
            {"codigo": "suelto", "nombre": "Suelto", "ruta": "x.suelto", "orden": 1},
            {
                "codigo": "padre",
                "nombre": "Padre",
                "ruta": "x.padre",
                "orden": 2,
                "items": [
                    {"codigo": "hijo_b", "nombre": "Hijo B", "ruta": "x.hijo_b", "orden": 2},
                    {"codigo": "hijo_a", "nombre": "Hijo A", "ruta": "x.hijo_a", "orden": 1},
                ],
            },
        ],
    }
    monkeypatch.setattr(registry, "_MODULOS_REGISTRY", modulos)


@pytest.fixture
def usuario_con(data_factory):
    def crear(claves, rol="usuario"):
        usuario = data_factory.usuario(rol=rol)
        empresa = data_factory.empresa()
        grupo = data_factory.grupo()
        data_factory.asignar_empresa(usuario, empresa)
        data_factory.asignar_grupo(usuario, grupo, empresa)
        data_factory.permisos(grupo, claves)
        return auth_headers(usuario, empresa)

    return crear


def _modulo(client, headers):
    menus = client.get(MENUS, headers=headers).json()["items"]
    return next((m for m in menus if m["codigo"] == "mod_test"), None)


def test_hijo_sin_permiso_del_padre_muestra_el_padre_como_rotulo(client, modulo_anidado, usuario_con):
    modulo = _modulo(client, usuario_con(["mod_test", "mod_test.hijo_a"]))

    assert [i["codigo"] for i in modulo["items"]] == ["padre"]
    padre = modulo["items"][0]
    assert padre["ruta"] is None and padre["es_link"] is False
    assert [h["codigo"] for h in padre["items"]] == ["hijo_a"]
    assert padre["items"][0]["ruta"] == "x.hijo_a"


def test_padre_con_permiso_propio_es_link_y_ordena_los_hijos(client, modulo_anidado, usuario_con):
    modulo = _modulo(client, usuario_con(["mod_test", "mod_test.padre", "mod_test.hijo_a", "mod_test.hijo_b"]))

    padre = modulo["items"][0]
    assert padre["ruta"] == "x.padre" and padre["es_link"] is True
    assert [h["codigo"] for h in padre["items"]] == ["hijo_a", "hijo_b"]


def test_padre_sin_hijos_visibles_ni_permiso_propio_no_aparece(client, modulo_anidado, usuario_con):
    modulo = _modulo(client, usuario_con(["mod_test", "mod_test.suelto"]))

    assert [i["codigo"] for i in modulo["items"]] == ["suelto"]
    assert modulo["items"][0]["items"] == []


def test_permiso_del_hijo_sin_el_modulo_no_muestra_nada(client, modulo_anidado, usuario_con):
    assert _modulo(client, usuario_con(["mod_test.hijo_a"])) is None


def test_admin_ve_el_arbol_completo(client, modulo_anidado, usuario_con):
    modulo = _modulo(client, usuario_con([], rol="admin"))

    assert [i["codigo"] for i in modulo["items"]] == ["suelto", "padre"]
    assert [h["codigo"] for h in modulo["items"][1]["items"]] == ["hijo_a", "hijo_b"]


def test_detalle_de_permisos_lista_los_hijos_planos_con_su_padre(client, modulo_anidado, usuario_con):
    detalle = client.get(DETALLE, headers=usuario_con([])).json()
    modulo = next(m for m in detalle if m["codigo"] == "mod_test")

    assert [(i["codigo"], i["padre"]) for i in modulo["items"]] == [
        ("suelto", None),
        ("padre", None),
        ("hijo_a", "padre"),
        ("hijo_b", "padre"),
    ]
