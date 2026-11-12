"""
Módulo Operaciones - Gestión de Equipos
"""

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from modulos.auth_helpers import get_api_request_func, require_permiso

operaciones_bp = Blueprint("operaciones", __name__, template_folder="templates", url_prefix="/operaciones")


# === LISTAR EQUIPOS ===
@operaciones_bp.route("/equipos")
@require_permiso("operaciones.equipos")
def equipos_list():
    api_request = get_api_request_func()
    token = session.get("token")

    buscar = request.args.get("buscar", "")
    pagina = request.args.get("pagina", 1, type=int)
    filtro_activo = request.args.get("activo", "")

    params = f"?pagina={pagina}&por_pagina=50"
    if buscar:
        params += f"&buscar={buscar}"
    if filtro_activo:
        params += f"&activo={'true' if filtro_activo == 'activo' else 'false'}"

    data, status = api_request("GET", f"/operaciones/equipos{params}", token=token)

    items = data.get("items", []) if isinstance(data, dict) else []
    total = data.get("total", 0) if isinstance(data, dict) else 0
    total_paginas = data.get("total_paginas", 1) if isinstance(data, dict) else 1

    # Cargar empleados para filtros
    empleados, _ = api_request("GET", "/nomina/empleados/buscar-select", token=token)

    if request.headers.get("HX-Request"):
        return render_template(
            "operaciones/partials/equipos_table.html",
            items=items,
            total=total,
            pagina=pagina,
            total_paginas=total_paginas,
            buscar=buscar,
            filtro_activo=filtro_activo,
        )

    return render_template(
        "operaciones/equipos_list.html",
        items=items,
        total=total,
        pagina=pagina,
        total_paginas=total_paginas,
        buscar=buscar,
        empleados=empleados or [],
        filtro_activo=filtro_activo,
    )


# === CREAR EQUIPO ===
@operaciones_bp.route("/equipos/nuevo", methods=["GET", "POST"])
@require_permiso("operaciones.equipos")
def equipos_create():
    api_request = get_api_request_func()
    token = session.get("token")

    if request.method == "POST":
        data = _get_equipo_form_data()

        result, status = api_request("POST", "/operaciones/equipos", data, token=token)

        if status in [200, 201]:
            flash("Equipo creado exitosamente", "success")
            if request.headers.get("HX-Request"):
                return "", 200, {"HX-Redirect": url_for("operaciones.equipos_list")}
            return redirect(url_for("operaciones.equipos_list"))

        error = result.get("detail", "Error al crear equipo")
        if request.headers.get("HX-Request"):
            return f'<div class="p-4 rounded-xl bg-red-50 text-red-800 border border-red-200 mb-4">{error}</div>'
        flash(error, "error")

    empleados, _ = api_request("GET", "/nomina/empleados/buscar-select", token=token)

    return render_template("operaciones/equipos_form.html", item=None, empleados=empleados or [])


# === EDITAR EQUIPO ===
@operaciones_bp.route("/equipos/<id>/editar", methods=["GET", "POST"])
@require_permiso("operaciones.equipos")
def equipos_edit(id):
    api_request = get_api_request_func()
    token = session.get("token")

    if request.method == "POST":
        data = _get_equipo_form_data()

        result, status = api_request("PUT", f"/operaciones/equipos/{id}", data, token=token)

        if status == 200:
            flash("Equipo actualizado exitosamente", "success")
            if request.headers.get("HX-Request"):
                return "", 200, {"HX-Redirect": url_for("operaciones.equipos_list")}
            return redirect(url_for("operaciones.equipos_list"))

        error = result.get("detail", "Error al actualizar equipo")
        if request.headers.get("HX-Request"):
            return f'<div class="p-4 rounded-xl bg-red-50 text-red-800 border border-red-200 mb-4">{error}</div>'
        flash(error, "error")

    item, _ = api_request("GET", f"/operaciones/equipos/{id}", token=token)
    empleados, _ = api_request("GET", "/nomina/empleados/buscar-select", token=token)

    return render_template("operaciones/equipos_form.html", item=item, empleados=empleados or [])


# === CAMBIAR ESTADO ===
@operaciones_bp.route("/equipos/<id>/estado/<nuevo_estado>", methods=["PUT"])
@require_permiso("operaciones.equipos")
def equipos_cambiar_estado(id, nuevo_estado):
    api_request = get_api_request_func()
    token = session.get("token")

    activo = nuevo_estado.lower() == "true"
    result, status = api_request("PUT", f"/operaciones/equipos/{id}", {"activo": activo}, token=token)

    if status == 200:
        return "", 200, {"HX-Trigger": "equipoEstadoCambiado"}
    return f'<div class="p-4 rounded-xl bg-red-50 text-red-800">{result.get("detail", "Error")}</div>', 400


def _get_equipo_form_data():
    """Extrae los datos del formulario de equipo."""
    integrantes = request.form.getlist("integrantes_ids")

    return {
        "nombre": request.form.get("nombre"),
        "cliente_id": request.form.get("cliente_id") or None,
        "lider_id": request.form.get("lider_id") or None,
        "activo": request.form.get("activo") == "true",
        "integrantes_ids": integrantes,
    }
