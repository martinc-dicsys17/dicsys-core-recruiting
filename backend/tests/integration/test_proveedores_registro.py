"""Registro de proveedores: ABM, oficinas, contactos, adjunto, auditoría y evaluación activa."""

import io
import json
import uuid
import zipfile
from datetime import timedelta
from urllib.parse import quote

import pymupdf
import pytest
from PIL import Image

from backend.modules.administracion import proveedores_miniaturas as miniaturas
from backend.modules.administracion.proveedores_auditoria import Actor
from backend.modules.administracion.proveedores_comun import asegurar_item, hoy_argentina
from backend.modules.administracion.proveedores_models import (
    EvaluacionItem,
    EvaluacionProveedores,
    ProveedorDocumento,
    ProveedoresAuditoria,
    RegistroProveedor,
)
from backend.tests.helpers.auth import auth_headers

URL = "/api/v1/proveedores"
PDF = b"%PDF-1.4\n%prueba\n"
pytestmark = [pytest.mark.integration, pytest.mark.deploy_gate]


@pytest.fixture
def entorno(data_factory):
    empresa = data_factory.empresa()
    usuario = data_factory.usuario()
    grupo = data_factory.grupo()
    data_factory.asignar_empresa(usuario, empresa)
    data_factory.asignar_grupo(usuario, grupo, empresa)
    data_factory.permisos(grupo, ["admin_contable", "admin_contable.proveedores"])
    headers = {**auth_headers(usuario, empresa), "X-Cliente-IP": "203.0.113.7", "X-Cliente-User-Agent": "Navegador/1.0"}
    referente = data_factory.empleado(empresa, nombre="Federico", apellido="Vega", email_corporativo="fvega@dicsys.com")
    return {"empresa": empresa, "usuario": usuario, "headers": headers, "referente": referente}


@pytest.fixture
def evaluacion_activa(db_session, entorno):
    hoy = hoy_argentina()
    evaluacion = EvaluacionProveedores(
        empresa_id=entorno["empresa"].id,
        periodo=str(hoy.year),
        fecha_apertura=hoy - timedelta(days=1),
        fecha_cierre=hoy + timedelta(days=10),
    )
    db_session.add(evaluacion)
    db_session.flush()
    return evaluacion


def _datos(entorno, **datos):
    """Un proveedor completo (con los datos obligatorios), con lo que pida cada test pisado."""
    return {
        "nombre": "ODOO",
        "referente_empleado_id": str(entorno["referente"].id),
        "servicio_provisto": "ERP",
        "tipo_informacion": "Datos contables",
        "acuerdo_servicio": "No",
        "politica_nda": "https://www.odoo.com/privacy",
        **datos,
    }


def _crear(client, entorno, **datos):
    return client.post(URL, headers=entorno["headers"], json=_datos(entorno, **datos))


def _crear_con_adjunto(client, entorno, archivo=("Acuerdo.pdf", PDF, "application/pdf"), **datos):
    return client.post(
        f"{URL}/con-adjunto",
        headers=entorno["headers"],
        data={"datos": json.dumps(_datos(entorno, acuerdo_servicio="Si", **datos))},
        files={"archivo": archivo},
    )


def _sumar(db_session, evaluacion, *proveedores):
    """Lo que hacen la importación del Sheet o «Agregar proveedor»: entran a la evaluación."""
    for p in proveedores:
        asegurar_item(
            db_session,
            evaluacion,
            db_session.get(RegistroProveedor, uuid.UUID(p["id"])),
            Actor(usuario_id=None, email="sheet@dicsys.com"),
        )
    db_session.commit()  # como la API: un rollback posterior no lo borra


def test_alta_con_referente_y_normalizacion_de_datos(client, entorno):
    response = _crear(
        client,
        entorno,
        tipo="herramienta",
        referente_empleado_id=str(entorno["referente"].id),
        telefono_whatsapp="+54 9 351 123-4567",
        pagina_web="www.odoo.com",
        email="  ventas@odoo.com ",
    )

    assert response.status_code == 201, response.text
    datos = response.json()
    assert datos["referente"] == {
        "id": str(entorno["referente"].id),
        "nombre": "Vega, Federico",
        "email": "fvega@dicsys.com",
    }
    assert datos["telefono_whatsapp"] == "5493511234567"
    assert datos["pagina_web"] == "https://www.odoo.com"
    assert datos["email"] == "ventas@odoo.com"
    assert datos["tipo"] == "herramienta" and datos["activo"] is True


def test_datos_fiscales_y_observaciones_como_en_clientes(client, entorno):
    response = _crear(
        client,
        entorno,
        cuit=" 30708519363 ",
        responsabilidad_afip="Responsable Inscripto",
        nro_ingresos_brutos=" 901-123456-7 ",
        observaciones="  Factura en dólares  ",
    )

    assert response.status_code == 201, response.text
    datos = response.json()
    assert datos["cuit"] == "30-70851936-3"  # se normaliza como en Clientes
    assert datos["responsabilidad_afip"] == "Responsable Inscripto"
    assert (datos["nro_ingresos_brutos"], datos["observaciones"]) == ("901-123456-7", "Factura en dólares")
    # Del exterior: sin CUIT y con su tipo de IVA
    exterior = _crear(client, entorno, nombre="Atlassian", responsabilidad_afip="Proveedor del Exterior")
    assert exterior.status_code == 201 and exterior.json()["cuit"] is None
    # Se busca por CUIT con o sin guiones
    for buscar in ("30708519363", "70851936", "30-70851936"):
        encontrados = client.get(URL, headers=entorno["headers"], params={"buscar": buscar}).json()["items"]
        assert [p["nombre"] for p in encontrados] == ["ODOO"]
    # y el nombre sin importar mayúsculas ni acentos
    _crear(client, entorno, nombre="Banco Galicía")
    for buscar in ("GALICIA", "galicía"):
        encontrados = client.get(URL, headers=entorno["headers"], params={"buscar": buscar}).json()["items"]
        assert [p["nombre"] for p in encontrados] == ["Banco Galicía"]


@pytest.mark.parametrize(
    "campo, valor",
    [
        ("email", "no-es-mail"),
        ("telefono_whatsapp", "123"),
        ("tipo", "otro"),
        ("acuerdo_servicio", "Tal vez"),
        ("acuerdo_servicio", "N/A"),
        ("cuit", "30-70851936-4"),
        ("cuit", "3070851936"),
        ("responsabilidad_afip", "Cliente del Exterior"),
        ("nro_ingresos_brutos", "x" * 51),
    ],
)
def test_alta_rechaza_datos_invalidos(client, entorno, campo, valor):
    assert _crear(client, entorno, **{campo: valor}).status_code == 422


@pytest.mark.parametrize(
    "campo, valor, mensaje",
    [
        # El mensaje del validador llega a la pantalla; si ya nombra el campo no se repite la etiqueta
        ("cuit", "30-70851936-4", "CUIT inválido: el dígito verificador no es correcto"),
        (
            "telefono_whatsapp",
            "123",
            "WhatsApp: debe tener entre 8 y 15 dígitos, con código de país (ej: 5493511234567)",
        ),
        # Los errores de librería (email) siguen con el texto genérico en español
        ("email", "no-es-mail", "Email: tiene un valor inválido"),
    ],
)
def test_los_errores_de_validacion_dicen_que_corregir(client, entorno, campo, valor, mensaje):
    respuesta = _crear(client, entorno, **{campo: valor})
    assert respuesta.json()["detail"] == mensaje


@pytest.mark.parametrize(
    "faltante, mensaje",
    [
        ({"referente_empleado_id": None}, "usuario referente"),
        ({"servicio_provisto": "   "}, "servicio / bien provisto"),
        ({"tipo_informacion": None}, "tipo de información que manejan"),
        ({"acuerdo_servicio": None}, "¿hay acuerdo de servicio firmado? (Sí o No)"),
        ({"politica_nda": ""}, "política de seguridad / NDA (sin acuerdo firmado es obligatoria)"),
    ],
)
def test_alta_exige_los_datos_obligatorios(client, entorno, faltante, mensaje):
    respuesta = _crear(client, entorno, **faltante)
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"] == f"Faltan datos obligatorios: {mensaje}"


def test_con_acuerdo_firmado_el_alta_trae_el_adjunto(client, db_session, entorno, fake_storage):
    # El alta con adjunto sube el archivo y crea el proveedor en el mismo pedido
    alta = _crear_con_adjunto(client, entorno, politica_nda=None)
    assert alta.status_code == 201, alta.text
    proveedor = alta.json()
    assert (proveedor["acuerdo_servicio"], proveedor["politica_nda_archivo_nombre"]) == ("Si", "Acuerdo.pdf")
    assert len(fake_storage.files) == 1
    evento = db_session.query(ProveedoresAuditoria).filter_by(entidad_id=uuid.UUID(proveedor["id"])).one()
    assert evento.despues["politica_nda_archivo_nombre"] == "Acuerdo.pdf"

    # Sin archivo, el alta JSON no alcanza
    respuesta = _crear(client, entorno, nombre="Otro", acuerdo_servicio="Si", politica_nda=None)
    assert respuesta.status_code == 422
    assert respuesta.json() == {
        "detail": "Con acuerdo de servicio firmado hay que adjuntar el archivo del acuerdo / NDA"
    }

    # Con acuerdo firmado el adjunto se puede reemplazar, no quitar
    ruta = f"{URL}/{proveedor['id']}/nda"
    quitar = client.delete(ruta, headers=entorno["headers"])
    assert quitar.status_code == 409 and "adjunto es obligatorio" in quitar.json()["detail"]
    assert len(fake_storage.files) == 1


@pytest.mark.parametrize(
    "datos, archivo, estado",
    [
        ({"servicio_provisto": None}, ("Acuerdo.pdf", PDF, "application/pdf"), 422),
        ({"nombre": "Mapfre"}, ("Acuerdo.pdf", PDF, "application/pdf"), 409),  # nombre repetido
        ({}, ("Acuerdo.pdf", b"MZ ejecutable disfrazado", "application/pdf"), 422),
    ],
)
def test_alta_con_adjunto_que_falla_no_deja_el_archivo(client, entorno, fake_storage, datos, archivo, estado):
    assert _crear(client, entorno, nombre="Mapfre").status_code == 201
    respuesta = _crear_con_adjunto(client, entorno, archivo=archivo, **{"nombre": "Odoo", **datos})
    assert respuesta.status_code == estado, respuesta.text
    assert fake_storage.files == {}


@pytest.mark.parametrize(
    "datos, mensaje",
    [
        (
            {"telefono_whatsapp": "123"},
            "WhatsApp: debe tener entre 8 y 15 dígitos, con código de país (ej: 5493511234567)",
        ),
        ({"servicio_provisto": None}, "Faltan datos obligatorios: servicio / bien provisto"),
    ],
)
def test_los_errores_del_alta_con_adjunto_se_leen_como_los_del_alta(client, entorno, fake_storage, datos, mensaje):
    respuesta = _crear_con_adjunto(client, entorno, **datos)
    assert respuesta.status_code == 422
    assert respuesta.json()["detail"] == mensaje


def test_pasar_a_acuerdo_firmado_pide_subir_antes_el_adjunto(client, entorno, fake_storage):
    proveedor = _crear(client, entorno).json()
    url = f"{URL}/{proveedor['id']}"
    firmado = _datos(entorno, acuerdo_servicio="Si", politica_nda=None)
    respuesta = client.put(url, headers=entorno["headers"], json=firmado)
    assert respuesta.status_code == 422 and "adjuntar el archivo" in respuesta.json()["detail"]

    client.post(f"{url}/nda", headers=entorno["headers"], files={"archivo": ("Acuerdo.pdf", PDF, "application/pdf")})
    assert client.put(url, headers=entorno["headers"], json=firmado).status_code == 200


def test_nombre_duplicado_sin_importar_acentos_ni_mayusculas(client, entorno):
    assert _crear(client, entorno, nombre="Mapfre Seguros").status_code == 201
    response = _crear(client, entorno, nombre="  MÁPFRE   seguros ")
    assert response.status_code == 409
    assert "Mapfre Seguros" in response.json()["detail"]


def test_referente_de_otra_empresa_no_se_acepta(client, data_factory, entorno):
    ajeno = data_factory.empleado(data_factory.empresa())
    assert _crear(client, entorno, referente_empleado_id=str(ajeno.id)).status_code == 404


def test_listado_con_metricas_y_filtros(client, db_session, entorno):
    headers = entorno["headers"]
    con_referente = _crear(client, entorno, nombre="ODOO", referente_empleado_id=str(entorno["referente"].id)).json()
    # Sin referente solo quedan los registros de antes de que fuera obligatorio
    db_session.add(RegistroProveedor(empresa_id=entorno["empresa"].id, nombre="Banco Galicia", tipo="proveedor"))
    db_session.commit()
    baja = _crear(client, entorno, nombre="Webmail").json()
    assert client.post(f"{URL}/{baja['id']}/baja", headers=headers).status_code == 200

    datos = client.get(URL, headers=headers).json()
    assert datos["metricas"] == {"activos": 2, "sin_referente": 1, "de_baja": 1}
    assert [p["nombre"] for p in datos["items"]] == ["Banco Galicia", "ODOO"]
    assert [p["nombre"] for p in client.get(f"{URL}?sin_referente=true", headers=headers).json()["items"]] == [
        "Banco Galicia"
    ]
    assert [
        p["id"] for p in client.get(f"{URL}?referente_id={entorno['referente'].id}", headers=headers).json()["items"]
    ] == [con_referente["id"]]
    assert [p["nombre"] for p in client.get(f"{URL}?estado=baja", headers=headers).json()["items"]] == ["Webmail"]
    assert [p["nombre"] for p in client.get(f"{URL}?buscar=gali", headers=headers).json()["items"]] == ["Banco Galicia"]


def test_sin_permiso_del_item_no_accede(client, data_factory, entorno):
    usuario = data_factory.usuario()
    grupo = data_factory.grupo()
    data_factory.asignar_empresa(usuario, entorno["empresa"])
    data_factory.asignar_grupo(usuario, grupo, entorno["empresa"])
    data_factory.permisos(grupo, ["admin_contable", "admin_contable.clientes"])
    assert client.get(URL, headers=auth_headers(usuario, entorno["empresa"])).status_code == 403


def test_otra_empresa_no_ve_el_proveedor(client, data_factory, entorno):
    proveedor = _crear(client, entorno).json()
    otra = data_factory.empresa()
    data_factory.asignar_empresa(entorno["usuario"], otra)
    grupo = data_factory.grupo()
    data_factory.asignar_grupo(entorno["usuario"], grupo, otra)
    data_factory.permisos(grupo, ["admin_contable", "admin_contable.proveedores"])
    headers_otra = auth_headers(entorno["usuario"], otra)
    assert client.get(f"{URL}/{proveedor['id']}", headers=headers_otra).status_code == 404
    assert client.get(URL, headers=headers_otra).json()["total"] == 0


def test_auditoria_registra_ip_navegador_y_solo_los_cambios(client, db_session, entorno):
    proveedor = _crear(client, entorno, razon_social="Odoo SA").json()
    client.put(f"{URL}/{proveedor['id']}", headers=entorno["headers"], json=_datos(entorno, razon_social="Odoo S.A."))

    eventos = (
        db_session.query(ProveedoresAuditoria)
        .filter(ProveedoresAuditoria.entidad_id == uuid.UUID(proveedor["id"]))
        .order_by(ProveedoresAuditoria.fecha_hora)
        .all()
    )
    assert [e.accion for e in eventos] == ["crear", "editar"]
    assert all(e.ip == "203.0.113.7" and e.user_agent == "Navegador/1.0" for e in eventos)
    assert eventos[0].usuario_email == entorno["usuario"].email
    assert eventos[1].antes == {"razon_social": "Odoo SA"}
    assert eventos[1].despues == {"razon_social": "Odoo S.A."}


def test_oficinas_un_solo_domicilio_legal_y_contactos_un_solo_principal(client, entorno):
    headers = entorno["headers"]
    proveedor = _crear(client, entorno).json()
    base = f"{URL}/{proveedor['id']}"
    central = client.post(
        f"{base}/oficinas",
        headers=headers,
        json={
            "nombre_oficina": "Casa central",
            "calle": "Av. Colón",
            "numero": "100",
            "localidad": "Córdoba",
            "provincia": "Córdoba",
            "es_legal": True,
        },
    ).json()
    exterior = client.post(
        f"{base}/oficinas",
        headers=headers,
        json={"calle": "Calle 1", "localidad": "Hangzhou", "pais": "China", "provincia": "  ", "es_legal": True},
    )
    assert exterior.status_code == 201 and exterior.json()["provincia"] is None

    ana = client.post(
        f"{base}/contactos",
        headers=headers,
        json={"nombre": "Ana", "apellido": "Pérez", "es_principal": True, "oficina_id": central["id"]},
    ).json()
    client.post(f"{base}/contactos", headers=headers, json={"nombre": "Juan", "es_principal": True})

    ficha = client.get(base, headers=headers).json()
    assert [o["es_legal"] for o in ficha["oficinas"]] == [False, True]
    principales = {c["nombre"]: c["es_principal"] for c in ficha["contactos"]}
    assert principales == {"Ana": False, "Juan": True}
    assert next(c for c in ficha["contactos"] if c["id"] == ana["id"])["oficina"] == "Casa central"

    assert client.delete(f"{base}/oficinas/{central['id']}", headers=headers).status_code == 200
    ficha = client.get(base, headers=headers).json()
    assert len(ficha["oficinas"]) == 1
    assert next(c for c in ficha["contactos"] if c["id"] == ana["id"])["oficina_id"] is None


def test_marcar_al_editar_no_depende_del_orden_de_los_ids(client, entorno):
    """Se edita siempre la fila de id menor: marcarla antes de desmarcar la otra violaba el índice único parcial,
    porque los UPDATE salen en orden de clave primaria (F18-P23)."""
    headers = entorno["headers"]
    base = f"{URL}/{_crear(client, entorno).json()['id']}"

    def oficina(nombre, legal):
        return {"nombre_oficina": nombre, "calle": "Calle 1", "localidad": "Córdoba", "es_legal": legal}

    def contacto(nombre, principal):
        return {"nombre": nombre, "es_principal": principal}

    for ruta, cuerpo, campo, nombre in (
        ("oficinas", oficina, "es_legal", "nombre_oficina"),
        ("contactos", contacto, "es_principal", "nombre"),
    ):
        filas = [
            client.post(f"{base}/{ruta}", headers=headers, json=cuerpo(n, marca)).json()
            for n, marca in (("A", True), ("B", False))
        ]
        menor, mayor = sorted(filas, key=lambda f: uuid.UUID(f["id"]))
        if not mayor[campo]:  # la marca queda en la de id mayor (editar esa no fallaba ni antes del fix)
            r = client.put(f"{base}/{ruta}/{mayor['id']}", headers=headers, json=cuerpo(mayor[nombre], True))
            assert r.status_code == 200, r.text
        r = client.put(f"{base}/{ruta}/{menor['id']}", headers=headers, json=cuerpo(menor[nombre], True))
        assert r.status_code == 200, f"{ruta}: {r.text}"
        ficha = client.get(base, headers=headers).json()
        assert {f["id"]: f[campo] for f in ficha[ruta]} == {menor["id"]: True, mayor["id"]: False}


def test_contacto_con_oficina_de_otro_proveedor_se_rechaza(client, entorno):
    headers = entorno["headers"]
    uno = _crear(client, entorno, nombre="Uno").json()
    otro = _crear(client, entorno, nombre="Otro").json()
    oficina = client.post(f"{URL}/{otro['id']}/oficinas", headers=headers, json={"calle": "X", "localidad": "Y"}).json()
    response = client.post(
        f"{URL}/{uno['id']}/contactos", headers=headers, json={"nombre": "Ana", "oficina_id": oficina["id"]}
    )
    assert response.status_code == 404


def test_el_alta_no_suma_el_proveedor_a_la_evaluacion_activa(client, db_session, entorno, evaluacion_activa):
    """Entra solo por la importación del Sheet o con «Agregar proveedor» (reemplaza a D-75)."""
    proveedor = _crear(client, entorno, referente_empleado_id=str(entorno["referente"].id)).json()
    assert db_session.query(EvaluacionItem).filter_by(proveedor_id=uuid.UUID(proveedor["id"])).count() == 0


def test_cambio_de_referente_alcanza_a_la_evaluacion_activa(
    client, db_session, data_factory, entorno, evaluacion_activa
):
    proveedor = _crear(client, entorno, referente_empleado_id=str(entorno["referente"].id)).json()
    _sumar(db_session, evaluacion_activa, proveedor)
    nuevo = data_factory.empleado(entorno["empresa"], nombre="Natalia", apellido="Gonzalez")

    client.put(
        f"{URL}/{proveedor['id']}",
        headers=entorno["headers"],
        json=_datos(entorno, referente_empleado_id=str(nuevo.id)),
    )

    item = db_session.query(EvaluacionItem).filter_by(proveedor_id=uuid.UUID(proveedor["id"])).one()
    assert item.evaluador_empleado_id == nuevo.id


def test_baja_quita_de_la_activa_solo_si_estaba_pendiente(client, db_session, entorno, evaluacion_activa):
    headers = entorno["headers"]
    pendiente = _crear(client, entorno, nombre="Pendiente").json()
    evaluado = _crear(client, entorno, nombre="Evaluado").json()
    _sumar(db_session, evaluacion_activa, pendiente, evaluado)
    item_evaluado = db_session.query(EvaluacionItem).filter_by(proveedor_id=uuid.UUID(evaluado["id"])).one()
    item_evaluado.mal_manejo = "No"
    item_evaluado.evaluado_at = item_evaluado.created_at
    db_session.flush()

    client.post(f"{URL}/{pendiente['id']}/baja", headers=headers)
    client.post(f"{URL}/{evaluado['id']}/baja", headers=headers)

    vigentes = {i.proveedor_id for i in db_session.query(EvaluacionItem).filter(EvaluacionItem.deleted_at.is_(None))}
    assert vigentes == {uuid.UUID(evaluado["id"])}
    assert client.delete(f"{URL}/{evaluado['id']}", headers=headers).status_code == 409

    # Reactivarlo en el registro no lo vuelve a sumar: se agrega desde la evaluación
    client.post(f"{URL}/{pendiente['id']}/reactivar", headers=headers)
    vigentes = {i.proveedor_id for i in db_session.query(EvaluacionItem).filter(EvaluacionItem.deleted_at.is_(None))}
    assert uuid.UUID(pendiente["id"]) not in vigentes


def test_eliminar_sin_evaluaciones_lo_saca_del_registro(client, db_session, entorno):
    proveedor = _crear(client, entorno).json()
    assert client.delete(f"{URL}/{proveedor['id']}", headers=entorno["headers"]).status_code == 200
    assert client.get(f"{URL}/{proveedor['id']}", headers=entorno["headers"]).status_code == 404
    assert db_session.get(RegistroProveedor, uuid.UUID(proveedor["id"])).deleted_at is not None


def test_adjunto_nda_sube_descarga_reemplaza_y_quita(client, entorno, fake_storage):
    headers = {k: v for k, v in entorno["headers"].items()}
    proveedor = _crear(client, entorno).json()
    ruta = f"{URL}/{proveedor['id']}/nda"

    subido = client.post(ruta, headers=headers, files={"archivo": ("NDA firmado.pdf", PDF, "application/pdf")})
    assert subido.status_code == 200, subido.text
    assert subido.json()["politica_nda_archivo_nombre"] == "NDA firmado.pdf"
    clave = next(iter(fake_storage.files))
    assert clave.startswith(f"proveedores/{entorno['empresa'].id}/nda/") and clave.endswith(".pdf")

    descarga = client.get(ruta, headers=headers)
    assert descarga.status_code == 200 and descarga.content == PDF
    assert descarga.headers["content-type"] == "application/pdf"
    assert "attachment" in descarga.headers["content-disposition"]

    png = b"\x89PNG\r\n\x1a\n" + b"0" * 10
    client.post(ruta, headers=headers, files={"archivo": ("nda.png", png, "image/png")})
    assert list(fake_storage.files) != [clave] and len(fake_storage.files) == 1

    assert client.delete(ruta, headers=headers).json()["politica_nda_archivo_nombre"] is None
    assert fake_storage.files == {}
    assert client.get(ruta, headers=headers).status_code == 404


@pytest.mark.parametrize(
    "nombre, contenido",
    [
        ("nda.pdf", b"MZ ejecutable disfrazado"),
        ("nda.exe", b"MZ"),
        ("nda.docx", b"PK\x03\x04no es un docx"),
        ("nda.pdf", b""),
    ],
)
def test_adjunto_invalido_se_rechaza_por_contenido(client, entorno, fake_storage, nombre, contenido):
    proveedor = _crear(client, entorno).json()
    response = client.post(
        f"{URL}/{proveedor['id']}/nda",
        headers=entorno["headers"],
        files={"archivo": (nombre, contenido, "application/octet-stream")},
    )
    assert response.status_code == 422
    assert fake_storage.files == {}


def test_buscar_empleados_de_la_nomina(client, data_factory, entorno):
    data_factory.empleado(entorno["empresa"], nombre="Inactivo", apellido="Vega", activo=False)
    data_factory.empleado(data_factory.empresa(), nombre="Ajeno", apellido="Vega")
    nombres = [e["nombre"] for e in client.get(f"{URL}/empleados?buscar=vega", headers=entorno["headers"]).json()]
    assert nombres == ["Vega, Federico"]


# ─── Estado (activo / inactivo) desde la edición ────────────────────────────────


def test_el_estado_se_cambia_desde_la_edicion(client, db_session, entorno, evaluacion_activa):
    proveedor = _crear(client, entorno).json()
    _sumar(db_session, evaluacion_activa, proveedor)
    url = f"{URL}/{proveedor['id']}"

    # Sin «activo» (o igual al actual) no cambia nada
    assert client.put(url, headers=entorno["headers"], json=_datos(entorno)).json()["activo"] is True

    inactivo = client.put(url, headers=entorno["headers"], json=_datos(entorno, activo=False))
    assert inactivo.status_code == 200 and inactivo.json()["activo"] is False
    # Inactivo: sale de la evaluación activa porque estaba pendiente; se sigue viendo
    item = db_session.query(EvaluacionItem).filter_by(proveedor_id=uuid.UUID(proveedor["id"])).one()
    assert item.deleted_at is not None
    assert client.get(url, headers=entorno["headers"]).status_code == 200

    assert client.put(url, headers=entorno["headers"], json=_datos(entorno, activo=True)).json()["activo"] is True
    acciones = [
        e.accion
        for e in db_session.query(ProveedoresAuditoria)
        .filter_by(entidad_id=uuid.UUID(proveedor["id"]))
        .order_by(ProveedoresAuditoria.fecha_hora)
    ]
    assert acciones == ["crear", "baja", "reactivar"]


# ─── Documentos ─────────────────────────────────────────────────────────────────


def _pdf():
    documento = pymupdf.open()
    documento.new_page(width=300, height=400).insert_text((40, 60), "Contrato")
    return documento.tobytes()


def _png():
    salida = io.BytesIO()
    Image.new("RGB", (800, 600), "navy").save(salida, "PNG")
    return salida.getvalue()


def _office(parte):
    """Un zip con solo la parte principal: pasa la validación del tipo, pero no se puede leer."""
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w") as archivo:
        archivo.writestr(parte, "<xml/>")
    return salida.getvalue()


def _xlsx(filas=(("Proveedor", "Servicio", "Costo mensual"), ("ODOO", "ERP", 1500.5), ("Webex", "Videollamadas", 450))):
    from openpyxl import Workbook

    libro = Workbook()
    hoja = libro.active
    hoja.title = "Costos"
    for fila in filas:
        hoja.append(list(fila))
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def _docx(*parrafos, extra=""):
    """docx mínimo: (estilo, texto) por párrafo; estilo 'Heading1' para los títulos."""
    cuerpo = "".join(
        f"<w:p>{f'<w:pPr><w:pStyle w:val={chr(34)}{estilo}{chr(34)}/></w:pPr>' if estilo else ''}"
        f"<w:r><w:t>{texto}</w:t></w:r></w:p>"
        for estilo, texto in parrafos
    )
    documento = (
        f'<?xml version="1.0" encoding="UTF-8"?>{extra}'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{cuerpo}</w:body></w:document>"
    )
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w") as archivo:
        archivo.writestr("[Content_Types].xml", "<Types/>")
        archivo.writestr("word/document.xml", documento)
    return salida.getvalue()


ACUERDO = (
    ("Heading1", "Acuerdo de confidencialidad"),
    (None, "Entre Dicsys S.A. y el proveedor, las partes acuerdan no divulgar la información compartida."),
)


def _subir(client, entorno, proveedor_id, *archivos):
    return client.post(
        f"{URL}/{proveedor_id}/documentos",
        headers=entorno["headers"],
        files=[("archivos", archivo) for archivo in archivos],
    )


def test_documentos_se_suben_varios_con_miniatura_y_se_descargan_con_su_nombre(
    client, db_session, entorno, fake_storage
):
    proveedor = _crear(client, entorno).json()

    respuesta = _subir(
        client,
        entorno,
        proveedor["id"],
        ("Contrato firmado 2026.pdf", _pdf(), "application/pdf"),
        ("Logo.png", _png(), "image/png"),
        ("Costos.xlsx", _xlsx(), "application/octet-stream"),
        ("NDA.docx", _docx(*ACUERDO), "application/octet-stream"),
    )

    assert respuesta.status_code == 201, respuesta.text
    subidos = {d["nombre"]: d for d in respuesta.json()}
    assert set(subidos) == {"Contrato firmado 2026.pdf", "Logo.png", "Costos.xlsx", "NDA.docx"}
    assert all(d["con_miniatura"] for d in subidos.values())
    assert subidos["Costos.xlsx"]["extension"] == ".xlsx" and subidos["Logo.png"]["tipo_mime"] == "image/png"
    # En el bucket: {empresa}/proveedores/{proveedor}/{uuid}{ext}, y la miniatura al lado
    carpeta = f"{entorno['empresa'].id}/proveedores/{proveedor['id']}/"
    assert len(fake_storage.files) == 8 and all(clave.startswith(carpeta) for clave in fake_storage.files)
    documento = db_session.get(ProveedorDocumento, uuid.UUID(subidos["Contrato firmado 2026.pdf"]["id"]))
    assert documento.clave == f"{carpeta}{documento.id.hex}.pdf"
    assert documento.miniatura_clave == f"{carpeta}{documento.id.hex}-miniatura.png"
    assert "Contrato" not in documento.clave  # el nombre original queda solo en la base

    # La ficha los trae; la descarga va con el nombre original
    ficha = client.get(f"{URL}/{proveedor['id']}", headers=entorno["headers"]).json()
    assert {d["nombre"] for d in ficha["documentos"]} == set(subidos)
    descarga = client.get(f"{URL}/{proveedor['id']}/documentos/{documento.id}", headers=entorno["headers"])
    assert descarga.status_code == 200 and descarga.content == fake_storage.files[documento.clave]["content"]
    assert (
        descarga.headers["content-disposition"] == f"attachment; filename*=UTF-8''{quote('Contrato firmado 2026.pdf')}"
    )
    miniatura = client.get(f"{URL}/{proveedor['id']}/documentos/{documento.id}/miniatura", headers=entorno["headers"])
    assert miniatura.status_code == 200 and miniatura.headers["content-type"] == "image/png"
    with Image.open(io.BytesIO(miniatura.content)) as imagen:
        assert imagen.width == miniaturas.ANCHO
    evento = db_session.query(ProveedoresAuditoria).filter_by(entidad="documento", entidad_id=documento.id).one()
    assert (evento.accion, evento.despues["nombre"]) == ("subir", "Contrato firmado 2026.pdf")


def test_sin_miniatura_la_api_responde_404_y_la_pantalla_muestra_el_tipo(client, entorno, fake_storage):
    """Un xlsx que pasa la validación pero no se puede leer se sube igual, sin miniatura."""
    proveedor = _crear(client, entorno).json()

    respuesta = _subir(
        client, entorno, proveedor["id"], ("Costos.xlsx", _office("xl/workbook.xml"), "application/octet-stream")
    )

    assert respuesta.status_code == 201
    [documento] = respuesta.json()
    assert documento["con_miniatura"] is False and len(fake_storage.files) == 1
    sin = client.get(f"{URL}/{proveedor['id']}/documentos/{documento['id']}/miniatura", headers=entorno["headers"])
    assert sin.status_code == 404


@pytest.mark.parametrize(
    "nombre, contenido, mensaje",
    [
        ("virus.exe", b"MZ", "«virus.exe»: Solo se aceptan archivos PDF, JPG, PNG, DOC, DOCX o XLSX"),
        (
            "Costos.xlsx",
            b"PK\x03\x04no es un excel",
            "«Costos.xlsx»: El contenido del archivo no coincide con su extensión",
        ),
    ],
)
def test_si_un_documento_no_es_valido_no_se_sube_ninguno(client, entorno, fake_storage, nombre, contenido, mensaje):
    proveedor = _crear(client, entorno).json()

    respuesta = _subir(
        client,
        entorno,
        proveedor["id"],
        ("Logo.png", _png(), "image/png"),
        (nombre, contenido, "application/octet-stream"),
    )

    assert respuesta.status_code == 422
    assert respuesta.json()["detail"] == mensaje
    assert fake_storage.files == {}


def test_eliminar_un_documento_lo_saca_del_bucket_y_queda_en_la_auditoria(client, db_session, entorno, fake_storage):
    proveedor = _crear(client, entorno).json()
    [documento] = _subir(client, entorno, proveedor["id"], ("Contrato.pdf", _pdf(), "application/pdf")).json()
    url = f"{URL}/{proveedor['id']}/documentos/{documento['id']}"

    assert client.delete(url, headers=entorno["headers"]).status_code == 200

    assert fake_storage.files == {}  # el documento y su miniatura
    assert client.get(f"{URL}/{proveedor['id']}/documentos", headers=entorno["headers"]).json() == []
    assert client.get(url, headers=entorno["headers"]).status_code == 404
    registro = db_session.get(ProveedorDocumento, uuid.UUID(documento["id"]))
    assert registro.deleted_at is not None
    acciones = [
        e.accion
        for e in db_session.query(ProveedoresAuditoria)
        .filter_by(entidad="documento", entidad_id=registro.id)
        .order_by(ProveedoresAuditoria.fecha_hora)
    ]
    assert acciones == ["subir", "eliminar"]


def test_documentos_de_otra_empresa_o_de_otro_proveedor_no_se_ven(client, data_factory, entorno, fake_storage):
    uno = _crear(client, entorno).json()
    otro = _crear(client, entorno, nombre="Otro").json()
    [documento] = _subir(client, entorno, uno["id"], ("Contrato.pdf", _pdf(), "application/pdf")).json()

    # Con el id de otro proveedor de la misma empresa
    assert client.get(f"{URL}/{otro['id']}/documentos/{documento['id']}", headers=entorno["headers"]).status_code == 404
    # Desde otra empresa
    otra = data_factory.empresa()
    data_factory.asignar_empresa(entorno["usuario"], otra)
    grupo = data_factory.grupo()
    data_factory.asignar_grupo(entorno["usuario"], grupo, otra)
    data_factory.permisos(grupo, ["admin_contable", "admin_contable.proveedores"])
    headers_otra = auth_headers(entorno["usuario"], otra)
    assert client.get(f"{URL}/{uno['id']}/documentos/{documento['id']}", headers=headers_otra).status_code == 404
    assert client.delete(f"{URL}/{uno['id']}/documentos/{documento['id']}", headers=headers_otra).status_code == 404


def test_un_proveedor_inactivo_conserva_y_sigue_cargando_documentos(client, entorno, fake_storage):
    proveedor = _crear(client, entorno).json()
    _subir(client, entorno, proveedor["id"], ("Contrato.pdf", _pdf(), "application/pdf"))
    client.post(f"{URL}/{proveedor['id']}/baja", headers=entorno["headers"])

    assert _subir(client, entorno, proveedor["id"], ("Anexo.pdf", _pdf(), "application/pdf")).status_code == 201
    ficha = client.get(f"{URL}/{proveedor['id']}", headers=entorno["headers"]).json()
    assert ficha["activo"] is False and {d["nombre"] for d in ficha["documentos"]} == {"Contrato.pdf", "Anexo.pdf"}


# ─── Vistas previas de Word y Excel ─────────────────────────────────────────────


def _medidas(png):
    with Image.open(io.BytesIO(png)) as imagen:
        return imagen.size


def test_vista_previa_de_excel_y_word():
    assert _medidas(miniaturas.generar(_xlsx(), ".xlsx")) == (miniaturas.ANCHO, miniaturas.ALTO_PAGINA)
    assert _medidas(miniaturas.generar(_docx(*ACUERDO), ".docx")) == (miniaturas.ANCHO, miniaturas.ALTO_PAGINA)
    # Un documento largo se corta al llenar la página
    largo = _docx(*[(None, "Cláusula con bastante texto para ocupar varias líneas. " * 6)] * 40)
    assert _medidas(miniaturas.generar(largo, ".docx")) == (miniaturas.ANCHO, miniaturas.ALTO_PAGINA)
    # Word 97 no se puede leer en Python puro: queda con el tipo
    assert miniaturas.generar(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1resto", ".doc") is None


def test_los_parrafos_de_word_distinguen_titulos():
    parrafos = miniaturas._parrafos_docx(_docx(*ACUERDO, (None, "")))
    assert parrafos == [
        (True, "Acuerdo de confidencialidad"),
        (False, "Entre Dicsys S.A. y el proveedor, las partes acuerdan no divulgar la información compartida."),
        (False, ""),
    ]


@pytest.mark.parametrize(
    "extension, contenido",
    [
        (".xlsx", _xlsx(filas=())),  # hoja vacía
        (".docx", _docx((None, ""))),  # sin texto
        (".docx", _docx(*ACUERDO, extra='<!DOCTYPE d [<!ENTITY e "x">]>')),  # declaraciones XML: no se procesan
    ],
)
def test_sin_contenido_o_sospechoso_queda_sin_miniatura(extension, contenido):
    assert miniaturas.generar(contenido, extension) is None


def test_un_zip_que_descomprime_demasiado_no_se_lee(monkeypatch):
    monkeypatch.setattr(miniaturas, "DESCOMPRIMIDO_MAXIMO", 100)
    assert miniaturas.generar(_xlsx(), ".xlsx") is None
    assert miniaturas.generar(_docx(*ACUERDO), ".docx") is None


def test_celdas_de_excel_con_formato_argentino():
    from datetime import date, datetime

    assert miniaturas._texto_de_celda(1500.5) == "1.500,50"
    assert miniaturas._texto_de_celda(2000.0) == "2.000"
    assert miniaturas._texto_de_celda(date(2026, 10, 9)) == "09/10/2026"
    assert miniaturas._texto_de_celda(datetime(2026, 10, 9, 14, 30)) == "09/10/2026 14:30"
    assert miniaturas._texto_de_celda(None) == ""
