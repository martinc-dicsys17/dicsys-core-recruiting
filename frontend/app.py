"""
Frontend - Flask + HTMX + Alpine.js
Aplicación modular
"""

import hashlib
import os
import re
import uuid
from http.cookies import SimpleCookie
from urllib.parse import urlsplit

import httpx
from flask import Flask, Response, abort, g, has_request_context, request, send_from_directory, session
from werkzeug.middleware.proxy_fix import ProxyFix

# Métodos que mutan estado: solo se aceptan desde el propio host (defensa CSRF por cabeceras).
MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
# Endpoints que llaman otros servidores, sin navegador: no mandan Origin ni Referer y no usan la cookie de sesión, así
# que el CSRF no aplica. El canje del código OpenID Connect se autentica con las credenciales del cliente (F21).
SIN_CHEQUEO_DE_ORIGEN = frozenset({"oidc.token"})
# SECRET_KEY de ejemplo del .env.template: en producción el frontend no arranca con ella
SECRET_KEY_DEL_TEMPLATE = "tu-clave-secreta-aqui-cambiar-en-produccion"


# Puente de sesión (F07-P05): la cookie del refresh que emite el backend (Path=/api/v1/auth) pasa por Flask al navegador
REFRESCO = "refresh_token"
# Un X-Request-ID que llega se usa si tiene forma de id, como en backend/core/pedido.py (F06-P06)
ID_DE_PEDIDO = re.compile(r"[A-Za-z0-9._\-]{1,128}")


def _flag(nombre, default):
    return os.getenv(nombre, default).strip().lower() == "true"


def _guardar_refresco(respuesta_api):
    """Lo que el backend dijo del refresh (F07-P05): la línea de Set-Cookie va al navegador en la respuesta de Flask
    (after_request) y el valor queda en la sesión de Flask, para que el logout de esta UI cierre la sesión en el
    backend. Un Max-Age=0 (logout, refresh inválido) lo saca de la sesión."""
    for linea in respuesta_api.headers.get_list("set-cookie"):
        galleta = SimpleCookie()
        galleta.load(linea)
        if REFRESCO not in galleta:
            continue
        g.setdefault("_cookies_refresco", []).append(linea)
        if galleta[REFRESCO]["max-age"] == "0" or not galleta[REFRESCO].value:
            session.pop("refresh", None)
        else:
            session["refresh"] = galleta[REFRESCO].value


def create_app(config=None, api_request_func=None):
    app = Flask(__name__)
    config = config or {}
    environment = os.getenv("ENVIRONMENT", "production").strip().lower()
    testing = bool(config.get("TESTING")) or _flag("TESTING", "false")

    # SECRET_KEY firma la cookie de sesión (que lleva el JWT adentro): sin ella las
    # sesiones serían forjables, así que fuera de tests no hay fallback.
    secret_key = os.getenv("SECRET_KEY") or config.get("SECRET_KEY")
    if not secret_key:
        if not testing:
            raise RuntimeError("SECRET_KEY no configurada: definila en el entorno (.env) antes de arrancar el frontend")
        secret_key = "frontend-test-secret"
    # En producción tampoco vale el valor de ejemplo del .env.template: firmaría cookies forjables (F02-P05)
    if environment == "production" and not testing and secret_key == SECRET_KEY_DEL_TEMPLATE:
        raise RuntimeError(
            "SECRET_KEY es el valor de ejemplo del .env.template: definí uno propio antes de arrancar en producción"
        )
    app.config["SECRET_KEY"] = secret_key

    # El debugger de Werkzeug solo existe en desarrollo explícito; en cualquier otro entorno
    # queda apagado aunque DEBUG venga en True.
    app.config["DEBUG"] = environment == "development" and _flag("DEBUG", "false")
    app.config["APP_NAME"] = "Dicsys Core"
    app.config["API_URL"] = os.getenv("API_URL", "http://fastapi-app:5000")

    # Cookie de sesión: HttpOnly siempre, SameSite=Lax siempre, Secure salvo en desarrollo
    # local sin TLS (delante hay un Traefik que termina el certificado).
    cookie_secure = _flag("SESSION_COOKIE_SECURE", "false" if (environment == "development" or testing) else "true")
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = cookie_secure
    if cookie_secure:
        app.config["PREFERRED_URL_SCHEME"] = "https"

    # Chequeo de Origin/Referer en métodos mutantes. En tests queda apagado salvo que el
    # test lo pida (los clientes de prueba no mandan esas cabeceras).
    app.config["ORIGIN_CHECK"] = _flag("ORIGIN_CHECK", "false" if testing else "true")

    if config:
        app.config.update(config)

    # Duración de sesión cuando el usuario marca "Mantener sesión iniciada"
    from datetime import timedelta

    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)

    @app.before_request
    def fijar_id_de_pedido():
        """Id de pedido (F06-P06): el X-Request-ID que llegó (el de la SPA en v2) si tiene forma de id, o uno nuevo.
        Viaja a la API en cada llamada y vuelve en la respuesta: el mismo id en los logs de Flask y de FastAPI."""
        entrante = request.headers.get("X-Request-ID", "")
        g.id_pedido = entrante if ID_DE_PEDIDO.fullmatch(entrante) else uuid.uuid4().hex

    @app.before_request
    def rechazar_origen_ajeno():
        """Defensa CSRF por cabeceras (OWASP): una mutación tiene que venir del propio host.

        El navegador manda `Origin` en todo envío cross-site y no se puede falsificar desde
        una página; `Referer` es el respaldo para clientes viejos. Sin ninguna de las dos,
        se rechaza.
        """
        if request.method not in MUTATING_METHODS or not app.config.get("ORIGIN_CHECK", True):
            return None
        if request.endpoint in SIN_CHEQUEO_DE_ORIGEN:
            return None
        origen = request.headers.get("Origin")
        fuente = origen if origen and origen != "null" else request.headers.get("Referer")
        if not fuente or urlsplit(fuente).netloc.lower() != request.host.lower():
            abort(403, description="Origen no permitido")
        return None

    # Detrás del reverse proxy que termina TLS: respetar X-Forwarded-Proto/Host
    # para que request.scheme sea 'https'. Sin esto, url_for(_external=True) y
    # request.url generan 'http://' y rompen el og:image en WhatsApp/Twitter
    # (que exigen HTTPS y no siguen el redirect 301).
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    # Favicon en la raíz (los browsers siempre buscan /favicon.ico)
    @app.route("/favicon.ico")
    def favicon():
        return send_from_directory(
            os.path.join(app.static_folder, "favicon"), "favicon.ico", mimetype="image/vnd.microsoft.icon"
        )

    def _proxy_with_cache(backend_url, timeout=10.0, max_age=86400):
        """Proxy genérico con soporte de ETag y Cache-Control.

        - Genera ETag basado en MD5 del contenido
        - Si el browser envía If-None-Match y coincide, devuelve 304
        - max_age: segundos de cache (default 1 día)
        """
        try:
            with httpx.Client(timeout=timeout) as client:
                response = client.get(backend_url)
                if response.status_code != 200:
                    return Response(response.content, status=response.status_code)

                content = response.content
                etag = hashlib.md5(content).hexdigest()

                # Si el browser ya tiene esta versión, devolver 304
                if_none_match = request.headers.get("If-None-Match")
                if if_none_match and if_none_match.strip('"') == etag:
                    return Response(
                        status=304,
                        headers={
                            "ETag": f'"{etag}"',
                            "Cache-Control": f"public, max-age={max_age}",
                        },
                    )

                return Response(
                    content,
                    status=200,
                    content_type=response.headers.get("content-type", "application/octet-stream"),
                    headers={
                        "ETag": f'"{etag}"',
                        "Cache-Control": f"public, max-age={max_age}",
                    },
                )
        except Exception:
            return Response("", status=404)

    # Helper para llamadas a la API
    def api_request(method, endpoint, data=None, token=None):
        url = f"{app.config['API_URL']}/api/v1{endpoint}"
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if has_request_context() and g.get("id_pedido"):
            headers["X-Request-ID"] = g.id_pedido  # F06-P06
        if has_request_context():
            # El backend solo ve a Flask: le pasamos la IP real (ProxyFix) y el
            # navegador del usuario para las auditorías que los registran.
            if request.remote_addr:
                headers["X-Cliente-IP"] = request.remote_addr
            user_agent = request.headers.get("User-Agent")
            if user_agent:
                headers["X-Cliente-User-Agent"] = user_agent[:500]
            if endpoint.startswith("/auth/"):
                # como haría el navegador con la cookie del refresh (Path=/api/v1/auth), y el CSRF que piden
                # /auth/refresh y /auth/logout (F07-P04); Flask es la propia app
                headers["X-Requested-With"] = "XMLHttpRequest"
                if session.get("refresh"):
                    headers["Cookie"] = f"{REFRESCO}={session['refresh']}"

        try:
            with httpx.Client(timeout=120.0) as client:
                if method == "GET":
                    response = client.get(url, headers=headers)
                elif method == "POST":
                    response = client.post(url, json=data, headers=headers)
                elif method == "PUT":
                    response = client.put(url, json=data, headers=headers)
                elif method == "DELETE":
                    # client.delete no acepta cuerpo: request lo manda cuando hay datos (revocación de
                    # licencias, desactivar 2FA); sin datos sale vacío como antes.
                    response = client.request("DELETE", url, json=data, headers=headers)

                if has_request_context():
                    _guardar_refresco(response)

                # Si el token expiró, limpiar sesión y marcar para redirect
                if response.status_code == 401:
                    # No limpiar sesión durante flujo 2FA
                    if not (
                        hasattr(request, "endpoint")
                        and request.endpoint
                        and ("login_2fa" in request.endpoint or "login_2fa_setup" in request.endpoint)
                    ):
                        session.clear()
                        request._session_cleared_by_401 = True

                if response.status_code == 204:
                    return {}, 204
                return response.json(), response.status_code
        except Exception as e:
            import logging

            logging.getLogger(__name__).error(f"Error en api_request {method} {endpoint}: {e}")
            return {"error": "Error de comunicación con el servidor"}, 500

    # Guardar api_request en config para que los módulos lo usen
    app.config["api_request"] = api_request_func or api_request

    # Proxy para archivos estáticos del backend
    @app.route("/files/<path:filepath>")
    def proxy_files(filepath):
        """Proxy para servir archivos del backend."""
        return _proxy_with_cache(f"{app.config['API_URL']}/files/{filepath}")

    # Proxy para fotos de nómina del backend
    @app.route("/fotos/<path:filepath>")
    def proxy_fotos(filepath):
        """Proxy para servir fotos de empleados del backend."""
        return _proxy_with_cache(f"{app.config['API_URL']}/fotos/{filepath}")

    # Proxy para thumbnails de archivos (PDFs renderizados como PNG)
    @app.route("/storage/thumbnail/<path:filepath>")
    def proxy_storage_thumbnail(filepath):
        """Proxy para servir thumbnails de archivos (PDFs renderizados como PNG)."""
        return _proxy_with_cache(f"{app.config['API_URL']}/storage/thumbnail/{filepath}", timeout=30.0)

    # Vista previa en PDF de un CV Word (Recruiting): la conversión se hace en el backend; sin caché para no mostrar un
    # CV reemplazado
    @app.route("/storage/preview-pdf/<path:filepath>")
    def proxy_storage_preview_pdf(filepath):
        """Proxy para la vista previa en PDF de un CV .doc/.docx."""
        return _proxy_with_cache(f"{app.config['API_URL']}/storage/preview-pdf/{filepath}", timeout=90.0, max_age=0)

    @app.route("/storage/preview-pdf", methods=["POST"])
    def proxy_storage_preview_pdf_subido():
        """Convierte a PDF un CV Word subido (todavía no guardado) para la vista previa del modal de comparación."""
        if "token" not in session:
            return Response("", status=401)
        archivo = request.files.get("archivo")
        if not archivo or not archivo.filename:
            return Response("", status=400)
        try:
            with httpx.Client(timeout=90.0) as client:
                resp = client.post(
                    f"{app.config['API_URL']}/storage/preview-pdf",
                    headers={"Authorization": f"Bearer {session.get('token')}"},
                    files={
                        "archivo": (
                            archivo.filename,
                            archivo.read(),
                            archivo.content_type or "application/octet-stream",
                        )
                    },
                )
            if resp.status_code != 200:
                return Response("", status=resp.status_code)
            return Response(
                resp.content, status=200, content_type="application/pdf", headers={"Cache-Control": "no-store"}
            )
        except Exception:
            return Response("", status=502)

    # Proxy genérico para archivos en cloud storage del backend
    @app.route("/storage/<path:filepath>")
    def proxy_storage(filepath):
        """Proxy para servir archivos desde cloud_storage del backend."""
        return _proxy_with_cache(f"{app.config['API_URL']}/storage/{filepath}", timeout=30.0)

    # Filtro Jinja2: convierte keys de storage a URLs servibles
    @app.template_filter("storage_url")
    def storage_url_filter(key):
        """Convierte una key de storage a URL.
        Keys de cloud (sin / al inicio) → /storage/{key}
        URLs legacy (con / al inicio) → se devuelven tal cual
        """
        if not key:
            return ""
        if key.startswith("/"):
            return key  # URL legacy, ya es servible
        return f"/storage/{key}"

    @app.template_filter("storage_thumb")
    def storage_thumb_filter(key):
        """Convierte una key de storage a URL de thumbnail.
        Para PDFs genera un PNG de la primera página. Para imágenes devuelve la imagen."""
        if not key:
            return ""
        if key.startswith("/"):
            return key
        return f"/storage/thumbnail/{key}"

    @app.template_filter("from_json")
    def from_json_filter(value):
        """Parsea un string JSON a objeto Python (lista vacía si falla/está vacío)."""
        import json

        if not value:
            return []
        try:
            return json.loads(value)
        except ValueError, TypeError:
            return []

    @app.template_filter("fecha_es")
    def fecha_es_filter(fecha):
        """Formatea una fecha en español (ej: 12 de enero de 2026)."""
        if not fecha:
            return ""
        from datetime import date, datetime

        # Convertir string a date si es necesario
        if isinstance(fecha, str):
            try:
                fecha = datetime.fromisoformat(fecha.replace("Z", "+00:00")).date()
            except Exception:
                return fecha

        if not isinstance(fecha, (date, datetime)):
            return str(fecha)

        meses = [
            "enero",
            "febrero",
            "marzo",
            "abril",
            "mayo",
            "junio",
            "julio",
            "agosto",
            "septiembre",
            "octubre",
            "noviembre",
            "diciembre",
        ]

        if isinstance(fecha, datetime):
            fecha = fecha.date()

        return f"{fecha.day} de {meses[fecha.month - 1]} de {fecha.year}"

    def _parse_utc_datetime(value):
        if not value:
            return None

        from datetime import datetime, timezone

        if isinstance(value, datetime):
            dt = value
        elif isinstance(value, str):
            try:
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        else:
            return None

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @app.template_filter("datetime_gmt3_ampm")
    def datetime_gmt3_ampm_filter(value):
        dt = _parse_utc_datetime(value)
        if not dt:
            return value or ""

        from datetime import timedelta

        local_dt = dt - timedelta(hours=3)
        return local_dt.strftime("%Y-%m-%d %I:%M %p")

    # Proxy para llamadas API desde JavaScript (Alpine.js, fetch, etc.)
    @app.route("/api/v1/<path:endpoint>", methods=["GET", "POST", "PUT", "DELETE"])
    def proxy_api(endpoint):
        """Proxy para llamadas a la API desde el frontend JavaScript."""
        token = session.get("token")
        url = f"{app.config['API_URL']}/api/v1/{endpoint}"

        # Incluir query params
        if request.query_string:
            url += f"?{request.query_string.decode()}"

        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if request.remote_addr:
            # como en api_request: la IP del navegador, para el límite de intentos del ingreso (F07-P07)
            headers["X-Cliente-IP"] = request.remote_addr
        if g.get("id_pedido"):
            headers["X-Request-ID"] = g.id_pedido  # F06-P06
        if endpoint.startswith("auth/"):
            # la SPA (F07-P05): la cookie del refresh del navegador y su cabecera de CSRF siguen hasta el backend
            if request.cookies.get(REFRESCO):
                headers["Cookie"] = f"{REFRESCO}={request.cookies[REFRESCO]}"
            if request.headers.get("X-Requested-With"):
                headers["X-Requested-With"] = request.headers["X-Requested-With"]

        try:
            with httpx.Client(timeout=10.0) as client:
                if request.method == "GET":
                    response = client.get(url, headers=headers)
                elif request.method == "POST":
                    response = client.post(url, json=request.get_json(silent=True), headers=headers)
                elif request.method == "PUT":
                    response = client.put(url, json=request.get_json(silent=True), headers=headers)
                elif request.method == "DELETE":
                    response = client.request("DELETE", url, json=request.get_json(silent=True), headers=headers)

                _guardar_refresco(response)
                respuesta = Response(
                    response.content,
                    status=response.status_code,
                    content_type=response.headers.get("content-type", "application/json"),
                )
                if "retry-after" in response.headers:  # el 429 del límite de intentos (F07-P07)
                    respuesta.headers["Retry-After"] = response.headers["retry-after"]
                return respuesta
        except Exception as e:
            return {"error": str(e)}, 500

    # Registrado antes que check_session_cleared para correr después: si ese hook cambia la respuesta por un redirect al
    # login, la cookie del refresh viaja igual
    @app.after_request
    def devolver_id_de_pedido(response):
        if g.get("id_pedido"):
            response.headers["X-Request-ID"] = g.id_pedido
        return response

    @app.after_request
    def reenviar_cookie_de_refresco(response):
        """Puente de sesión (F07-P05): el Set-Cookie del refresh que mandó el backend llega al navegador."""
        for linea in g.pop("_cookies_refresco", []):
            response.headers.add("Set-Cookie", linea)
        return response

    # Middleware: si el token expiró (sesión limpiada por api_request 401), redirigir al login
    @app.after_request
    def check_session_cleared(response):
        """Si durante el request se limpió la sesión por 401, redirigir al login."""
        if (
            request.endpoint
            and request.endpoint != "core.login"
            and request.endpoint != "core.logout"
            and request.endpoint != "core.health"
            and request.endpoint != "static"
            and not request.endpoint.startswith("core.forgot")
            and not request.endpoint.startswith("core.reset")
            and not request.endpoint.startswith("core.set")
            and not request.endpoint.startswith("core.login_2fa")
            # OpenID Connect (F21) maneja el 401 por su cuenta: authorize pide el login conservando el ingreso
            # pendiente y el canje responde invalid_client a la app, server a server (PG-26)
            and not request.endpoint.startswith("oidc.")
            and getattr(request, "_session_cleared_by_401", False)
        ):
            print(
                f"[MIDDLEWARE] Session cleared by 401 during request to {request.endpoint}, redirecting to login",
                flush=True,
            )
            from modulos.auth_helpers import respuesta_sin_sesion

            return app.make_response(respuesta_sin_sesion())
        return response

    # Context processor global
    @app.context_processor
    def inject_globals():
        menus = []
        # Cargar menús si hay usuario logueado
        if session.get("token"):
            try:
                print("[CONTEXT] Loading menus for user session...", flush=True)
                data, status = app.config["api_request"](
                    "GET",
                    "/menus",
                    token=session.get("token"),
                )
                print(f"[CONTEXT] Menus response: status={status}, data_type={type(data)}", flush=True)
                if status == 200 and isinstance(data, dict):
                    menus = data.get("items") or []
                    print(f"[CONTEXT] Loaded {len(menus)} menus", flush=True)
            except Exception as e:
                print(f"[CONTEXT] Error cargando menús: {e}", flush=True)
        else:
            print("[CONTEXT] No token in session, skipping menus", flush=True)

        return {
            "config": app.config,
            "user": session.get("user"),
            "menus": menus,
            "is_htmx": request.headers.get("HX-Request") == "true",
            "empresa_nombre": session.get("empresa_nombre", ""),
            "empresa_logo": session.get("empresa_logo", ""),
            "empresa_id": session.get("empresa_id", ""),
        }

    # Registrar módulos
    from modulos.administracion.app_module import administracion_bp
    from modulos.core.app_module import core_bp
    from modulos.empresa.app_module import empresa_bp
    from modulos.hrbp.app_module import hrbp_bp
    from modulos.innovacion.app_module import certificates_bp, innovacion_bp
    from modulos.llm.app_module import llm_bp
    from modulos.nomina.app_module import nomina_bp
    from modulos.notificaciones.app_module import notificaciones_bp
    from modulos.oidc.app_module import oidc_bp
    from modulos.operaciones.app_module import operaciones_bp
    from modulos.parametros.app_module import parametros_bp
    from modulos.permisos.app_module import permisos_bp
    from modulos.recibos.app_module import recibos_admin_bp, recibos_nomina_bp, recibos_portal_bp
    from modulos.recruiting.app_module import recruiting_bp
    from modulos.sincronizacion.app_module import sincronizacion_bp
    from modulos.soporte.app_module import soporte_bp
    from modulos.starmiles.app_module import starmiles_bp
    from modulos.tareas.app_module import tareas_bp
    from modulos.usuarios.app_module import usuarios_bp

    app.register_blueprint(core_bp)
    app.register_blueprint(usuarios_bp)
    app.register_blueprint(permisos_bp)
    app.register_blueprint(nomina_bp)
    app.register_blueprint(starmiles_bp)
    app.register_blueprint(sincronizacion_bp)
    app.register_blueprint(hrbp_bp)
    app.register_blueprint(administracion_bp)
    app.register_blueprint(operaciones_bp)
    app.register_blueprint(soporte_bp)
    app.register_blueprint(innovacion_bp)
    app.register_blueprint(certificates_bp)
    app.register_blueprint(empresa_bp)
    app.register_blueprint(llm_bp)
    app.register_blueprint(parametros_bp)
    app.register_blueprint(notificaciones_bp)
    app.register_blueprint(tareas_bp)
    app.register_blueprint(recibos_admin_bp)
    app.register_blueprint(recibos_portal_bp)
    app.register_blueprint(recibos_nomina_bp)
    app.register_blueprint(oidc_bp)  # proveedor OpenID Connect (F21)
    app.register_blueprint(recruiting_bp)

    return app


app = create_app()

if __name__ == "__main__":
    # Dev server de Flask: solo desarrollo (el Dockerfile lo usa únicamente con
    # ENVIRONMENT=development; en producción corre gunicorn).
    port = int(os.getenv("FLASK_PORT", 3003))
    app.run(host="0.0.0.0", port=port, debug=app.config["DEBUG"])
