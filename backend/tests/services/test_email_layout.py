"""Mails con la marca de Dicsys Core: layout común, bienvenida y restablecer contraseña."""

import pytest

from backend.core import email_layout as correo
from backend.modules.usuarios import emails

pytestmark = pytest.mark.services


def test_layout_con_la_marca_en_azul_y_los_datos_escapados():
    cuerpo = correo.pagina(
        titulo="Título <x>",
        subtitulo="Sub & más",
        seccion="Sección",
        cuerpo=correo.parrafo(correo.e("<script>")) + correo.lista(["A&B"]),
        pie="Pie",
    )

    assert correo.marca() in cuerpo and "#0967D2" in cuerpo  # el azul primary de la app
    assert "#4F46E5" not in cuerpo and "#7C3AED" not in cuerpo  # sin el violeta
    assert "Título &lt;x&gt;" in cuerpo and "Sub &amp; más" in cuerpo and "&lt;script&gt;" in cuerpo
    assert "A&amp;B" in cuerpo and "<script>" not in cuerpo


def test_bienvenida_con_el_link_y_los_datos_escapados():
    html = emails.bienvenida("Ana <b>", "ana@dicsys.com", "https://core/magic?t=1&x=2", 24)
    assert "Ana &lt;b&gt;" in html and "ana@dicsys.com" in html
    assert 'href="https://core/magic?t=1&amp;x=2"' in html and "Configurar mi contraseña" in html
    assert "24 horas" in html and "#0967D2" in html


def test_bienvenida_con_password_y_restablecer():
    con_password = emails.bienvenida_con_password("Ana", "ana@dicsys.com", "p<ss>", "https://core/login")
    assert "p&lt;ss&gt;" in con_password and "Ingresar al sistema" in con_password
    assert "Importante" in con_password and "cambiar tu contraseña" in con_password

    restablecer = emails.restablecer_password("Ana", "https://core/reset-password?token=abc")
    assert "Restablecer contraseña" in restablecer and "token=abc" in restablecer and "1 hora" in restablecer


def test_el_diseno_conserva_iconos_titulo_destacado_y_avisos():
    """La idea de las plantillas originales: ícono arriba, título en azul, íconos en botón y datos."""
    bienvenida = emails.bienvenida("Ana", "ana@dicsys.com", "https://core/magic", 48)
    assert "👋" in bienvenida and "🔐&nbsp; Configurar mi contraseña" in bienvenida
    assert "📧" in bienvenida and "⏰" in bienvenida and "box-shadow" in bienvenida

    con_password = emails.bienvenida_con_password("Ana", "ana@dicsys.com", "clave", "https://core/login")
    assert "🔑&nbsp; Contraseña:" in con_password and "<code" in con_password
    assert "🚀&nbsp; Ingresar al sistema" in con_password and "⚠️&nbsp; Importante:" in con_password

    # Los íconos son opcionales: sin ellos las piezas quedan como antes
    assert "&nbsp;" not in correo.boton("https://x", "Ir")
    assert "<strong>" not in correo.nota("Solo texto")
