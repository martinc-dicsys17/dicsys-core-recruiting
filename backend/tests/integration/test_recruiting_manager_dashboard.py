"""Manager Dashboard de Recruiting (GET /api/v1/recruiting/manager-dashboard): acceso exclusivo de administradores y
cálculos. Las reglas son las de ManagerDashboardService del módulo original (modulo-recluiter)."""

import uuid
from datetime import datetime, timedelta

import pytest

from backend.core.utils import utc_now
from backend.modules.recruiting.models import Candidato, GestionBusqueda, HistorialPipeline, Solicitud
from backend.tests.helpers.auth import auth_headers

pytestmark = pytest.mark.integration

URL = "/api/v1/recruiting/manager-dashboard"
PERMISOS_DASHBOARD = ["recruiting", "recruiting.dashboard"]
PRESENTADO = datetime(2025, 1, 6, 12, 0, 0)  # bien en el pasado: los días sin movimiento no dependen de la fecha de hoy


def _dias(n):
    return PRESENTADO + timedelta(days=n)


@pytest.fixture
def empresa(data_factory):
    return data_factory.empresa()


@pytest.fixture
def admin(data_factory, empresa):
    usuario = data_factory.usuario(rol="admin")
    data_factory.asignar_empresa(usuario, empresa)
    return usuario


@pytest.fixture
def usuario_con_grupo(data_factory, empresa):
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


class Datos:
    """Postulaciones mínimas para los tests."""

    def __init__(self, session, empresa):
        self.session = session
        self.empresa = empresa

    def _guardar(self, objeto):
        self.session.add(objeto)
        self.session.flush()
        return objeto

    def busqueda(self, externo, titulo="Backend Python", empresa=None):
        return self._guardar(
            Solicitud(
                empresa_id=(empresa or self.empresa).id,
                cliente="ACME",
                titulo=titulo,
                estado="Abierta",
                activo=True,
                externo_id=externo.id,
            )
        )

    def postulacion(self, busqueda, creador, *, etapa, estado="En proceso", motivo=None, movimientos=(), cambio=None):
        """Candidato creado por `creador`, presentado en PRESENTADO, con su recorrido [(anterior, nueva, día)]."""
        candidato = self._guardar(
            Candidato(
                empresa_id=busqueda.empresa_id,
                nombre="Cand",
                apellido=uuid.uuid4().hex[:6],
                email=f"{uuid.uuid4().hex}@example.com",
                headline="Dev",
                seniority="Senior",
                activo=True,
                creador_id=creador.id,
            )
        )
        self._guardar(
            GestionBusqueda(
                empresa_id=busqueda.empresa_id,
                oportunidad_id=busqueda.id,
                candidato_id=candidato.id,
                etapa_actual=etapa,
                estado=estado,
                motivo_descarte=motivo,
                fecha_cambio_etapa=cambio or (_dias(movimientos[-1][2]) if movimientos else PRESENTADO),
                created_at=PRESENTADO,
            )
        )
        for anterior, nueva, dia in movimientos:
            self._guardar(
                HistorialPipeline(
                    empresa_id=busqueda.empresa_id,
                    oportunidad_id=busqueda.id,
                    candidato_id=candidato.id,
                    etapa_anterior=anterior,
                    etapa_nueva=nueva,
                    created_at=_dias(dia),
                )
            )
        return candidato


@pytest.fixture
def datos(db_session, empresa):
    return Datos(db_session, empresa)


@pytest.fixture
def externo(usuario_con_grupo):
    return usuario_con_grupo("EXTERNOS", permisos=PERMISOS_DASHBOARD)


# --- Acceso ---------------------------------------------------------------------------------------------------------


def test_sin_token_responde_401(client):
    assert client.get(URL).status_code == 401


def test_el_admin_accede(client, admin, empresa):
    respuesta = client.get(URL, headers=auth_headers(admin, empresa))
    assert respuesta.status_code == 200
    assert set(respuesta.json()) == {
        "filtros",
        "umbrales",
        "granularidad_evolucion",
        "criterios",
        "resumen",
        "externos",
        "tiempos",
        "alertas",
        "opciones_usuarios",
        "opciones_busquedas",
        "no_disponible",
    }


def test_un_recruiter_con_permiso_de_dashboard_no_accede(client, usuario_con_grupo, empresa):
    reclutador = usuario_con_grupo("Recruiting")
    respuesta = client.get(URL, headers=auth_headers(reclutador, empresa))
    assert respuesta.status_code == 403
    assert "resumen" not in respuesta.json()


def test_un_externo_no_accede(client, externo, empresa):
    assert client.get(URL, headers=auth_headers(externo, empresa)).status_code == 403


def test_un_usuario_sin_permisos_no_accede(client, usuario_con_grupo, empresa):
    sin_permisos = usuario_con_grupo(permisos=["configuracion"])
    assert client.get(URL, headers=auth_headers(sin_permisos, empresa)).status_code == 403


def test_el_email_admin_no_alcanza_si_el_rol_no_es_admin(client, data_factory, empresa):
    # La identificación es por rol (require_admin), no por email como en el módulo original
    impostor = data_factory.usuario(rol="usuario", email="admin@admin.com")
    data_factory.asignar_empresa(impostor, empresa)
    assert client.get(URL, headers=auth_headers(impostor, empresa)).status_code == 403


def test_filtros_invalidos_responden_422(client, admin, empresa):
    for consulta in ("tipo=otro", "dias_estancado=0", "umbral_tasa_avance=101", "oportunidad_id=no-es-uuid"):
        assert client.get(f"{URL}?{consulta}", headers=auth_headers(admin, empresa)).status_code == 422


def test_el_contrato_declara_el_operation_id_y_la_respuesta_tipada(client):
    operacion = client.get("/openapi.json").json()["paths"][URL]["get"]
    assert operacion["operationId"] == "recruiting_manager_dashboard"
    esquema = operacion["responses"]["200"]["content"]["application/json"]["schema"]
    assert esquema == {"$ref": "#/components/schemas/ManagerDashboard"}


# --- Cálculos -------------------------------------------------------------------------------------------------------


def test_sin_externos_todo_es_cero_real(client, admin, empresa):
    datos = client.get(URL, headers=auth_headers(admin, empresa)).json()

    assert datos["externos"] == [] and datos["alertas"] == []
    assert datos["resumen"]["postulaciones"] == 0
    assert datos["resumen"]["tasa_avance"] is None  # sin base: no es un cero
    assert datos["resumen"]["revision"] == {"cantidad": 0, "promedio_dias": None, "mediana_dias": None}


def test_indicadores_del_externo(client, admin, empresa, datos, externo):
    busqueda = datos.busqueda(externo)
    datos.postulacion(
        busqueda,
        externo,
        etapa="Ingreso",
        movimientos=[
            ("Candidato", "Entrevista RRHH", 1),
            ("Entrevista RRHH", "Oferta", 5),
            ("Oferta", "Ingreso", 9),
        ],
    )
    datos.postulacion(
        busqueda,
        externo,
        etapa="Descartados",
        estado="Descartado",
        motivo="Sin skills",
        movimientos=[("Candidato", "Descartados", 3)],
    )
    datos.postulacion(busqueda, externo, etapa="Candidato", cambio=utc_now() - timedelta(days=30))
    interno = admin  # candidato cargado por el equipo interno en la búsqueda del externo: no le cuenta
    datos.postulacion(busqueda, interno, etapa="Oferta", movimientos=[("Candidato", "Oferta", 2)])

    cuerpo = client.get(URL, headers=auth_headers(admin, empresa)).json()
    resumen = cuerpo["resumen"]

    assert resumen["postulaciones"] == 3 and resumen["candidatos_unicos"] == 3
    assert (resumen["avanzaron"], resumen["tasa_avance"]) == (1, 33.3)
    assert (resumen["entrevista"], resumen["finales"], resumen["contratados"]) == (1, 1, 1)
    assert (resumen["descartados"], resumen["tasa_descartados"]) == (1, 33.3)
    assert resumen["estancados"] == 1
    assert resumen["revision"] == {"cantidad": 2, "promedio_dias": 2.0, "mediana_dias": 2.0}
    assert {e["etapa"]: e["cantidad"] for e in resumen["embudo"]} == {
        "Candidato": 3,
        "Screening": 0,
        "Entrevista RRHH": 1,
        "Entrevista Líder Dicsys": 0,
        "Validación Administración": 0,
        "Entrevista Cliente": 0,
        "Oferta": 1,
        "Examen Médico Preocupacional": 0,
        "Ingreso": 1,
    }
    assert resumen["motivos_descarte"] == [{"motivo": "Sin skills", "cantidad": 1}]
    assert resumen["evolucion"] == [{"periodo": "2025-01-06", "presentados": 3, "avanzaron": 1}]
    assert cuerpo["granularidad_evolucion"] == "dia"

    (fila,) = cuerpo["externos"]
    assert fila["usuario_id"] == str(externo.id) and fila["tipo"] == "Sin clasificar"
    assert fila["busquedas_asignadas"] == 1
    assert fila["cuadrante"] == "bajo_volumen_alta_tasa"  # 33,3 % >= 20 % de umbral, 3 < 10 postulaciones
    assert fila["por_busqueda"][0]["presentados"] == 3

    tiempos = cuerpo["tiempos"]
    assert tiempos["hasta_descarte"]["promedio_dias"] == 3.0
    assert tiempos["hasta_oferta"]["promedio_dias"] == 5.0
    assert tiempos["hasta_ingreso"]["promedio_dias"] == 9.0
    assert {(t["desde"], t["hasta"], t["promedio_dias"]) for t in tiempos["entre_etapas"]} == {
        ("Candidato", "Entrevista RRHH", 1.0),
        ("Entrevista RRHH", "Oferta", 4.0),
        ("Oferta", "Ingreso", 4.0),
        ("Candidato", "Descartados", 3.0),
    }
    assert len(tiempos["estancados"]) == 1 and tiempos["estancados"][0]["dias_sin_movimiento"] >= 30
    assert [(a["tipo"], a["severidad"]) for a in cuerpo["alertas"]] == [("sin_movimiento", "media")]


def test_alerta_de_volumen_con_baja_tasa_y_umbrales_configurables(client, admin, empresa, datos, externo):
    busqueda = datos.busqueda(externo)
    for _ in range(4):
        datos.postulacion(busqueda, externo, etapa="Candidato", cambio=utc_now())  # recién movidas: no están estancadas

    por_defecto = client.get(URL, headers=auth_headers(admin, empresa)).json()
    ajustado = client.get(f"{URL}?umbral_volumen=4&umbral_tasa_avance=50", headers=auth_headers(admin, empresa)).json()

    assert por_defecto["alertas"] == []  # 4 postulaciones: bajo el umbral de volumen de 10
    assert [(a["tipo"], a["severidad"]) for a in ajustado["alertas"]] == [("volumen_baja_tasa", "alta")]
    assert ajustado["externos"][0]["cuadrante"] == "alto_volumen_baja_tasa"
    assert ajustado["umbrales"]["umbral_volumen"] == 4


def test_filtra_por_fecha_de_presentacion_y_por_busqueda(client, admin, empresa, datos, externo):
    una = datos.busqueda(externo, "Una")
    otra = datos.busqueda(externo, "Otra")
    datos.postulacion(una, externo, etapa="Candidato")
    datos.postulacion(otra, externo, etapa="Candidato")
    cabecera = auth_headers(admin, empresa)

    assert client.get(f"{URL}?fecha_desde=2025-01-07", headers=cabecera).json()["resumen"]["postulaciones"] == 0
    assert client.get(f"{URL}?fecha_hasta=2025-01-06", headers=cabecera).json()["resumen"]["postulaciones"] == 2
    assert client.get(f"{URL}?oportunidad_id={una.id}", headers=cabecera).json()["resumen"]["postulaciones"] == 1
    assert client.get(f"{URL}?usuario_ids={uuid.uuid4()}", headers=cabecera).json()["externos"] == []


def test_solo_cuenta_la_empresa_activa(client, admin, empresa, data_factory, datos, externo):
    otra = data_factory.empresa()
    ajena = datos.busqueda(externo, empresa=otra)
    datos.postulacion(ajena, externo, etapa="Candidato")

    assert client.get(URL, headers=auth_headers(admin, empresa)).json()["resumen"]["postulaciones"] == 0
