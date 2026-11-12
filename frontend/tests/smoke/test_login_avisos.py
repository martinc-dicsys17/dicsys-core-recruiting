"""El login muestra los avisos que llegan con la redirección (link vencido, contraseña configurada, sesión expirada).

Los toasts del layout solo existen con sesión, así que antes estos avisos no se veían en el login y aparecían recién
después de entrar (F02-P03).
"""

import pytest

pytestmark = [pytest.mark.frontend, pytest.mark.smoke]


@pytest.mark.parametrize(
    "categoria,mensaje",
    [
        ("error", "El enlace es inválido o ha expirado"),
        ("success", "¡Contraseña configurada correctamente! Ya podés iniciar sesión"),
    ],
)
def test_el_login_muestra_el_aviso_y_lo_consume(frontend_client, categoria, mensaje):
    with frontend_client.session_transaction() as sesion:
        sesion["_flashes"] = [(categoria, mensaje)]

    html = frontend_client.get("/login").get_data(as_text=True)
    assert mensaje in html and f'data-flash="{categoria}"' in html
    assert html.count(mensaje) == 1, "un solo bloque de avisos en el login"
    assert mensaje not in frontend_client.get("/login").get_data(as_text=True), "se muestra una sola vez"
