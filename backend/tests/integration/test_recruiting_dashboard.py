"""Dashboard de Recruiting (GET /api/v1/recruiting/dashboard): permisos, indicadores, visibilidad por grupo, avisos
y cantidad de consultas. Las reglas son las del DashboardService del módulo original (modulo-recluiter)."""

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import event

from backend.database import engine
from backend.modules.recruiting.models import (
    Candidato,
    GestionBusqueda,
    Postulacion,
    RecruitingHabilidad,
    RecruitingSkill,
    Solicitud,
    TransicionEstado,
)
from backend.modules.recruiting.services import DashboardService
from backend.tests.helpers.auth import auth_headers

pytestmark = pytest.mark.integration

URL = "/api/v1/recruiting/dashboard"
PERMISOS_DASHBOARD = ["recruiting", "recruiting.dashboard"]
BASE = datetime(2026, 11, 10, 12, 0, 0)


class Recruiting:
    """Datos mínimos de Recruiting para los tests."""

    def __init__(self, session, empresa):
        self.session = session
        self.empresa = empresa

    def _guardar(self, objeto):
        self.session.add(objeto)
        self.session.flush()
        return objeto

    def busqueda(self, *, estado="Abierta", activo=True, externo=None, creada=BASE, empresa=None, titulo="Dev"):
        return self._guardar(
            Solicitud(
                empresa_id=(empresa or self.empresa).id,
                cliente="ACME",
                titulo=titulo,
                estado=estado,
                activo=activo,
                externo_id=externo.id if externo else None,
                created_at=creada,
            )
        )

    def candidato(self, *, activo=True, creador=None, creado=BASE, empresa=None, nombre="Ana", borrado=False):
        return self._guardar(
            Candidato(
                empresa_id=(empresa or self.empresa).id,
                nombre=nombre,
                apellido="Perez",
                email=f"{uuid.uuid4().hex}@example.com",
                headline="Backend Developer",
                seniority="Senior",
                activo=activo,
                creador_id=creador.id if creador else None,
                created_at=creado,
                deleted_at=BASE if borrado else None,
            )
        )

    def en_pipeline(self, busqueda, candidato, *, estado="En proceso", activo=True):
        return self._guardar(
            GestionBusqueda(
                empresa_id=self.empresa.id,
                oportunidad_id=busqueda.id,
                candidato_id=candidato.id,
                etapa_actual="Entrevista RRHH",
                estado=estado,
                activo=activo,
            )
        )

    def postulacion(self, busqueda, candidato, *, estado="En proceso", activo=True):
        return self._guardar(
            Postulacion(
                empresa_id=self.empresa.id,
                solicitud_id=busqueda.id,
                candidato_id=candidato.id,
                estado=estado,
                activo=activo,
            )
        )

    def transicion(self, candidato, *, estado="Entrevista", motivo=None, creada=BASE):
        return self._guardar(
            TransicionEstado(
                empresa_id=self.empresa.id,
                candidato_id=candidato.id,
                estado_nuevo=estado,
                motivo_rechazo=motivo,
                created_at=creada,
            )
        )


@pytest.fixture
def empresa(data_factory):
    return data_factory.empresa()


@pytest.fixture
def recruiting(db_session, empresa):
    return Recruiting(db_session, empresa)


@pytest.fixture
def usuario_con_grupo(data_factory, empresa):
    """Un usuario de la empresa en un grupo con el nombre dado y los permisos del Dashboard."""

    def crear(nombre_grupo="Reclutadores Test", permisos=PERMISOS_DASHBOARD):
        usuario = data_factory.usuario()
        grupo = data_factory.grupo(
            nombre=f"{nombre_grupo} {uuid.uuid4().hex[:6]}" if nombre_grupo != "EXTERNOS" else nombre_grupo
        )
        data_factory.asignar_empresa(usuario, empresa)
        data_factory.asignar_grupo(usuario, grupo, empresa)
        data_factory.permisos(grupo, permisos)
        return usuario

    return crear


@pytest.fixture
def admin(data_factory, empresa):
    usuario = data_factory.usuario(rol="admin")
    data_factory.asignar_empresa(usuario, empresa)
    return usuario


# --- Permisos -------------------------------------------------------------------------------------------------------


def test_sin_token_responde_401(client):
    assert client.get(URL).status_code == 401


def test_sin_el_modulo_recruiting_responde_403(client, usuario_con_grupo, empresa):
    usuario = usuario_con_grupo(permisos=["configuracion"])
    assert client.get(URL, headers=auth_headers(usuario, empresa)).status_code == 403


def test_con_el_modulo_pero_sin_el_item_dashboard_responde_403(client, usuario_con_grupo, empresa):
    usuario = usuario_con_grupo(permisos=["recruiting", "recruiting.candidatos"])
    respuesta = client.get(URL, headers=auth_headers(usuario, empresa))
    assert respuesta.status_code == 403
    assert respuesta.json()["detail"] == "No tenés acceso a 'dashboard'"


def test_con_el_modulo_y_el_item_dashboard_responde_200(client, usuario_con_grupo, empresa):
    usuario = usuario_con_grupo()
    respuesta = client.get(URL, headers=auth_headers(usuario, empresa))
    assert respuesta.status_code == 200
    assert set(respuesta.json()) == {"kpis", "avisos", "resumen_operativo"}


def test_el_admin_entra_sin_permisos_de_grupo(client, admin, empresa):
    assert client.get(URL, headers=auth_headers(admin, empresa)).status_code == 200


def test_el_contrato_declara_el_operation_id_y_la_respuesta_tipada(client):
    operacion = client.get("/openapi.json").json()["paths"][URL]["get"]
    assert operacion["operationId"] == "recruiting_dashboard"
    esquema = operacion["responses"]["200"]["content"]["application/json"]["schema"]
    assert esquema == {"$ref": "#/components/schemas/RecruitingDashboard"}


# --- Indicadores ----------------------------------------------------------------------------------------------------


def test_indicadores_de_la_empresa_activa(client, admin, empresa, data_factory, recruiting, db_session):
    otra = data_factory.empresa()
    abierta = recruiting.busqueda(estado="Abierta")
    recruiting.busqueda(estado="Pre-ingreso")
    recruiting.busqueda(estado="Ganada")
    recruiting.busqueda(estado="Abierta", activo=False)  # dada de baja: no cuenta en ningún lado
    recruiting.busqueda(estado="Abierta", empresa=otra)  # otra empresa
    ana = recruiting.candidato()
    beto = recruiting.candidato(nombre="Beto")
    recruiting.candidato(activo=False)
    recruiting.candidato(empresa=otra)
    borrado = recruiting.candidato(borrado=True)  # activo pero con deleted_at: cuenta como candidato, no en proceso
    recruiting.en_pipeline(abierta, ana)
    recruiting.en_pipeline(abierta, borrado)
    recruiting.en_pipeline(abierta, beto, estado="Descartado")
    db_session.add_all(
        [
            RecruitingSkill(nombre=f"skill-{uuid.uuid4().hex}", activo=True),
            RecruitingSkill(nombre=f"skill-{uuid.uuid4().hex}", activo=True),
            RecruitingSkill(nombre=f"skill-{uuid.uuid4().hex}", activo=False),
            RecruitingHabilidad(nombre=f"hab-{uuid.uuid4().hex}", activo=True),
            RecruitingHabilidad(nombre=f"hab-{uuid.uuid4().hex}", activo=False),
        ]
    )
    db_session.flush()

    datos = client.get(URL, headers=auth_headers(admin, empresa)).json()

    assert datos["kpis"] == {
        "busquedas_activas": 2,
        "total_candidatos": 3,
        "postulaciones_en_proceso": 1,
        "skills_catalogo": 2,
        "habilidades_catalogo": 1,
    }
    assert datos["resumen_operativo"] == {"tasa_candidatos_proceso": 33.3, "busquedas_totales": 3}


def test_sin_pipeline_en_proceso_cuenta_las_postulaciones(admin, empresa, recruiting, db_session):
    busqueda = recruiting.busqueda()
    ana = recruiting.candidato()
    beto = recruiting.candidato(nombre="Beto")
    recruiting.en_pipeline(busqueda, ana, estado="Descartado")
    recruiting.postulacion(busqueda, ana)
    recruiting.postulacion(busqueda, beto, estado="Rechazado")

    datos = DashboardService.obtener(db_session, empresa.id, admin)

    assert datos.kpis.postulaciones_en_proceso == 1
    assert datos.resumen_operativo.tasa_candidatos_proceso == 50.0


def test_sin_candidatos_la_tasa_es_cero(admin, empresa, db_session):
    datos = DashboardService.obtener(db_session, empresa.id, admin)
    assert datos.resumen_operativo.tasa_candidatos_proceso == 0
    assert datos.avisos == []


# --- Visibilidad por grupo ------------------------------------------------------------------------------------------


def test_el_externo_ve_solo_sus_busquedas_y_sus_candidatos(usuario_con_grupo, empresa, recruiting, db_session):
    externo = usuario_con_grupo("EXTERNOS")
    otro = usuario_con_grupo("Reclutadores")
    asignada = recruiting.busqueda(externo=externo)
    recruiting.busqueda(externo=otro)
    recruiting.busqueda(estado="Pre-ingreso")
    propio = recruiting.candidato(creador=externo)
    ajeno = recruiting.candidato(creador=otro)
    recruiting.en_pipeline(asignada, propio)
    recruiting.en_pipeline(asignada, ajeno)
    recruiting.transicion(propio, estado="Entrevista")
    recruiting.transicion(ajeno, estado="Oferta")

    datos = DashboardService.obtener(db_session, empresa.id, externo)

    assert datos.kpis.busquedas_activas == 1
    assert datos.resumen_operativo.busquedas_totales == 1
    assert datos.kpis.total_candidatos == 1
    assert datos.kpis.postulaciones_en_proceso == 1
    transiciones = [a for a in datos.avisos if a.tipo == "transicion"]
    assert [a.descripcion for a in transiciones] == ["Pasó a 'Entrevista'"]


def test_el_grupo_de_recruiting_ve_todo_aunque_tambien_este_en_externos(
    usuario_con_grupo, data_factory, empresa, recruiting, db_session
):
    usuario = usuario_con_grupo("RECLUIT")  # variante de nombre del grupo de Recruiting
    data_factory.asignar_grupo(usuario, data_factory.grupo(nombre="EXTERNOS"), empresa)
    otro = usuario_con_grupo("Otros")
    recruiting.busqueda(externo=otro)
    recruiting.busqueda()
    recruiting.candidato(creador=otro)
    recruiting.candidato()

    datos = DashboardService.obtener(db_session, empresa.id, usuario)

    assert datos.kpis.busquedas_activas == 2
    assert datos.kpis.total_candidatos == 2


def test_otro_grupo_ve_todas_las_busquedas_y_solo_sus_candidatos(usuario_con_grupo, empresa, recruiting, db_session):
    usuario = usuario_con_grupo("Comercial")
    recruiting.busqueda()
    recruiting.busqueda(estado="Pre-ingreso")
    recruiting.candidato(creador=usuario)
    recruiting.candidato()

    datos = DashboardService.obtener(db_session, empresa.id, usuario)

    assert datos.kpis.busquedas_activas == 2
    assert datos.kpis.total_candidatos == 1


def test_un_grupo_de_otra_empresa_no_cuenta(usuario_con_grupo, data_factory, empresa, recruiting, db_session):
    usuario = usuario_con_grupo("Comercial")
    otra = data_factory.empresa()
    data_factory.asignar_grupo(usuario, data_factory.grupo(nombre="RECRUITING"), otra)
    recruiting.candidato()

    datos = DashboardService.obtener(db_session, empresa.id, usuario)

    assert datos.kpis.total_candidatos == 0


# --- Avisos ---------------------------------------------------------------------------------------------------------


def test_avisos_de_busquedas_sin_postulantes(admin, empresa, recruiting, db_session):
    sin_nadie = recruiting.busqueda(titulo="Sin nadie")
    con_pipeline = recruiting.busqueda(titulo="Con pipeline")
    con_postulacion = recruiting.busqueda(titulo="Con postulacion")
    pipeline_inactivo = recruiting.busqueda(titulo="Pipeline inactivo")
    recruiting.busqueda(titulo="Pre ingreso", estado="Pre-ingreso")  # solo las Abiertas generan aviso
    candidato = recruiting.candidato(creado=BASE - timedelta(days=30))
    recruiting.en_pipeline(con_pipeline, candidato, estado="Descartado")  # cualquier estado activo cuenta
    recruiting.postulacion(con_postulacion, candidato)
    recruiting.en_pipeline(pipeline_inactivo, candidato, activo=False)

    avisos = [
        a for a in DashboardService.obtener(db_session, empresa.id, admin).avisos if a.tipo == "busqueda_sin_candidatos"
    ]

    assert sorted(a.titulo for a in avisos) == [
        "Búsqueda sin postulantes: Pipeline inactivo",
        "Búsqueda sin postulantes: Sin nadie",
    ]
    aviso = next(a for a in avisos if a.titulo.endswith("Sin nadie"))
    assert aviso.id == f"sin_cands_{sin_nadie.id}"
    assert aviso.descripcion == "La búsqueda para ACME no tiene candidatos asignados en el embudo."
    assert aviso.tiempo == f"{sin_nadie.dias_abierta} días abierta"
    assert aviso.enlace == f"/recruiting/oportunidades/{sin_nadie.id}"
    assert (aviso.icono, aviso.color) == ("alert-triangle", "amber")


def test_avisos_de_transiciones_y_candidatos_nuevos(admin, empresa, recruiting, db_session):
    candidato = recruiting.candidato(nombre="Carla", creado=datetime(2026, 11, 9, 2, 30))
    recruiting.transicion(candidato, estado="Descartado", motivo="Pretension alta", creada=datetime(2026, 11, 9, 15, 5))

    avisos = DashboardService.obtener(db_session, empresa.id, admin).avisos

    transicion, nuevo = avisos
    assert transicion.tipo == "transicion"
    assert transicion.titulo == "Cambio de etapa: Carla Perez"
    assert transicion.descripcion == "Pasó a 'Descartado' (Pretension alta)"
    assert transicion.tiempo == "09/11 12:05"  # 15:05 UTC en hora argentina
    assert transicion.enlace == f"/recruiting/candidatos/{candidato.id}"
    assert nuevo.tipo == "candidato_nuevo"
    assert nuevo.titulo == "Nuevo candidato: Carla Perez"
    assert nuevo.descripcion == "Backend Developer · Senior"
    assert nuevo.tiempo == "08/11 23:30"  # 02:30 UTC del 9 es el 8 a la noche en Argentina


def test_los_avisos_van_del_mas_reciente_al_mas_viejo_y_son_ocho_como_mucho(admin, empresa, recruiting, db_session):
    for dia in range(6):
        recruiting.busqueda(titulo=f"B{dia}", creada=BASE - timedelta(days=dia))
    candidatos = [
        recruiting.candidato(nombre=f"C{dia}", creado=BASE - timedelta(days=dia, hours=1)) for dia in range(5)
    ]
    for dia, candidato in enumerate(candidatos):
        for n in range(2):
            recruiting.transicion(candidato, creada=BASE - timedelta(days=dia, hours=2 + n))

    avisos = DashboardService.obtener(db_session, empresa.id, admin).avisos

    assert len(avisos) == 8
    fechas = [a.created_at for a in avisos]
    assert fechas == sorted(fechas, reverse=True)
    assert sum(a.tipo == "transicion" for a in avisos) <= 5
    assert sum(a.tipo == "candidato_nuevo" for a in avisos) <= 3


# --- Consultas ------------------------------------------------------------------------------------------------------


def _consultas(funcion):
    sentencias = []

    def contar(conn, cursor, statement, parameters, context, executemany):
        sentencias.append(statement)

    event.listen(engine, "before_cursor_execute", contar)
    try:
        funcion()
    finally:
        event.remove(engine, "before_cursor_execute", contar)
    return len(sentencias)


def test_la_cantidad_de_consultas_no_crece_con_los_datos(usuario_con_grupo, empresa, recruiting, db_session):
    usuario = usuario_con_grupo("Comercial")
    recruiting.busqueda()
    recruiting.transicion(recruiting.candidato(creador=usuario))
    pocas = _consultas(lambda: DashboardService.obtener(db_session, empresa.id, usuario))

    for n in range(15):
        recruiting.busqueda(titulo=f"Extra {n}")
        recruiting.transicion(recruiting.candidato(creador=usuario))
    muchas = _consultas(lambda: DashboardService.obtener(db_session, empresa.id, usuario))

    assert pocas == muchas
    assert muchas <= 9
