"""Endpoints públicos del proveedor OpenID Connect en core.dicsys.ai (F21, docs/OIDC.md).

La lógica vive en el backend (/api/v1/oidc/*). Acá queda lo del navegador: la sesión de Core, el login con retoma y
las redirecciones. El pedido de autorización pendiente viaja en una cookie firmada aparte y no en la sesión, porque
el login vacía la sesión ante cualquier 401 del backend (una contraseña mal escrita, por ejemplo).
"""

import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import unquote_plus

from flask import (
    Blueprint,
    abort,
    current_app,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from itsdangerous import BadSignature, URLSafeTimedSerializer
from markupsafe import Markup

oidc_bp = Blueprint("oidc", __name__, template_folder="templates")

PARAMETROS = (
    "response_type",
    "client_id",
    "redirect_uri",
    "scope",
    "state",
    "nonce",
    "code_challenge",
    "code_challenge_method",
)
COOKIE = "oidc_pendiente"
VIGENCIA = 600  # segundos, lo mismo que vive un código de autorización
# Lo que la app recibe en el id_token por cada scope (backend/modules/oidc/services.py), para el login
RECIBE = (
    ("email", "mail", "Tu email"),
    ("profile", "user", "Tu nombre y tu foto de perfil"),
    ("openid", "fingerprint", "Un identificador de tu cuenta que no cambia"),
)
# Cómo muestra el login a cada app, por client_id: su nombre (en vez del registrado en el cliente) y sus logos, en
# frontend/static/apps/, copiados sin tocar de la app. La marca es cuadrada (la `o` de razorback) y va como <img>. La
# horizontal es la animada de la barra de razorback: su tinta es currentColor, así que va en línea (en un <img> no
# hereda el color) y el login le da la tinta. `tinta` es la caja del dibujo sin el aire del archivo, la misma que usa
# razorback (frontend/src/lib/marca.ts).
APPS = {
    "razorback": {
        "nombre": "Razorback · Innovación",
        "marca": "apps/razorback/razorback-marca-o.svg",
        "horizontal": "apps/razorback/razorback-adaptable-h-inicio-animado.svg",
        "tinta": "80 80 1040 92.7",
    },
}


def _api():
    return current_app.config["api_request"]


def _serializador() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="oidc-pendiente")


def leer_pendiente() -> dict | None:
    """El ingreso con Core que quedó esperando el login: {'pedido': {...}, 'cliente': nombre}, o None."""
    valor = request.cookies.get(COOKIE)
    if not valor:
        return None
    try:
        return _serializador().loads(valor, max_age=VIGENCIA)
    except BadSignature:  # también si venció
        return None


@lru_cache(maxsize=8)
def _svg_en_linea(ruta: str, tinta: str) -> Markup:
    """El SVG del archivo para ir en línea: la caja recortada a la tinta y sin ancho ni alto propios (el tamaño lo
    pone el login)."""

    def etiqueta(m):
        svg = re.sub(r'\sviewBox="[^"]*"', f' viewBox="{tinta}"', m.group(0))
        svg = re.sub(r'\s(?:width|height)="[^"]*"', "", svg)
        return svg.replace("<svg", '<svg class="h-7 w-auto"', 1)  # 28 px de alto

    return Markup(re.sub(r"<svg\b[^>]*>", etiqueta, Path(ruta).read_text(encoding="utf-8"), count=1))


def _logos(app: dict) -> dict:
    if not app:
        return {}
    archivo = Path(current_app.static_folder) / app["horizontal"]
    return {"marca": app["marca"], "horizontal": _svg_en_linea(str(archivo), app["tinta"])}


def contexto_del_login(pendiente: dict | None) -> dict | None:
    """Lo que el login muestra de un ingreso pendiente: la app (su nombre, «nombre · detalle», y sus logos) y lo que
    va a recibir según el scope del pedido. None sin ingreso pendiente."""
    if not pendiente:
        return None
    pedido = pendiente.get("pedido", {})
    app = APPS.get(pedido.get("client_id"), {})
    cliente = app.get("nombre") or pendiente.get("cliente") or "la aplicación"
    nombre, _, detalle = cliente.partition(" · ")
    scopes = (pedido.get("scope") or "").split()
    recibe = [(icono, texto) for scope, icono, texto in RECIBE if scope in scopes]
    return {
        "cliente": cliente,
        "nombre": nombre,
        "detalle": detalle,
        "inicial": nombre[:1].upper(),
        "logos": _logos(app),
        "recibe": recibe,
        "resumen": ", ".join(texto.lower() for _, texto in recibe),
    }


def url_retoma() -> str | None:
    """Con un ingreso pendiente, la URL que lo retoma: el login termina ahí en vez de en el inicio de Core."""
    pendiente = leer_pendiente()
    return url_for("oidc.authorize", **pendiente["pedido"]) if pendiente else None


def _guardar(respuesta, pendiente: dict):
    respuesta.set_cookie(
        COOKIE,
        _serializador().dumps(pendiente),
        max_age=VIGENCIA,
        httponly=True,
        samesite="Lax",
        secure=request.is_secure,
    )
    return respuesta


def _cerrar(respuesta):
    respuesta.delete_cookie(COOKIE)
    return respuesta


def _json(datos, status: int, **cabeceras):
    respuesta = jsonify(datos)
    respuesta.status_code = status
    respuesta.headers.update(cabeceras)
    return respuesta


def _error(datos: dict, status: int = 400):
    """Un error del pedido: vuelve al cliente si el backend dio a dónde; si no (cliente o redirect_uri no registrados),
    se muestra acá y no se redirige a ningún lado."""
    if datos.get("redirect"):
        return _cerrar(redirect(datos["redirect"]))
    pagina = render_template(
        "oidc/error.html", error=datos.get("error"), descripcion=datos.get("error_description") or datos.get("detail")
    )
    return _cerrar(make_response(pagina, status))


@oidc_bp.route("/.well-known/openid-configuration")
def configuracion():
    datos, status = _api()("GET", "/oidc/configuracion")
    return _json(datos, status, **({"Cache-Control": "public, max-age=3600"} if status == 200 else {}))


@oidc_bp.route("/oidc/jwks")
def jwks():
    datos, status = _api()("GET", "/oidc/jwks")
    return _json(datos, status, **({"Cache-Control": "public, max-age=300"} if status == 200 else {}))


@oidc_bp.route("/oidc/authorize")
def authorize():
    pedido = {k: request.args[k] for k in PARAMETROS if k in request.args}
    api = _api()
    if session.get("token"):
        datos, status = api("POST", "/oidc/autorizar", pedido, token=session["token"])
        if status == 200:
            return _cerrar(redirect(datos["redirect"]))
        if status == 404:
            abort(404)
        if status != 401:
            return _error(datos, status)
        # 401: la sesión de Core venció; se pide el login otra vez
    datos, status = api("POST", "/oidc/validar", pedido)
    if status == 404:
        abort(404)
    if status != 200:
        return _error(datos, status)
    return _guardar(redirect(url_for("core.login")), {"pedido": pedido, "cliente": datos.get("cliente")})


@oidc_bp.route("/oidc/cancelar")
def cancelar():
    """Cancelar en el login, o una cuenta desactivada: vuelve al cliente con access_denied."""
    pendiente = leer_pendiente()
    if not pendiente:
        return redirect(url_for("core.login"))
    datos, status = _api()("POST", "/oidc/denegar", pendiente["pedido"])
    if status == 200:
        return _cerrar(redirect(datos["redirect"]))
    return _error(datos, status)


@oidc_bp.route("/oidc/token", methods=["POST"])
def token():
    """Canje del código, server a server. client_secret_basic o client_secret_post: el backend recibe los dos igual."""
    datos = {
        k: request.form.get(k)
        for k in ("grant_type", "code", "redirect_uri", "code_verifier", "client_id", "client_secret")
    }
    if request.authorization is not None and request.authorization.type == "basic":
        # RFC 6749 §2.3.1: id y secreto van form-urlencoded antes del Basic
        datos["client_id"] = unquote_plus(request.authorization.username or "")
        datos["client_secret"] = unquote_plus(request.authorization.password or "")
    respuesta, status = _api()("POST", "/oidc/token", datos)
    cabeceras = {"Cache-Control": "no-store", "Pragma": "no-cache"}
    if status == 401:
        cabeceras["WWW-Authenticate"] = 'Basic realm="Dicsys Core"'
    return _json(respuesta, status, **cabeceras)
