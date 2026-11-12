"""
Módulo Notificaciones - Saludos de cumpleaños por Webex.

Vistas:
- notificaciones.cumpleanos          : UI principal con cumpleañeros del día, estado del proceso y log de envíos.
- notificaciones.cumpleanos_panel    : partial HTMX (se refresca solo mientras el proceso corre).
- notificaciones.cumpleanos_procesar : dispara el proceso de envío en el backend.
- notificaciones.oauth_callback      : callback OAuth de la integración lectora de Webex
                                       (/notificaciones/oauth/callback: debe coincidir con
                                       el Redirect URI registrado en developer.webex.com).
                                       La URL absoluta se deriva del host del request, así
                                       el mismo código sirve en localhost y producción.
"""

import logging

from flask import Blueprint, render_template, request, session, url_for

from modulos.auth_helpers import get_api_request_func, require_permiso
from modulos.error_helpers import error_html, format_api_error

logger = logging.getLogger(__name__)

notificaciones_bp = Blueprint("notificaciones", __name__, template_folder="templates", url_prefix="/notificaciones")

# Submódulo de Configuración (igual que Parámetros).
login_required = require_permiso("configuracion.notificaciones")


def _toast_success(mensaje):
    """Script que dispara un toast de éxito (sistema global de Alpine.js)."""
    msg = mensaje.replace("\\", "\\\\").replace("'", "\\'")
    return f"""
    <script>
    (function() {{
        if (typeof Alpine !== 'undefined' && Alpine.store('toasts')) {{
            Alpine.store('toasts').success('{msg}', 4000);
        }}
    }})();
    </script>
    """


def _detalle(result):
    """Extrae el detail de una respuesta de la API de forma segura."""
    return result.get("detail") if isinstance(result, dict) else None


def _callback_url():
    """
    URL absoluta del callback OAuth, derivada del host con el que el usuario
    accede (http://localhost:8080, https://core.dicsys.ai, etc.). Debe estar
    registrada en los Redirect URIs de la integración de Webex.

    El esquema sale de X-Forwarded-Proto (el proxy termina el TLS y Flask ve
    http); si no viene el header, todo host no-local se asume https.
    """
    scheme = (request.headers.get("X-Forwarded-Proto") or request.scheme).split(",")[0].strip()
    host = request.host
    es_local = host.split(":")[0] in ("localhost", "127.0.0.1")
    if scheme == "http" and not es_local:
        scheme = "https"
    return f"{scheme}://{host}" + url_for("notificaciones.oauth_callback")


def _obtener_panel(api_request, token):
    """Arma el contexto del panel: cumpleañeros de hoy + cuenta lectora + log."""
    from urllib.parse import quote

    hoy, _ = api_request("GET", "/notificaciones/cumpleanos/hoy", token=token)
    if not isinstance(hoy, dict):
        hoy = {}

    reader, _ = api_request(
        "GET",
        f"/notificaciones/webex-reader?redirect_uri={quote(_callback_url(), safe='')}",
        token=token,
    )
    if not isinstance(reader, dict):
        reader = {}

    estado = request.values.get("estado", "").strip()
    endpoint_logs = "/notificaciones/logs?limit=100"
    if estado:
        endpoint_logs += f"&estado={estado}"
    logs, _ = api_request("GET", endpoint_logs, token=token)
    if not isinstance(logs, dict):
        logs = {}

    return {
        "cumpleaneros": hoy.get("items", []),
        "en_ejecucion": hoy.get("en_ejecucion", False),
        "reader": reader,
        "logs": logs.get("items", []),
        "filtro_estado": estado,
    }


def _render_panel(api_request, token):
    return render_template("notificaciones/partials/panel.html", **_obtener_panel(api_request, token))


# ─── UI PRINCIPAL ────────────────────────────────────────────────────────────


@notificaciones_bp.route("/cumpleanos", methods=["GET"])
@login_required
def cumpleanos():
    api_request = get_api_request_func()
    token = session.get("token")

    ctx = _obtener_panel(api_request, token)
    if request.headers.get("HX-Request"):
        return render_template("notificaciones/partials/panel.html", **ctx)
    return render_template("notificaciones/list.html", **ctx)


# ─── PANEL (PARTIAL CON AUTO-REFRESH) ────────────────────────────────────────


@notificaciones_bp.route("/cumpleanos/panel", methods=["GET"])
@login_required
def cumpleanos_panel():
    api_request = get_api_request_func()
    token = session.get("token")
    return _render_panel(api_request, token)


# ─── PROCESAR ────────────────────────────────────────────────────────────────


@notificaciones_bp.route("/cumpleanos/procesar", methods=["POST"])
@login_required
def cumpleanos_procesar():
    api_request = get_api_request_func()
    token = session.get("token")

    result, status = api_request("POST", "/notificaciones/cumpleanos/procesar", {}, token=token)

    if status == 200:
        mensaje = result.get("message", "Proceso iniciado") if isinstance(result, dict) else "Proceso iniciado"
        return _render_panel(api_request, token) + _toast_success(mensaje)

    return _render_panel(api_request, token) + error_html(_detalle(result), "Error al iniciar el proceso de envío"), 400


# ─── CALLBACK OAUTH WEBEX (cuenta lectora) ───────────────────────────────────


@notificaciones_bp.route("/oauth/callback")
def oauth_callback():
    """
    Recibe el authorization code de Webex y lo canjea contra el backend.
    La URL completa (host + /notificaciones/oauth/callback) debe coincidir
    con un Redirect URI registrado en la integración de Webex.
    """
    code = request.args.get("code")
    state = request.args.get("state")
    error = request.args.get("error")

    if error:
        return render_template("notificaciones/oauth_resultado.html", ok=False, detalle=f"Webex devolvió: {error}"), 400
    if not code:
        return render_template(
            "notificaciones/oauth_resultado.html", ok=False, detalle="No se recibió el authorization code"
        ), 400
    if "token" not in session:
        return render_template(
            "notificaciones/oauth_resultado.html",
            ok=False,
            detalle="No hay sesión iniciada. Iniciá sesión y volvé a autorizar desde Notificaciones → Cumpleaños.",
        ), 401

    api_request = get_api_request_func()
    result, status = api_request(
        "POST",
        "/notificaciones/webex-reader/code",
        {"code": code, "state": state, "redirect_uri": _callback_url()},
        token=session.get("token"),
    )

    if status == 200 and isinstance(result, dict):
        return render_template("notificaciones/oauth_resultado.html", ok=True, email=result.get("account_email"))

    return render_template(
        "notificaciones/oauth_resultado.html",
        ok=False,
        detalle=format_api_error(_detalle(result), "No se pudo conectar la cuenta lectora"),
    ), 400
