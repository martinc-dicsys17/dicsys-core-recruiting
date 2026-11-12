"""Aviso de canje nuevo de Star Miles al room de Webex de quienes aprueban (F20)."""

import json
from datetime import datetime
from decimal import Decimal

import pytest

from backend.modules.nomina.models import Empleado
from backend.modules.parametros.models import Parametro
from backend.modules.starmiles import avisos
from backend.modules.starmiles.models import Canje, EmpleadoStarMiles, ItemCanje
from backend.modules.starmiles.services import CanjeService
from backend.modules.tareas import cola
from backend.modules.tareas.models import Envio

pytestmark = [pytest.mark.integration, pytest.mark.deploy_gate]


@pytest.fixture
def entorno(db_session, data_factory):
    empresa = data_factory.empresa()
    empleado = Empleado(
        empresa_id=empresa.id, codigo="SM-1", cuil=20_300_000_011, dni=30_000_011, nombre="ANA", apellido="PÉREZ"
    )
    db_session.add(empleado)
    db_session.flush()
    db_session.add(
        EmpleadoStarMiles(
            empresa_id=empresa.id, empleado_id=empleado.id, millas_historicas=5000, millas_disponibles=5000
        )
    )
    producto = ItemCanje(empresa_id=empresa.id, nombre="Mochila Dicsys", tipo="producto", star_miles_costo=1250)
    mercadolibre = ItemCanje(empresa_id=empresa.id, nombre="Compra en MercadoLibre", tipo="mercadolibre")
    db_session.add_all([producto, mercadolibre])
    db_session.flush()
    return {"empresa": empresa, "empleado": empleado, "producto": producto, "mercadolibre": mercadolibre}


def _room(db_session, valor="room-canjes"):
    db_session.add(
        Parametro(
            categoria="Notificaciones",
            subcategoria="Webex",
            key=avisos.CLAVE_ROOM,
            nombre="Sala de Notificación de Canjes de Star Miles",
            valor=valor,
        )
    )
    db_session.flush()


def _canjear(db_session, entorno, item, **datos):
    return CanjeService.crear(
        db_session,
        entorno["empresa"].id,
        str(entorno["empleado"].id),
        {"item_id": str(item.id), "cantidad": 1, **datos},
    )


def test_un_canje_nuevo_encola_la_card_al_room_y_el_programador_la_manda(db_session, entorno, fake_webex):
    _room(db_session)

    canje = _canjear(db_session, entorno, entorno["producto"], comentario="Talle M, color azul")

    [envio] = db_session.query(Envio).all()
    assert (envio.origen, envio.canal, envio.destino, envio.estado) == (
        "starmiles_canjes",
        "webex_room",
        "room-canjes",
        "pendiente",
    )
    assert envio.clave == f"starmiles_canje:{canje.id}"  # un canje, un aviso
    assert envio.asunto == "Nuevo canje de Star Miles: Ana Pérez"
    card = envio.contenido["card"]
    texto = json.dumps(card, ensure_ascii=False)
    assert "Ana Pérez pidió un canje" in texto and "Mochila Dicsys" in texto
    assert "1.250" in texto and "Talle M, color azul" in texto
    assert card["actions"][0]["url"].endswith("/starmiles/aprobador/canjes")

    resultado = cola.despachar(db_session, pausar=False)
    assert resultado["enviados"] == 1
    [mensaje] = fake_webex.messages
    assert mensaje["kind"] == "card" and mensaje["room_id"] == "room-canjes"
    assert mensaje["text"] == "Nuevo canje de Star Miles: Ana Pérez pidió «Mochila Dicsys» (1.250 Star Miles)."


def test_canje_de_mercadolibre_muestra_el_precio_y_el_link(db_session, entorno):
    _room(db_session)

    _canjear(
        db_session,
        entorno,
        entorno["mercadolibre"],
        star_miles_calculado=1234,
        mercadolibre_url="https://articulo.mercadolibre.com.ar/MLA-1",
        mercadolibre_precio=Decimal("1234.50"),
    )

    card = db_session.query(Envio).one().contenido["card"]
    assert "$ 1.234,50" in json.dumps(card, ensure_ascii=False)
    assert card["actions"][1] == {
        "type": "Action.OpenUrl",
        "title": "Ver en MercadoLibre",
        "url": "https://articulo.mercadolibre.com.ar/MLA-1",
    }


@pytest.mark.parametrize("valor", [None, "", "   "])
def test_sin_room_configurado_no_se_avisa_y_el_canje_se_registra(db_session, entorno, valor):
    if valor is not None:
        _room(db_session, valor)

    canje = _canjear(db_session, entorno, entorno["producto"])

    assert db_session.get(Canje, canje.id).estado == "pendiente"
    assert db_session.query(Envio).count() == 0


def test_si_el_aviso_falla_el_canje_se_registra_igual(db_session, entorno, monkeypatch):
    _room(db_session)

    def roto(*args, **kwargs):
        raise RuntimeError("cola caída")

    monkeypatch.setattr(cola, "encolar", roto)
    canje = _canjear(db_session, entorno, entorno["producto"])

    assert db_session.get(Canje, canje.id).estado == "pendiente"
    assert db_session.query(Envio).count() == 0


def test_la_card_usa_la_hora_argentina():
    canje = Canje(cantidad=2, star_miles_total=500, fecha_solicitud=datetime(2026, 10, 5, 15, 30))
    item = ItemCanje(nombre="Taza")
    card = avisos.tarjeta_canje(canje, None, item)
    texto = json.dumps(card, ensure_ascii=False)
    assert "05/10/2026 12:30" in texto  # 15:30 UTC
    assert "Un colaborador pidió un canje" in texto
