"""
Helpers centralizados de autenticación y permisos para el frontend.
Reemplaza los login_required duplicados en cada módulo.
"""

from functools import wraps

from flask import jsonify, redirect, render_template, request, session, url_for

SESION_VENCIDA = "Tu sesión venció: volvé a iniciar sesión"


def get_api_request_func():
    """Obtiene la función api_request del app principal."""
    from flask import current_app

    return current_app.config.get("api_request")


def respuesta_sin_sesion():
    """
    Sin sesión (o vencida) se va al login, según quién pide:
    - HTMX (ej. el indicador de la campana, cada 60 s): HX-Redirect, así htmx lleva la página
      entera al login. Un 302 lo sigue el navegador y htmx metía el login dentro del elemento.
    - fetch JSON (pantallas con Alpine): 401 con el motivo, para que la pantalla lo muestre.
    - navegación normal: redirect.
    """
    destino = url_for("core.login")
    if request.headers.get("HX-Request"):
        return "", 200, {"HX-Redirect": destino}
    if request.accept_mimetypes.best == "application/json":
        return jsonify({"detail": SESION_VENCIDA}), 401
    return redirect(destino)


def login_required(f):
    """Decorador para rutas que requieren autenticación."""

    @wraps(f)
    def decorated(*args, **kwargs):
        if "token" not in session:
            return respuesta_sin_sesion()
        return f(*args, **kwargs)

    return decorated


def require_permiso(codigo_modulo):
    """
    Decorador factory que verifica que el usuario tenga acceso a un módulo.
    Incluye login_required implícitamente.
    Los admin siempre pasan.

    Uso:
        @require_permiso('nomina')
        def empleados_list():
            ...
    """

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            print(f"[PERMISO] === Verificando permiso '{codigo_modulo}' para ruta {request.path} ===", flush=True)

            if "token" not in session:
                print("[PERMISO] No hay token en sesión, redirigiendo a login", flush=True)
                return respuesta_sin_sesion()

            user = session.get("user", {})
            print(f"[PERMISO] User: id={user.get('id')}, email={user.get('email')}, rol={user.get('rol')}", flush=True)

            # Admin tiene acceso total
            if user.get("rol") == "admin":
                print("[PERMISO] User es admin, acceso total", flush=True)
                return f(*args, **kwargs)

            # Verificar permisos via API
            permisos = _obtener_permisos_usuario()
            print(f"[PERMISO] Permisos obtenidos: {permisos}", flush=True)
            print(
                f"[PERMISO] Buscando key '{codigo_modulo}' -> valor: {permisos.get(codigo_modulo, 'NO EXISTE')}",
                flush=True,
            )

            modulo_principal = codigo_modulo.split(".", 1)[0]
            tiene_modulo = permisos.get(modulo_principal, False)
            tiene_permiso = permisos.get(codigo_modulo, False)

            if not tiene_modulo or not tiene_permiso:
                print(f"[PERMISO] ❌ ACCESO DENEGADO para módulo '{codigo_modulo}'", flush=True)
                if request.headers.get("HX-Request"):
                    return (
                        '<div class="p-4 rounded-xl bg-red-50 text-red-800 border border-red-200">No tenés acceso a este módulo</div>',
                        403,
                    )
                return render_template("core/403.html", modulo=codigo_modulo), 403

            print(f"[PERMISO] ✅ Acceso concedido para módulo '{codigo_modulo}'", flush=True)
            return f(*args, **kwargs)

        return decorated

    return decorator


def _obtener_permisos_usuario():
    """Obtiene los permisos del usuario actual desde la API (sin cache para reflejar cambios en tiempo real)."""
    user = session.get("user", {})
    user_id = user.get("id")
    print(f"[PERMISOS_API] Consultando permisos para user_id={user_id}", flush=True)
    if not user_id:
        print("[PERMISOS_API] No hay user_id, retornando vacío", flush=True)
        return {}

    try:
        api_request = get_api_request_func()
        token = session.get("token")
        print(f"[PERMISOS_API] Llamando GET /permisos/mis-permisos, token exists={bool(token)}", flush=True)
        data, status = api_request("GET", "/permisos/mis-permisos", token=token)
        print(f"[PERMISOS_API] Respuesta: status={status}, data={data}", flush=True)

        if status == 200 and isinstance(data, dict):
            permisos = data.get("permisos", {})
            print(f"[PERMISOS_API] Permisos parseados: {permisos}", flush=True)
            return permisos
        else:
            print(f"[PERMISOS_API] Respuesta no exitosa: status={status}", flush=True)
    except Exception as e:
        print(f"[PERMISOS_API] Error obteniendo permisos: {e}", flush=True)

    return {}


def limpiar_cache_permisos():
    """Limpia el cache de permisos en sesión. Llamar cuando se modifiquen permisos."""
    session.pop("permisos_modulos", None)
