"""
Módulo HRBP - Gestión de Entregas RRHH
"""

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from modulos.auth_helpers import get_api_request_func, require_permiso
from modulos.error_helpers import error_html, format_api_error

hrbp_bp = Blueprint("hrbp", __name__, template_folder="templates", url_prefix="/hrbp")


# === ITEMS (Tipos de Items) ===
@hrbp_bp.route("/items")
@require_permiso("hrbp.gestion_items")
def items_list():
    api_request = get_api_request_func()
    token = session.get("token")

    buscar = request.args.get("buscar", "")
    stock_bajo = request.args.get("stock_bajo", "")

    params = f"?buscar={buscar}" if buscar else ""
    if stock_bajo:
        params += "&stock_bajo=true" if params else "?stock_bajo=true"

    data, _ = api_request("GET", f"/hrbp/items{params}", token=token)
    items = data.get("items", []) if isinstance(data, dict) else []

    if request.headers.get("HX-Request"):
        return render_template("hrbp/partials/items_table.html", items=items)
    return render_template("hrbp/items_list.html", items=items, buscar=buscar, stock_bajo=stock_bajo)


@hrbp_bp.route("/items/nuevo", methods=["GET", "POST"])
@require_permiso("hrbp.gestion_items")
def items_create():
    if request.method == "POST":
        api_request = get_api_request_func()
        token = session.get("token")

        data = {
            "nombre": request.form.get("nombre"),
            "descripcion": request.form.get("descripcion") or None,
            "stock_actual": int(request.form.get("stock_actual", 0)),
            "stock_minimo": int(request.form.get("stock_minimo", 0)),
        }

        result, status = api_request("POST", "/hrbp/items", data, token=token)

        if status in [200, 201]:
            flash("Item creado exitosamente", "success")
            if request.headers.get("HX-Request"):
                return "", 200, {"HX-Redirect": url_for("hrbp.items_list")}
            return redirect(url_for("hrbp.items_list"))

        err_block = error_html(result.get("detail"), "Error al crear item")
        if request.headers.get("HX-Request"):
            return err_block
        flash(format_api_error(result.get("detail"), "Error al crear item"), "error")

    return render_template("hrbp/item_form.html", item=None)


@hrbp_bp.route("/items/<id>/editar", methods=["GET", "POST"])
@require_permiso("hrbp.gestion_items")
def items_edit(id):
    api_request = get_api_request_func()
    token = session.get("token")

    if request.method == "POST":
        data = {
            "nombre": request.form.get("nombre"),
            "descripcion": request.form.get("descripcion") or None,
            "stock_actual": int(request.form.get("stock_actual", 0)),
            "stock_minimo": int(request.form.get("stock_minimo", 0)),
        }

        result, status = api_request("PUT", f"/hrbp/items/{id}", data, token=token)

        if status == 200:
            flash("Item actualizado", "success")
            if request.headers.get("HX-Request"):
                return "", 200, {"HX-Redirect": url_for("hrbp.items_list")}
            return redirect(url_for("hrbp.items_list"))

        err_block = error_html(result.get("detail"), "Error al actualizar")
        if request.headers.get("HX-Request"):
            return err_block
        flash(format_api_error(result.get("detail"), "Error al actualizar"), "error")

    item, _ = api_request("GET", f"/hrbp/items/{id}", token=token)
    return render_template("hrbp/item_form.html", item=item)


@hrbp_bp.route("/items/<id>/eliminar", methods=["DELETE"])
@require_permiso("hrbp.gestion_items")
def items_delete(id):
    api_request = get_api_request_func()
    token = session.get("token")
    result, status = api_request("DELETE", f"/hrbp/items/{id}", token=token)

    if status == 200:
        return "", 200, {"HX-Trigger": "itemDeleted"}
    return error_html(result.get("detail"), "Error al eliminar"), 400


@hrbp_bp.route("/items/<id>/ajustar-stock", methods=["POST"])
@require_permiso("hrbp.gestion_items")
def items_ajustar_stock(id):
    api_request = get_api_request_func()
    token = session.get("token")

    data = {"cantidad": int(request.form.get("cantidad", 0)), "motivo": request.form.get("motivo") or None}

    result, status = api_request("POST", f"/hrbp/items/{id}/ajustar-stock", data, token=token)

    if status == 200:
        return "", 200, {"HX-Trigger": "stockAjustado"}
    return error_html(result.get("detail"), "Error al ajustar stock"), 400


# === ENTREGAS ===
@hrbp_bp.route("/entregas")
@require_permiso("hrbp.entregas")
def entregas_list():
    api_request = get_api_request_func()
    token = session.get("token")

    item_tipo_id = request.args.get("item_tipo_id", "")

    params = f"?item_tipo_id={item_tipo_id}" if item_tipo_id else ""

    data, _ = api_request("GET", f"/hrbp/entregas{params}", token=token)
    entregas = data.get("items", []) if isinstance(data, dict) else []

    # Obtener items para filtro
    items_data, _ = api_request("GET", "/hrbp/items?por_pagina=100", token=token)
    items = items_data.get("items", []) if isinstance(items_data, dict) else []

    if request.headers.get("HX-Request"):
        return render_template("hrbp/partials/entregas_table.html", entregas=entregas)
    return render_template("hrbp/entregas_list.html", entregas=entregas, items=items, item_tipo_id=item_tipo_id)


@hrbp_bp.route("/entregas/nueva", methods=["GET", "POST"])
@require_permiso("hrbp.entregas")
def entregas_create():
    api_request = get_api_request_func()
    token = session.get("token")

    if request.method == "POST":
        data = {
            "item_tipo_id": request.form.get("item_tipo_id"),
            "empleado_id": request.form.get("empleado_id"),
            "cantidad": int(request.form.get("cantidad", 1)),
            "observaciones": request.form.get("observaciones") or None,
        }

        result, status = api_request("POST", "/hrbp/entregas", data, token=token)

        if status in [200, 201]:
            flash("Entrega registrada exitosamente", "success")
            if request.headers.get("HX-Request"):
                return "", 200, {"HX-Redirect": url_for("hrbp.entregas_list")}
            return redirect(url_for("hrbp.entregas_list"))

        err_block = error_html(result.get("detail"), "Error al registrar entrega")
        if request.headers.get("HX-Request"):
            return err_block
        flash(format_api_error(result.get("detail"), "Error al registrar entrega"), "error")

    # Obtener items y empleados para los selects
    items_data, _ = api_request("GET", "/hrbp/items?por_pagina=100", token=token)
    items = items_data.get("items", []) if isinstance(items_data, dict) else []

    # Usar endpoint optimizado para selects
    empleados_data, _ = api_request("GET", "/nomina/empleados/buscar-select", token=token)
    empleados = empleados_data if isinstance(empleados_data, list) else []

    return render_template("hrbp/entrega_form.html", entrega=None, items=items, empleados=empleados)


@hrbp_bp.route("/entregas/<id>/eliminar", methods=["DELETE"])
@require_permiso("hrbp.entregas")
def entregas_delete(id):
    api_request = get_api_request_func()
    token = session.get("token")
    result, status = api_request("DELETE", f"/hrbp/entregas/{id}", token=token)

    if status == 200:
        return "", 200, {"HX-Trigger": "entregaDeleted"}
    return error_html(result.get("detail"), "Error al eliminar"), 400
