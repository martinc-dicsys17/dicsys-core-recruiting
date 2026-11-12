"""
Módulo Recruiting. Por ahora solo el Dashboard y el Manager Dashboard; Candidatos, Búsquedas, Pipeline y Parámetros
se migran después.
"""

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from modulos.auth_helpers import get_api_request_func, require_permiso

recruiting_bp = Blueprint("recruiting", __name__, template_folder="templates", url_prefix="/recruiting")

ERROR_DASHBOARD = "No se pudo cargar el Dashboard de Recruiting. Probá de nuevo en unos minutos."


def _es_admin():
    """Solo orienta la interfaz (qué dashboard mostrar): el acceso real lo valida el backend con require_admin en cada
    llamada al Manager Dashboard. En el módulo original esto era el email admin@admin.com; en el Core es el rol."""
    return (session.get("user") or {}).get("rol") == "admin"


# === DASHBOARD ===
# /recruiting/dashboard va primero: es la URL que arma url_for('recruiting.dashboard') para el menú.
# El administrador entra por el mismo ítem del menú y ve el Manager Dashboard, como en el módulo original.
@recruiting_bp.route("/")
@recruiting_bp.route("/dashboard")
@require_permiso("recruiting.dashboard")
def dashboard():
    if _es_admin():
        return redirect(url_for("recruiting.manager_dashboard"))

    api_request = get_api_request_func()
    data, status = api_request("GET", "/recruiting/dashboard", token=session.get("token"))

    if status != 200 or not isinstance(data, dict):
        # Sin datos no se muestran ceros: se avisa que no se pudo cargar
        detalle = data.get("detail") if isinstance(data, dict) else None
        return render_template("recruiting/dashboard.html", dashboard=None, error=detalle or ERROR_DASHBOARD)

    return render_template("recruiting/dashboard.html", dashboard=data, error=None)


# === MANAGER DASHBOARD (solo administradores) ===
# Cuelga de /recruiting/dashboard para que el ítem "Dashboard" del menú siga resaltado (el menú compara el prefijo).
@recruiting_bp.route("/dashboard/manager")
@require_permiso("recruiting.dashboard")
def manager_dashboard():
    if not _es_admin():
        return render_template("core/403.html", modulo="recruiting.manager_dashboard"), 403
    return render_template("recruiting/manager_dashboard.html")


@recruiting_bp.route("/dashboard/manager/datos")
@require_permiso("recruiting.dashboard")
def manager_dashboard_datos():
    """Proxy de los indicadores: el backend valida el acceso (require_admin) y responde 403 si corresponde."""
    api_request = get_api_request_func()
    consulta = request.query_string.decode("utf-8")
    endpoint = "/recruiting/manager-dashboard" + (f"?{consulta}" if consulta else "")
    try:
        data, status = api_request("GET", endpoint, token=session.get("token"))
    except Exception:
        return jsonify({"error": "Error de comunicación con el servidor"}), 500
    if status == 200 and isinstance(data, dict):
        return jsonify(data), 200
    detalle = data.get("detail") if isinstance(data, dict) else None
    if isinstance(detalle, list):
        detalle = "Filtros inválidos"
    return jsonify({"error": detalle or "Error al obtener el Manager Dashboard"}), status or 500
