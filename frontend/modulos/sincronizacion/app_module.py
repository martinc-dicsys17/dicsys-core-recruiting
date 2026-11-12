"""
Módulo Sincronización - Actualización de Datos desde fuentes externas
"""

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from modulos.auth_helpers import get_api_request_func, require_permiso

# Todos los procesos en una página (son pocos; la API pagina desde F07-P08)
PROCESOS = "/sincronizacion/procesos?por_pagina=100"

sincronizacion_bp = Blueprint(
    "sincronizacion", __name__, template_folder="templates", url_prefix="/configuracion/sincronizacion"
)


@sincronizacion_bp.route("")
@require_permiso("configuracion.actualizacion_datos")
def listar():
    """Lista los procesos de sincronización."""
    api_request = get_api_request_func()
    token = session.get("token")
    data, status = api_request("GET", PROCESOS, token=token)

    procesos = data.get("items", []) if isinstance(data, dict) else []

    if request.headers.get("HX-Request"):
        return render_template("sincronizacion/partials/table.html", procesos=procesos)
    return render_template("sincronizacion/list.html", procesos=procesos)


@sincronizacion_bp.route("/<id>/ejecutar", methods=["POST"])
@require_permiso("configuracion.actualizacion_datos")
def ejecutar(id):
    """Ejecuta un proceso de sincronización."""
    api_request = get_api_request_func()
    token = session.get("token")

    # El backend registra como ejecutor al usuario del token
    result, status = api_request("POST", f"/sincronizacion/procesos/{id}/ejecutar", token=token)

    # Recargar la tabla con los datos actualizados
    data, _ = api_request("GET", PROCESOS, token=token)
    procesos = data.get("items", []) if isinstance(data, dict) else []

    # Agregar mensaje de resultado: el de la corrida o, si no corrió (404, 409), el error
    mensaje = result.get("mensaje") or result.get("detail") or "Proceso ejecutado"
    exito = status == 200 and result.get("exito", False)

    if request.headers.get("HX-Request"):
        from flask import make_response

        response = make_response(
            render_template("sincronizacion/partials/table.html", procesos=procesos, mensaje=mensaje, exito=exito)
        )
        response.headers["HX-Retarget"] = "#procesos-container"
        response.headers["HX-Reswap"] = "innerHTML"
        return response

    if exito:
        flash(mensaje, "success")
    else:
        flash(mensaje, "error")

    return redirect(url_for("sincronizacion.listar"))


@sincronizacion_bp.route("/<id>/toggle", methods=["POST"])
@require_permiso("configuracion.actualizacion_datos")
def toggle_activo(id):
    """Activa/desactiva un proceso."""
    api_request = get_api_request_func()
    token = session.get("token")

    # Obtener estado actual
    proceso, _ = api_request("GET", f"/sincronizacion/procesos/{id}", token=token)
    nuevo_estado = not proceso.get("activo", True)

    # Actualizar
    api_request("PUT", f"/sincronizacion/procesos/{id}", {"activo": nuevo_estado}, token=token)

    if request.headers.get("HX-Request"):
        data, _ = api_request("GET", PROCESOS, token=token)
        procesos = data.get("items", []) if isinstance(data, dict) else []
        return render_template("sincronizacion/partials/table.html", procesos=procesos)

    return redirect(url_for("sincronizacion.listar"))


@sincronizacion_bp.route("/<id>/logs")
@require_permiso("configuracion.actualizacion_datos")
def logs(id):
    """Muestra los logs de un proceso: el modal de la pantalla de procesos. Sin HTMX (un link directo) vuelve a esa
    pantalla: no hay página propia de logs (PG-33)."""
    if not request.headers.get("HX-Request"):
        return redirect(url_for("sincronizacion.listar"))
    api_request = get_api_request_func()
    token = session.get("token")

    proceso, _ = api_request("GET", f"/sincronizacion/procesos/{id}", token=token)
    data, _ = api_request("GET", f"/sincronizacion/procesos/{id}/logs?por_pagina=20", token=token)
    logs = data.get("items", []) if isinstance(data, dict) else []

    return render_template("sincronizacion/partials/logs_modal.html", proceso=proceso, logs=logs)
