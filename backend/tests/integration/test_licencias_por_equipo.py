"""Arbol Equipo -> Empleados -> Licencias, con gasto general sin duplicados."""

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import event

from backend.core.utils import utc_now
from backend.modules.innovacion.licencias_models import Herramienta, Licencia, Proveedor
from backend.modules.innovacion.licencias_schemas import EmpleadoOpcion, EquipoLicencias
from backend.modules.innovacion.licencias_services import LicenciaService
from backend.modules.innovacion.licencias_utils import normalizar_nombre
from backend.modules.nomina.models import Empleado
from backend.modules.operaciones.models import Equipo, equipo_integrantes
from backend.tests.helpers.auth import auth_headers

POR_EQUIPO = "/api/v1/innovacion/licencias/por-equipo"
POR_EMPLEADO = "/api/v1/innovacion/licencias/por-empleado"
EMPLEADOS = "/api/v1/innovacion/licencias/empleados"
pytestmark = [pytest.mark.integration, pytest.mark.deploy_gate]


@pytest.fixture
def arbol(db_session, data_factory):
    usuario = data_factory.usuario()
    empresa = data_factory.empresa()
    grupo = data_factory.grupo()
    data_factory.asignar_empresa(usuario, empresa)
    data_factory.asignar_grupo(usuario, grupo, empresa)
    data_factory.permisos(grupo, ["innovacion", "innovacion.licencias"])

    empleados = {}
    for indice, apellido in enumerate(["Lescano", "Gimenez", "Sosa"], 1):
        empleado = Empleado(
            id=uuid.uuid4(),
            empresa_id=empresa.id,
            codigo=f"ARBOL-{indice}",
            cuil=20300000000 + indice,
            dni=30000000 + indice,
            apellido=apellido,
            nombre="Prueba",
            activo=True,
        )
        db_session.add(empleado)
        empleados[apellido] = empleado

    herramientas = []
    for nombre in ["Claude", "ChatGPT"]:
        proveedor = Proveedor(
            id=uuid.uuid4(),
            empresa_id=empresa.id,
            nombre=nombre,
            nombre_normalizado=normalizar_nombre(nombre),
        )
        herramienta = Herramienta(
            id=uuid.uuid4(),
            empresa_id=empresa.id,
            nombre=nombre,
            nombre_normalizado=normalizar_nombre(nombre),
            proveedor_rel=proveedor,
            moneda="USD",
        )
        db_session.add(herramienta)
        herramientas.append(herramienta)
    db_session.flush()

    licencias = []
    for apellido, herramienta, costo, activa, moneda in [
        ("Lescano", 0, "20.10", True, "USD"),
        ("Lescano", 1, "30.20", True, "USD"),
        ("Lescano", 0, "99.00", False, "USD"),
        ("Gimenez", 0, "50.00", True, "USD"),
        ("Sosa", 0, "100.01", True, "ARS"),
    ]:
        licencia = Licencia(
            id=uuid.uuid4(),
            empresa_id=empresa.id,
            empleado_id=empleados[apellido].id,
            herramienta_id=herramientas[herramienta].id,
            fecha_inicio=date.today().replace(day=1),
            activa=activa,
            costo_mensual=Decimal(costo),
            moneda=moneda,
        )
        db_session.add(licencia)
        licencias.append(licencia)

    equipos = {}
    for nombre, integrantes in [("Alpha", ["Lescano", "Gimenez"]), ("Beta", ["Lescano"])]:
        equipo = Equipo(id=uuid.uuid4(), empresa_id=empresa.id, nombre=nombre, activo=True)
        db_session.add(equipo)
        db_session.flush()
        for apellido in integrantes:
            db_session.execute(
                equipo_integrantes.insert().values(
                    equipo_id=equipo.id,
                    empleado_id=empleados[apellido].id,
                )
            )
        equipos[nombre] = equipo
    db_session.flush()
    return {
        "headers": auth_headers(usuario, empresa),
        "empresa": empresa,
        "empleados": empleados,
        "equipos": equipos,
        "herramientas": herramientas,
        "licencias": licencias,
    }


def test_arbol_repite_multi_equipo_y_deduplica_metricas(client, arbol):
    respuesta = client.get(POR_EQUIPO, headers=arbol["headers"])
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["total"] == 3
    assert cuerpo["total_empleados"] == 3
    alpha, beta, sin_equipo = cuerpo["items"]
    assert [g["equipo_nombre"] for g in cuerpo["items"]] == ["Alpha", "Beta", "Sin equipo"]
    assert alpha["total_empleados"] == 2
    assert [e["empleado_nombre"] for e in alpha["empleados"]] == ["Gimenez, Prueba", "Lescano, Prueba"]
    assert alpha["empleados"][1] == beta["empleados"][0]
    assert beta["empleados"][0]["cantidad"] == 3
    assert beta["empleados"][0]["cantidad_activas"] == 2
    assert beta["totales"] == [{"moneda": "USD", "total": 50.3}]
    assert alpha["totales"] == [{"moneda": "USD", "total": 100.3}]
    assert sin_equipo["equipo_id"] is None
    assert sin_equipo["empleados"][0]["empleado_id"] == str(arbol["empleados"]["Sosa"].id)
    assert cuerpo["metricas"]["mes_actual"] == [
        {"moneda": "ARS", "total": 100.01},
        {"moneda": "USD", "total": 100.3},
    ]


def test_pagina_equipos_completos_y_conserva_total_general(client, arbol):
    paginas = [
        client.get(
            POR_EQUIPO,
            headers=arbol["headers"],
            params={
                "por_pagina": 1,
                "pagina": pagina,
            },
        ).json()
        for pagina in (1, 2, 3, 4)
    ]
    assert paginas[0]["total_paginas"] == 3
    assert paginas[0]["total_empleados"] == 3
    assert len(paginas[0]["items"][0]["empleados"]) == 2
    assert paginas[0]["items"][0]["empleados"][1]["cantidad"] == 3
    assert paginas[1]["items"][0]["equipo_nombre"] == "Beta"
    assert paginas[2]["items"][0]["equipo_id"] is None
    assert paginas[3]["items"] == []
    assert all(pagina["metricas"] == paginas[0]["metricas"] for pagina in paginas)


def test_serializar_el_arbol_no_consulta_por_empleado_o_licencia(arbol, db_session):
    empresa_id = arbol["empresa"].id
    db_session.expire_all()
    consultas = []
    conexion = db_session.connection()

    def registrar(_conn, _cursor, statement, _parameters, _context, _executemany):
        consultas.append(statement)

    event.listen(conexion, "before_cursor_execute", registrar)
    try:
        resultado = LicenciaService.listar_por_equipo(db_session, empresa_id)
        consultas_carga = len(consultas)
        assert consultas_carga <= 5
        items = [EquipoLicencias.from_grupo(grupo) for grupo in resultado["items"]]
        assert len(items) == 3
        assert len(consultas) == consultas_carga
    finally:
        event.remove(conexion, "before_cursor_execute", registrar)


def test_filtro_equipo_no_expande_otros_equipos_del_empleado(client, arbol):
    cuerpo = client.get(
        POR_EQUIPO,
        headers=arbol["headers"],
        params={
            "equipo_id": str(arbol["equipos"]["Beta"].id),
        },
    ).json()
    assert cuerpo["total"] == 1
    assert cuerpo["total_empleados"] == 1
    assert cuerpo["items"][0]["equipo_nombre"] == "Beta"
    assert cuerpo["metricas"]["mes_actual"] == [{"moneda": "USD", "total": 50.3}]


@pytest.mark.parametrize("filtro", ["proveedor_id", "buscar"])
def test_filtros_recortan_licencias_empleados_y_grupos(client, arbol, filtro):
    valor = str(arbol["herramientas"][1].proveedor_id) if filtro == "proveedor_id" else "ChatGPT"
    cuerpo = client.get(POR_EQUIPO, headers=arbol["headers"], params={filtro: valor}).json()
    assert cuerpo["total"] == 2
    assert cuerpo["total_empleados"] == 1
    assert cuerpo["metricas"]["mes_actual"] == [{"moneda": "USD", "total": 30.2}]
    for equipo in cuerpo["items"]:
        assert equipo["total_empleados"] == 1
        assert [lic["herramienta"] for lic in equipo["empleados"][0]["licencias"]] == ["ChatGPT"]
        assert equipo["totales"] == [{"moneda": "USD", "total": 30.2}]


def test_filtro_empleado_incluye_sin_equipo(client, arbol):
    cuerpo = client.get(
        POR_EQUIPO,
        headers=arbol["headers"],
        params={
            "empleado_id": str(arbol["empleados"]["Sosa"].id),
        },
    ).json()
    assert cuerpo["total"] == cuerpo["total_empleados"] == 1
    assert cuerpo["items"][0]["equipo_id"] is None
    assert cuerpo["metricas"]["mes_actual"] == [{"moneda": "ARS", "total": 100.01}]


def test_equipos_inactivos_o_borrados_no_son_pertenencias(client, arbol, db_session):
    arbol["equipos"]["Alpha"].activo = False
    arbol["equipos"]["Beta"].deleted_at = utc_now()
    db_session.flush()
    cuerpo = client.get(POR_EQUIPO, headers=arbol["headers"]).json()
    assert cuerpo["total"] == 1
    assert cuerpo["items"][0]["equipo_id"] is None
    assert cuerpo["items"][0]["total_empleados"] == 3
    for endpoint in (POR_EQUIPO, POR_EMPLEADO):
        for equipo in arbol["equipos"].values():
            filtrado = client.get(
                endpoint,
                headers=arbol["headers"],
                params={
                    "equipo_id": str(equipo.id),
                },
            ).json()
            assert filtrado["total"] == 0
            assert filtrado["metricas"]["mes_actual"] == []


def test_no_mezcla_equipos_ni_licencias_de_otras_empresas(client, arbol, db_session, data_factory):
    ajena = data_factory.empresa()
    equipo = Equipo(id=uuid.uuid4(), empresa_id=ajena.id, nombre="Equipo secreto", activo=True)
    empleado = Empleado(
        id=uuid.uuid4(),
        empresa_id=ajena.id,
        codigo="AJENO",
        cuil=20400000001,
        dni=40000001,
        apellido="Ajeno",
        nombre="Secreto",
        activo=True,
    )
    herramienta = Herramienta(
        id=uuid.uuid4(),
        empresa_id=ajena.id,
        nombre="Herramienta secreta",
        nombre_normalizado="herramienta secreta",
        moneda="USD",
    )
    db_session.add_all([equipo, empleado, herramienta])
    db_session.flush()
    db_session.add(
        Licencia(
            empresa_id=ajena.id,
            empleado_id=empleado.id,
            herramienta_id=herramienta.id,
            fecha_inicio=date.today().replace(day=1),
            costo_mensual=Decimal("999"),
            moneda="USD",
            activa=True,
        )
    )
    # Incluso una asociacion heredada cruzada no debe filtrar el equipo ajeno.
    for empleado_id in [empleado.id, arbol["empleados"]["Sosa"].id]:
        db_session.execute(
            equipo_integrantes.insert().values(
                equipo_id=equipo.id,
                empleado_id=empleado_id,
            )
        )
    db_session.flush()
    respuesta = client.get(POR_EQUIPO, headers=arbol["headers"])
    assert "secreto" not in respuesta.text.lower()
    assert respuesta.json()["total_empleados"] == 3
    assert respuesta.json()["metricas"]["mes_actual"][-1]["total"] == 100.3
    for endpoint in (POR_EQUIPO, POR_EMPLEADO):
        filtrado = client.get(endpoint, headers=arbol["headers"], params={"equipo_id": str(equipo.id)})
        assert filtrado.json()["total"] == 0


@pytest.mark.parametrize("endpoint", [POR_EMPLEADO, POR_EQUIPO])
def test_subtotales_usan_vigencia_del_mes_actual(client, arbol, db_session, endpoint):
    primero = date.today().replace(day=1)
    proximo = (primero + timedelta(days=32)).replace(day=1)
    vencida, futura, inactiva, vigente, sin_equipo = arbol["licencias"]
    vencida.fecha_inicio = primero - timedelta(days=60)
    vencida.fecha_fin = primero - timedelta(days=1)
    futura.fecha_inicio = proximo
    # Los limites del mes son inclusivos, igual que la tarjeta general.
    vigente.fecha_inicio = proximo - timedelta(days=1)
    sin_equipo.fecha_fin = primero
    db_session.flush()
    cuerpo = client.get(endpoint, headers=arbol["headers"]).json()
    empleados = (
        cuerpo["items"]
        if endpoint == POR_EMPLEADO
        else [emp for equipo in cuerpo["items"] for emp in equipo["empleados"]]
    )
    lescano = next(emp for emp in empleados if emp["empleado_id"] == str(arbol["empleados"]["Lescano"].id))
    assert lescano["cantidad"] == 3
    assert lescano["totales"] == []
    assert cuerpo["metricas"]["mes_actual"] == [
        {"moneda": "ARS", "total": 100.01},
        {"moneda": "USD", "total": 50.0},
    ]
    if endpoint == POR_EQUIPO:
        assert cuerpo["items"][0]["totales"] == [{"moneda": "USD", "total": 50.0}]
        assert cuerpo["items"][1]["totales"] == []


def test_licencia_gratuita_preserva_cero(client, arbol, db_session):
    arbol["licencias"][4].costo_mensual = Decimal("0")
    db_session.flush()
    cuerpo = client.get(
        POR_EQUIPO,
        headers=arbol["headers"],
        params={
            "empleado_id": str(arbol["empleados"]["Sosa"].id),
        },
    ).json()
    equipo = cuerpo["items"][0]
    assert equipo["empleados"][0]["licencias"][0]["costo_mensual"] == 0
    assert equipo["totales"] == cuerpo["metricas"]["mes_actual"] == [{"moneda": "ARS", "total": 0.0}]


@pytest.mark.parametrize("filtro", ["equipo_id", "empleado_id", "proveedor_id"])
def test_filtros_uuid_invalidos_responden_vacio(client, arbol, filtro):
    respuesta = client.get(POR_EQUIPO, headers=arbol["headers"], params={filtro: "no-es-uuid"})
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["items"] == []
    assert respuesta.json()["total_empleados"] == 0


@pytest.mark.parametrize("endpoint", [POR_EQUIPO, EMPLEADOS])
def test_vistas_exigen_permiso_del_submodulo(client, data_factory, endpoint):
    usuario = data_factory.usuario()
    empresa = data_factory.empresa()
    grupo = data_factory.grupo()
    data_factory.asignar_empresa(usuario, empresa)
    data_factory.asignar_grupo(usuario, grupo, empresa)
    data_factory.permisos(grupo, ["innovacion", "innovacion.resumen"])
    respuesta = client.get(endpoint, headers=auth_headers(usuario, empresa))
    assert respuesta.status_code == 403


@pytest.mark.parametrize("endpoint", [POR_EMPLEADO, POR_EQUIPO])
def test_seleccion_multiple_es_union_sin_duplicados_y_pagina_el_conjunto(client, arbol, endpoint):
    seleccionados = {str(arbol["empleados"][nombre].id) for nombre in ("Lescano", "Sosa")}
    params = [("empleado_id", id_) for id_ in seleccionados]
    params.append(("empleado_id", str(arbol["empleados"]["Lescano"].id)))
    total = 2 if endpoint == POR_EMPLEADO else 3
    encontrados = set()
    for pagina in range(1, total + 1):
        respuesta = client.get(
            endpoint,
            headers=arbol["headers"],
            params=params
            + [
                ("pagina", pagina),
                ("por_pagina", 1),
            ],
        )
        assert respuesta.status_code == 200, respuesta.text
        cuerpo = respuesta.json()
        assert cuerpo["total"] == cuerpo["total_paginas"] == total
        assert len(cuerpo["items"]) == 1
        assert cuerpo["metricas"]["mes_actual"] == [
            {"moneda": "ARS", "total": 100.01},
            {"moneda": "USD", "total": 50.3},
        ]
        assert cuerpo["metricas"]["mes_anterior"] == [{"moneda": "ARS", "total": 0.0}, {"moneda": "USD", "total": 0.0}]
        empleados = cuerpo["items"] if endpoint == POR_EMPLEADO else cuerpo["items"][0]["empleados"]
        ids_pagina = {emp["empleado_id"] for emp in empleados}
        assert ids_pagina <= seleccionados
        encontrados.update(ids_pagina)
        if endpoint == POR_EQUIPO:
            assert cuerpo["total_empleados"] == 2
    assert encontrados == seleccionados


@pytest.mark.parametrize("endpoint", [POR_EMPLEADO, POR_EQUIPO])
def test_seleccion_multiple_se_combina_con_equipo_y_proveedor(client, arbol, endpoint):
    respuesta = client.get(
        endpoint,
        headers=arbol["headers"],
        params=[
            ("empleado_id", str(arbol["empleados"]["Lescano"].id)),
            ("empleado_id", str(arbol["empleados"]["Sosa"].id)),
            ("equipo_id", str(arbol["equipos"]["Alpha"].id)),
            ("proveedor_id", str(arbol["herramientas"][1].proveedor_id)),
        ],
    )
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["total"] == 1
    assert cuerpo["metricas"]["mes_actual"] == [{"moneda": "USD", "total": 30.2}]
    empleado = cuerpo["items"][0] if endpoint == POR_EMPLEADO else cuerpo["items"][0]["empleados"][0]
    assert empleado["empleado_id"] == str(arbol["empleados"]["Lescano"].id)
    assert [lic["herramienta"] for lic in empleado["licencias"]] == ["ChatGPT"]


@pytest.mark.parametrize("endpoint", [POR_EMPLEADO, POR_EQUIPO])
def test_seleccion_multiple_ignora_ids_ajenos_e_invalidos_sin_ampliar_resultados(
    client,
    arbol,
    db_session,
    data_factory,
    endpoint,
):
    ajena = data_factory.empresa()
    empleado = Empleado(
        id=uuid.uuid4(),
        empresa_id=ajena.id,
        codigo="MULTI-AJENO",
        cuil=20500000001,
        dni=50000001,
        apellido="Ajeno",
        nombre="Secreto",
        activo=True,
    )
    herramienta = Herramienta(
        id=uuid.uuid4(),
        empresa_id=ajena.id,
        nombre="Herramienta ajena",
        nombre_normalizado="herramienta ajena",
        moneda="USD",
    )
    db_session.add_all([empleado, herramienta])
    db_session.flush()
    db_session.add(
        Licencia(
            empresa_id=ajena.id,
            empleado_id=empleado.id,
            herramienta_id=herramienta.id,
            fecha_inicio=date.today().replace(day=1),
            costo_mensual=Decimal("999"),
            moneda="USD",
            activa=True,
        )
    )
    db_session.flush()
    sosa_id = str(arbol["empleados"]["Sosa"].id)
    respuesta = client.get(
        endpoint,
        headers=arbol["headers"],
        params=[
            ("empleado_id", str(empleado.id)),
            ("empleado_id", sosa_id),
            ("empleado_id", "no-es-uuid"),
            ("empleado_id", ""),
        ],
    )
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["total"] == 1
    assert "Secreto" not in respuesta.text
    assert cuerpo["metricas"]["mes_actual"] == [{"moneda": "ARS", "total": 100.01}]
    empleados = cuerpo["items"] if endpoint == POR_EMPLEADO else cuerpo["items"][0]["empleados"]
    assert [emp["empleado_id"] for emp in empleados] == [sosa_id]


@pytest.mark.parametrize("endpoint", [POR_EMPLEADO, POR_EQUIPO])
def test_seleccion_sin_uuids_validos_no_elimina_el_filtro(client, arbol, endpoint):
    respuesta = client.get(
        endpoint,
        headers=arbol["headers"],
        params=[
            ("empleado_id", "no-es-uuid"),
            ("empleado_id", ""),
        ],
    )
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["items"] == []
    assert cuerpo["total"] == 0
    assert cuerpo["metricas"]["mes_actual"] == []


@pytest.mark.parametrize("usar_lista", [False, True])
def test_servicio_conserva_filtro_escalar_y_prioriza_lista(arbol, db_session, usar_lista):
    filtros = {"empleado_id": str(arbol["empleados"]["Lescano"].id)}
    nombre = "Lescano"
    if usar_lista:
        nombre = "Sosa"
        filtros["empleado_ids"] = [str(arbol["empleados"][nombre].id)]
    resultado = LicenciaService.listar_por_empleado(db_session, arbol["empresa"].id, filtros=filtros)
    assert resultado["total"] == 1
    assert resultado["items"][0]["empleado_id"] == arbol["empleados"][nombre].id


def test_catalogo_empleados_es_minimo_completo_y_aislado(client, arbol, db_session, data_factory):
    ajena = data_factory.empresa()
    extras = [
        Empleado(
            id=uuid.uuid4(),
            empresa_id=arbol["empresa"].id,
            codigo=f"CAT-{indice}",
            cuil=20600000000 + indice,
            dni=60000000 + indice,
            apellido=f"Catalogo {indice:03}",
            nombre="Activo",
            activo=True,
        )
        for indice in range(205)
    ]
    excluidos = [
        Empleado(
            empresa_id=arbol["empresa"].id,
            codigo="CAT-INACTIVO",
            cuil=20700000001,
            dni=70000001,
            apellido="Inactivo",
            nombre="Prueba",
            activo=False,
        ),
        Empleado(
            empresa_id=arbol["empresa"].id,
            codigo="CAT-BORRADO",
            cuil=20700000002,
            dni=70000002,
            apellido="Borrado",
            nombre="Prueba",
            activo=True,
            deleted_at=utc_now(),
        ),
        Empleado(
            empresa_id=ajena.id,
            codigo="CAT-AJENO",
            cuil=20700000003,
            dni=70000003,
            apellido="Ajeno",
            nombre="Prueba",
            activo=True,
        ),
    ]
    db_session.add_all(extras + excluidos)
    db_session.flush()
    # El usuario del arbol tiene permiso de licencias, sin acceso a nomina.
    respuesta = client.get(EMPLEADOS, headers=arbol["headers"])
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert len(cuerpo) == 208
    assert all(set(fila) == {"id", "nombre", "codigo"} for fila in cuerpo)
    assert [fila["nombre"] for fila in cuerpo] == sorted(fila["nombre"] for fila in cuerpo)
    ids = {fila["id"] for fila in cuerpo}
    assert all(str(empleado.id) in ids for empleado in extras)
    assert not any(str(empleado.id) in ids for empleado in excluidos)
    sosa = arbol["empleados"]["Sosa"]
    assert next(fila for fila in cuerpo if fila["id"] == str(sosa.id)) == {
        "id": str(sosa.id),
        "nombre": sosa.empleado_nombre_completo,
        "codigo": sosa.codigo,
    }


def test_catalogo_empleados_carga_solo_identificacion_en_una_consulta(arbol, db_session):
    empresa_id = arbol["empresa"].id
    db_session.expire_all()
    consultas = []
    conexion = db_session.connection()

    def registrar(_conn, _cursor, statement, _parameters, _context, _executemany):
        consultas.append(statement)

    event.listen(conexion, "before_cursor_execute", registrar)
    try:
        filas = LicenciaService.listar_empleados(db_session, empresa_id)
        opciones = [EmpleadoOpcion.from_fila(fila) for fila in filas]
        assert len(opciones) == 3
        assert len(consultas) == 1
        assert set(filas[0]._mapping) == {"id", "apellido", "nombre", "codigo"}
        assert "JOIN" not in consultas[0].upper()
    finally:
        event.remove(conexion, "before_cursor_execute", registrar)


@pytest.mark.parametrize("endpoint", [POR_EMPLEADO, POR_EQUIPO])
def test_varios_equipos_unen_integrantes_sin_duplicar_gasto(client, arbol, endpoint, data_factory, db_session):
    ajena = data_factory.empresa()
    ajeno = Equipo(empresa_id=ajena.id, nombre="Ajeno", activo=True)
    db_session.add(ajeno)
    db_session.flush()
    seleccion = [str(eq.id) for eq in arbol["equipos"].values()]
    respuesta = client.get(
        endpoint,
        headers=arbol["headers"],
        params=[("equipo_id", valor) for valor in [*seleccion, seleccion[0], str(ajeno.id), "invalido"]],
    )
    assert respuesta.status_code == 200
    datos = respuesta.json()
    assert datos["total"] == 2
    assert datos["metricas"]["mes_actual"] == [{"moneda": "USD", "total": 100.3}]
    if endpoint == POR_EQUIPO:
        assert {equipo["equipo_id"] for equipo in datos["items"]} == set(seleccion)
    else:
        assert {empleado["empleado_id"] for empleado in datos["items"]} == {
            str(arbol["empleados"][nombre].id) for nombre in ["Lescano", "Gimenez"]
        }
    vacio = client.get(
        endpoint, headers=arbol["headers"], params=[("equipo_id", str(ajeno.id)), ("equipo_id", "invalido")]
    )
    assert vacio.json()["items"] == []


@pytest.mark.parametrize("por_equipo", [True, False])
def test_revocacion_revisa_y_quita_solo_asignaciones_confirmadas(client, arbol, db_session, data_factory, por_equipo):
    base = "/api/v1/innovacion/licencias/revocacion"
    payload = {"herramienta_id": str(arbol["herramientas"][0].id)}
    if por_equipo:
        payload["equipo_ids"] = [str(e.id) for e in arbol["equipos"].values()]
    else:
        payload["empleado_ids"] = [str(arbol["empleados"][n].id) for n in ["Lescano", "Gimenez"]]
    r = client.post(base + "/preview", json=payload, headers=arbol["headers"])
    assert r.status_code == 200, r.text
    preview = r.json()
    assert preview["empleados"] == 2
    assert set(preview["licencia_ids"]) == {str(arbol["licencias"][i].id) for i in [0, 2, 3]}
    # Una asignación nueva, creada después de revisar, queda fuera del alcance.
    nueva = Licencia(
        id=uuid.uuid4(),
        empresa_id=arbol["empresa"].id,
        empleado_id=arbol["empleados"]["Lescano"].id,
        herramienta_id=arbol["herramientas"][0].id,
        fecha_inicio=date.today(),
        activa=True,
        moneda="USD",
    )
    ajena = Licencia(
        id=uuid.uuid4(),
        empresa_id=data_factory.empresa().id,
        empleado_id=arbol["empleados"]["Lescano"].id,
        herramienta_id=arbol["herramientas"][0].id,
        fecha_inicio=date.today(),
        activa=True,
        moneda="USD",
    )
    db_session.add_all([nueva, ajena])
    db_session.flush()
    ids = preview["licencia_ids"] + [preview["licencia_ids"][0], str(ajena.id)]
    r = client.request("DELETE", base, json={"licencia_ids": ids}, headers=arbol["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["revocadas"] == 3
    db_session.expire_all()
    assert nueva.deleted_at is None and ajena.deleted_at is None
    assert arbol["licencias"][1].deleted_at is None
    assert arbol["licencias"][4].deleted_at is None
    assert arbol["herramientas"][0].deleted_at is None
    assert client.request("DELETE", base, json={"licencia_ids": ids}, headers=arbol["headers"]).json()["revocadas"] == 0


def test_revocacion_rechaza_seleccion_vacia_y_sin_autenticacion(client, arbol):
    base = "/api/v1/innovacion/licencias/revocacion"
    assert (
        client.post(
            base + "/preview", json={"herramienta_id": str(arbol["herramientas"][0].id)}, headers=arbol["headers"]
        ).status_code
        == 422
    )
    assert client.request("DELETE", base, json={"licencia_ids": []}, headers=arbol["headers"]).status_code == 422
    assert client.request("DELETE", base, json={"licencia_ids": [str(arbol["licencias"][0].id)]}).status_code == 401


@pytest.mark.parametrize("invalida", [False, True])
def test_alta_varias_herramientas_es_atomica(client, arbol, db_session, invalida):
    db_session.commit()
    herramienta_ids = [str(h.id) for h in arbol["herramientas"]]
    if invalida:
        herramienta_ids[-1] = str(uuid.uuid4())
    antes = db_session.query(Licencia).count()
    payload = {
        "empleado_ids": [str(arbol["empleados"][n].id) for n in ["Lescano", "Gimenez", "Lescano"]],
        "licencias": [
            {"herramienta_id": h, "fecha_inicio": date.today().isoformat(), "costo_mensual": costo, "moneda": moneda}
            for h, costo, moneda in zip(herramienta_ids, ["20.50", "1500.00"], ["USD", "ARS"])
        ],
    }
    r = client.post("/api/v1/innovacion/licencias/lote", json=payload, headers=arbol["headers"])
    assert r.status_code == (404 if invalida else 201), r.text
    assert db_session.query(Licencia).count() == antes + (0 if invalida else 4)
    if not invalida:
        assert r.json()["creadas"] == 4
