"""Administración → Proveedores: páginas, permisos por pantalla, relays a la API y adjunto."""

import httpx
import pytest

pytestmark = [pytest.mark.frontend, pytest.mark.deploy_gate]


def _sesion(client, rol="usuario"):
    with client.session_transaction() as session:
        session["token"] = "test-token"
        session["user"] = {"id": "user-id", "email": "user@example.com", "nombre": "Test", "rol": rol}


def _permisos(fake_api, *items):
    permisos = {"admin_contable": True, **{f"admin_contable.{i}": True for i in items}}
    fake_api.respond("GET", "/permisos/mis-permisos", {"permisos": permisos})
    fake_api.respond("GET", "/menus", {"items": []})


@pytest.mark.parametrize(
    "ruta, item, texto",
    [
        ("/administracion/proveedores", "proveedores", "Nuevo proveedor"),
        ("/administracion/evaluaciones-proveedores", "evaluacion_proveedores", "Evaluación de Proveedores"),
        (
            "/administracion/config-evaluaciones-proveedores",
            "evaluacion_config",
            "Campañas de evaluación de proveedores",
        ),
    ],
)
def test_cada_pantalla_exige_su_permiso(frontend_client, fake_api, ruta, item, texto):
    _sesion(frontend_client)
    _permisos(fake_api, "clientes")
    assert frontend_client.get(ruta).status_code == 403

    _permisos(fake_api, item)
    respuesta = frontend_client.get(ruta)
    assert respuesta.status_code == 200
    assert texto in respuesta.get_data(as_text=True)


def test_relay_del_registro_pasa_metodo_query_y_cuerpo(frontend_client, fake_api):
    _sesion(frontend_client)
    _permisos(fake_api, "proveedores")
    fake_api.respond("GET", "/proveedores?pagina=2&estado=baja", {"items": [], "total": 0})
    fake_api.respond("PUT", "/proveedores/p-1", {"detail": "Ya existe el proveedor «ODOO»"}, status=409)

    assert frontend_client.get("/administracion/proveedores/api?pagina=2&estado=baja").json == {"items": [], "total": 0}
    respuesta = frontend_client.put("/administracion/proveedores/api/p-1", json={"nombre": "ODOO"})

    assert respuesta.status_code == 409 and respuesta.json["detail"] == "Ya existe el proveedor «ODOO»"
    assert fake_api.calls[-1] == {
        "method": "PUT",
        "endpoint": "/proveedores/p-1",
        "data": {"nombre": "ODOO"},
        "token": "test-token",
    }


def test_relay_del_tablero_solo_permite_sus_rutas(frontend_client, fake_api):
    _sesion(frontend_client)
    _permisos(fake_api, "evaluacion_proveedores")
    fake_api.respond("GET", "/evaluaciones-proveedores/tablero", {"items": []})
    fake_api.respond("PUT", "/evaluaciones-proveedores/items/i-1", {"id": "i-1"})

    assert frontend_client.get("/administracion/evaluaciones-proveedores/api/tablero").status_code == 200
    assert (
        frontend_client.put(
            "/administracion/evaluaciones-proveedores/api/items/i-1", json={"mal_manejo": "No"}
        ).status_code
        == 200
    )
    # La configuración es de otra pantalla (otro permiso)
    assert frontend_client.get("/administracion/evaluaciones-proveedores/api/configuracion").status_code == 404


def test_config_permite_eliminar_evaluaciones_con_confirmacion(frontend_client, fake_api):
    _sesion(frontend_client)
    _permisos(fake_api, "evaluacion_config")
    html = frontend_client.get("/administracion/config-evaluaciones-proveedores").get_data(as_text=True)
    assert '@click="porEliminar = e"' in html and '@click="eliminarEvaluacion()"' in html
    assert 'aria-labelledby="titulo-eliminar"' in html

    fake_api.respond("DELETE", "/evaluaciones-proveedores/evaluaciones/ev-1", {"message": "Eliminada"})
    respuesta = frontend_client.delete("/administracion/config-evaluaciones-proveedores/api/evaluaciones/ev-1")
    assert respuesta.status_code == 200
    assert fake_api.calls[-1]["method"] == "DELETE"


def test_config_tiene_la_pestana_de_auto_generacion(frontend_client, fake_api):
    _sesion(frontend_client)
    _permisos(fake_api, "evaluacion_config")
    html = frontend_client.get("/administracion/config-evaluaciones-proveedores?tab=autogeneracion").get_data(
        as_text=True
    )
    assert "configEvaluaciones('/administracion/config-evaluaciones-proveedores', 'autogeneracion')" in html
    assert "@click=\"cambiarPestana('autogeneracion')\"" in html
    assert "Auto-generación de evaluaciones" in html and "guardarAutogeneracion()" in html
    assert "(día y mes, sin año)" in html

    fake_api.respond("PUT", "/evaluaciones-proveedores/autogeneracion", {"activa": False})
    respuesta = frontend_client.put(
        "/administracion/config-evaluaciones-proveedores/api/autogeneracion", json={"activa": False}
    )
    assert respuesta.status_code == 200
    assert fake_api.calls[-1]["data"] == {"activa": False}


def test_relay_de_config_exige_el_permiso_de_admin(frontend_client, fake_api):
    _sesion(frontend_client)
    _permisos(fake_api, "evaluacion_proveedores")
    assert frontend_client.get("/administracion/config-evaluaciones-proveedores/api/configuracion").status_code == 403

    _permisos(fake_api, "evaluacion_config")
    fake_api.respond("POST", "/evaluaciones-proveedores/importaciones", {"id": "imp-1"}, status=201)
    respuesta = frontend_client.post("/administracion/config-evaluaciones-proveedores/api/importaciones", json={})
    assert respuesta.status_code == 201 and respuesta.json == {"id": "imp-1"}
    assert frontend_client.get("/administracion/config-evaluaciones-proveedores/api/tablero").status_code == 404


@pytest.fixture
def backend_http(monkeypatch):
    pedidos, respuestas = [], []

    def manejador(pedido):
        pedidos.append(pedido)
        return respuestas.pop(0)

    cliente_real = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: cliente_real(transport=httpx.MockTransport(manejador), **kw))
    return pedidos, respuestas


def test_adjunto_se_sube_y_descarga_por_el_backend(frontend_client, fake_api, backend_http):
    pedidos, respuestas = backend_http
    _sesion(frontend_client)
    _permisos(fake_api, "proveedores")
    respuestas.append(httpx.Response(200, json={"id": "p-1", "politica_nda_archivo_nombre": "nda.pdf"}))
    respuestas.append(
        httpx.Response(
            200,
            content=b"%PDF-1.4",
            headers={"content-type": "application/pdf", "Content-Disposition": "attachment; filename*=UTF-8''nda.pdf"},
        )
    )

    import io

    subida = frontend_client.post(
        "/administracion/proveedores/p-1/nda",
        content_type="multipart/form-data",
        data={"archivo": (io.BytesIO(b"%PDF-1.4"), "nda.pdf", "application/pdf")},
        headers={"User-Agent": "Navegador/1.0"},
    )
    descarga = frontend_client.get("/administracion/proveedores/p-1/nda")

    assert subida.status_code == 200 and subida.json["politica_nda_archivo_nombre"] == "nda.pdf"
    assert str(pedidos[0].url) == "http://backend.test/api/v1/proveedores/p-1/nda"
    assert pedidos[0].headers["Authorization"] == "Bearer test-token"
    assert pedidos[0].headers["X-Cliente-User-Agent"] == "Navegador/1.0"
    assert b'filename="nda.pdf"' in pedidos[0].read()
    assert descarga.status_code == 200 and descarga.data == b"%PDF-1.4"
    assert descarga.headers["Content-Disposition"].startswith("attachment")


def test_documentos_se_suben_varios_y_se_descargan_por_el_backend(frontend_client, fake_api, backend_http):
    pedidos, respuestas = backend_http
    _sesion(frontend_client)
    _permisos(fake_api, "proveedores")
    respuestas.append(httpx.Response(201, json=[{"id": "d-1"}, {"id": "d-2"}]))
    respuestas.append(
        httpx.Response(
            200,
            content=b"%PDF-1.4",
            headers={
                "content-type": "application/pdf",
                "Content-Disposition": "attachment; filename*=UTF-8''Contrato%202026.pdf",
            },
        )
    )
    respuestas.append(
        httpx.Response(
            200, content=b"\x89PNG", headers={"content-type": "image/png", "Cache-Control": "private, max-age=86400"}
        )
    )
    respuestas.append(httpx.Response(404, json={"detail": "El documento no tiene miniatura"}))

    import io

    subida = frontend_client.post(
        "/administracion/proveedores/p-1/documentos",
        content_type="multipart/form-data",
        data={
            "archivos": [
                (io.BytesIO(b"%PDF-1.4"), "Contrato 2026.pdf", "application/pdf"),
                (io.BytesIO(b"PK"), "Costos.xlsx", "application/octet-stream"),
            ]
        },
    )
    descarga = frontend_client.get("/administracion/proveedores/p-1/documentos/d-1")
    miniatura = frontend_client.get("/administracion/proveedores/p-1/documentos/d-1/miniatura")
    sin_miniatura = frontend_client.get("/administracion/proveedores/p-1/documentos/d-2/miniatura")

    assert subida.status_code == 201 and len(subida.json) == 2
    assert str(pedidos[0].url) == "http://backend.test/api/v1/proveedores/p-1/documentos"
    cuerpo = pedidos[0].read()
    assert cuerpo.count(b'name="archivos"') == 2 and b'filename="Contrato 2026.pdf"' in cuerpo
    assert descarga.status_code == 200 and descarga.data == b"%PDF-1.4"
    assert descarga.headers["Content-Disposition"] == "attachment; filename*=UTF-8''Contrato%202026.pdf"
    assert miniatura.status_code == 200 and miniatura.headers["Cache-Control"] == "private, max-age=86400"
    assert sin_miniatura.status_code == 404
    # Sin archivos no llega a la API
    vacia = frontend_client.post(
        "/administracion/proveedores/p-1/documentos", content_type="multipart/form-data", data={}
    )
    assert vacia.status_code == 422 and len(pedidos) == 4


def test_documentos_y_estado_en_la_vista_y_la_edicion(frontend_client, fake_api):
    _sesion(frontend_client)
    _permisos(fake_api, "proveedores")
    fake_api.respond("GET", "/proveedores/p-1", {**DETALLE, "activo": False})

    vista = frontend_client.get("/administracion/proveedores/p-1").get_data(as_text=True)
    edicion = frontend_client.get("/administracion/proveedores/p-1/editar?tab=documentos").get_data(as_text=True)
    alta = frontend_client.get("/administracion/proveedores/nuevo").get_data(as_text=True)

    # Vista: pestaña con miniatura (o el tipo si no hay) y descarga; estado «Inactivo»
    assert "@click=\"tab = 'documentos'\"" in vista and "Contrato 2026.pdf" in vista
    assert 'src="/administracion/proveedores/p-1/documentos/d-1/miniatura"' in vista
    assert "/documentos/d-2/miniatura" not in vista and ">XLSX</span>" in vista
    assert 'href="/administracion/proveedores/p-1/documentos/d-1"' in vista and "2,4 MB" in vista and "850 B" in vista
    assert ">Inactivo</span>" in vista and "De baja" not in vista
    # Edición: abre en Documentos, sube varios a la vez y tiene el Estado
    assert "tab: 'documentos'" in edicion and 'type="file" multiple' in edicion
    assert 'accept=".pdf,.xlsx,.png,.jpg,.jpeg,.doc,.docx"' in edicion
    assert '<option value="inactivo">Inactivo</option>' in edicion
    # Alta: sin documentos ni estado (nace activo)
    assert 'type="file" multiple' not in alta and '<option value="inactivo">' not in alta


def test_alta_con_acuerdo_firmado_manda_datos_y_adjunto_juntos(frontend_client, fake_api, backend_http):
    pedidos, respuestas = backend_http
    _sesion(frontend_client)
    _permisos(fake_api, "proveedores")
    respuestas.append(httpx.Response(201, json={"id": "p-9", "politica_nda_archivo_nombre": "acuerdo.pdf"}))
    respuestas.append(httpx.Response(422, json={"detail": "Faltan datos obligatorios: usuario referente"}))

    import io

    alta = frontend_client.post(
        "/administracion/proveedores/nuevo/con-adjunto",
        content_type="multipart/form-data",
        data={
            "datos": '{"nombre": "ODOO", "acuerdo_servicio": "Si"}',
            "archivo": (io.BytesIO(b"%PDF-1.4"), "acuerdo.pdf", "application/pdf"),
        },
    )
    assert alta.status_code == 201 and alta.json["id"] == "p-9"
    assert str(pedidos[0].url) == "http://backend.test/api/v1/proveedores/con-adjunto"
    assert pedidos[0].headers["Authorization"] == "Bearer test-token"
    cuerpo = pedidos[0].read()
    assert b'filename="acuerdo.pdf"' in cuerpo and b'"acuerdo_servicio": "Si"' in cuerpo

    rechazo = frontend_client.post(
        "/administracion/proveedores/nuevo/con-adjunto",
        content_type="multipart/form-data",
        data={"datos": "{}", "archivo": (io.BytesIO(b"%PDF-1.4"), "a.pdf", "application/pdf")},
    )
    assert rechazo.status_code == 422 and rechazo.json["detail"] == "Faltan datos obligatorios: usuario referente"
    # Sin archivo no llega a la API
    sin_archivo = frontend_client.post("/administracion/proveedores/nuevo/con-adjunto", data={"datos": "{}"})
    assert sin_archivo.status_code == 422 and len(pedidos) == 2


DETALLE = {
    "id": "p-1",
    "nombre": "ODOO",
    "razon_social": "Odoo S.A.",
    "tipo": "herramienta",
    "cuit": "30-70851936-3",
    "responsabilidad_afip": "Proveedor del Exterior",
    "nro_ingresos_brutos": "901-123456-7",
    "observaciones": "Factura en dólares",
    "referente": {"id": "e-1", "nombre": "Vega, Federico", "email": "fvega@dicsys.com"},
    "servicio_provisto": "ERP",
    "tipo_informacion": None,
    "email": "ventas@odoo.com",
    "telefono_whatsapp": "5493511234567",
    "pagina_web": "https://www.odoo.com",
    "acuerdo_servicio": "Si",
    "politica_nda": "NDA firmado 2026",
    "politica_nda_archivo_nombre": "nda.pdf",
    "activo": True,
    "oficinas": [
        {
            "id": "o-1",
            "nombre_oficina": "Casa central",
            "calle": "Av. Colón",
            "numero": "1200",
            "piso": None,
            "departamento": None,
            "localidad": "Córdoba",
            "provincia": "Córdoba",
            "pais": "Argentina",
            "codigo_postal": None,
            "es_legal": True,
        }
    ],
    "contactos": [
        {
            "id": "c-1",
            "nombre": "Ana",
            "apellido": "Pérez",
            "cargo": "Cuentas",
            "telefono": None,
            "email": "ana@odoo.com",
            "es_principal": True,
            "notas": None,
            "oficina_id": "o-1",
            "oficina": "Casa central",
        }
    ],
    "documentos": [
        {
            "id": "d-1",
            "nombre": "Contrato 2026.pdf",
            "extension": ".pdf",
            "tipo_mime": "application/pdf",
            "tamano": 2516582,
            "con_miniatura": True,
            "subido_por": "admin@dicsys.com",
            "subido_at": "2026-10-09T12:00:00",
        },
        {
            "id": "d-2",
            "nombre": "Costos.xlsx",
            "extension": ".xlsx",
            "tipo_mime": "application/vnd.ms-excel",
            "tamano": 850,
            "con_miniatura": False,
            "subido_por": "admin@dicsys.com",
            "subido_at": "2026-10-09T12:00:00",
        },
    ],
    "historial": [
        {
            "evaluacion_id": "ev-1",
            "periodo": "2026",
            "evaluador": "Vega, Federico",
            "incidentes": "No",
            "mal_manejo": "Si",
            "evidencia_incidentes": None,
            "evidencia_mal_manejo": "Incidente en https://drive.google.com/ficha",
            "con_hallazgo": True,
            "evaluado_at": "2026-10-02T18:08:57",
        }
    ],
}


def test_el_listado_lleva_al_alta_y_las_filas_a_la_vista(frontend_client, fake_api):
    _sesion(frontend_client)
    _permisos(fake_api, "proveedores")
    html = frontend_client.get("/administracion/proveedores").get_data(as_text=True)
    assert 'href="/administracion/proveedores/nuevo"' in html
    assert "Ver ficha" not in html
    assert ">Página web</th>" in html and ">Usuario referente</th>" not in html
    assert "`${base}/${p.id}`" in html and "`${base}/${p.id}/editar`" in html


def test_la_vista_es_de_solo_lectura_con_boton_editar(frontend_client, fake_api):
    _sesion(frontend_client)
    _permisos(fake_api, "proveedores")
    fake_api.respond("GET", "/proveedores/p-1", DETALLE)

    html = frontend_client.get("/administracion/proveedores/p-1").get_data(as_text=True)

    assert "ODOO" in html and "Odoo S.A." in html and "Vega, Federico" in html
    assert "fvega@dicsys.com" not in html  # del usuario referente alcanza con el nombre
    assert 'href="/administracion/proveedores/p-1/editar"' in html
    assert 'href="/administracion/proveedores/p-1/nda"' in html  # descargar sí
    assert 'type="file"' not in html and "Adjuntar" not in html  # adjuntar no
    assert "https://web.whatsapp.com/send?phone=5493511234567" in html and "+5493511234567" in html
    assert "mailto:" not in html and "ventas@odoo.com" in html  # el email sin link
    assert "Casa central" in html and "Domicilio legal" in html and "Ana Pérez" in html
    assert "Mostrar evidencia" in html and '<a href="https://drive.google.com/ficha"' in html
    assert "2 de octubre de 2026" in html and "Checklist" not in html


def test_la_vista_no_cuenta_registros_y_lista_oficinas_y_contactos_en_tabla_o_cards(frontend_client, fake_api):
    _sesion(frontend_client)
    _permisos(fake_api, "proveedores")
    fake_api.respond("GET", "/proveedores/p-1", DETALLE)

    html = frontend_client.get("/administracion/proveedores/p-1").get_data(as_text=True)

    for etiqueta in ("Oficinas", "Contactos", "Evaluaciones"):
        assert f"</i>{etiqueta}" in html and f"{etiqueta} (" not in html
    # Pestañas con el estilo de /perfil (subrayado), no las de pastilla
    assert "absolute bottom-0 left-0 right-0 h-0.5 bg-primary-500" in html and "shadow-md" not in html
    # Datos fiscales y observaciones, como en Clientes
    assert "30-70851936-3" in html and "Proveedor del Exterior" in html and "901-123456-7" in html
    assert "Factura en dólares" in html
    assert html.count("@click=\"vista = 'tabla'\"") == 2 and html.count("@click=\"vista = 'cards'\"") == 2
    assert html.count("""x-show="vista === 'tabla'\"""") == 2 and html.count("""x-show="vista === 'cards'\"""") == 2
    assert ">AP<" in "".join(html.split())  # iniciales en la card del contacto


def test_el_alta_pide_el_adjunto_solo_con_acuerdo_firmado(frontend_client, fake_api):
    _sesion(frontend_client)
    _permisos(fake_api, "proveedores")
    fake_api.respond("GET", "/proveedores/p-1", DETALLE)

    edicion = frontend_client.get("/administracion/proveedores/p-1/editar").get_data(as_text=True)
    alta = frontend_client.get("/administracion/proveedores/nuevo").get_data(as_text=True)

    assert 'type="file"' in edicion and "Archivo adjunto de política / NDA" in edicion
    assert "Guardar cambios" in edicion and "Agregar oficina" in edicion
    assert '"politica_nda_archivo_nombre": "nda.pdf"' in edicion
    # En el alta el archivo aparece con acuerdo firmado y viaja junto con los datos
    assert "Archivo adjunto del acuerdo / NDA" in alta and ":required=\"datos.acuerdo_servicio === 'Si'\"" in alta
    assert "/administracion/proveedores/nuevo/con-adjunto" in alta
    assert "Las oficinas, los contactos y los documentos se cargan después de crear el proveedor" in alta
    assert "Crear proveedor" in alta


def test_el_form_marca_los_obligatorios_y_el_acuerdo_es_si_o_no(frontend_client, fake_api):
    _sesion(frontend_client)
    _permisos(fake_api, "proveedores")
    alta = frontend_client.get("/administracion/proveedores/nuevo").get_data(as_text=True)

    assert 'x-model="datos.servicio_provisto" required' in alta and 'x-model="datos.tipo_informacion" required' in alta
    assert 'x-model="datos.acuerdo_servicio" required' in alta
    assert '<option value="Si">Sí</option>' in alta and "N/A" not in alta
    assert ":required=\"datos.acuerdo_servicio === 'No'\"" in alta  # sin acuerdo, la política/NDA
    # El referente no se puede quitar, solo cambiar; el buscador avisa si falta
    assert ">Quitar</button>" not in alta and "Elegí el usuario referente de la nómina" in alta


def test_alta_y_edicion_separan_contacto_y_seguridad_en_pestanas(frontend_client, fake_api):
    _sesion(frontend_client)
    _permisos(fake_api, "proveedores")
    fake_api.respond("GET", "/proveedores/p-1", DETALLE)

    edicion = frontend_client.get("/administracion/proveedores/p-1/editar").get_data(as_text=True)
    alta = frontend_client.get("/administracion/proveedores/nuevo").get_data(as_text=True)

    for clave in ("datos", "contacto", "seguridad", "oficinas", "contactos"):
        assert f"@click=\"tab = '{clave}'\"" in edicion
    assert """data-tab="contacto" x-show="tab === 'contacto'\"""" in edicion
    assert """data-tab="seguridad" x-show="tab === 'seguridad'\"""" in edicion
    # El alta también tiene pestañas, las del formulario: Oficinas y Contactos, después de crear
    for clave in ("datos", "contacto", "seguridad"):
        assert f"@click=\"tab = '{clave}'\"" in alta
    assert "@click=\"tab = 'oficinas'\"" not in alta and "@click=\"tab = 'contactos'\"" not in alta
    assert """data-tab="contacto" x-show="tab === 'contacto'\"""" in alta
    assert """data-tab="seguridad" x-show="tab === 'seguridad'\"""" in alta
    # Al guardar: lo que falta o tiene error se marca, con punto rojo en su pestaña
    for pagina in (alta, edicion):
        assert '@invalid.capture="alInvalido($event)"' in pagina and '@click="alPresionarGuardar()"' in pagina
        assert "pestanaConError('seguridad')" in pagina and 'data-campo="servicio_provisto"' in pagina


def test_proveedor_inexistente_vuelve_al_listado(frontend_client, fake_api):
    _sesion(frontend_client)
    _permisos(fake_api, "proveedores")
    fake_api.respond("GET", "/proveedores/no-existe", {"detail": "El proveedor no existe"}, status=404)

    for ruta in ("/administracion/proveedores/no-existe", "/administracion/proveedores/no-existe/editar"):
        respuesta = frontend_client.get(ruta)
        assert respuesta.status_code == 302 and respuesta.headers["Location"].endswith("/administracion/proveedores")


ITEM = {
    "id": "i-1",
    "proveedor": {"id": "p-1", "nombre": "ODOO", "razon_social": None},
    "tipo": "herramienta",
    "evaluacion": {
        "id": "ev-1",
        "periodo": "2026",
        "fecha_apertura": "2026-10-01",
        "fecha_cierre": "2026-10-31",
        "estado": "abierta",
        "activa": True,
        "metricas": {},
    },
    "evaluador": {"id": "e-1", "nombre": "Vega, Federico"},
    "preguntas": ["incidentes", "mal_manejo"],
    "opciones": {"incidentes": ["Si", "No", "N/A"], "mal_manejo": ["Si", "No"]},
    "incidentes": "No",
    "mal_manejo": "Si",
    "evidencia_incidentes": None,
    "evidencia_mal_manejo": "Incidente en https://drive.google.com/x",
    "con_hallazgo": True,
    "evaluado": True,
    "evaluado_at": "2026-10-02T18:08:57",
    "evaluado_por": "fvega@dicsys.com",
    "puede_editar": True,
    "es_admin": False,
    "historial": [
        {
            "fecha_hora": "2026-10-02T18:08:57",
            "usuario": "fvega@dicsys.com",
            "accion": "evaluar",
            "antes": {"mal_manejo": None},
            "despues": {"mal_manejo": "Si"},
        }
    ],
}


def test_el_tablero_enlaza_a_la_evaluacion_y_editar_solo_si_puede(frontend_client, fake_api):
    _sesion(frontend_client)
    _permisos(fake_api, "evaluacion_proveedores")
    html = frontend_client.get("/administracion/evaluaciones-proveedores").get_data(as_text=True)
    assert "`${base}/${item.id}`" in html
    assert 'x-show="item.puede_editar" :href="`${base}/${item.id}/editar`"' in html
    assert "Guardar evaluación" not in html  # ya no hay modal


def test_vista_completa_de_la_evaluacion(frontend_client, fake_api):
    _sesion(frontend_client)
    _permisos(fake_api, "evaluacion_proveedores")
    fake_api.respond("GET", "/evaluaciones-proveedores/items/i-1", ITEM)

    html = frontend_client.get("/administracion/evaluaciones-proveedores/i-1").get_data(as_text=True)

    assert "ODOO" in html and "Evaluación 2026" in html and "Con hallazgo" in html
    assert "Proveedores: ¿hubo mal manejo" in html and "no aplica" not in html and "Checklist" not in html
    # La evidencia del «Si», con links, oculta tras su botón; la pregunta respondida con «No» no tiene
    assert '<a href="https://drive.google.com/x"' in html
    assert html.count("Mostrar evidencia</span>") == 1 and 'id="evidencia-mal_manejo"' in html
    assert 'id="evidencia-incidentes"' not in html
    assert 'href="/administracion/evaluaciones-proveedores/i-1/editar"' in html
    assert "Evaluación guardada" in html and "fvega@dicsys.com" in html

    fake_api.respond("GET", "/evaluaciones-proveedores/items/i-1", {**ITEM, "puede_editar": False})
    html = frontend_client.get("/administracion/evaluaciones-proveedores/i-1").get_data(as_text=True)
    assert "/i-1/editar" not in html


def test_editar_la_evaluacion(frontend_client, fake_api):
    _sesion(frontend_client)
    _permisos(fake_api, "evaluacion_proveedores")
    fake_api.respond("GET", "/evaluaciones-proveedores/items/i-1", ITEM)
    html = frontend_client.get("/administracion/evaluaciones-proveedores/i-1/editar").get_data(as_text=True)
    assert "Editar evaluación" in html and "Guardar evaluación" in html
    assert '"preguntas": ["incidentes", "mal_manejo"]' in html
    # La evidencia aparece y se exige solo con «Si»
    assert 'x-show="pideEvidencia(campo)"' in html and ':required="pideEvidencia(campo)"' in html
    assert "Mostrar evidencia" not in html and "Checklist" not in html

    fake_api.respond("GET", "/evaluaciones-proveedores/items/i-1", {**ITEM, "puede_editar": False})
    respuesta = frontend_client.get("/administracion/evaluaciones-proveedores/i-1/editar")
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/administracion/evaluaciones-proveedores/i-1")


def test_evaluacion_ajena_vuelve_al_tablero(frontend_client, fake_api):
    _sesion(frontend_client)
    _permisos(fake_api, "evaluacion_proveedores")
    fake_api.respond(
        "GET", "/evaluaciones-proveedores/items/i-2", {"detail": "Esa evaluación no está asignada a vos"}, status=403
    )
    respuesta = frontend_client.get("/administracion/evaluaciones-proveedores/i-2")
    assert respuesta.status_code == 302
    assert respuesta.headers["Location"].endswith("/administracion/evaluaciones-proveedores")


def test_el_tablero_tiene_el_boton_agregar_proveedor(frontend_client, fake_api):
    _sesion(frontend_client)
    _permisos(fake_api, "evaluacion_proveedores")
    html = frontend_client.get("/administracion/evaluaciones-proveedores").get_data(as_text=True)
    assert 'x-show="puedeAgregar()"' in html and "Agregar proveedor" in html
    # Lo usan el admin y el evaluador: va por el relay del tablero, no por el de Configuración
    assert "evaluacionProveedores('/administracion/evaluaciones-proveedores')" in html


def test_agregar_pasa_por_el_relay_del_tablero(frontend_client, fake_api):
    """El backend decide qué puede agregar cada uno: el admin, cualquiera; el evaluador, los suyos."""
    _sesion(frontend_client)
    _permisos(fake_api, "evaluacion_proveedores")
    candidatos = {"total": 1, "items": [{"id": "p-1", "nombre": "Webmail", "en_evaluacion": False}]}
    fake_api.respond("GET", "/evaluaciones-proveedores/candidatos?buscar=web", candidatos)
    agregados = {"agregados": [{"id": "i-9", "proveedor_id": "p-1"}, {"id": "i-10", "proveedor_id": "p-2"}]}
    fake_api.respond("POST", "/evaluaciones-proveedores/items", agregados, status=201)
    base = "/administracion/evaluaciones-proveedores/api"

    assert frontend_client.get(f"{base}/candidatos?buscar=web").json == candidatos
    respuesta = frontend_client.post(f"{base}/items", json={"proveedor_ids": ["p-1", "p-2"]})
    assert respuesta.status_code == 201 and respuesta.json == agregados
    assert fake_api.calls[-1]["data"] == {"proveedor_ids": ["p-1", "p-2"]}
    # Configuración ya no los expone, ni el buscador de empleados del alta que ya no está
    config = "/administracion/config-evaluaciones-proveedores/api"
    _permisos(fake_api, "evaluacion_config")
    assert frontend_client.get(f"{config}/candidatos?buscar=web").status_code == 404
    assert frontend_client.get(f"{config}/empleados?buscar=ana").status_code == 404


def test_la_edicion_abre_la_pestana_pedida_y_avisa_lo_guardado(frontend_client, fake_api):
    _sesion(frontend_client)
    _permisos(fake_api, "proveedores")
    fake_api.respond("GET", "/proveedores/p-1", DETALLE)

    html = frontend_client.get("/administracion/proveedores/p-1/editar?tab=oficinas&ok=oficina").get_data(as_text=True)
    assert "tab: 'oficinas'" in html and "Oficina guardada" in html
    # Agregar y editar van en su propia página (como el domicilio en Clientes)
    assert 'href="/administracion/proveedores/p-1/oficinas/nueva"' in html
    assert 'href="/administracion/proveedores/p-1/contactos/nuevo"' in html
    assert ':href="urlOficina(o)"' in html and "guardarHijo" not in html
    # Datos fiscales y observaciones en el formulario
    assert ':value="datos.cuit"' in html and "mascaraCuit($event.target.value)" in html  # máscara XX-XXXXXXXX-X
    assert 'x-model="datos.observaciones"' in html
    # WhatsApp con máscara por país (libphonenumber-js) y referente elegido como ficha, no como placeholder
    assert "formatearTelefono($event.target.value)" in html and "libphonenumber-js@1.13.14" in html
    assert ':placeholder="referente ? referente.nombre' not in html and "cambiandoReferente = true" in html
    assert '<option value="Proveedor del Exterior">' in html

    html = frontend_client.get("/administracion/proveedores/p-1/editar?tab=cualquiera").get_data(as_text=True)
    assert "tab: 'datos'" in html


def test_pagina_de_oficina_nueva_y_de_edicion(frontend_client, fake_api):
    _sesion(frontend_client)
    _permisos(fake_api, "proveedores")
    fake_api.respond("GET", "/proveedores/p-1", DETALLE)

    nueva = frontend_client.get("/administracion/proveedores/p-1/oficinas/nueva").get_data(as_text=True)
    assert "Agregar oficina" in nueva and 'id="oficina-datos">{}' in nueva
    assert "url: '/administracion/proveedores/api/p-1/oficinas'" in nueva
    assert "volver: '/administracion/proveedores/p-1/editar?tab=oficinas'" in nueva

    edicion = frontend_client.get("/administracion/proveedores/p-1/oficinas/o-1/editar").get_data(as_text=True)
    assert "Editar oficina" in edicion and '"nombre_oficina": "Casa central"' in edicion

    respuesta = frontend_client.get("/administracion/proveedores/p-1/oficinas/no-existe/editar")
    assert respuesta.status_code == 302 and respuesta.location.endswith(
        "/administracion/proveedores/p-1/editar?tab=oficinas"
    )


def test_pagina_de_contacto_nuevo_y_de_edicion(frontend_client, fake_api):
    _sesion(frontend_client)
    _permisos(fake_api, "proveedores")
    fake_api.respond("GET", "/proveedores/p-1", DETALLE)

    nuevo = frontend_client.get("/administracion/proveedores/p-1/contactos/nuevo").get_data(as_text=True)
    assert "Agregar contacto" in nuevo and '<option value="o-1">Casa central</option>' in nuevo
    edicion = frontend_client.get("/administracion/proveedores/p-1/contactos/c-1/editar").get_data(as_text=True)
    assert "Editar contacto" in edicion and '"id": "c-1"' in edicion

    respuesta = frontend_client.get("/administracion/proveedores/p-1/contactos/no-existe/editar")
    assert respuesta.status_code == 302 and respuesta.location.endswith(
        "/administracion/proveedores/p-1/editar?tab=contactos"
    )

    # Sin el permiso del registro no se llega
    _permisos(fake_api, "evaluacion_proveedores")
    assert frontend_client.get("/administracion/proveedores/p-1/contactos/nuevo").status_code == 403


def test_config_separa_fuente_de_datos_recordatorios_y_canales(frontend_client, fake_api):
    _sesion(frontend_client)
    _permisos(fake_api, "evaluacion_config")
    html = frontend_client.get("/administracion/config-evaluaciones-proveedores").get_data(as_text=True)

    for clave, etiqueta in (("fuente", "Fuente de datos"), ("recordatorios", "Recordatorios"), ("canales", "Canales")):
        assert f"@click=\"cambiarPestana('{clave}')\"" in html and f"</i>{etiqueta}" in html
        assert f"x-show=\"pestana === '{clave}'\"" in html
    assert "cambiarPestana('configuracion')" not in html and "cambiarPestana('importar')" not in html
    # Cargar Sheet está en Fuente de datos y abre la importación en su propia página
    fuente = html[
        html.index("<section x-show=\"pestana === 'fuente'\"") : html.index(
            "<section x-show=\"pestana === 'recordatorios'\""
        )
    ]
    assert 'href="/administracion/config-evaluaciones-proveedores/importar"' in fuente
    assert "confirmarImportacion" not in html and "vista.filas" not in html
    assert html.count("Guardar configuración") == 3  # un Guardar por pestaña, para toda la configuración
    assert "configuracion?.cuenta_sheets" in html  # con quién compartir el Sheet
    # Canales: botón para probar con el aviso de un evaluador
    canales = html[html.index("<section x-show=\"pestana === 'canales'\"") :]
    assert '@click="probarCanales()"' in canales and 'x-model="prueba.evaluador"' in canales
    assert "absolute bottom-0 left-0 right-0 h-0.5 bg-primary-500" in html  # pestañas como /perfil

    # Vuelve a la pestaña pedida
    html = frontend_client.get("/administracion/config-evaluaciones-proveedores?tab=fuente").get_data(as_text=True)
    assert "configEvaluaciones('/administracion/config-evaluaciones-proveedores', 'fuente')" in html


def test_la_prueba_de_canales_pasa_por_el_relay_de_admin(frontend_client, fake_api):
    _sesion(frontend_client)
    _permisos(fake_api, "evaluacion_config")
    fake_api.respond(
        "POST",
        "/evaluaciones-proveedores/seguimiento/probar",
        [{"evaluador": "Vega, Federico", "canal": "email", "destino": "fvega@dicsys.com", "enviado": True}],
    )
    cuerpo = {"evaluador_id": "e-1", "canal_email": True, "email_cc": ""}

    respuesta = frontend_client.post(
        "/administracion/config-evaluaciones-proveedores/api/seguimiento/probar", json=cuerpo
    )
    assert respuesta.status_code == 200 and respuesta.json[0]["enviado"] is True
    assert fake_api.calls[-1]["data"] == cuerpo

    _permisos(fake_api, "evaluacion_proveedores")  # un evaluador no puede
    assert (
        frontend_client.post(
            "/administracion/config-evaluaciones-proveedores/api/seguimiento/probar", json=cuerpo
        ).status_code
        == 403
    )


def test_la_importacion_del_sheet_tiene_su_propia_pagina(frontend_client, fake_api):
    _sesion(frontend_client)
    _permisos(fake_api, "evaluacion_config")
    html = frontend_client.get("/administracion/config-evaluaciones-proveedores/importar").get_data(as_text=True)

    assert "Importar Sheet" in html and "api: '/administracion/config-evaluaciones-proveedores/api'" in html
    assert "volver: '/administracion/config-evaluaciones-proveedores?tab=fuente'" in html
    assert "vista.filas" in html and '@click="confirmar()"' in html and '@click="cancelar()"' in html

    # Solo el admin del módulo
    _permisos(fake_api, "evaluacion_proveedores")
    assert frontend_client.get("/administracion/config-evaluaciones-proveedores/importar").status_code == 403
