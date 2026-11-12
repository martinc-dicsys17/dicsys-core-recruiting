"""Las pantallas de licencias se sirven desde el blueprint de innovacion."""

from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from app import create_app


def _set_session(client):
    with client.session_transaction() as session:
        session["token"] = "test-token"
        session["user"] = {
            "id": "user-id",
            "email": "user@example.com",
            "nombre": "Test",
            "rol": "admin",
        }


def _proveedor():
    return {"id": "proveedor-id", "nombre": "Anthropic"}


def _herramienta():
    return {
        "id": "herramienta-id",
        "nombre": "Claude Code",
        "proveedor_id": "proveedor-id",
        "proveedor": "Anthropic",
        "costo_referencia": 200.0,
        "moneda": "USD",
        "activo": True,
    }


def _licencia(activa=True):
    return {
        "id": "licencia-id",
        "herramienta_id": "herramienta-id",
        "herramienta": "Claude Code",
        "proveedor_id": "proveedor-id",
        "proveedor": "Anthropic",
        "empleado_id": "empleado-id",
        "empleado_nombre": "Lescano, Tomas",
        "fecha_inicio": "01/09/2026",
        "fecha_fin": None,
        "costo_mensual": 200.0,
        "moneda": "USD",
        "nro_pedido_compra": "OC-2026-042",
        "activa": activa,
        "esta_vencida": False,
        "created_at": "2026-09-01T12:00:00",
        "updated_at": "2026-09-01T12:00:00",
    }


def _fila_empleado(licencias=None):
    """Una fila del listado: el empleado con sus licencias."""
    licencias = licencias if licencias is not None else [_licencia()]
    return {
        "empleado_id": "empleado-id",
        "empleado_nombre": "Lescano, Tomas",
        "licencias": licencias,
        "cantidad": len(licencias),
        "cantidad_activas": sum(1 for lic in licencias if lic["activa"]),
        "totales": [{"moneda": "USD", "total": 200.0}],
    }


def _metricas(actual=200.0, anterior=200.0):
    """Las tres cifras van sobre las mismas monedas, aun con delta cero."""
    delta = round(actual - anterior, 2)
    return {
        "mes_actual": [{"moneda": "USD", "total": actual}],
        "mes_anterior": [{"moneda": "USD", "total": anterior}],
        "delta": [{"moneda": "USD", "total": delta}],
        "tendencia": "estable" if not delta else ("sube" if delta > 0 else "baja"),
    }


def _catalogos(fake_api):
    fake_api.respond("GET", "/menus", {"menus": []})
    fake_api.respond("GET", "/innovacion/herramientas", [_herramienta()])
    fake_api.respond("GET", "/innovacion/proveedores", [_proveedor()])
    fake_api.respond(
        "GET",
        "/innovacion/licencias/equipos",
        [
            {"id": "equipo-id", "nombre": "Plataforma", "empleado_ids": ["empleado-id", "otro-id"]},
        ],
    )
    fake_api.respond(
        "GET",
        "/innovacion/licencias/empleados",
        [
            {"id": "empleado-id", "nombre": "Lescano, Tomás", "codigo": "DEV-001"},
            {"id": "otro-id", "nombre": "Sosa, María", "codigo": "DEV-002"},
        ],
    )


def _responder_listado(fake_api, filas=None, metricas=None, query="?pagina=1&por_pagina=25"):
    _catalogos(fake_api)
    fake_api.respond(
        "GET",
        f"/innovacion/licencias/por-empleado{query}",
        {
            "items": filas if filas is not None else [_fila_empleado()],
            "total": 1,
            "pagina": 1,
            "por_pagina": 25,
            "total_paginas": 1,
            "metricas": metricas or _metricas(),
        },
    )


@pytest.mark.frontend
@pytest.mark.deploy_gate
def test_listado_de_licencias_se_sirve_bajo_innovacion(frontend_client, fake_api):
    _set_session(frontend_client)
    _responder_listado(fake_api)

    response = frontend_client.get("/innovacion/licencias")

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Claude Code" in html
    assert "Lescano, Tomas" in html
    assert "/innovacion/licencias/" in html
    assert "/administracion/licencias" not in html


@pytest.mark.frontend
@pytest.mark.deploy_gate
def test_la_fila_es_el_empleado_con_su_total(frontend_client, fake_api):
    """El listado agrupa por persona: nombre, cantidad y total mensual."""
    _set_session(frontend_client)
    _responder_listado(fake_api)

    html = frontend_client.get("/innovacion/licencias").get_data(as_text=True)

    assert "Lescano, Tomas" in html
    assert "1 de 1 activa" in html
    assert 'aria-label="Licencias activas: 1 de 1"' in html
    assert "1 empleado" in html
    assert html.count("U$D 200.00") >= 2


@pytest.mark.frontend
@pytest.mark.deploy_gate
def test_el_checkbox_refleja_y_alterna_activa(frontend_client, fake_api):
    """Sin aprobacion: el checkbox es binario, activa o inactiva."""
    _set_session(frontend_client)
    _responder_listado(
        fake_api,
        filas=[
            _fila_empleado(
                licencias=[
                    _licencia(activa=True),
                    dict(_licencia(activa=False), id="licencia-inactiva", herramienta="Jira"),
                ]
            )
        ],
    )

    html = frontend_client.get("/innovacion/licencias", headers={"HX-Request": "true"}).get_data(as_text=True)

    # Activa: el click la desactiva. Inactiva: el click la activa.
    assert "/innovacion/licencias/licencia-id/activa/false" in html
    assert "/innovacion/licencias/licencia-inactiva/activa/true" in html
    # Las licencias son binarias; la selección de integrantes de un equipo puede ser parcial.
    assert "indeterminate" not in html


@pytest.mark.frontend
@pytest.mark.deploy_gate
def test_el_tooltip_trae_proveedor_costo_y_desde_cuando(frontend_client, fake_api):
    _set_session(frontend_client)
    _responder_listado(fake_api)

    html = frontend_client.get("/innovacion/licencias").get_data(as_text=True)

    assert "Anthropic" in html
    assert "Desde 01/09/2026" in html
    assert "OC-2026-042" in html


@pytest.mark.frontend
@pytest.mark.deploy_gate
def test_muestra_el_gasto_de_este_mes_y_del_anterior(frontend_client, fake_api):
    _set_session(frontend_client)
    _responder_listado(fake_api, metricas=_metricas(actual=300.0, anterior=335.5))

    html = frontend_client.get("/innovacion/licencias").get_data(as_text=True)

    assert "Mes actual" in html
    assert "Mes anterior" in html
    assert "U$D 335.50" in html
    assert "U$D 300.00" in html
    # Baja de gasto: signo menos, verde y flecha hacia abajo.
    assert "−U$D 35.50" in html
    assert "trending-down" in html


@pytest.mark.frontend
@pytest.mark.deploy_gate
def test_las_tres_tarjetas_muestran_las_mismas_monedas(frontend_client, fake_api):
    """Si una moneda falta en una tarjeta, se lee como si faltara el dato."""
    _set_session(frontend_client)
    _responder_listado(
        fake_api,
        metricas={
            "mes_actual": [{"moneda": "ARS", "total": 100.0}, {"moneda": "USD", "total": 171.0}],
            "mes_anterior": [{"moneda": "ARS", "total": 100.0}, {"moneda": "USD", "total": 206.5}],
            "delta": [{"moneda": "ARS", "total": 0.0}, {"moneda": "USD", "total": -35.5}],
            "tendencia": "baja",
        },
    )

    html = frontend_client.get("/innovacion/licencias").get_data(as_text=True)

    # Los pesos aparecen en las tres, aunque no varien.
    assert html.count("$ 100.00") >= 2
    assert "$ 0.00" in html
    assert "−U$D 35.50" in html


@pytest.mark.frontend
@pytest.mark.deploy_gate
def test_marca_en_rojo_cuando_el_gasto_sube(frontend_client, fake_api):
    _set_session(frontend_client)
    _responder_listado(fake_api, metricas=_metricas(actual=400.0, anterior=300.0))

    html = frontend_client.get("/innovacion/licencias").get_data(as_text=True)

    assert "+U$D 100.00" in html
    assert "trending-up" in html
    assert "bg-red-50/40" in html


@pytest.mark.frontend
@pytest.mark.deploy_gate
def test_sin_variacion_no_pinta_alarma(frontend_client, fake_api):
    _set_session(frontend_client)
    _responder_listado(fake_api, metricas=_metricas(actual=200.0, anterior=200.0))

    html = frontend_client.get("/innovacion/licencias").get_data(as_text=True)

    # Se muestra la moneda en cero, sin flecha ni color de alarma en la tarjeta.
    assert "trending-up" not in html
    assert "trending-down" not in html
    assert "bg-red-50/40" not in html
    assert "bg-emerald-50/40" not in html


@pytest.mark.frontend
@pytest.mark.deploy_gate
def test_los_filtros_son_equipo_proveedor_y_empleado(frontend_client, fake_api):
    """Los demas filtros se quitaron; estos tres alimentan del catalogo."""
    _set_session(frontend_client)
    _responder_listado(fake_api)

    html = frontend_client.get("/innovacion/licencias").get_data(as_text=True)

    assert 'x-model="filtros.equipo_ids"' in html
    assert 'x-model="filtros.proveedor_id"' in html
    assert 'x-model="buscar"' in html
    assert 'x-model="filtros.empleado_id"' not in html
    assert "alternarEmpleado(" in html
    assert "DEV-001" in html
    assert any(call["endpoint"] == "/innovacion/licencias/empleados" for call in fake_api.calls)
    assert not any(call["endpoint"].startswith("/nomina/") for call in fake_api.calls)
    assert "Plataforma" in html
    # Estado y herramienta ya no son filtros.
    assert 'x-model="filtros.estado"' not in html
    assert 'x-model="filtros.herramienta_id"' not in html


@pytest.mark.frontend
@pytest.mark.deploy_gate
def test_el_alta_es_un_modal_no_una_pantalla(frontend_client, fake_api):
    """Nueva Licencia abre el modal del listado, no navega."""
    _set_session(frontend_client)
    _responder_listado(fake_api)

    html = frontend_client.get("/innovacion/licencias").get_data(as_text=True)

    assert '@click="abrirNueva()"' in html
    assert 'x-show="showNueva"' in html
    assert '"empleado_ids": ["empleado-id", "otro-id"]' in html
    # El motivo salio de la carga.
    assert 'x-model="nueva.motivo"' not in html

    # Y la ruta de alta ya no sirve una pantalla.
    assert frontend_client.get("/innovacion/licencias/nuevo").status_code == 405


@pytest.mark.frontend
@pytest.mark.deploy_gate
def test_cada_fila_ofrece_alta_rapida_para_ese_empleado(frontend_client, fake_api):
    _set_session(frontend_client)
    _responder_listado(fake_api)

    html = frontend_client.get("/innovacion/licencias").get_data(as_text=True)

    assert "nueva-licencia-para" in html
    assert "Agregar una licencia a Lescano, Tomas" in html


@pytest.mark.frontend
@pytest.mark.deploy_gate
def test_la_paginacion_conserva_los_filtros(frontend_client, fake_api):
    """Pasar de pagina perdia todos los filtros menos la busqueda."""
    _set_session(frontend_client)
    _catalogos(fake_api)
    fake_api.respond(
        "GET",
        "/innovacion/licencias/por-empleado?pagina=1&por_pagina=25&proveedor_id=proveedor-id",
        {
            "items": [_fila_empleado()],
            "total": 40,
            "pagina": 1,
            "por_pagina": 25,
            "total_paginas": 2,
            "metricas": _metricas(),
        },
    )

    html = frontend_client.get("/innovacion/licencias?proveedor_id=proveedor-id").get_data(as_text=True)

    assert "pagina=2" in html
    assert "proveedor_id=proveedor-id" in html


@pytest.mark.frontend
@pytest.mark.deploy_gate
def test_rutas_viejas_de_administracion_ya_no_existen(frontend_client, fake_api):
    _set_session(frontend_client)
    fake_api.respond("GET", "/menus", {"menus": []})

    assert frontend_client.get("/administracion/licencias").status_code == 404
    assert frontend_client.get("/administracion/licencias/nuevo").status_code == 404


class _JerarquiaLicencias(HTMLParser):
    """Registra los details que contienen cada enlace de edición real."""

    def __init__(self, html):
        super().__init__()
        self.ancestros = []
        self.licencias = []
        self.enlaces = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "details":
            self.ancestros.append(attrs)
        if tag == "a" and attrs.get("href"):
            self.enlaces.append(attrs["href"])
        if tag == "a" and attrs.get("href", "").endswith("/editar"):
            self.licencias.append(tuple(self.ancestros))

    def handle_endtag(self, tag):
        if tag == "details":
            self.ancestros.pop()


def _responder_equipos(fake_api, query="?pagina=1&por_pagina=25", total_paginas=1):
    _catalogos(fake_api)
    fila = _fila_empleado()
    sin_equipo = dict(
        _fila_empleado(
            [
                dict(
                    _licencia(),
                    id="licencia-sin-equipo",
                    empleado_id="empleado-sin-equipo",
                    empleado_nombre="Sosa, Ana",
                    costo_mensual=100.0,
                ),
            ]
        ),
        empleado_id="empleado-sin-equipo",
        empleado_nombre="Sosa, Ana",
        totales=[{"moneda": "USD", "total": 100.0}],
    )
    fake_api.respond(
        "GET",
        f"/innovacion/licencias/por-equipo{query}",
        {
            "items": [
                {
                    "equipo_id": equipo_id,
                    "equipo_nombre": nombre,
                    "empleados": [fila if equipo_id else sin_equipo],
                    "total_empleados": 1,
                    "totales": (fila if equipo_id else sin_equipo)["totales"],
                }
                for equipo_id, nombre in [("eq-1", "Plataforma"), ("eq-2", "Innovación"), (None, "Sin equipo")]
            ],
            "total": 3,
            "total_empleados": 2,
            "pagina": 1,
            "total_paginas": total_paginas,
            "metricas": _metricas(actual=300.0, anterior=300.0),
        },
    )


@pytest.mark.frontend
@pytest.mark.deploy_gate
def test_vista_equipos_anida_empleados_y_licencias(frontend_client, fake_api):
    _set_session(frontend_client)
    _responder_equipos(fake_api)

    html = frontend_client.get("/innovacion/licencias?vista=equipos").get_data(as_text=True)

    assert 'aria-controls="licencias-vistas"' in html
    assert "Sin equipo" in html
    jerarquia = _JerarquiaLicencias(html)
    assert len(jerarquia.licencias) == 3
    assert [ancestros[0]["data-equipo-id"] for ancestros in jerarquia.licencias] == ["eq-1", "eq-2", ""]
    assert all(len(ancestros) == 1 for ancestros in jerarquia.licencias)
    assert 'data-empleado-id="empleado-id"' in html
    assert 'data-empleado-id="empleado-sin-equipo"' in html
    assert "U$D 300.00" in html
    assert "U$D 500.00" not in html
    assert "/innovacion/licencias/licencia-id/activa/false" in html
    assert 'data-url="/innovacion/licencias/licencia-id"' in html
    assert "borrarLicencia($el)" in html
    assert 'id="licencias-baja-titulo"' in html
    assert "Se quitarán en cascada todas sus licencias" in html
    assert "Se eliminarán en cascada todas sus herramientas y sus licencias" in html
    assert "de todos los empleados de la empresa activa." in html
    assert "hx-confirm=" not in html


@pytest.mark.frontend
@pytest.mark.deploy_gate
@pytest.mark.parametrize("vista", ["empleados", "equipos"])
def test_fragmento_conserva_multiseleccion_vista_y_filtros_sin_recargar_catalogos(frontend_client, fake_api, vista):
    _set_session(frontend_client)
    query = "?pagina=1&por_pagina=25&buscar=A%26B&equipo_id=eq-1&equipo_id=eq-2&proveedor_id=proveedor-id&empleado_id=empleado-id&empleado_id=otro-id"
    if vista == "equipos":
        _responder_equipos(fake_api, query=query, total_paginas=2)
    else:
        _responder_listado(fake_api, query=query)
        fake_api.respond(
            "GET",
            f"/innovacion/licencias/por-empleado{query}",
            {
                "items": [_fila_empleado()],
                "total": 30,
                "pagina": 1,
                "por_pagina": 25,
                "total_paginas": 2,
                "metricas": _metricas(),
            },
        )

    response = frontend_client.get(
        "/innovacion/licencias",
        query_string=[
            ("vista", vista),
            ("buscar", "A&B"),
            ("equipo_id", "eq-1"),
            ("equipo_id", " eq-2 "),
            ("equipo_id", ""),
            ("equipo_id", "eq-1"),
            ("proveedor_id", "proveedor-id"),
            ("empleado_id", "empleado-id"),
            ("empleado_id", ""),
            ("empleado_id", " otro-id "),
            ("empleado_id", "empleado-id"),
        ],
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert "<html" not in html
    siguiente = next(enlace for enlace in _JerarquiaLicencias(html).enlaces if "pagina=2" in enlace)
    assert parse_qs(urlsplit(siguiente).query) == {
        "pagina": ["2"],
        "vista": [vista],
        "buscar": ["A&B"],
        "equipo_id": ["eq-1", "eq-2"],
        "proveedor_id": ["proveedor-id"],
        "empleado_id": ["empleado-id", "otro-id"],
    }
    consultas = [call["endpoint"] for call in fake_api.calls if call["endpoint"] != "/menus"]
    assert consultas == [f"/innovacion/licencias/{'por-equipo' if vista == 'equipos' else 'por-empleado'}{query}"]
    if vista == "equipos":
        assert "2 empleados" in html
        assert "3 grupos" in html


@pytest.mark.frontend
@pytest.mark.deploy_gate
@pytest.mark.parametrize("vista", ["empleados", "equipos"])
def test_render_inicial_conserva_empleados_seleccionados(frontend_client, fake_api, vista):
    _set_session(frontend_client)
    query = "?pagina=1&por_pagina=25&empleado_id=empleado-id&empleado_id=otro-id"
    if vista == "equipos":
        _responder_equipos(fake_api, query=query)
    else:
        _responder_listado(fake_api, query=query)

    response = frontend_client.get(
        "/innovacion/licencias",
        query_string=[
            ("vista", vista),
            ("empleado_id", "empleado-id"),
            ("empleado_id", "otro-id"),
        ],
    )

    assert response.status_code == 200
    assert 'empleado_ids: ["empleado-id", "otro-id"]' in response.get_data(as_text=True)


@pytest.mark.frontend
@pytest.mark.deploy_gate
def test_vista_desconocida_usa_empleados(frontend_client, fake_api):
    _set_session(frontend_client)
    _responder_listado(fake_api)

    html = frontend_client.get("/innovacion/licencias?vista=desconocida").get_data(as_text=True)

    assert "<table" not in html
    ancestros = _JerarquiaLicencias(html).licencias[0]
    assert ancestros == ()
    assert 'data-empleado-id="empleado-id"' in html


@pytest.mark.frontend
@pytest.mark.deploy_gate
@pytest.mark.parametrize("catalogo", ["herramientas", "proveedores"])
@pytest.mark.parametrize("status", [204, 409])
def test_borrado_catalogo_propaga_resultado_y_conteo(frontend_client, fake_api, catalogo, status):
    _set_session(frontend_client)
    detalle = "'OenAI' está asignado a 1 herramienta"
    fake_api.respond("DELETE", f"/innovacion/{catalogo}/item-id", {"detail": detalle}, status=status)

    response = frontend_client.delete(f"/innovacion/{catalogo}/item-id")

    assert response.status_code == status
    if status == 409:
        assert response.json["detail"] == detalle


@pytest.mark.frontend
@pytest.mark.deploy_gate
def test_reapuntar_herramienta_envia_proveedor_y_permite_desasignarlo(frontend_client, fake_api):
    _set_session(frontend_client)
    fake_api.respond("PUT", "/innovacion/herramientas/item-id", _herramienta())

    response = frontend_client.put("/innovacion/herramientas/item-id", json={"proveedor_id": ""})

    assert response.status_code == 200
    assert fake_api.calls[-1]["data"] == {"proveedor_id": None}


@pytest.mark.frontend
@pytest.mark.deploy_gate
@pytest.mark.parametrize("status", [204, 404])
def test_borrar_licencia_refresca_o_devuelve_error_visible(frontend_client, fake_api, status):
    _set_session(frontend_client)
    fake_api.respond("DELETE", "/innovacion/licencias/item-id", {"detail": "Licencia no encontrada"}, status=status)

    response = frontend_client.delete("/innovacion/licencias/item-id")

    if status == 204:
        assert response.status_code == 200
        assert response.headers["HX-Trigger"] == "licenciaEstadoCambiado"
    else:
        assert response.status_code == 404
        assert response.json["detail"] == "Licencia no encontrada"


@pytest.mark.frontend
@pytest.mark.deploy_gate
@pytest.mark.parametrize("recurso", ["licencias", "herramientas", "proveedores"])
@pytest.mark.parametrize("status", [204, 404, 409])
def test_bajas_con_respuesta_http_real(monkeypatch, recurso, status):
    """Un 204 real no tiene JSON; FakeApi evitaba ese paso del proxy."""
    llamadas = []
    detalle = "Licencia no encontrada" if status == 404 else "Tiene licencias asignadas"
    ruta = f"/innovacion/{recurso}/item-id"

    def backend(request):
        llamadas.append(request)
        if status == 204:
            return httpx.Response(204)
        return httpx.Response(status, json={"detail": detalle})

    client_http = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: client_http(transport=httpx.MockTransport(backend), **kwargs))
    app = create_app(
        config={
            "TESTING": True,
            "SECRET_KEY": "frontend-test-secret",
            "API_URL": "http://backend.test",
        }
    )
    client = app.test_client()
    _set_session(client)

    response = client.delete(ruta)

    assert len(llamadas) == 1
    assert llamadas[0].method == "DELETE"
    assert str(llamadas[0].url) == f"http://backend.test/api/v1{ruta}"
    assert llamadas[0].headers["Authorization"] == "Bearer test-token"
    if status == 204:
        assert response.status_code == (200 if recurso == "licencias" else 204)
        assert response.data == b""
        if recurso == "licencias":
            assert response.headers["HX-Trigger"] == "licenciaEstadoCambiado"
    else:
        assert response.status_code == status
        assert response.json["detail"] == detalle


@pytest.mark.frontend
@pytest.mark.deploy_gate
@pytest.mark.parametrize("costo,normalizado", [("120,50", 120.5), (0, 0), ("", None), (99.9, 99.9)])
def test_alta_lote_normaliza_campos_y_conserva_seleccion(frontend_client, fake_api, costo, normalizado):
    _set_session(frontend_client)
    fake_api.respond("POST", "/innovacion/licencias/lote", {"creadas": 2}, status=201)

    response = frontend_client.post(
        "/innovacion/licencias/lote",
        json={
            "herramienta_id": "herramienta-id",
            "empleado_ids": ["empleado-id", "otro-id"],
            "fecha_inicio": "06/09/2026",
            "fecha_fin": "",
            "costo_mensual": costo,
            "moneda": "USD",
            "nro_pedido_compra": "OC-2026-042",
        },
    )

    assert response.status_code == 201
    assert response.json == {"creadas": 2}
    assert fake_api.calls[-1]["data"] == {
        "herramienta_id": "herramienta-id",
        "empleado_ids": ["empleado-id", "otro-id"],
        "fecha_inicio": "2026-09-06",
        "fecha_fin": None,
        "costo_mensual": normalizado,
        "moneda": "USD",
        "nro_pedido_compra": "OC-2026-042",
    }
    assert fake_api.calls[-1]["token"] == "test-token"


@pytest.mark.frontend
@pytest.mark.deploy_gate
@pytest.mark.parametrize("status", [404, 409, 422])
def test_alta_lote_preserva_error_backend(frontend_client, fake_api, status):
    _set_session(frontend_client)
    detalle = "No se pudo asignar la licencia a los empleados seleccionados"
    fake_api.respond("POST", "/innovacion/licencias/lote", {"detail": detalle}, status=status)

    response = frontend_client.post("/innovacion/licencias/lote", json={"empleado_ids": []})

    assert response.status_code == status
    assert response.json["detail"] == detalle


@pytest.mark.frontend
@pytest.mark.deploy_gate
def test_normalizador_compartido_conserva_edicion(frontend_client, fake_api):
    _set_session(frontend_client)
    fake_api.respond("PUT", "/innovacion/licencias/licencia-id", _licencia())

    response = frontend_client.post(
        "/innovacion/licencias/licencia-id/editar",
        headers={"HX-Request": "true"},
        data={
            "herramienta_id": "herramienta-id",
            "empleado_id": "empleado-id",
            "fecha_inicio": "06/09/2026",
            "fecha_fin": "2026-12-31",
            "costo_mensual": "30,25",
        },
    )

    assert response.status_code == 200
    assert fake_api.calls[-1]["data"] == {
        "herramienta_id": "herramienta-id",
        "empleado_id": "empleado-id",
        "fecha_inicio": "2026-09-06",
        "fecha_fin": "2026-12-31",
        "costo_mensual": 30.25,
        "moneda": "ARS",
        "nro_pedido_compra": None,
    }


@pytest.mark.frontend
@pytest.mark.deploy_gate
@pytest.mark.parametrize("costo", ["1.000,00", "abc", "NaN", "Infinity"])
def test_lote_rechaza_costo_invalido_antes_de_crear(frontend_client, fake_api, costo):
    _set_session(frontend_client)

    response = frontend_client.post(
        "/innovacion/licencias/lote",
        json={
            "empleado_ids": ["empleado-id", "otro-id"],
            "costo_mensual": costo,
        },
    )

    assert response.status_code == 422
    assert response.json["detail"] == "Ingresá un costo válido, por ejemplo 1000,50"
    assert not fake_api.calls


@pytest.mark.frontend
@pytest.mark.deploy_gate
def test_costo_invalido_tampoco_se_borra_en_edicion(frontend_client, fake_api):
    _set_session(frontend_client)

    response = frontend_client.post(
        "/innovacion/licencias/licencia-id/editar", data={"costo_mensual": "abc"}, headers={"HX-Request": "true"}
    )

    assert "Ingresá un costo válido" in response.get_data(as_text=True)
    assert not fake_api.calls


@pytest.mark.frontend
@pytest.mark.deploy_gate
def test_lote_muestra_error_real_de_fechas_sin_conversion_a_url(frontend_client, fake_api):
    _set_session(frontend_client)
    mensaje = "La fecha de fin no puede ser anterior a la fecha de inicio"
    fake_api.respond(
        "POST",
        "/innovacion/licencias/lote",
        {
            "detail": [
                {
                    "type": "value_error",
                    "loc": ["body"],
                    "msg": "Value error, " + mensaje,
                }
            ]
        },
        status=422,
    )

    response = frontend_client.post(
        "/innovacion/licencias/lote",
        json={
            "empleado_ids": ["empleado-id"],
            "fecha_inicio": "2026-09-06",
            "fecha_fin": "2026-09-01",
        },
    )

    assert response.status_code == 422
    assert mensaje in response.json["detail"]
    assert "http://" not in response.json["detail"]


@pytest.mark.frontend
@pytest.mark.deploy_gate
@pytest.mark.parametrize(
    "metodo, sufijo, datos",
    [
        ("POST", "/preview", {"herramienta_id": "h1", "equipo_ids": ["q1"]}),
        ("DELETE", "", {"licencia_ids": ["l1", "l2"]}),
    ],
)
def test_revocacion_propaga_seleccion_y_errores(frontend_client, fake_api, metodo, sufijo, datos):
    _set_session(frontend_client)
    endpoint = "/innovacion/licencias/revocacion" + sufijo
    fake_api.respond(metodo, endpoint, {"detail": "Sin permiso"}, status=403)
    respuesta = frontend_client.open(endpoint, method=metodo, json=datos)
    assert respuesta.status_code == 403
    assert fake_api.calls[-1]["data"] == datos
