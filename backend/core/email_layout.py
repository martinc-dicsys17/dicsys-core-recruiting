"""
Layout de los mails con la marca de Dicsys Core (D-96, D-97).

Encabezado con el nombre de la app en los azules del tema y, debajo, un título grande y
centrado con su ícono; después el contenido (párrafos, cajas con íconos, botón, avisos)
y el pie. Es la idea de las plantillas originales (título destacado, íconos, botón con
sombra, cajas de datos y de aviso) con los colores de la app en lugar del violeta.

Maquetado con tablas y estilos en línea, que es lo que respetan Gmail y Outlook; la
marca va como texto porque el logo es SVG y esos clientes no lo muestran. Los íconos son
emojis: se ven en todos los clientes sin cargar imágenes. Donde un cliente no soporta
algo (degradé, sombra, bordes redondeados en Outlook) queda el color sólido.

Las piezas (`parrafo`, `caja`, `credenciales`, `lista`, `nota`, `aclaracion`, `boton`,
`enlace_alternativo`) devuelven filas de la tabla principal; `pagina` arma el mail con
ellas. Todo dato que viene de la base o del usuario pasa por `e()`.
"""

import html
from typing import Iterable, Optional, Tuple

from backend.core.config import settings

# Los `primary` (azules) y los grises `dark` del tema de la app (base.html)
PRIMARIO, SECUNDARIO = "#0967D2", "#0552B5"  # primary-500 → primary-600, como los botones
CLARO = "#BAE3FF"  # primary-100
FONDO_ICONO = "#E6F2FF"  # primary-50
TEXTO, TEXTO_MEDIO, TEXTO_SUAVE, TEXTO_TENUE = "#0F172A", "#334155", "#64748B", "#94A3B8"
BORDE, FONDO_CAJA, FONDO = "#E2E8F0", "#F1F5F9", "#F1F5F9"
FONDO_CODIGO = "#E2E8F0"
# Avisos (ámbar)
AVISO_FONDO, AVISO_BORDE, AVISO_TEXTO = "#FEF3C7", "#F59E0B", "#92400E"
_DEGRADE = f"background:{PRIMARIO};background-image:linear-gradient(135deg,{PRIMARIO} 0%,{SECUNDARIO} 100%);"

e = html.escape


def marca() -> str:
    return e(settings.app_name or "Dicsys Core")


def _con_icono(icono: Optional[str], texto_html: str) -> str:
    return f"{icono}&nbsp; {texto_html}" if icono else texto_html


def parrafo(html_seguro: str) -> str:
    """Un párrafo. Recibe HTML ya armado (escapá los datos con `e()` antes)."""
    return (
        f'<tr><td style="padding:12px 40px 0;font-size:16px;color:{TEXTO_MEDIO};line-height:1.6;">'
        f"{html_seguro}</td></tr>"
    )


def caja(html_seguro: str, icono: Optional[str] = None) -> str:
    """Un recuadro gris claro con un dato destacado (ej. el email de acceso)."""
    return (
        f'<tr><td style="padding:20px 40px 0;"><div style="background:{FONDO_CAJA};border-radius:12px;'
        f'padding:18px 20px;font-size:15px;color:{TEXTO};line-height:1.6;">'
        f"{_con_icono(icono, html_seguro)}</div></td></tr>"
    )


def codigo(texto: str) -> str:
    """Un valor para copiar tal cual (una contraseña), en monoespaciada. Texto plano."""
    return (
        f'<code style="background:{FONDO_CODIGO};padding:4px 8px;border-radius:4px;'
        f'font-family:Consolas,Menlo,monospace;font-size:14px;">{e(texto)}</code>'
    )


def credenciales(filas: Iterable[Tuple[str, str, str]]) -> str:
    """
    Un recuadro con datos de acceso, uno por renglón: (ícono, etiqueta, valor). La etiqueta
    es texto plano; el valor es HTML ya escapado (ej. `e(email)` o `codigo(password)`).
    """
    renglones = "".join(
        f'<tr><td style="padding:6px 0;font-size:15px;color:{TEXTO};line-height:1.6;">'
        f"<strong>{icono}&nbsp; {e(etiqueta)}:</strong> {valor}</td></tr>"
        for icono, etiqueta, valor in filas
    )
    return (
        f'<tr><td style="padding:22px 40px 0;"><table role="presentation" width="100%" cellpadding="0" '
        f'cellspacing="0" style="background:{FONDO_CAJA};border-radius:12px;">'
        f'<tr><td style="padding:14px 20px;"><table role="presentation" width="100%" cellpadding="0" '
        f'cellspacing="0">{renglones}</table></td></tr></table></td></tr>'
    )


def lista(items: Iterable[str], vacia: str = "Sin elementos", icono: Optional[str] = None) -> str:
    """Una lista dentro de un recuadro; los ítems son texto plano. Sin ícono, una viñeta azul."""
    vineta = icono or f'<span style="color:{PRIMARIO};font-weight:bold;">&#8226;</span>'
    filas = (
        "".join(
            f'<tr><td style="padding:11px 18px;border-top:1px solid {BORDE};font-size:15px;color:{TEXTO};">'
            f"{vineta}&nbsp; {e(item)}</td></tr>"
            for item in items
        )
        or f'<tr><td style="padding:13px 18px;font-size:14px;color:{TEXTO_SUAVE};">{e(vacia)}</td></tr>'
    )
    return (
        f'<tr><td style="padding:18px 40px 0;"><table role="presentation" width="100%" cellpadding="0" '
        f'cellspacing="0" style="background:{FONDO_CAJA};border-radius:12px;overflow:hidden;">'
        f"{filas}</table></td></tr>"
    )


def nota(texto: str, titulo: Optional[str] = None, icono: Optional[str] = None) -> str:
    """
    Un aviso destacado en ámbar con borde a la izquierda (una advertencia, las pruebas).
    `titulo` va en negrita adelante (ej. «Importante»). Texto plano.
    """
    encabezado = f"<strong>{_con_icono(icono, e(titulo))}:</strong> " if titulo else _con_icono(icono, "")
    return (
        f'<tr><td style="padding:20px 40px 0;"><div style="background:{AVISO_FONDO};'
        f"border-left:4px solid {AVISO_BORDE};border-radius:12px;padding:16px 18px;font-size:14px;"
        f'color:{AVISO_TEXTO};line-height:1.5;">{encabezado}{e(texto)}</div></td></tr>'
    )


def aclaracion(html_seguro: str, icono: Optional[str] = None) -> str:
    """Una línea chica en gris (vencimiento de un enlace, qué hacer si no fue uno)."""
    return (
        f'<tr><td style="padding:16px 40px 0;font-size:14px;color:{TEXTO_SUAVE};line-height:1.5;">'
        f"{_con_icono(icono, html_seguro)}</td></tr>"
    )


def boton(url: str, texto: str, icono: Optional[str] = None) -> str:
    """El botón principal, centrado, con el degradé azul y sombra."""
    return (
        f'<tr><td align="center" style="padding:30px 40px 10px;"><a href="{e(url)}" style="display:inline-block;'
        f"{_DEGRADE}color:#FFFFFF;text-decoration:none;font-weight:bold;font-size:16px;padding:14px 32px;"
        f'border-radius:12px;box-shadow:0 4px 14px rgba(9,103,210,0.35);">{_con_icono(icono, e(texto))}</a>'
        f"</td></tr>"
    )


def enlace_alternativo(url: str) -> str:
    """El link escrito, por si el botón no funciona."""
    return (
        f'<tr><td align="center" style="padding:6px 40px 4px;font-size:13px;color:{TEXTO_SUAVE};'
        f'line-height:1.5;word-break:break-all;">Si el botón no funciona, copiá y pegá este enlace en tu '
        f'navegador:<br><a href="{e(url)}" style="color:{PRIMARIO};">{e(url)}</a></td></tr>'
    )


def pagina(
    *,
    titulo: str,
    cuerpo: str,
    subtitulo: Optional[str] = None,
    seccion: Optional[str] = None,
    pie: Optional[str] = None,
    icono: Optional[str] = None,
) -> str:
    """
    El mail completo. `titulo`, `subtitulo`, `seccion` y `pie` son texto plano; `icono` es
    un emoji que va en un círculo arriba del título; `cuerpo` es la concatenación de las
    piezas de este módulo (filas de la tabla principal).
    """
    icono_html = (
        f'<table role="presentation" align="center" cellpadding="0" cellspacing="0" '
        f'style="margin:0 auto 14px;"><tr><td align="center" valign="middle" width="64" height="64" '
        f'style="width:64px;height:64px;background:{FONDO_ICONO};border-radius:32px;font-size:30px;'
        f'line-height:64px;text-align:center;">{icono}</td></tr></table>'
        if icono
        else ""
    )
    subtitulo_html = (
        f'<div style="font-size:15px;color:{TEXTO_SUAVE};margin-top:8px;">{e(subtitulo)}</div>' if subtitulo else ""
    )
    seccion_html = f'<div style="font-size:13px;color:{CLARO};margin-top:2px;">{e(seccion)}</div>' if seccion else ""
    pie_html = f"<br>{e(pie)}" if pie else ""
    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{e(titulo)}</title></head>
<body style="margin:0;padding:0;background:{FONDO};font-family:Arial,Helvetica,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{FONDO};padding:24px 12px;">
<tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:600px;background:#FFFFFF;border-radius:14px;overflow:hidden;box-shadow:0 2px 10px rgba(15,23,42,0.08);">
  <tr><td style="{_DEGRADE}padding:18px 40px;">
    <div style="font-size:20px;font-weight:bold;color:#FFFFFF;letter-spacing:0.3px;">{marca()}</div>{seccion_html}
  </td></tr>
  <tr><td align="center" style="padding:34px 40px 10px;text-align:center;">
    {icono_html}<div style="font-size:26px;font-weight:bold;color:{PRIMARIO};line-height:1.3;">{e(titulo)}</div>{subtitulo_html}
  </td></tr>
  {cuerpo}
  <tr><td style="padding:30px 40px 0;"><div style="border-top:1px solid {BORDE};"></div></td></tr>
  <tr><td style="padding:16px 40px 24px;font-size:12px;color:{TEXTO_TENUE};text-align:center;line-height:1.5;">
    {marca()}{pie_html}
  </td></tr>
</table>
</td></tr></table>
</body></html>"""
