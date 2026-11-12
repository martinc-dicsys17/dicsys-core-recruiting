"""
Configuración → Tareas programadas (F19).

Una pantalla con tres pestañas: las tareas (horario, última corrida, próxima, «Ejecutar
ahora»), el historial de corridas y la cola de envíos (con «Reintentar»). El horario y si
cada tarea está activa se editan en Parámetros (categoría «Tareas programadas»), no acá.
"""

from flask import Blueprint, jsonify, render_template, request, session

from modulos.auth_helpers import get_api_request_func, require_permiso
from modulos.error_helpers import format_api_error

tareas_bp = Blueprint("tareas", __name__, template_folder="templates", url_prefix="/tareas-programadas")

require_tareas = require_permiso("configuracion.tareas_programadas")

# Lo único que la pantalla le pide a la API
RUTAS_API = ("", "corridas", "envios")
PESTANAS = ("tareas", "historial", "envios")


@tareas_bp.route("")
@require_tareas
def listar():
    tab = request.args.get("tab") if request.args.get("tab") in PESTANAS else "tareas"
    return render_template("tareas/list.html", tab=tab)


@tareas_bp.route("/api", methods=["GET"])
@tareas_bp.route("/api/<path:ruta>", methods=["GET", "POST"])
@require_tareas
def api(ruta=""):
    """Relay JSON a /api/v1/tareas con el token de la sesión."""
    raiz = ruta.split("/", 1)[0]
    permitida = raiz in RUTAS_API or ruta.endswith("/ejecutar") or ruta.endswith("/reintentar")
    if not permitida or (request.method == "POST" and not ruta.endswith(("/ejecutar", "/reintentar"))):
        return jsonify({"detail": "Ruta no disponible"}), 404
    endpoint = "/tareas" + (f"/{ruta}" if ruta else "")
    if request.query_string:
        endpoint = f"{endpoint}?{request.query_string.decode()}"
    resultado, status = get_api_request_func()(request.method, endpoint, None, token=session.get("token"))
    if status and status < 400:
        return jsonify(resultado), status
    detalle = resultado.get("detail") if isinstance(resultado, dict) else None
    return jsonify({"detail": format_api_error(detalle, "Error en tareas programadas")}), status or 500
