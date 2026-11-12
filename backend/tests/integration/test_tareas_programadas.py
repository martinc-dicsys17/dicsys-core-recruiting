"""Motor de tareas programadas (F19): horario, programador, historial, alertas, cola y tareas de los módulos."""

from datetime import date, datetime, time, timedelta

import pytest

from backend.core.utils import utc_now
from backend.modules.notificaciones import services as notificaciones, tareas as tareas_notificaciones
from backend.modules.notificaciones.models import NotificacionLog
from backend.modules.parametros.models import Parametro
from backend.modules.sincronizacion import tareas as tareas_sincronizacion  # noqa: F401 - registra sus tareas
from backend.modules.sincronizacion.models import ProcesoSincronizacion
from backend.modules.sincronizacion.services import SincronizacionService
from backend.modules.tareas import cola, programador, registro
from backend.modules.tareas.models import TareaCorrida
from backend.modules.tareas.parametros import asegurar_parametros, utc_a_argentina
from backend.modules.tareas.registro import (
    ZONA_ARGENTINA,
    FalloTarea,
    Horario,
    ahora_argentina,
    parsear_horario,
    proxima,
    registrar_tarea,
    toca,
)
from backend.tests.helpers.auth import auth_headers

URL = "/api/v1/tareas"
pytestmark = [pytest.mark.integration, pytest.mark.deploy_gate]


def ar(dia: date, hh: int, mm: int = 0) -> datetime:
    return datetime.combine(dia, time(hh, mm), tzinfo=ZONA_ARGENTINA)


LUNES = date(2026, 10, 5)


# ─── Horario ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("09:00", Horario("diaria", hora=time(9, 0))),
        ("  7:30 ", Horario("diaria", hora=time(7, 30))),
        ("L-V 09:00", Horario("habiles", hora=time(9, 0))),
        ("l - v 18:15", Horario("habiles", hora=time(18, 15))),
        ("cada 2h", Horario("horas", cada_horas=2)),
        ("Cada 6 horas", Horario("horas", cada_horas=6)),
    ],
)
def test_horarios_validos(texto, esperado):
    assert parsear_horario(texto) == esperado


@pytest.mark.parametrize("texto", ["", "25:00", "9", "cada 0h", "cada 30h", "mañana", "L-S 09:00"])
def test_horarios_invalidos(texto):
    with pytest.raises(ValueError, match="inválid"):
        parsear_horario(texto)


def test_toca_una_vez_por_dia_desde_la_hora():
    diaria = parsear_horario("09:00")
    assert not toca(diaria, ar(LUNES, 8, 59), None)
    assert toca(diaria, ar(LUNES, 9, 0), None)
    assert toca(diaria, ar(LUNES, 15, 0), None)  # si el backend estaba caído a la hora, corre al levantarse
    assert not toca(diaria, ar(LUNES, 15, 0), ar(LUNES, 9, 0))  # ya corrió hoy
    assert toca(diaria, ar(LUNES + timedelta(days=1), 9, 0), ar(LUNES, 9, 0))
    assert proxima(diaria, ar(LUNES, 10, 0), ar(LUNES, 9, 0)) == ar(LUNES + timedelta(days=1), 9, 0)


def test_habiles_no_corre_el_fin_de_semana_y_cada_n_horas():
    habiles = parsear_horario("L-V 09:00")
    sabado = LUNES + timedelta(days=5)
    assert not toca(habiles, ar(sabado, 10, 0), None)
    assert proxima(habiles, ar(sabado, 10, 0), ar(LUNES + timedelta(days=4), 9, 0)) == ar(
        LUNES + timedelta(days=7), 9, 0
    )
    cada2 = parsear_horario("cada 2h")
    assert toca(cada2, ar(LUNES, 10, 0), None)
    assert not toca(cada2, ar(LUNES, 11, 59), ar(LUNES, 10, 0))
    assert toca(cada2, ar(LUNES, 12, 0), ar(LUNES, 10, 0))


# ─── Registro de prueba ─────────────────────────────────────────────────────────


@pytest.fixture
def registro_limpio():
    """Deja solo las tareas que registra cada test y restaura el registro al terminar."""
    guardadas = dict(registro.TAREAS)
    registro.TAREAS.clear()
    programador._ultima_continua.clear()
    yield registro.TAREAS
    registro.TAREAS.clear()
    registro.TAREAS.update(guardadas)
    programador._ultima_continua.clear()


def _room_de_alertas(db, room="room-alertas"):
    asegurar_parametros(db)
    db.query(Parametro).filter_by(key="alertas_webex_room_id").one().valor = room
    db.flush()


def _configurar(db, codigo, activa="1", horario="09:00"):
    asegurar_parametros(db)
    db.query(Parametro).filter_by(key=f"tarea_{codigo}_activa").one().valor = activa
    db.query(Parametro).filter_by(key=f"tarea_{codigo}_horario").one().valor = horario
    db.flush()


def _corridas(db, codigo):
    return db.query(TareaCorrida).filter_by(tarea=codigo).order_by(TareaCorrida.creada_at).all()


def test_el_programador_corre_lo_que_toca_una_vez(db_session, registro_limpio, fake_webex):
    hechas = []
    registrar_tarea(
        codigo="prueba_ok", nombre="Prueba OK", modulo="Tests", funcion=lambda db: hechas.append(1) or "hecho"
    )
    registrar_tarea(codigo="prueba_apagada", nombre="Prueba apagada", modulo="Tests", funcion=lambda db: "no")
    _configurar(db_session, "prueba_ok")
    _configurar(db_session, "prueba_apagada", activa="0")

    hoy = datetime.now(ZONA_ARGENTINA).date()
    assert programador.vuelta(db_session, ar(hoy, 8, 0), en_hilos=False) == []
    assert programador.vuelta(db_session, ar(hoy, 9, 1), en_hilos=False) == ["prueba_ok"]
    assert programador.vuelta(db_session, ar(hoy, 9, 2), en_hilos=False) == []  # ya corrió hoy

    [corrida] = _corridas(db_session, "prueba_ok")
    assert (corrida.estado, corrida.disparo, corrida.resultado) == ("ok", "programado", "hecho")
    assert corrida.inicio and corrida.fin and hechas == [1]
    assert _corridas(db_session, "prueba_apagada") == []
    assert fake_webex.messages == []  # sin fallas, sin alertas


def test_sin_sus_parametros_una_tarea_no_corre(db_session, registro_limpio):
    registrar_tarea(
        codigo="prueba_sin_param",
        nombre="Sin parámetros",
        modulo="Tests",
        funcion=lambda db: "no debería",
        activa_default=True,
        horario_default="00:00",
    )
    assert programador.vuelta(db_session, ar(LUNES, 12, 0), en_hilos=False) == []


def test_la_falla_queda_en_el_historial_y_alerta_una_sola_vez(db_session, registro_limpio, fake_webex):
    def se_cae(db):
        raise FalloTarea("No responde la base de Odoo")

    registrar_tarea(codigo="prueba_falla", nombre="Nómina de prueba", modulo="Tests", funcion=se_cae)
    _configurar(db_session, "prueba_falla", horario="cada 1h")
    _room_de_alertas(db_session)

    # La corrida guarda su hora real y la ventana de «la última hora» mira el reloj real:
    # las horas simuladas salen de ahora (con una fecha fija, el test vencía ese día)
    primera = ahora_argentina()
    programador.vuelta(db_session, primera, en_hilos=False)
    [corrida] = _corridas(db_session, "prueba_falla")
    assert (corrida.estado, corrida.error, corrida.alerta_enviada) == ("error", "No responde la base de Odoo", True)
    [alerta] = fake_webex.messages
    assert alerta["kind"] == "card" and alerta["room_id"] == "room-alertas"
    assert alerta["card"]["body"][0]["text"] == "Falló: Nómina de prueba"
    assert "No responde la base de Odoo" in alerta["card"]["body"][2]["items"][0]["text"]
    assert alerta["card"]["actions"][0]["url"].endswith("/tareas-programadas?tab=historial")

    # Vuelve a fallar igual dentro de la hora: queda en el historial pero no repite la alerta
    programador.vuelta(db_session, primera + timedelta(minutes=61), en_hilos=False)
    assert [c.estado for c in _corridas(db_session, "prueba_falla")] == ["error", "error"]
    assert len(fake_webex.messages) == 1


def test_una_excepcion_inesperada_tambien_alerta_y_sin_room_queda_en_el_log(db_session, registro_limpio, fake_webex):
    registrar_tarea(codigo="prueba_bug", nombre="Bug", modulo="Tests", funcion=lambda db: 1 / 0)
    _configurar(db_session, "prueba_bug")  # sin room de alertas configurado

    programador.vuelta(db_session, ar(LUNES, 9, 30), en_hilos=False)
    [corrida] = _corridas(db_session, "prueba_bug")
    assert corrida.estado == "error" and corrida.error.startswith("ZeroDivisionError")
    assert corrida.alerta_enviada is False and fake_webex.messages == []


def test_continua_solo_deja_corrida_si_hizo_algo_o_fallo(db_session, registro_limpio, fake_webex):
    estado = {"respuesta": None}

    def avisos(db):
        if estado["respuesta"] == "error":
            raise FalloTarea("Empresa X: sin evaluación")
        return estado["respuesta"]

    registrar_tarea(codigo="prueba_continua", nombre="Continua", modulo="Tests", funcion=avisos, continua=True)
    _room_de_alertas(db_session)
    momento = ar(LUNES, 9, 0)

    programador.vuelta(db_session, momento, en_hilos=False)
    assert _corridas(db_session, "prueba_continua") == []
    estado["respuesta"] = "3 avisos encolados"
    programador.vuelta(
        db_session, momento + timedelta(seconds=20), en_hilos=False
    )  # corre como mucho una vez por minuto
    assert _corridas(db_session, "prueba_continua") == []
    programador.vuelta(db_session, momento + timedelta(minutes=1), en_hilos=False)
    assert [(c.estado, c.resultado) for c in _corridas(db_session, "prueba_continua")] == [("ok", "3 avisos encolados")]
    estado["respuesta"] = "error"
    programador.vuelta(db_session, momento + timedelta(minutes=2), en_hilos=False)
    assert _corridas(db_session, "prueba_continua")[-1].estado == "error"
    assert len(fake_webex.messages) == 1


def test_las_corridas_interrumpidas_por_un_reinicio_quedan_en_error(db_session, registro_limpio, fake_webex):
    registrar_tarea(codigo="prueba_larga", nombre="Larga", modulo="Tests", funcion=lambda db: "ok")
    _room_de_alertas(db_session)
    db_session.add(TareaCorrida(tarea="prueba_larga", estado="en_curso", inicio=utc_now()))
    db_session.flush()

    assert programador.marcar_interrumpidas(db_session) == 1
    [corrida] = _corridas(db_session, "prueba_larga")
    assert corrida.estado == "error" and "reinició" in corrida.error and len(fake_webex.messages) == 1


# ─── API ────────────────────────────────────────────────────────────────────────


@pytest.fixture
def admin(data_factory):
    empresa = data_factory.empresa()
    usuario = data_factory.usuario()
    grupo = data_factory.grupo()
    data_factory.asignar_empresa(usuario, empresa)
    data_factory.asignar_grupo(usuario, grupo, empresa)
    data_factory.permisos(grupo, ["configuracion", "configuracion.tareas_programadas"])
    return {"usuario": usuario, "headers": auth_headers(usuario, empresa)}


def test_pantalla_lista_tareas_y_corre_una_a_mano(client, db_session, registro_limpio, admin):
    registrar_tarea(
        codigo="prueba_manual", nombre="Manual", modulo="Tests", funcion=lambda db: "listo", horario_default="L-V 07:00"
    )
    registrar_tarea(codigo="prueba_continua", nombre="Continua", modulo="Tests", funcion=lambda db: None, continua=True)
    _configurar(db_session, "prueba_manual", activa="1", horario="L-V 07:00")

    tabla = client.get(URL, headers=admin["headers"]).json()
    assert tabla["alertas_configuradas"] is False and tabla["parametro_alertas"] == "alertas_webex_room_id"
    filas = {t["codigo"]: t for t in tabla["tareas"]}
    manual = filas["prueba_manual"]
    assert manual["activa"] is True and manual["horario"] == "L-V 07:00"
    assert manual["horario_texto"] == "De lunes a viernes a las 07:00" and manual["proxima"]
    assert manual["parametros"] == ["tarea_prueba_manual_activa", "tarea_prueba_manual_horario"]
    assert filas["prueba_continua"]["continua"] is True and filas["prueba_continua"]["parametros"] == []

    pedida = client.post(f"{URL}/prueba_manual/ejecutar", headers=admin["headers"])
    assert pedida.status_code == 201 and pedida.json()["estado"] == "pendiente"
    assert pedida.json()["solicitada_por"] == admin["usuario"].email
    assert client.post(f"{URL}/prueba_manual/ejecutar", headers=admin["headers"]).status_code == 409
    assert client.post(f"{URL}/no_existe/ejecutar", headers=admin["headers"]).status_code == 404

    _configurar(db_session, "prueba_manual", activa="0", horario="L-V 07:00")  # que solo corra la pedida a mano
    programador.vuelta(db_session, en_hilos=False)  # el programador la toma en la próxima vuelta
    [corrida] = client.get(f"{URL}/corridas?tarea=prueba_manual", headers=admin["headers"]).json()
    assert (corrida["estado"], corrida["disparo"], corrida["resultado"]) == ("ok", "manual", "listo")
    filas = {t["codigo"]: t for t in client.get(URL, headers=admin["headers"]).json()["tareas"]}
    assert filas["prueba_manual"]["ultima"]["estado"] == "ok"


def test_horario_invalido_se_ve_en_la_pantalla_y_no_corre(client, db_session, registro_limpio, admin):
    registrar_tarea(codigo="prueba_mal", nombre="Mal", modulo="Tests", funcion=lambda db: "no")
    _configurar(db_session, "prueba_mal", horario="a las 9")

    [fila] = client.get(URL, headers=admin["headers"]).json()["tareas"]
    assert "inválido" in fila["horario_error"] and fila["proxima"] is None
    assert programador.vuelta(db_session, ar(LUNES, 23, 0), en_hilos=False) == []


@pytest.mark.parametrize(
    "sufijo, valor, mensaje",
    [
        ("horario", "25:99", "Hora inválida: «25:99»"),
        ("horario", "todos los dias", "Horario inválido: «todos los dias». Usá «09:00», «L-V 09:00» o «cada 2h»"),
        ("activa", "activo", "Valor inválido: «activo». Usá 1 (corre sola) o 0 (solo a mano)"),
    ],
)
def test_parametros_no_guarda_un_horario_o_activa_que_el_programador_no_entiende(
    client, db_session, data_factory, registro_limpio, sufijo, valor, mensaje
):
    registrar_tarea(codigo="prueba_param", nombre="Param", modulo="Tests", funcion=lambda db: "ok")
    _configurar(db_session, "prueba_param", activa="0", horario="08:00")
    empresa, usuario, grupo = data_factory.empresa(), data_factory.usuario(), data_factory.grupo()
    data_factory.asignar_empresa(usuario, empresa)
    data_factory.asignar_grupo(usuario, grupo, empresa)
    data_factory.permisos(grupo, ["configuracion", "configuracion.parametros"])
    headers = auth_headers(usuario, empresa)
    parametro = db_session.query(Parametro).filter_by(key=f"tarea_prueba_param_{sufijo}").one()
    anterior = parametro.valor

    for metodo, url, cuerpo in (
        ("put", f"/api/v1/parametros/{parametro.id}/valor", {"valor": valor}),
        (
            "put",
            f"/api/v1/parametros/{parametro.id}",
            {"categoria": parametro.categoria, "nombre": parametro.nombre, "key": parametro.key, "valor": valor},
        ),
    ):
        respuesta = getattr(client, metodo)(url, headers=headers, json=cuerpo)
        assert respuesta.status_code == 422 and respuesta.json() == {"detail": mensaje}
    db_session.refresh(parametro)
    assert parametro.valor == anterior

    # Lo que sí entiende se guarda, y vacío vuelve al valor por defecto
    for bueno in ("L-V 07:30" if sufijo == "horario" else "si", ""):
        assert (
            client.put(f"/api/v1/parametros/{parametro.id}/valor", headers=headers, json={"valor": bueno}).status_code
            == 200
        )


def test_sin_permiso_no_entra(client, data_factory):
    empresa = data_factory.empresa()
    usuario = data_factory.usuario()
    grupo = data_factory.grupo()
    data_factory.asignar_empresa(usuario, empresa)
    data_factory.asignar_grupo(usuario, grupo, empresa)
    data_factory.permisos(grupo, ["configuracion", "configuracion.parametros"])
    assert client.get(URL, headers=auth_headers(usuario, empresa)).status_code == 403


# ─── Cola de envíos ─────────────────────────────────────────────────────────────


def test_la_cola_despacha_en_orden_sin_duplicados_y_avisa_al_modulo(db_session, fake_email, fake_webex):
    avisados = []
    cola.registrar_manejador("prueba", lambda db, ident, envio: avisados.append((ident, envio.estado)))
    primero = cola.encolar(
        db_session,
        origen="tests",
        canal="email",
        destino="ana@dicsys.com",
        asunto="Hola",
        contenido={"html": "<p>Hola</p>", "cc": ["it@dicsys.com"]},
        clave="k1",
        referencia="prueba:1",
    )
    assert (
        cola.encolar(
            db_session, origen="tests", canal="email", destino="ana@dicsys.com", contenido={"html": "x"}, clave="k1"
        )
        is None
    )  # misma clave: no se duplica
    cola.encolar(
        db_session,
        origen="tests",
        canal="webex_room",
        destino="room-1",
        asunto="Resumen",
        contenido={"card": {"type": "AdaptiveCard"}, "texto": "Resumen"},
    )

    assert cola.despachar(db_session, pausar=False) == {"enviados": 2, "reintentos": 0, "fallidos": 0}
    assert fake_email.messages[0]["to"] == ["ana@dicsys.com", "it@dicsys.com"]
    assert fake_webex.messages[0]["room_id"] == "room-1" and fake_webex.messages[0]["kind"] == "card"
    db_session.refresh(primero)
    assert primero.estado == "enviado" and primero.intentos == 1 and avisados == [("1", "enviado")]


def test_la_cola_reintenta_y_al_tercer_fallo_alerta(db_session, fake_webex, monkeypatch):
    _room_de_alertas(db_session)
    alertas = []
    # Se parchea el adaptador falso, no el proxy webex_service: el proxy delega por __getattr__ y
    # al deshacer el parche le quedaría grabado el método de este test
    monkeypatch.setattr(
        fake_webex,
        "send_card",
        lambda tarjeta, fallback_text="", **destino: (
            alertas.append(tarjeta) or {"success": True}
            if destino.get("room_id") == "room-alertas"
            else {
                "success": False,
                "status_code": 404,
                "error": '{"message":"Could not find a room with provided ID."}',
            }
        ),
    )
    envio = cola.encolar(
        db_session,
        origen="avisos_evaluacion_proveedores",
        canal="webex_room",
        destino="room-roto",
        contenido={"card": {"type": "AdaptiveCard"}, "texto": "x"},
    )

    for intento in range(1, 4):
        resumen = cola.despachar(db_session, pausar=False)
        db_session.refresh(envio)
        assert envio.intentos == intento and "No se encontró el room" in envio.error
        if intento < 3:
            assert resumen["reintentos"] == 1 and envio.estado == "pendiente"
            assert envio.proximo_intento_at > utc_now()  # espera creciente: 1 y 5 minutos
            assert cola.despachar(db_session, pausar=False) == {"enviados": 0, "reintentos": 0, "fallidos": 0}
            envio.proximo_intento_at = utc_now() - timedelta(seconds=1)  # como si hubiera pasado la espera
            db_session.flush()
    assert envio.estado == "error" and envio.alerta_enviada is True
    [alerta] = alertas
    assert alerta["body"][0]["text"] == "No salieron 1 envío"

    assert cola.reintentar(db_session, envio).estado == "pendiente" and envio.intentos == 0


def test_reintentar_por_api(client, db_session, admin):
    envio = cola.encolar(db_session, origen="tests", canal="email", destino="x@dicsys.com", contenido={"html": "x"})
    envio.estado, envio.error = "error", "SendGrid caído"
    db_session.flush()

    [fila] = client.get(f"{URL}/envios?estado=error", headers=admin["headers"]).json()
    assert fila["error"] == "SendGrid caído"
    respuesta = client.post(f"{URL}/envios/{envio.id}/reintentar", headers=admin["headers"])
    assert respuesta.status_code == 200 and respuesta.json()["estado"] == "pendiente"
    assert client.post(f"{URL}/envios/{envio.id}/reintentar", headers=admin["headers"]).status_code == 409


# ─── Migración de los crons viejos ──────────────────────────────────────────────


def test_migra_los_parametros_de_los_crons_viejos_sin_cambiar_el_horario_real(db_session):
    for key, valor, default in (
        ("notificaciones_cron_activo", "0", "1"),
        ("notificaciones_cron_hora", "13:30", "12:00"),
        ("notificaciones_refresh_token_hora", None, "08:00"),
        ("sync_webex_cron_activo", "1", "0"),
        ("sync_webex_cron_hora", None, "11:00"),
    ):
        db_session.add(Parametro(categoria="Viejos", key=key, nombre=key, valor=valor, valor_default=default))
    db_session.flush()

    assert asegurar_parametros(db_session) is True
    valores = {p.key: p.valor for p in db_session.query(Parametro).filter(Parametro.deleted_at.is_(None))}
    assert valores["tarea_cumpleanos_activa"] == "0" and valores["tarea_cumpleanos_horario"] == "10:30"
    assert valores["tarea_webex_refresh_token_lector_horario"] == "05:00"
    assert valores["tarea_sync_webex_membresias_activa"] == "1"
    assert valores["tarea_sync_webex_membresias_horario"] == "08:00"
    assert "alertas_webex_room_id" in valores
    assert valores["tarea_sync_nomina_odoo_activa"] is None  # sin cron viejo: queda el default (apagado)
    viejos = db_session.query(Parametro).filter(Parametro.key.like("%cron%")).all()
    assert viejos and all(p.deleted_at is not None for p in viejos)
    assert asegurar_parametros(db_session) is False  # idempotente


@pytest.mark.parametrize("utc, argentina", [("12:00", "09:00"), ("02:15", "23:15"), ("nada", None)])
def test_utc_a_argentina(utc, argentina):
    assert utc_a_argentina(utc) == argentina


# ─── Tareas de los módulos ──────────────────────────────────────────────────────


def test_cumpleanos_falla_si_algun_saludo_no_salio(db_session, monkeypatch):
    def proceso_simulado(usuario):
        for nombre, estado, error in (("Ana Paz", "enviado", None), ("Luis Sosa", "error", "Webex caído")):
            db_session.add(
                NotificacionLog(
                    tipo="cumpleanos",
                    fecha_evento=date.today(),
                    empleado_nombre=nombre,
                    estado=estado,
                    error_detalle=error,
                )
            )
        db_session.flush()
        notificaciones._proceso_lock.release()

    monkeypatch.setattr(notificaciones.NotificacionService, "_procesar_cumpleanos", staticmethod(proceso_simulado))
    with pytest.raises(FalloTarea, match="1 saludo.*Luis Sosa: Webex caído"):
        tareas_notificaciones.saludos_de_cumpleanos(db_session)
    assert not notificaciones._proceso_lock.locked()

    # Con un envío manual en curso, la programada se omite sin pisarlo
    notificaciones._proceso_lock.acquire()
    try:
        assert "en curso" in tareas_notificaciones.saludos_de_cumpleanos(db_session)
    finally:
        notificaciones._proceso_lock.release()


def test_un_proceso_de_actualizacion_de_datos_programado(db_session, monkeypatch):
    proceso = ProcesoSincronizacion(codigo="sync_webex_membresias", nombre="Webex", tipo_origen="api", activo=True)
    db_session.add(proceso)
    db_session.flush()
    correr = registro.TAREAS["sync_webex_membresias"].funcion

    monkeypatch.setattr(
        SincronizacionService,
        "ejecutar_sincronizacion",
        staticmethod(
            lambda db, proceso_id, usuario=None, empresa_id=None: {
                "exito": True,
                "mensaje": "Membresías al día",
                "registros_procesados": 40,
                "registros_creados": 2,
                "registros_actualizados": 0,
                "registros_errores": 0,
            }
        ),
    )
    assert correr(db_session).startswith("Membresías al día · 40 procesados, 2 creados")

    monkeypatch.setattr(
        SincronizacionService,
        "ejecutar_sincronizacion",
        staticmethod(
            lambda db, proceso_id, usuario=None, empresa_id=None: {"exito": False, "mensaje": "Error: token vencido"}
        ),
    )
    with pytest.raises(FalloTarea, match="token vencido"):
        correr(db_session)

    proceso.activo = False
    db_session.flush()
    assert "desactivado" in correr(db_session)
