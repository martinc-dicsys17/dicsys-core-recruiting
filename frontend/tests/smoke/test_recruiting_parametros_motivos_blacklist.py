"""Recruiting → Parámetros → Motivos de Blacklist: permiso de las rutas, la pestaña en las pantallas de Parámetros y el
reenvío al backend de listar, crear, editar y eliminar. El backend valida el acceso de verdad: acá se prueba lo que la
pantalla pide, muestra y reenvía."""

import re

import pytest

pytestmark = [pytest.mark.frontend]

RAIZ = "/recruiting/parametros/motivos-blacklist"
API = f"{RAIZ}/api"
BACKEND = "/recruiting/parametros/motivos-blacklist"
MOTIVOS = [{"id": 1, "motivo": "Conducta inapropiada"}, {"id": 2, "motivo": "Otro motivo"}]


def _sesion(client, fake_api, *permisos):
    with client.session_transaction() as session:
        session["token"] = "test-token"
        session["user"] = {"id": "user-id", "email": "user@example.com", "nombre": "Test", "rol": "usuario"}
        session["empresa_nombre"] = "Dicsys.AI"
    fake_api.respond("GET", "/permisos/mis-permisos", {"permisos": {p: True for p in permisos}})
    fake_api.respond("GET", "/menus", {"items": []})


def _con_permiso(client, fake_api):
    _sesion(client, fake_api, "recruiting", "recruiting.parametros")


def _llamada(fake_api, metodo, endpoint):
    return next(c for c in fake_api.calls if c["method"] == metodo and c["endpoint"] == endpoint)


# --- Permisos de las rutas ------------------------------------------------------------------------------------------


@pytest.mark.parametrize("metodo, ruta", [("get", RAIZ), ("get", API), ("post", API), ("put", f"{API}/1"), ("delete", f"{API}/1")])
def test_sin_sesion_redirige_al_login(frontend_client, metodo, ruta):
    respuesta = getattr(frontend_client, metodo)(ruta)
    assert respuesta.status_code == 302 and "/login" in respuesta.headers["Location"]


@pytest.mark.parametrize("metodo, ruta", [("get", RAIZ), ("get", API), ("post", API), ("put", f"{API}/1"), ("delete", f"{API}/1")])
def test_sin_el_item_parametros_responde_403(frontend_client, fake_api, metodo, ruta):
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.candidatos")
    assert getattr(frontend_client, metodo)(ruta).status_code == 403
    assert not [c for c in fake_api.calls if c["endpoint"].startswith(BACKEND)]


# --- Pantalla y pestaña ---------------------------------------------------------------------------------------------


def test_la_pantalla_muestra_el_abm_con_su_pestana_activa(frontend_client, fake_api):
    _con_permiso(frontend_client, fake_api)
    respuesta = frontend_client.get(RAIZ)
    html = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "Catálogo de Motivos de Blacklist" in html
    assert "Nuevo Motivo" in html
    pestana = re.search(r'<a href="/recruiting/parametros/motivos-blacklist"[^>]*>', html).group(0)
    assert "font-bold" in pestana and "border-primary-600" in pestana  # la pestaña activa
    provincias = re.search(r'<a href="/recruiting/parametros/provincias"[^>]*>', html).group(0)
    assert "border-primary-600" not in provincias


@pytest.mark.parametrize(
    "ruta",
    [
        "/recruiting/parametros",
        "/recruiting/parametros/skills",
        "/recruiting/parametros/habilidades",
        "/recruiting/parametros/provincias",
        "/recruiting/parametros/ciudades",
        "/recruiting/parametros/lideres",
        "/recruiting/parametros/reclutadores",
        "/recruiting/parametros/perfiles-profesionales",
        "/recruiting/parametros/archivos-cv",
    ],
)
def test_las_demas_pantallas_de_parametros_ofrecen_la_pestana(frontend_client, fake_api, ruta):
    _con_permiso(frontend_client, fake_api)
    fake_api.respond("GET", "/recruiting/parametros/config", {"match_minimo_porcentaje": 50})
    fake_api.respond("GET", "/recruiting/parametros/archivos-cv", [])
    respuesta = frontend_client.get(ruta)

    assert respuesta.status_code == 200
    assert f'href="{RAIZ}"' in respuesta.get_data(as_text=True)


# --- Reenvío al backend ---------------------------------------------------------------------------------------------


def test_listar_reenvia_y_devuelve_los_motivos(frontend_client, fake_api):
    _con_permiso(frontend_client, fake_api)
    fake_api.respond("GET", BACKEND, MOTIVOS)

    respuesta = frontend_client.get(API)

    assert respuesta.status_code == 200
    assert respuesta.get_json() == {"success": True, "motivos": MOTIVOS}
    assert _llamada(fake_api, "GET", BACKEND)["token"] == "test-token"


def test_crear_reenvia_el_cuerpo(frontend_client, fake_api):
    _con_permiso(frontend_client, fake_api)
    nuevo = {"id": 3, "motivo": "Suplantacion de identidad"}
    fake_api.respond("POST", BACKEND, nuevo, 201)

    respuesta = frontend_client.post(API, json={"motivo": "Suplantacion de identidad"})

    assert respuesta.status_code == 201
    assert respuesta.get_json() == {"success": True, "motivo": nuevo}
    assert _llamada(fake_api, "POST", BACKEND)["data"] == {"motivo": "Suplantacion de identidad"}


def test_editar_reenvia_el_id_y_el_cuerpo(frontend_client, fake_api):
    _con_permiso(frontend_client, fake_api)
    fake_api.respond("PUT", f"{BACKEND}/2", {"id": 2, "motivo": "Otro"})

    respuesta = frontend_client.put(f"{API}/2", json={"motivo": "Otro"})

    assert respuesta.status_code == 200 and respuesta.get_json()["success"] is True
    assert _llamada(fake_api, "PUT", f"{BACKEND}/2")["data"] == {"motivo": "Otro"}


def test_eliminar_reenvia_el_delete(frontend_client, fake_api):
    _con_permiso(frontend_client, fake_api)
    fake_api.respond("DELETE", f"{BACKEND}/2", {"message": "Motivo eliminado correctamente."})

    respuesta = frontend_client.delete(f"{API}/2")

    assert respuesta.status_code == 200
    assert respuesta.get_json() == {"success": True, "resultado": {"message": "Motivo eliminado correctamente."}}


def test_el_error_del_backend_llega_a_la_pantalla_con_su_estado(frontend_client, fake_api):
    _con_permiso(frontend_client, fake_api)
    fake_api.respond("POST", BACKEND, {"detail": "Ya existe un motivo con el nombre 'Otro motivo'."}, 409)

    respuesta = frontend_client.post(API, json={"motivo": "otro motivo"})

    assert respuesta.status_code == 409
    assert respuesta.get_json() == {"success": False, "error": "Ya existe un motivo con el nombre 'Otro motivo'."}


def test_el_id_debe_ser_entero(frontend_client, fake_api):
    _con_permiso(frontend_client, fake_api)
    assert frontend_client.put(f"{API}/abc", json={"motivo": "x"}).status_code == 404
