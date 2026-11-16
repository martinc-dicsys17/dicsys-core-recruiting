"""Recruiting → Candidatos: permisos de las rutas, listado con sus filtros y paginación, formulario, ficha, edición, baja,
carga de CV (reenvío al backend) y el ítem del menú. El backend valida el acceso de verdad: acá se prueba lo que la
pantalla pide, muestra y reenvía."""

import io
from urllib.parse import parse_qsl, urlsplit

import httpx
import pytest

pytestmark = [pytest.mark.frontend]

ID_ANA = "11111111-1111-1111-1111-111111111111"

PERMISOS_EXTERNO = {"puede_eliminar_candidatos": False, "puede_cargar_cv_general": False, "puede_carga_masiva": False}
PERMISOS_TODOS = {"puede_eliminar_candidatos": True, "puede_cargar_cv_general": True, "puede_carga_masiva": True}

ANA = {
    "id": ID_ANA,
    "codigo": "C-1001",
    "empresa_id": "22222222-2222-2222-2222-222222222222",
    "nombre": "Ana",
    "apellido": "Perez",
    "email": "ana@example.com",
    "telefono": "+54 351 1234567",
    "ubicacion": "Cordoba, Cordoba",
    "provincia_id": 1,
    "ciudad_id": 10,
    "dni": None,
    "fecha_nacimiento": None,
    "linkedin_url": None,
    "cv_url": "recruiting/cv/ana.pdf",
    "headline": "Backend Developer",
    "seniority": "Senior",
    "modalidad": "Remoto",
    "skills": ["Python"],
    "habilidades": [],
    "pretension_salarial": None,
    "moneda": "ARS",
    "moneda_pretension": "ARS",
    "estado": "Activo",
    "activo": True,
    "fuente": "Portal Propio",
    "creador_id": None,
    "created_at": "2026-11-10T12:00:00",
    "updated_at": "2026-11-10T12:00:00",
}


def _sesion(client, fake_api, *permisos, rol="usuario", acciones=PERMISOS_TODOS):
    with client.session_transaction() as session:
        session["token"] = "test-token"
        session["user"] = {"id": "user-id", "email": "user@example.com", "nombre": "Test", "rol": rol}
        session["empresa_nombre"] = "Dicsys.AI"
    fake_api.respond("GET", "/permisos/mis-permisos", {"permisos": {p: True for p in permisos}})
    fake_api.respond("GET", "/menus", {"items": []})
    fake_api.respond("GET", "/recruiting/candidatos/permisos", acciones)


def _catalogos(fake_api):
    fake_api.respond(
        "GET", "/recruiting/provincias", [{"provincia_id": 1, "nombre": "Cordoba", "cantidad_ciudades": 1}]
    )
    fake_api.respond(
        "GET",
        "/recruiting/ciudades",
        [{"ciudad_id": 10, "nombre": "Cordoba", "provincia_id": 1, "provincia_nombre": "Cordoba"}],
    )
    fake_api.respond(
        "GET",
        "/recruiting/skills",
        [
            {"id": "s1", "nombre": "Python", "categoria": "Lenguajes", "sinonimos": [], "activo": True},
            {"id": "s2", "nombre": "Django", "categoria": "Lenguajes", "sinonimos": [], "activo": True},
        ],
    )
    fake_api.respond("GET", "/recruiting/habilidades", [{"id": "h1", "nombre": "Liderazgo", "activo": True}])
    fake_api.respond(
        "GET", "/recruiting/niveles-seniority", [{"id": 1, "nombre": "Junior"}, {"id": 2, "nombre": "Senior"}]
    )
    fake_api.respond("GET", "/recruiting/candidatos/perfiles-puesto", ["Backend Developer", "QA Tester"])


def _llamada(fake_api, prefijo):
    return next(c for c in fake_api.calls if c["endpoint"].startswith(prefijo))


# --- Permisos de las rutas ------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ruta", ["/recruiting/candidatos", "/recruiting/candidatos/nuevo", f"/recruiting/candidatos/{ID_ANA}"]
)
def test_sin_sesion_redirige_al_login(frontend_client, ruta):
    respuesta = frontend_client.get(ruta)
    assert respuesta.status_code == 302 and "/login" in respuesta.headers["Location"]


@pytest.mark.parametrize(
    "ruta", ["/recruiting/candidatos", "/recruiting/candidatos/nuevo", f"/recruiting/candidatos/{ID_ANA}"]
)
def test_sin_el_item_candidatos_responde_403(frontend_client, fake_api, ruta):
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.dashboard")
    assert frontend_client.get(ruta).status_code == 403


def test_las_acciones_de_escritura_tambien_exigen_el_item(frontend_client, fake_api):
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.dashboard")
    assert frontend_client.post("/recruiting/candidatos", json={"nombre": "X"}).status_code == 403
    assert frontend_client.put(f"/recruiting/candidatos/{ID_ANA}", json={"nombre": "X"}).status_code == 403
    assert frontend_client.delete(f"/recruiting/candidatos/{ID_ANA}").status_code == 403
    assert frontend_client.post("/recruiting/candidatos/cargar-cv-masivo/iniciar").status_code == 403


# --- Listado: pantalla Vue ------------------------------------------------------------------------------------------
# El listado, sus filtros y la paginación son de la pantalla Vue (frontend-vue/tests/candidatos_listado.test.mjs); acá
# se prueba que la URL original conserva todos los parámetros y que el acceso sigue protegido.


def test_el_listado_abre_la_pantalla_vue_y_no_consulta_al_backend(frontend_client, fake_api):
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.candidatos")

    respuesta = frontend_client.get("/recruiting/candidatos")

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/v2/recruiting/candidatos")
    assert not any(c["endpoint"].startswith("/recruiting/candidatos") for c in fake_api.calls)


def test_el_listado_conserva_filtros_pagina_y_tamano(frontend_client, fake_api):
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.candidatos")

    respuesta = frontend_client.get(
        "/recruiting/candidatos?page=2&limit=50&busqueda=ana perez&seniority=Senior&ubicacion=otros"
        "&puesto=QA Tester&categorias=Lenguajes&skills=Python&estado=Activo&fuente=LinkedIn&accion=cargar-cv"
    )

    consulta = dict(parse_qsl(urlsplit(respuesta.headers["Location"]).query))
    assert urlsplit(respuesta.headers["Location"]).path == "/v2/recruiting/candidatos"
    assert consulta == {
        "page": "2",
        "limit": "50",
        "busqueda": "ana perez",
        "seniority": "Senior",
        "ubicacion": "otros",
        "puesto": "QA Tester",
        "categorias": "Lenguajes",
        "skills": "Python",
        "estado": "Activo",
        "fuente": "LinkedIn",
        "accion": "cargar-cv",
    }


def test_el_listado_conserva_volver_y_descarta_parametros_ajenos(frontend_client, fake_api):
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.candidatos")

    respuesta = frontend_client.get("/recruiting/candidatos?volver=/recruiting/dashboard&ruta=otra&x=1")

    consulta = dict(parse_qsl(urlsplit(respuesta.headers["Location"]).query))
    assert consulta == {"volver": "/recruiting/dashboard"}
    assert urlsplit(respuesta.headers["Location"]).path == "/v2/recruiting/candidatos"


def test_el_admin_entra_al_listado_sin_permisos_de_grupo(frontend_client, fake_api):
    _sesion(frontend_client, fake_api, rol="admin")

    assert frontend_client.get("/recruiting/candidatos").status_code == 302


# --- Formulario de alta ---------------------------------------------------------------------------------------------


def test_el_alta_abre_la_pantalla_vue_conservando_busqueda_y_volver(frontend_client, fake_api):
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.candidatos")

    respuesta = frontend_client.get("/recruiting/candidatos/nuevo")
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/v2/recruiting/candidatos/nuevo")

    respuesta = frontend_client.get(f"/recruiting/candidatos/nuevo?busqueda_id={ID_ANA}&volver=/recruiting/candidatos")
    ubicacion = respuesta.headers["Location"]
    assert "/v2/recruiting/candidatos/nuevo?" in ubicacion
    assert f"busqueda_id={ID_ANA}" in ubicacion and "volver=/recruiting/candidatos" in ubicacion
    # Solo se reenvían busqueda_id y volver: otros parámetros (p. ej. «ruta») no pueden pisar el destino
    respuesta = frontend_client.get("/recruiting/candidatos/nuevo?ruta=otra&x=1")
    assert respuesta.headers["Location"].endswith("/v2/recruiting/candidatos/nuevo")
    # Los catálogos ya no los arma Flask: la pantalla Vue los pide a la API.
    assert not any(c["endpoint"].startswith("/recruiting/skills") for c in fake_api.calls)


def test_el_alta_reenvia_el_cuerpo_normalizado_al_backend(frontend_client, fake_api):
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.candidatos")
    fake_api.respond("POST", "/recruiting/candidatos", ANA, 201)

    respuesta = frontend_client.post(
        "/recruiting/candidatos",
        json={
            "nombre": "Ana",
            "apellido": "Perez",
            "email": " ana@example.com ",
            "skills": "Python, Django",
            "salario": "1.500.000,50",
            "fecha_nacimiento": "25/12/1990",
            "provincia_id": "1",
            "ciudad_id": "",
            "puesto": "Backend Developer",
        },
    )

    assert respuesta.status_code == 201
    assert respuesta.get_json()["success"] is True and respuesta.get_json()["redirect"] == "/recruiting/candidatos"
    enviado = _llamada(fake_api, "/recruiting/candidatos")["data"]
    assert enviado["email"] == "ana@example.com"
    assert enviado["skills"] == ["Python", "Django"]
    assert enviado["pretension_salarial"] == 1500000.5
    assert enviado["fecha_nacimiento"] == "1990-12-25"
    assert (enviado["provincia_id"], enviado["ciudad_id"]) == (1, None)
    assert enviado["headline"] == "Backend Developer"


def test_el_alta_devuelve_el_detalle_del_backend_cuando_falla(frontend_client, fake_api):
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.candidatos")
    fake_api.respond(
        "POST",
        "/recruiting/candidatos",
        {"detail": "Ya existe un candidato registrado con este email por otro usuario."},
        400,
    )

    respuesta = frontend_client.post("/recruiting/candidatos", json={"nombre": "Ana", "email": "ana@example.com"})

    assert respuesta.status_code == 400
    assert respuesta.get_json() == {
        "success": False,
        "error": "Ya existe un candidato registrado con este email por otro usuario.",
    }


def test_el_alta_clasica_con_error_vuelve_a_mostrar_el_formulario(frontend_client, fake_api):
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.candidatos")
    _catalogos(fake_api)
    fake_api.respond("POST", "/recruiting/candidatos", {"detail": "Email: no es un email válido"}, 422)

    respuesta = frontend_client.post("/recruiting/candidatos", data={"nombre": "Ana Perez", "email": "mal"})

    assert respuesta.status_code == 422
    assert "Email: no es un email válido" in respuesta.get_data(as_text=True)


# --- Ficha, edición y baja ------------------------------------------------------------------------------------------


def test_la_ficha_abre_la_pantalla_vue_conservando_volver_y_no_consulta_al_backend(frontend_client, fake_api):
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.candidatos")

    respuesta = frontend_client.get(f"/recruiting/candidatos/{ID_ANA}")
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith(f"/v2/recruiting/candidatos/{ID_ANA}")
    assert not [c for c in fake_api.calls if c["endpoint"].startswith("/recruiting/candidatos/")]

    respuesta = frontend_client.get(f"/recruiting/candidatos/{ID_ANA}?volver=/recruiting/candidatos?page=2&x=1")
    assert f"/v2/recruiting/candidatos/{ID_ANA}?volver=" in respuesta.headers["Location"]
    assert "x=1" not in respuesta.headers["Location"]


def test_la_edicion_de_la_ficha_sigue_siendo_la_pantalla_anterior_en_modo_edicion(frontend_client, fake_api):
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.candidatos")
    _catalogos(fake_api)
    fake_api.respond("GET", f"/recruiting/candidatos/{ID_ANA}", ANA)

    respuesta = frontend_client.get(f"/recruiting/candidatos/{ID_ANA}?editar=1")
    html = respuesta.get_data(as_text=True)

    assert respuesta.status_code == 200
    assert "ana@example.com" in html and "Backend Developer" in html
    assert 'x-init="iniciarEdicion()"' in html


def test_la_edicion_de_un_candidato_que_no_se_puede_ver_vuelve_al_listado_con_el_motivo(frontend_client, fake_api):
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.candidatos")
    fake_api.respond(
        "GET", f"/recruiting/candidatos/{ID_ANA}", {"detail": "No tenes permiso para acceder a este candidato."}, 403
    )

    respuesta = frontend_client.get(f"/recruiting/candidatos/{ID_ANA}?editar=1")

    assert respuesta.status_code == 302 and respuesta.headers["Location"].endswith("/recruiting/candidatos")


def test_un_id_que_no_es_uuid_responde_404_sin_llamar_al_backend(frontend_client, fake_api):
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.candidatos")

    assert frontend_client.get("/recruiting/candidatos/no-es-un-uuid").status_code == 404
    assert not [c for c in fake_api.calls if "no-es-un-uuid" in c["endpoint"]]


def test_la_edicion_normaliza_la_fecha_y_reenvia(frontend_client, fake_api):
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.candidatos")
    fake_api.respond("PUT", f"/recruiting/candidatos/{ID_ANA}", ANA)

    respuesta = frontend_client.put(
        f"/recruiting/candidatos/{ID_ANA}", json={"fecha_nacimiento": "01-02-1985", "seniority": "Junior"}
    )

    assert respuesta.status_code == 200 and respuesta.get_json()["success"] is True
    enviado = _llamada(fake_api, f"/recruiting/candidatos/{ID_ANA}")["data"]
    assert enviado == {"fecha_nacimiento": "1985-02-01", "seniority": "Junior"}


def test_la_edicion_devuelve_el_error_del_backend(frontend_client, fake_api):
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.candidatos")
    fake_api.respond("PUT", f"/recruiting/candidatos/{ID_ANA}", {"detail": "Candidato no encontrado"}, 404)

    respuesta = frontend_client.put(f"/recruiting/candidatos/{ID_ANA}", json={"nombre": "X"})

    assert respuesta.status_code == 404
    assert respuesta.get_json() == {"success": False, "error": "Candidato no encontrado"}


def test_la_baja_redirige_al_listado(frontend_client, fake_api):
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.candidatos")
    fake_api.respond(
        "DELETE", f"/recruiting/candidatos/{ID_ANA}", {"ok": True, "mensaje": "Candidato dado de baja correctamente"}
    )

    respuesta = frontend_client.delete(f"/recruiting/candidatos/{ID_ANA}")

    assert respuesta.status_code == 200
    assert respuesta.get_json() == {"success": True, "redirect": "/recruiting/candidatos"}


def test_la_baja_muestra_por_que_no_se_pudo(frontend_client, fake_api):
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.candidatos")
    fake_api.respond(
        "DELETE",
        f"/recruiting/candidatos/{ID_ANA}",
        {"detail": "Los usuarios del grupo EXTERNOS no pueden eliminar candidatos"},
        403,
    )

    respuesta = frontend_client.delete(f"/recruiting/candidatos/{ID_ANA}")

    assert respuesta.status_code == 403
    assert "EXTERNOS" in respuesta.get_json()["error"]


# --- Carga de CV (reenvío de archivos) ------------------------------------------------------------------------------


class RespuestaHttp:
    def __init__(self, cuerpo, status):
        self._cuerpo, self.status_code = cuerpo, status

    def json(self):
        return self._cuerpo


@pytest.fixture
def backend_http(monkeypatch):
    """Reemplaza el cliente httpx con el que el frontend reenvía los archivos y registra lo que le llega."""
    estado = {"llamadas": [], "respuesta": RespuestaHttp({}, 200)}

    class Cliente:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def request(self, metodo, url, headers=None, files=None):
            estado["llamadas"].append({"metodo": metodo, "url": url, "headers": headers, "files": files})
            return estado["respuesta"]

    monkeypatch.setattr(httpx, "Client", Cliente)
    return estado


def _pdf(nombre="cv.pdf", contenido=b"%PDF-1.4 contenido"):
    return (io.BytesIO(contenido), nombre)


def test_cargar_cv_reenvia_el_archivo_con_el_token_y_redirige_al_listado(frontend_client, fake_api, backend_http):
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.candidatos")
    backend_http["respuesta"] = RespuestaHttp({"ok": True, "candidato": ANA}, 201)

    respuesta = frontend_client.post(
        "/recruiting/candidatos/cargar-cv", data={"archivo": _pdf()}, content_type="multipart/form-data"
    )

    assert respuesta.status_code == 201
    assert (
        respuesta.get_json()["redirect"] == "/recruiting/candidatos"
        and respuesta.get_json()["candidato"]["id"] == ID_ANA
    )
    # El aviso lo muestra la pantalla Vue: no queda un mensaje flash pendiente para la próxima página
    with frontend_client.session_transaction() as sesion:
        assert not sesion.get("_flashes")
    llamada = backend_http["llamadas"][0]
    assert llamada["url"] == "http://backend.test/api/v1/recruiting/candidatos/cargar-cv"
    assert llamada["headers"] == {"Authorization": "Bearer test-token"}
    assert llamada["files"]["archivo"][0] == "cv.pdf"


def test_cargar_cv_con_email_existente_y_cv_distinto_devuelve_ambos_para_comparar(
    frontend_client, fake_api, backend_http
):
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.candidatos")
    backend_http["respuesta"] = RespuestaHttp(
        {
            "ok": False,
            "requiere_comparacion": True,
            "error": "ya existe",
            "actual": {"email": "a@x.com"},
            "nuevo": {"email": "a@x.com"},
        },
        409,
    )

    respuesta = frontend_client.post(
        "/recruiting/candidatos/cargar-cv", data={"archivo": _pdf()}, content_type="multipart/form-data"
    )

    assert respuesta.status_code == 409
    assert respuesta.get_json() == {
        "ok": False,
        "requiere_comparacion": True,
        "actual": {"email": "a@x.com"},
        "nuevo": {"email": "a@x.com"},
    }


def test_cargar_cv_valida_extension_y_tamano_antes_de_llamar_al_backend(frontend_client, fake_api, backend_http):
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.candidatos")

    sin_archivo = frontend_client.post("/recruiting/candidatos/cargar-cv", data={}, content_type="multipart/form-data")
    txt = frontend_client.post(
        "/recruiting/candidatos/cargar-cv", data={"archivo": _pdf("cv.txt")}, content_type="multipart/form-data"
    )
    grande = frontend_client.post(
        "/recruiting/candidatos/cargar-cv",
        data={"archivo": _pdf("cv.pdf", b"0" * (5 * 1024 * 1024 + 1))},
        content_type="multipart/form-data",
    )

    assert (sin_archivo.status_code, txt.status_code, grande.status_code) == (400, 400, 400)
    assert backend_http["llamadas"] == []


def test_el_grupo_externos_no_puede_cargar_cv_desde_el_listado(frontend_client, fake_api, backend_http):
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.candidatos", acciones=PERMISOS_EXTERNO)

    respuesta = frontend_client.post(
        "/recruiting/candidatos/cargar-cv", data={"archivo": _pdf()}, content_type="multipart/form-data"
    )

    assert respuesta.status_code == 403 and backend_http["llamadas"] == []


def test_un_error_5xx_del_backend_muestra_el_mensaje_generico_y_no_el_detalle_interno(
    frontend_client, fake_api, backend_http
):
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.candidatos")
    backend_http["respuesta"] = RespuestaHttp({"detail": "psycopg2.errors.UndefinedTable: relation x"}, 500)

    respuesta = frontend_client.post(
        "/recruiting/candidatos/cargar-cv", data={"archivo": _pdf()}, content_type="multipart/form-data"
    )

    assert respuesta.status_code == 500
    assert respuesta.get_json() == {"ok": False, "error": "No se pudo completar la operación. Intentá nuevamente"}


def test_subir_cv_a_un_candidato_valida_el_limite_de_2_mb(frontend_client, fake_api, backend_http):
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.candidatos")

    respuesta = frontend_client.post(
        f"/recruiting/candidatos/{ID_ANA}/cv",
        data={"archivo": _pdf("cv.pdf", b"0" * (2 * 1024 * 1024 + 1))},
        content_type="multipart/form-data",
    )

    assert respuesta.status_code == 400 and "2 MB" in respuesta.get_json()["error"]
    assert backend_http["llamadas"] == []


def test_subir_cv_a_un_candidato_reenvia_al_backend(frontend_client, fake_api, backend_http):
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.candidatos")
    backend_http["respuesta"] = RespuestaHttp(ANA, 200)

    respuesta = frontend_client.post(
        f"/recruiting/candidatos/{ID_ANA}/cv", data={"archivo": _pdf()}, content_type="multipart/form-data"
    )

    assert respuesta.status_code == 200
    assert backend_http["llamadas"][0]["url"].endswith(f"/recruiting/candidatos/{ID_ANA}/cv")


def test_la_carga_masiva_valida_los_archivos_y_devuelve_el_lote(frontend_client, fake_api, backend_http):
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.candidatos")
    backend_http["respuesta"] = RespuestaHttp(
        {"lote_id": "lote-1", "estado": "preparando", "procesados": 0, "total": 0}, 202
    )

    mal = frontend_client.post(
        "/recruiting/candidatos/cargar-cv-masivo/iniciar",
        data={"archivos": [_pdf("a.exe")]},
        content_type="multipart/form-data",
    )
    bien = frontend_client.post(
        "/recruiting/candidatos/cargar-cv-masivo/iniciar",
        data={"archivos": [_pdf("a.pdf"), _pdf("b.zip")]},
        content_type="multipart/form-data",
    )

    assert mal.status_code == 400
    assert bien.status_code == 200 and bien.get_json()["lote_id"] == "lote-1"
    assert len(backend_http["llamadas"]) == 1
    assert [f[0] for f in backend_http["llamadas"][0]["files"]] == ["archivos", "archivos"]


def test_el_avance_y_la_cancelacion_del_lote_se_consultan_en_el_backend(frontend_client, fake_api, backend_http):
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.candidatos")
    backend_http["respuesta"] = RespuestaHttp(
        {"lote_id": "lote-1", "estado": "procesando", "procesados": 3, "total": 10}, 200
    )

    avance = frontend_client.get("/recruiting/candidatos/cargar-cv-masivo/lote-1/estado")
    cancelar = frontend_client.post("/recruiting/candidatos/cargar-cv-masivo/lote-1/cancelar")

    assert avance.get_json()["procesados"] == 3 and cancelar.status_code == 200
    assert [(c["metodo"], c["url"].rsplit("/", 1)[-1]) for c in backend_http["llamadas"]] == [
        ("GET", "estado"),
        ("POST", "cancelar"),
    ]


def test_un_lote_inexistente_muestra_el_detalle_del_backend(frontend_client, fake_api, backend_http):
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.candidatos")
    backend_http["respuesta"] = RespuestaHttp({"detail": "Lote no encontrado"}, 404)

    respuesta = frontend_client.get("/recruiting/candidatos/cargar-cv-masivo/x/estado")

    assert respuesta.status_code == 404 and respuesta.get_json() == {"ok": False, "error": "Lote no encontrado"}


# --- Menú y navegación ----------------------------------------------------------------------------------------------


MENU_RECRUITING = {
    "items": [
        {
            "codigo": "recruiting",
            "nombre": "Recruiting",
            "icono": "user-check",
            "orden": 0,
            "items": [
                {
                    "codigo": "dashboard",
                    "nombre": "Dashboard Recruiting",
                    "icono": "layout-dashboard",
                    "ruta": "recruiting.dashboard",
                    "es_link": True,
                    "orden": 0,
                    "items": [],
                },
                {
                    "codigo": "candidatos",
                    "nombre": "Candidatos",
                    "icono": "users",
                    "ruta": "recruiting.candidatos",
                    "es_link": True,
                    "orden": 1,
                    "items": [],
                },
                {
                    "codigo": "oportunidades",
                    "nombre": "Búsquedas",
                    "icono": "list",
                    "ruta": None,
                    "es_link": False,
                    "orden": 2,
                    "items": [],
                },
            ],
        }
    ]
}


def test_el_menu_enlaza_candidatos_y_marca_la_seccion_activa(frontend_client, fake_api):
    """El listado ya es una pantalla Vue (su menú lo dibuja la SPA); en la ficha, que sigue en Flask, el ítem se resalta."""
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.candidatos")
    fake_api.respond("GET", "/menus", MENU_RECRUITING)
    _catalogos(fake_api)
    fake_api.respond("GET", f"/recruiting/candidatos/{ID_ANA}", ANA)

    html = frontend_client.get(f"/recruiting/candidatos/{ID_ANA}?editar=1").get_data(as_text=True)

    assert 'href="/recruiting/candidatos"' in html
    fragmento = html.split('href="/recruiting/candidatos"', 1)[1][:400]
    assert "bg-primary-50" in fragmento, "el ítem Candidatos queda resaltado en la ficha"
    assert "Próx." in html  # Búsquedas, Pipeline y Parámetros siguen pendientes


def test_el_dashboard_enlaza_a_candidatos_solo_a_quien_tiene_el_item(frontend_client, fake_api):
    dashboard = {
        "kpis": {
            "busquedas_activas": 1,
            "total_candidatos": 5,
            "postulaciones_en_proceso": 0,
            "skills_catalogo": 1,
            "habilidades_catalogo": 1,
        },
        "avisos": [
            {
                "id": "c-1",
                "tipo": "candidato_nuevo",
                "titulo": "Nuevo candidato: Ana Perez",
                "descripcion": "Se sumó al banco",
                "tiempo": "hoy",
                "icono": "user-plus",
                "color": "emerald",
                "enlace": f"/recruiting/candidatos/{ID_ANA}",
                "created_at": "2026-11-10T12:00:00",
            }
        ],
        "resumen_operativo": {"tasa_candidatos_proceso": 0, "busquedas_totales": 1},
    }
    _sesion(frontend_client, fake_api, "recruiting", "recruiting.dashboard", "recruiting.candidatos")
    fake_api.respond("GET", "/recruiting/dashboard", dashboard)
    con_item = frontend_client.get("/recruiting/dashboard").get_data(as_text=True)

    assert f'href="/recruiting/candidatos/{ID_ANA}"' in con_item
    assert 'href="/recruiting/candidatos?accion=cargar-cv"' in con_item
    assert 'data-testid="kpi-total_candidatos"' in con_item and 'href="/recruiting/candidatos"' in con_item

    _sesion(frontend_client, fake_api, "recruiting", "recruiting.dashboard")
    sin_item = frontend_client.get("/recruiting/dashboard").get_data(as_text=True)
    assert "/recruiting/candidatos" not in sin_item
