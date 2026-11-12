"""Errores de Webex legibles: los usan cumpleaños, evaluación de proveedores e innovación."""

import pytest

from backend.core.webex import describir_error

pytestmark = pytest.mark.services

ERROR_TEAM = (
    '{"message":"Unable to post message to room: \\"User 0000 must join the team conversation before '
    'posting activities\\"","errors":[],"trackingId":"ROUTERGW_x"}'
)


@pytest.mark.parametrize(
    "resultado, esperado",
    [
        ({"error": ERROR_TEAM, "status_code": 403}, "no es miembro del equipo (team)"),
        (
            {"error": '{"message":"Could not find a room with provided ID."}', "status_code": 404},
            "No se encontró el room",
        ),
        ({"error": '{"message":"The request requires a valid access token."}', "status_code": 401}, "token del bot"),
        (
            {"error": '{"message":"Algo nuevo de Webex"}', "status_code": 400},
            "Algo nuevo de Webex",
        ),  # su message, sin JSON
        ({"error": "Timeout al conectar con Webex API"}, "Timeout al conectar con Webex API"),
        ({}, "Webex no confirmó el envío"),
        (None, "Webex no confirmó el envío"),
    ],
)
def test_los_errores_de_webex_se_muestran_legibles(resultado, esperado):
    assert esperado in describir_error(resultado)
