"""
Módulo Core - Rutas principales: login, logout, dashboard, profile, health
"""

import base64
import hashlib
import secrets
from functools import wraps
from urllib.parse import urlencode

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from itsdangerous import BadSignature, URLSafeTimedSerializer

from modulos.auth_helpers import respuesta_sin_sesion
from modulos.error_helpers import error_html, format_api_error
from modulos.oidc.app_module import contexto_del_login, leer_pendiente, url_retoma

core_bp = Blueprint("core", __name__, template_folder="templates")


def get_api_request_func():
    """Obtiene la función api_request del app principal."""
    from flask import current_app

    return current_app.config.get("api_request")


def _home_url():
    """Retorna la URL de inicio según si el usuario tiene empleado asignado. Con un ingreso OpenID Connect pendiente
    (otra app que entra con Core, F21), el login termina retomándolo."""
    retoma = url_retoma()
    if retoma:
        return retoma
    user = session.get("user", {})
    if user.get("empleado_id"):
        return url_for("starmiles.home")
    return url_for("core.dashboard")


def login_required(f):
    """Decorador para rutas protegidas."""

    @wraps(f)
    def decorated(*args, **kwargs):
        print(f"[LOGIN_REQUIRED] Checking auth for {request.path}, token exists: {'token' in session}", flush=True)
        if "token" not in session:
            print("[LOGIN_REQUIRED] No token, redirecting to login", flush=True)
            return respuesta_sin_sesion()
        print("[LOGIN_REQUIRED] Token found, proceeding", flush=True)
        return f(*args, **kwargs)

    return decorated


@core_bp.route("/login", methods=["GET", "POST"])
def login():
    print(f"[LOGIN] Method: {request.method}, Headers: HX-Request={request.headers.get('HX-Request')}", flush=True)
    if request.method == "POST":
        api_request = get_api_request_func()
        email = request.form.get("email")
        password = request.form.get("password")

        data, status = api_request("POST", "/auth/login", {"email": email, "password": password})

        if status == 200:
            respuesta = _continuar_ingreso(data, request.form.get("remember") == "on", email)
            if respuesta is not None:
                return respuesta

        # Ingreso OpenID Connect pendiente y una cuenta que no puede entrar: vuelve a la app con access_denied (F21)
        if _cuenta_rechazada(status, data) and leer_pendiente():
            return _ir(url_for("oidc.cancelar"))

        error = format_api_error(data.get("detail"), "Credenciales inválidas")
        if request.headers.get("HX-Request"):
            return f"""<div class="flex items-center gap-3 p-4 bg-red-50 border border-red-300 rounded-xl text-red-700 text-sm font-medium animate-fade-in" role="alert">
                <svg class="w-5 h-5 text-red-500 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/></svg>
                <span>{error}</span>
            </div>"""
        flash(error, "error")

    # Con un ingreso OpenID Connect pendiente, el login muestra la app, con sus logos, lo que recibe y Cancelar (F21)
    return render_template(
        "core/login.html", oidc_pendiente=contexto_del_login(leer_pendiente()), google=google_disponible()
    )


def _cuenta_rechazada(status, data):
    """La cuenta existe pero no puede entrar: desactivada o sin email corporativo (F22)."""
    detalle = str(data.get("detail") or "") if isinstance(data, dict) else ""
    return (status == 401 and detalle == "Usuario desactivado") or (
        status == 403 and detalle.startswith("Tu usuario no tiene un email corporativo")
    )


def _ir(url):
    """Redirige al navegador, también cuando el pedido vino por htmx."""
    if request.headers.get("HX-Request"):
        return "", 200, {"HX-Redirect": url}
    return redirect(url)


def _continuar_ingreso(data, recordar=False, email=None):
    """Sigue un ingreso que el backend aceptó, con contraseña o con Google (F22): el código del 2FA, su alta
    obligatoria o la sesión con su empresa. None si la respuesta no es ninguno de esos."""
    if data.get("requires_2fa"):
        # 2FA requerido: guardar temp_token y mostrar step 2
        session["2fa_temp_token"] = data["temp_token"]
        session["2fa_user"] = data.get("user", {})
        session["2fa_remember"] = recordar
        return _ir(url_for("core.login_2fa"))

    if data.get("requires_2fa_setup"):
        # 2FA obligatorio pero no configurado: guardar setup_token y redirigir al wizard
        session["2fa_setup_token"] = data["setup_token"]
        session["2fa_user"] = data.get("user", {})
        session["2fa_remember"] = recordar
        return _ir(url_for("core.login_2fa_setup"))

    if "access_token" not in data:
        return None

    api_request = get_api_request_func()
    session["token"] = data["access_token"]
    session["user"] = data.get("user", {"email": email})
    session.pop("permisos_modulos", None)  # Limpiar cache de permisos

    # Mantener sesión iniciada: si el usuario marcó "remember", la cookie dura 30 días
    # Si no, la cookie expira al cerrar el navegador
    session.permanent = recordar

    # ─── Multi-empresa: auto-seleccionar la primera empresa ─────
    if data.get("requiere_seleccion_empresa") and data.get("empresas"):
        empresas = data["empresas"]
        # Auto-seleccionar la primera empresa de la lista
        emp = empresas[0]

        # Llamar al endpoint de selección para obtener JWT con empresa_id
        sel_data, sel_status = api_request(
            "POST", "/auth/seleccionar-empresa", {"empresa_id": emp["id"]}, token=data["access_token"]
        )

        if sel_status == 200 and "access_token" in sel_data:
            session["token"] = sel_data["access_token"]
            session["user"] = sel_data.get("user", session.get("user", {}))
            session["empresa_id"] = emp["id"]
            session["empresa_nombre"] = emp.get("nombre_fantasia") or emp.get("razon_social", "")
            session["empresa_logo"] = emp.get("logo", "") or ""
            session.pop("permisos_modulos", None)
        else:
            # Fallback: usar JWT temporal y primera empresa
            session["empresa_id"] = emp["id"]
            session["empresa_nombre"] = emp.get("nombre_fantasia") or emp.get("razon_social", "")
            session["empresa_logo"] = emp.get("logo", "") or ""

        return _ir(_home_url())

    # Una sola empresa → guardar datos de empresa en session
    # El backend ya incluyó empresa_id en el JWT
    if data.get("empresas") and len(data["empresas"]) == 1:
        emp = data["empresas"][0]
        session["empresa_id"] = emp["id"]
        session["empresa_nombre"] = emp.get("nombre_fantasia") or emp.get("razon_social", "")
        session["empresa_logo"] = emp.get("logo", "") or ""

    return _ir(_home_url())


# ─── Ingreso con Google (F22, docs/IngresoGoogle.md) ────────────────────
# El backend arma la URL de Google, canjea el código e identifica a la persona. Acá queda lo del navegador: el state,
# el nonce y el verificador de PKCE viajan en una cookie firmada aparte (como el ingreso OIDC pendiente), porque la
# sesión se vacía ante cualquier 401 del backend.
GOOGLE_COOKIE = "google_ingreso"
GOOGLE_VIGENCIA = 600  # segundos para volver de Google


def _google_serializador() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="google-ingreso")


def google_disponible():
    """El dominio de las cuentas de Google si el backend tiene configurado el ingreso con Google; si no, None y el
    login no muestra el botón."""
    try:
        data, status = get_api_request_func()("GET", "/auth/google/disponible")
    except Exception:  # noqa: BLE001 - sin backend el login se muestra igual, sin el botón
        return None
    return (data.get("dominio") or "") if status == 200 and data.get("disponible") else None


def _login_con_error(mensaje):
    flash(mensaje, "error")
    return redirect(url_for("core.login"))


@core_bp.route("/login/google")
def login_google():
    """Lleva el navegador a Google con un pedido nuevo: state, nonce y PKCE S256."""
    verificador = secrets.token_urlsafe(48)
    pendiente = {"state": secrets.token_urlsafe(24), "nonce": secrets.token_urlsafe(24), "verificador": verificador}
    desafio = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b"=").decode()
    data, status = get_api_request_func()(
        "POST",
        "/auth/google/autorizacion",
        {
            "state": pendiente["state"],
            "nonce": pendiente["nonce"],
            "code_challenge": desafio,
        },
    )
    if status == 404:
        abort(404)
    if status != 200 or not data.get("url"):
        return _login_con_error(format_api_error(data.get("detail"), "No se pudo iniciar el ingreso con Google"))
    respuesta = redirect(data["url"])
    respuesta.set_cookie(
        GOOGLE_COOKIE,
        _google_serializador().dumps(pendiente),
        max_age=GOOGLE_VIGENCIA,
        httponly=True,
        samesite="Lax",
        secure=request.is_secure,
    )
    return respuesta


@core_bp.route("/login/google/callback")
def login_google_vuelta():
    """La vuelta de Google: con el código, el backend identifica a la persona y el login sigue como con la
    contraseña (2FA según el parámetro google_login_requiere_2fa, empresa y, si venía de otra app, la retoma)."""
    pendiente = None
    if request.cookies.get(GOOGLE_COOKIE):
        try:
            pendiente = _google_serializador().loads(request.cookies[GOOGLE_COOKIE], max_age=GOOGLE_VIGENCIA)
        except BadSignature:  # también si venció
            pendiente = None
    respuesta = make_response(_vuelta_de_google(pendiente))
    respuesta.delete_cookie(GOOGLE_COOKIE)
    return respuesta


def _vuelta_de_google(pendiente):
    if request.args.get("error"):
        if request.args["error"] == "access_denied":
            return _login_con_error("Cancelaste el ingreso con Google")
        return _login_con_error("Google no completó el ingreso. Probá de nuevo.")
    if not pendiente or not request.args.get("code") or request.args.get("state") != pendiente.get("state"):
        return _login_con_error("El ingreso con Google venció o no empezó en este navegador. Probá de nuevo.")
    data, status = get_api_request_func()(
        "POST",
        "/auth/google/ingreso",
        {
            "code": request.args["code"],
            "code_verifier": pendiente["verificador"],
            "nonce": pendiente["nonce"],
        },
    )
    if status == 200:
        respuesta = _continuar_ingreso(data)
        if respuesta is not None:
            return respuesta
    # Ingreso OpenID Connect pendiente y una cuenta que no puede entrar: vuelve a la app con access_denied (F21)
    if _cuenta_rechazada(status, data) and leer_pendiente():
        return redirect(url_for("oidc.cancelar"))
    return _login_con_error(format_api_error(data.get("detail"), "No se pudo entrar con Google"))


@core_bp.route("/login/2fa", methods=["GET", "POST"])
def login_2fa():
    """Step 2 del login: verificar código 2FA."""
    temp_token = session.get("2fa_temp_token")
    user_2fa = session.get("2fa_user", {})

    if not temp_token:
        flash("Sesión expirada, ingresá de nuevo", "error")
        return redirect(url_for("core.login"))

    if request.method == "POST":
        api_request = get_api_request_func()
        code = request.form.get("code", "").strip()

        data, status = api_request("POST", "/auth/verify-2fa", {"temp_token": temp_token, "code": code})

        if status == 200 and "access_token" in data:
            # Limpiar datos de 2FA de la sesión
            remember = session.pop("2fa_remember", False)
            session.pop("2fa_temp_token", None)
            session.pop("2fa_user", None)

            session["token"] = data["access_token"]
            session["user"] = data.get("user", {})
            session.pop("permisos_modulos", None)
            session.permanent = remember

            # Manejar empresa (mismo flujo que login normal)
            if data.get("requiere_seleccion_empresa") and data.get("empresas"):
                empresas = data["empresas"]
                emp = empresas[0]
                sel_data, sel_status = api_request(
                    "POST", "/auth/seleccionar-empresa", {"empresa_id": emp["id"]}, token=data["access_token"]
                )
                if sel_status == 200 and "access_token" in sel_data:
                    session["token"] = sel_data["access_token"]
                    session["user"] = sel_data.get("user", session.get("user", {}))
                session["empresa_id"] = emp["id"]
                session["empresa_nombre"] = emp.get("nombre_fantasia") or emp.get("razon_social", "")
                session["empresa_logo"] = emp.get("logo", "") or ""
            elif data.get("empresas") and len(data["empresas"]) == 1:
                emp = data["empresas"][0]
                session["empresa_id"] = emp["id"]
                session["empresa_nombre"] = emp.get("nombre_fantasia") or emp.get("razon_social", "")
                session["empresa_logo"] = emp.get("logo", "") or ""

            if request.headers.get("HX-Request"):
                return "", 200, {"HX-Redirect": _home_url()}
            return redirect(_home_url())

        error = "Código incorrecto" if status == 401 else "Error al verificar"
        if status == 429:  # límite de intentos (F07-P07): el aviso del backend dice cuándo probar de nuevo
            error = format_api_error(data.get("detail"), "Demasiados intentos")
        if "expirad" in str(data.get("detail", "")).lower():
            session.pop("2fa_temp_token", None)
            flash("Sesión expirada, ingresá de nuevo", "error")
            return redirect(url_for("core.login"))

        if request.headers.get("HX-Request"):
            return f"""<div class="p-4 bg-red-50 border border-red-300 rounded-xl text-red-700 text-sm font-medium animate-fade-in">{error}</div>"""
        flash(error, "error")

    return render_template("core/login_2fa.html", user_2fa=user_2fa)


@core_bp.route("/login/2fa-setup", methods=["GET", "POST"])
def login_2fa_setup():
    """Setup obligatorio de 2FA durante el primer login."""
    setup_token = session.get("2fa_setup_token")
    user_2fa = session.get("2fa_user", {})

    if not setup_token:
        flash("Sesión expirada, ingresá de nuevo", "error")
        return redirect(url_for("core.login"))

    api_request = get_api_request_func()

    if request.method == "POST":
        action = request.form.get("action")

        if action == "setup":
            # Generar QR
            result, status = api_request("POST", "/auth/me/2fa/setup", token=setup_token)
            if status == 200:
                from flask import jsonify

                return jsonify(result)
            from flask import jsonify

            return jsonify({"error": "Error al generar QR"}), 400

        elif action == "enable":
            code = request.form.get("code", "").strip()
            result, status = api_request("POST", "/auth/me/2fa/enable", {"code": code}, token=setup_token)
            if status == 200:
                # Guardar el código para auto-login después
                session["2fa_last_code"] = code
                from flask import jsonify

                return jsonify({"success": True, "backup_codes": result.get("backup_codes", [])})
            from flask import jsonify

            return jsonify({"error": result.get("detail", "Código incorrecto")}), 401

        elif action == "complete":
            # Auto-login: usar el setup_token para hacer verify-2fa
            code = session.pop("2fa_last_code", "")
            if not code:
                return redirect(url_for("core.login"))

            # El setup_token tiene user_id, lo usamos como temp_token para verify
            data, status = api_request("POST", "/auth/verify-2fa", {"temp_token": setup_token, "code": code})

            session.pop("2fa_setup_token", None)
            session.pop("2fa_user", None)

            if status == 200 and "access_token" in data:
                session["token"] = data["access_token"]
                session["user"] = data.get("user", {})
                session.pop("permisos_modulos", None)
                session.permanent = session.pop("2fa_remember", False)

                if data.get("empresas") and len(data["empresas"]) >= 1:
                    emp = data["empresas"][0]
                    if data.get("requiere_seleccion_empresa"):
                        sel_data, sel_status = api_request(
                            "POST", "/auth/seleccionar-empresa", {"empresa_id": emp["id"]}, token=data["access_token"]
                        )
                        if sel_status == 200 and "access_token" in sel_data:
                            session["token"] = sel_data["access_token"]
                            session["user"] = sel_data.get("user", session.get("user", {}))
                    session["empresa_id"] = emp["id"]
                    session["empresa_nombre"] = emp.get("nombre_fantasia") or emp.get("razon_social", "")
                    session["empresa_logo"] = emp.get("logo", "") or ""

                from flask import jsonify

                return jsonify({"redirect": _home_url()})

            from flask import jsonify

            return jsonify({"redirect": url_for("core.login")})

    return render_template("core/login_2fa_setup.html", user_2fa=user_2fa)


@core_bp.route("/cambiar-empresa", methods=["POST"])
@login_required
def cambiar_empresa():
    """Cambia la empresa activa sin cerrar sesión."""
    api_request = get_api_request_func()
    token = session.get("token")
    empresa_id = request.form.get("empresa_id")

    if not empresa_id:
        if request.headers.get("HX-Request"):
            return (
                '<div class="p-4 rounded-xl bg-red-50 text-red-800 border border-red-200">Seleccioná una empresa</div>',
                400,
            )
        flash("Seleccioná una empresa", "error")
        return redirect(url_for("core.dashboard"))

    data, status = api_request("POST", "/auth/cambiar-empresa", {"empresa_id": empresa_id}, token=token)

    if status == 200 and "access_token" in data:
        session["token"] = data["access_token"]
        session["user"] = data.get("user", session.get("user", {}))
        session.pop("permisos_modulos", None)

        # Actualizar empresa activa en session
        # Obtener nombre de la empresa desde la lista de empresas del usuario
        user_empresas_data, emp_status = api_request("GET", "/auth/mis-empresas", token=data["access_token"])
        if emp_status == 200 and isinstance(user_empresas_data, list):
            for emp in user_empresas_data:
                if str(emp.get("id")) == empresa_id:
                    session["empresa_id"] = empresa_id
                    session["empresa_nombre"] = emp.get("nombre_fantasia") or emp.get("razon_social", "")
                    session["empresa_logo"] = emp.get("logo", "") or ""
                    break
        else:
            session["empresa_id"] = empresa_id
            session["empresa_nombre"] = ""
            session["empresa_logo"] = ""

        flash("Empresa cambiada exitosamente", "success")
        if request.headers.get("HX-Request"):
            return "", 200, {"HX-Redirect": _home_url()}
        return redirect(_home_url())

    error = format_api_error(data.get("detail") if isinstance(data, dict) else None, "Error al cambiar empresa")
    if request.headers.get("HX-Request"):
        return f'<div class="p-4 rounded-xl bg-red-50 text-red-800 border border-red-200">{error}</div>', 400
    flash(error, "error")
    return redirect(url_for("core.dashboard"))


@core_bp.route("/empresas-usuario-lista")
@login_required
def empresas_usuario_lista():
    """Retorna partial HTML con la lista de empresas del usuario para el dropdown de cambio."""
    api_request = get_api_request_func()
    token = session.get("token")

    data, status = api_request("GET", "/auth/mis-empresas", token=token)
    empresas = data if status == 200 and isinstance(data, list) else []
    empresa_activa_id = session.get("empresa_id", "")

    if len(empresas) <= 1:
        return '<p class="text-sm text-dark-400 py-2">Solo tenés una empresa asignada</p>'

    html_parts = ['<div class="space-y-2 max-h-48 overflow-y-auto">']
    for emp in empresas:
        emp_id = str(emp.get("id", ""))
        is_active = emp_id == str(empresa_activa_id)
        nombre = emp.get("nombre_fantasia") or emp.get("razon_social", "")
        cuit = emp.get("cuit", "")

        if is_active:
            html_parts.append(f"""
                <div class="flex items-center gap-3 p-2 rounded-xl bg-primary-50 border border-primary-200">
                    <div class="w-8 h-8 bg-primary-100 rounded-lg flex items-center justify-center flex-shrink-0">
                        <i data-lucide="check" class="w-4 h-4 text-primary-600"></i>
                    </div>
                    <div class="min-w-0">
                        <p class="text-sm font-semibold text-primary-700 truncate">{nombre}</p>
                        <p class="text-xs text-primary-500 font-mono">{cuit}</p>
                    </div>
                </div>""")
        else:
            html_parts.append(f'''
                <button type="submit" name="empresa_id" value="{emp_id}"
                        class="w-full flex items-center gap-3 p-2 rounded-xl hover:bg-dark-50 transition-colors text-left">
                    <div class="w-8 h-8 bg-dark-100 rounded-lg flex items-center justify-center flex-shrink-0">
                        <i data-lucide="building-2" class="w-4 h-4 text-dark-400"></i>
                    </div>
                    <div class="min-w-0">
                        <p class="text-sm font-medium text-dark-700 truncate">{nombre}</p>
                        <p class="text-xs text-dark-400 font-mono">{cuit}</p>
                    </div>
                </button>''')

    html_parts.append("</div>")
    return "".join(html_parts)


@core_bp.route("/empresas-usuario-count")
@login_required
def empresas_usuario_count():
    """Retorna la cantidad de empresas del usuario (para decidir si mostrar dropdown)."""
    api_request = get_api_request_func()
    token = session.get("token")

    data, status = api_request("GET", "/auth/mis-empresas", token=token)
    count = len(data) if status == 200 and isinstance(data, list) else 0
    return jsonify({"count": count})


@core_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        api_request = get_api_request_func()
        email = request.form.get("email")

        data, status = api_request("POST", "/auth/forgot-password", {"email": email})

        message = data.get("message", "Si el correo existe, recibirás instrucciones")

        if request.headers.get("HX-Request"):
            return f'<div class="alert alert-success">{message}</div>'
        flash(message, "success")
        return redirect(url_for("core.login"))

    return render_template("core/forgot_password.html")


@core_bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    token = request.args.get("token") or request.form.get("token")

    if not token:
        flash("Token de recuperación no válido", "error")
        return redirect(url_for("core.login"))

    if request.method == "POST":
        api_request = get_api_request_func()
        password = request.form.get("password")

        data, status = api_request("POST", "/auth/reset-password", {"token": token, "password": password})

        if status == 200:
            flash("Contraseña actualizada correctamente", "success")
            if request.headers.get("HX-Request"):
                return (
                    '<div class="alert alert-success">Contraseña actualizada. Redirigiendo...</div>',
                    200,
                    {"HX-Redirect": url_for("core.login")},
                )
            return redirect(url_for("core.login"))

        error = format_api_error(data.get("detail"), "Error al restablecer contraseña")
        if request.headers.get("HX-Request"):
            return f'<div class="alert alert-error">{error}</div>'
        flash(error, "error")

    return render_template("core/reset_password.html", token=token)


@core_bp.route("/set-password", methods=["GET", "POST"])
def set_password():
    """Página para configurar contraseña desde magic link de bienvenida."""
    token = request.args.get("token") or request.form.get("token")

    if not token:
        flash("Enlace inválido", "error")
        return redirect(url_for("core.login"))

    api_request = get_api_request_func()

    # Validar token primero (solo en GET)
    if request.method == "GET":
        data, status = api_request("GET", f"/usuarios/magic-link/validar/{token}")

        if status != 200:
            flash("El enlace es inválido o ha expirado", "error")
            return redirect(url_for("core.login"))

        return render_template(
            "core/set_password.html", token=token, email=data.get("email"), nombre=data.get("nombre")
        )

    # POST - establecer contraseña
    password = request.form.get("password")
    confirm = request.form.get("confirm")

    if password != confirm:
        if request.headers.get("HX-Request"):
            return '<div class="alert alert-error">Las contraseñas no coinciden</div>'
        # Re-validar token para mostrar el form de nuevo
        data, status = api_request("GET", f"/usuarios/magic-link/validar/{token}")
        if status != 200:
            flash("El enlace es inválido o ha expirado", "error")
            return redirect(url_for("core.login"))
        flash("Las contraseñas no coinciden", "error")
        return render_template(
            "core/set_password.html", token=token, email=data.get("email"), nombre=data.get("nombre")
        )

    data, status = api_request(
        "POST",
        "/usuarios/magic-link/set-password",
        {"token": token, "password": password, "confirmar_password": confirm},
    )

    if status == 200:
        flash("¡Contraseña configurada correctamente! Ya podés iniciar sesión", "success")
        if request.headers.get("HX-Request"):
            return (
                '<div class="alert alert-success">¡Contraseña configurada! Redirigiendo al login...</div>',
                200,
                {"HX-Redirect": url_for("core.login")},
            )
        return redirect(url_for("core.login"))

    # Error al establecer contraseña - ir directo al login con el error
    error = format_api_error(data.get("detail"), "Error al configurar contraseña")
    if request.headers.get("HX-Request"):
        return f'<div class="alert alert-error">{error}</div>'
    flash(error, "error")
    return redirect(url_for("core.login"))


@core_bp.route("/logout")
def logout():
    if session.get("refresh"):
        # cierra también la sesión del navegador en el backend (F07-P05): revoca el refresh y borra su cookie
        get_api_request_func()("POST", "/auth/logout")
    session.clear()
    return redirect(url_for("core.login"))


@core_bp.route("/health")
def health():
    return jsonify({"status": "healthy", "service": "frontend"})


@core_bp.route("/")
@login_required
def dashboard():
    print(f"[DASHBOARD] User session: {session.get('user')}, Token exists: {bool(session.get('token'))}")
    api_request = get_api_request_func()
    token = session.get("token")
    usuarios, _ = api_request("GET", "/usuarios", token=token)
    grupos, _ = api_request("GET", "/permisos/grupos", token=token)

    stats = {
        "usuarios": usuarios.get("total", 0) if isinstance(usuarios, dict) else 0,
        "grupos": grupos.get("total", 0) if isinstance(grupos, dict) else 0,
        "activos": len([u for u in usuarios.get("usuarios", []) if u.get("activo")])
        if isinstance(usuarios, dict)
        else 0,
    }
    print(f"[DASHBOARD] Stats: {stats}")

    return render_template("core/dashboard.html", stats=stats)


@core_bp.route("/perfil")
@login_required
def profile():
    api_request = get_api_request_func()
    token = session.get("token")

    # Usar el nuevo endpoint unificado de auth/me/perfil
    data, status = api_request("GET", "/auth/me/perfil", token=token)

    empleado = None
    carreras = []
    if status == 200 and isinstance(data, dict):
        empleado = data.get("empleado")
        if empleado:
            carreras_data, _ = api_request("GET", "/nomina/carreras/todos", token=token)
            carreras = carreras_data or []

    return render_template(
        "core/profile.html",
        empleado=empleado,
        carreras=carreras,
        user_totp_enabled=data.get("totp_enabled", False) if status == 200 else False,
        email_secundario=data.get("email_secundario") if status == 200 else None,
    )


@core_bp.route("/perfil/editar", methods=["POST"])
@login_required
def profile_edit():
    """Edita los datos personales del empleado vinculado al usuario logueado."""
    api_request = get_api_request_func()
    token = session.get("token")

    section = request.form.get("_section", "personal")
    secciones_validas = {"personal", "direccion", "emergencia", "ocasiones"}
    if section not in secciones_validas:
        msg = "Sección de perfil no válida"
        if request.headers.get("HX-Request"):
            return f'<div class="p-4 rounded-xl bg-red-50 text-red-800 border border-red-200">{msg}</div>', 400
        flash(msg, "error")
        return redirect(url_for("core.profile"))

    data = {}

    if section == "personal":
        data = {
            "telefono_personal": request.form.get("telefono_personal") or None,
            "email_personal": request.form.get("email_personal") or None,
            "estado_civil": request.form.get("estado_civil") or None,
            "nivel_estudio": request.form.get("nivel_estudio") or None,
            "carrera_id": request.form.get("carrera_id") or None,
        }
    elif section == "direccion":
        # Dirección laboral no es editable por el empleado — gestionada por RRHH
        return (
            '<div class="p-4 rounded-xl bg-amber-50 text-amber-800 border border-amber-200">La dirección laboral es gestionada por RRHH.</div>',
            403,
        )
    elif section == "emergencia":
        data = {
            "contacto_emergencia": request.form.get("contacto_emergencia") or None,
            "numero_emergencia": request.form.get("numero_emergencia") or None,
            "parentesco": request.form.get("parentesco") or None,
        }
    elif section == "ocasiones":
        data = {
            "usar_direccion_laboral": request.form.get("usar_direccion_laboral") == "true",
            "dir_obsequios_pais": request.form.get("dir_obsequios_pais") or None,
            "dir_obsequios_provincia": request.form.get("dir_obsequios_provincia") or None,
            "dir_obsequios_localidad": request.form.get("dir_obsequios_localidad") or None,
            "dir_obsequios_codigo_postal": request.form.get("dir_obsequios_codigo_postal") or None,
            "dir_obsequios_barrio": request.form.get("dir_obsequios_barrio") or None,
            "dir_obsequios_calle": request.form.get("dir_obsequios_calle") or None,
            "dir_obsequios_numero": request.form.get("dir_obsequios_numero") or None,
            "dir_obsequios_piso": request.form.get("dir_obsequios_piso") or None,
            "dir_obsequios_departamento": request.form.get("dir_obsequios_departamento") or None,
            "preferencia_alimentaria": request.form.get("preferencia_alimentaria") or None,
            "instrucciones_entrega": request.form.get("instrucciones_entrega") or None,
        }

    result, status = api_request("PUT", "/auth/me/perfil", data, token=token)

    if status == 200:
        # El email personal es de la ficha: el de la sesión sigue siendo el de la cuenta (F22)
        if request.headers.get("HX-Request"):
            return '<div class="p-4 rounded-xl bg-emerald-50 text-emerald-800 border border-emerald-200 flex items-center gap-2"><i data-lucide="check-circle" class="w-5 h-5"></i>Cambios guardados correctamente</div>'
        flash("Perfil actualizado exitosamente", "success")
        return redirect(url_for("core.profile"))

    error = format_api_error(result.get("detail") if isinstance(result, dict) else None, "Error al actualizar perfil")
    if request.headers.get("HX-Request"):
        return error_html(error), 422
    flash(error, "error")
    return redirect(url_for("core.profile"))


@core_bp.route("/perfil/cambiar-password", methods=["POST"])
@login_required
def profile_change_password():
    """Cambia la contraseña del usuario logueado."""
    api_request = get_api_request_func()
    token = session.get("token")

    password_actual = request.form.get("password_actual", "").strip()
    password_nueva = request.form.get("password_nueva", "").strip()

    if not password_actual or not password_nueva:
        error_msg = "Completá ambos campos de contraseña"
        if request.headers.get("HX-Request"):
            return error_html(error_msg), 422
        flash(error_msg, "error")
        return redirect(url_for("core.profile"))

    if len(password_nueva) < 8:
        error_msg = "La nueva contraseña debe tener al menos 8 caracteres"
        if request.headers.get("HX-Request"):
            return error_html(error_msg), 422
        flash(error_msg, "error")
        return redirect(url_for("core.profile"))

    data = {
        "password_actual": password_actual,
        "password_nueva": password_nueva,
    }

    result, status = api_request("PUT", "/auth/me/password", data, token=token)

    if status == 200:
        if request.headers.get("HX-Request"):
            return '<div class="p-4 rounded-xl bg-emerald-50 text-emerald-800 border border-emerald-200 flex items-center gap-2"><i data-lucide="check-circle" class="w-5 h-5"></i>Contraseña actualizada correctamente</div>'
        flash("Contraseña actualizada correctamente", "success")
        return redirect(url_for("core.profile"))

    error = format_api_error(
        result.get("detail") if isinstance(result, dict) else None, "Error al cambiar la contraseña"
    )
    if request.headers.get("HX-Request"):
        return error_html(error), 422
    flash(error, "error")
    return redirect(url_for("core.profile"))


# Notificaciones internas


@core_bp.route("/notificaciones-internas/bandeja")
@login_required
def bandeja_notificaciones():
    api_request = get_api_request_func()
    data, status = api_request("GET", "/notificaciones-internas?limite=10", token=session.get("token"))
    if status != 200 or not isinstance(data, dict):
        data = {"items": [], "total_no_leidas": 0}
    return render_template("core/partials/notificaciones_bandeja.html", **data)


@core_bp.route("/notificaciones-internas/indicador")
@login_required
def indicador_notificaciones():
    api_request = get_api_request_func()
    data, status = api_request("GET", "/notificaciones-internas/no-leidas", token=session.get("token"))
    total = data.get("total_no_leidas", 0) if status == 200 and isinstance(data, dict) else 0
    return render_template("core/partials/notificaciones_indicador.html", total_no_leidas=total)


@core_bp.route("/notificaciones")
@login_required
def historial_notificaciones():
    api_request = get_api_request_func()
    pagina = request.args.get("pagina", 1, type=int)
    data, status = api_request(
        "GET",
        f"/notificaciones-internas/historial?pagina={pagina}&por_pagina=20",
        token=session.get("token"),
    )
    if status != 200 or not isinstance(data, dict):
        data = {"items": [], "total": 0, "pagina": pagina, "total_paginas": 1}
    return render_template("core/notificaciones_historial.html", **data)


@core_bp.route("/notificaciones/auditoria")
@login_required
def auditoria_notificaciones():
    if session.get("user", {}).get("rol") != "admin":
        abort(403)

    pagina = request.args.get("pagina", 1, type=int)
    buscar = request.args.get("buscar", "").strip()
    origen = request.args.get("origen", "").strip()
    query = {"pagina": pagina, "por_pagina": 20}
    if buscar:
        query["buscar"] = buscar
    if origen:
        query["origen"] = origen

    api_request = get_api_request_func()
    data, status = api_request(
        "GET", f"/notificaciones-internas/auditoria?{urlencode(query)}", token=session.get("token")
    )
    if status != 200 or not isinstance(data, dict):
        data = {"items": [], "total": 0, "pagina": pagina, "total_paginas": 1}
    return render_template("core/notificaciones_auditoria.html", buscar=buscar, origen=origen, **data)


@core_bp.route("/notificaciones-internas/<notificacion_id>/leer", methods=["POST"])
@login_required
def leer_notificacion(notificacion_id):
    api_request = get_api_request_func()
    _, status = api_request("PUT", f"/notificaciones-internas/{notificacion_id}/leer", token=session.get("token"))
    if status == 200:
        return "", 200, {"HX-Trigger": "notificacionesActualizadas"}
    return "", 400


@core_bp.route("/notificaciones-internas/<notificacion_id>/eliminar", methods=["POST"])
@login_required
def eliminar_notificacion(notificacion_id):
    api_request = get_api_request_func()
    _, status = api_request("DELETE", f"/notificaciones-internas/{notificacion_id}", token=session.get("token"))
    if status == 200:
        return "", 200, {"HX-Trigger": "notificacionesActualizadas"}
    return "", 400


@core_bp.route("/notificaciones-internas/leer-todas", methods=["POST"])
@login_required
def leer_todas_notificaciones():
    api_request = get_api_request_func()
    _, status = api_request("PUT", "/notificaciones-internas/leer-todas", token=session.get("token"))
    if status != 200:
        return error_html("No se pudieron actualizar las notificaciones"), 400
    return make_response(bandeja_notificaciones(), 200, {"HX-Trigger": "notificacionesActualizadas"})


# ─── 2FA Proxy endpoints ─────────────────────────────────────────────────────


@core_bp.route("/perfil/2fa/setup", methods=["POST"])
@login_required
def twofa_setup():
    api_request = get_api_request_func()
    token = session.get("token")
    result, status = api_request("POST", "/auth/me/2fa/setup", token=token)
    from flask import jsonify

    return jsonify(result), status


@core_bp.route("/perfil/2fa/enable", methods=["POST"])
@login_required
def twofa_enable():
    api_request = get_api_request_func()
    token = session.get("token")
    data = request.get_json()
    result, status = api_request("POST", "/auth/me/2fa/enable", data, token=token)
    from flask import jsonify

    return jsonify(result), status


@core_bp.route("/perfil/2fa/disable", methods=["POST"])
@login_required
def twofa_disable():
    api_request = get_api_request_func()
    token = session.get("token")
    data = request.get_json()
    result, status = api_request("DELETE", "/auth/me/2fa", data, token=token)
    from flask import jsonify

    return jsonify(result), status


@core_bp.route("/perfil/avatar", methods=["POST"])
@login_required
def upload_avatar():
    """Sube avatar del usuario actual via proxy al backend."""
    import httpx
    from flask import current_app

    if "file" not in request.files:
        return jsonify({"error": "No se envió archivo"}), 400

    file = request.files["file"]
    token = session.get("token")
    user = session.get("user", {})
    user_id = user.get("id")

    if not user_id:
        return jsonify({"error": "Usuario no identificado"}), 400

    api_url = current_app.config["API_URL"]

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{api_url}/api/v1/auth/me/avatar",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": (file.filename, file.read(), file.content_type)},
            )
            result = response.json()

            # Actualizar avatar_url en la sesión
            if response.status_code == 200 and result.get("avatar_url"):
                session["user"]["avatar_url"] = result["avatar_url"]
                session.modified = True

            return jsonify(result), response.status_code
    except Exception as e:
        import logging

        logging.getLogger(__name__).error(f"Error al subir avatar usuario {user_id}: {e}", exc_info=True)
        return jsonify({"error": "Error al subir avatar. Si el problema persiste, contactá al administrador."}), 500
