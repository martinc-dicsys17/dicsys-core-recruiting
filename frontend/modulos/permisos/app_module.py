"""
Módulo Permisos - Gestión de grupos y permisos
"""

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for

from modulos.auth_helpers import get_api_request_func, require_permiso
from modulos.error_helpers import error_html, format_api_error

permisos_bp = Blueprint("permisos", __name__, template_folder="templates", url_prefix="/permisos")


# === LISTAR GRUPOS ===
@permisos_bp.route("/grupos", methods=["GET", "POST"])
@require_permiso("configuracion.permisos")
def grupos_list():
    api_request = get_api_request_func()
    token = session.get("token")

    # POST: Crear nuevo grupo
    if request.method == "POST":
        data = {"nombre": request.form.get("nombre"), "descripcion": request.form.get("descripcion") or None}
        result, status = api_request("POST", "/permisos/grupos", data, token=token)

        if status in [200, 201]:
            if request.headers.get("HX-Request"):
                # Recargar la lista de grupos
                data_grupos, _ = api_request("GET", "/permisos/grupos", token=token)
                grupos = data_grupos.get("grupos", []) if isinstance(data_grupos, dict) else []
                return render_template("permisos/partials/grupos_grid.html", grupos=grupos)
            flash("Grupo creado exitosamente", "success")
            return redirect(url_for("permisos.grupos_list"))

        err_block = error_html(result.get("detail"), "Error al crear grupo")
        if request.headers.get("HX-Request"):
            return err_block, 400
        flash(format_api_error(result.get("detail"), "Error al crear grupo"), "error")

    # GET: Listar grupos
    data, _ = api_request("GET", "/permisos/grupos", token=token)
    grupos = data.get("grupos", []) if isinstance(data, dict) else []

    if request.headers.get("HX-Request"):
        return render_template("permisos/partials/grupos_grid.html", grupos=grupos)
    return render_template("permisos/grupos.html", grupos=grupos)


# === EDITAR GRUPO ===
@permisos_bp.route("/grupos/<id>/editar", methods=["GET", "POST"])
@require_permiso("configuracion.permisos")
def edit_grupo(id):
    api_request = get_api_request_func()
    token = session.get("token")

    if request.method == "POST":
        data = {
            "nombre": request.form.get("nombre"),
            "descripcion": request.form.get("descripcion") or None,
            "activo": request.form.get("activo") == "on",
        }
        result, status = api_request("PUT", f"/permisos/grupos/{id}", data, token=token)

        if status == 200:
            flash("Grupo actualizado", "success")
            if request.headers.get("HX-Request"):
                return "", 200, {"HX-Redirect": url_for("permisos.grupos_list")}
            return redirect(url_for("permisos.grupos_list"))

        err_block = error_html(result.get("detail"), "Error al actualizar")
        if request.headers.get("HX-Request"):
            return err_block
        flash(format_api_error(result.get("detail"), "Error al actualizar"), "error")

    # Obtener grupo
    grupo, _ = api_request("GET", f"/permisos/grupos/{id}", token=token)
    if not grupo or "id" not in grupo:
        flash("Grupo no encontrado", "error")
        return redirect(url_for("permisos.grupos_list"))

    # Obtener módulos disponibles con submódulos
    modulos, _ = api_request("GET", "/permisos/modulos/detalle", token=token)
    modulos = modulos if isinstance(modulos, list) else []

    # Obtener usuarios del grupo
    usuarios_grupo, _ = api_request("GET", f"/permisos/grupos/{id}/usuarios", token=token)
    usuarios_grupo = usuarios_grupo if isinstance(usuarios_grupo, list) else []

    # Obtener todos los usuarios, ordenados alfabéticamente para mostrar
    usuarios_data, _ = api_request("GET", "/usuarios?por_pagina=1000&ordenar_por=nombre&ordenar_dir=asc", token=token)
    todos_usuarios = usuarios_data.get("usuarios", []) if isinstance(usuarios_data, dict) else []
    todos_usuarios.sort(key=lambda u: (u.get("nombre") or "").lower())

    # Obtener departamentos para el filtro
    departamentos_data, _ = api_request("GET", "/permisos/departamentos-lista", token=token)
    departamentos = departamentos_data if isinstance(departamentos_data, list) else []

    return render_template(
        "permisos/grupo_form.html",
        grupo=grupo,
        modulos=modulos,
        usuarios_grupo=usuarios_grupo,
        todos_usuarios=todos_usuarios,
        departamentos=departamentos,
    )


# === BUSCAR USUARIOS PARA GRUPO ===
@permisos_bp.route("/grupos/<id>/buscar-usuarios", methods=["GET"])
@require_permiso("configuracion.permisos")
def buscar_usuarios_grupo(id):
    """Busca usuarios y devuelve el partial HTML con checkboxes."""
    api_request = get_api_request_func()
    token = session.get("token")
    buscar = request.args.get("buscar", "").strip()
    departamento_id = request.args.get("departamento_id", "").strip()
    activo = request.args.get("activo", "").strip()

    # Usuarios ya asignados al grupo (para marcar checkboxes)
    usuarios_grupo, _ = api_request("GET", f"/permisos/grupos/{id}/usuarios", token=token)
    usuarios_grupo = usuarios_grupo if isinstance(usuarios_grupo, list) else []
    usuarios_grupo_ids = [u["id"] for u in usuarios_grupo]

    # Construir params de búsqueda
    params = "por_pagina=1000&ordenar_por=nombre&ordenar_dir=asc"
    if buscar:
        params += f"&buscar={buscar}"
    if departamento_id:
        params += f"&departamento_id={departamento_id}"
    if activo in ("true", "false"):
        params += f"&activo={activo}"

    usuarios_data, _ = api_request("GET", f"/usuarios?{params}", token=token)
    todos_usuarios = usuarios_data.get("usuarios", []) if isinstance(usuarios_data, dict) else []
    todos_usuarios.sort(key=lambda u: (u.get("nombre") or "").lower())

    # Devolver partial HTML
    return render_template(
        "permisos/partials/usuarios_lista.html", todos_usuarios=todos_usuarios, usuarios_grupo_ids=usuarios_grupo_ids
    )


# === ASIGNAR PERMISOS ===
@permisos_bp.route("/grupos/<id>/permisos", methods=["POST"])
@require_permiso("configuracion.permisos")
def asignar_permisos(id):
    api_request = get_api_request_func()
    token = session.get("token")

    # Obtener módulos disponibles para saber cuáles procesar
    modulos_data, _ = api_request("GET", "/permisos/modulos/detalle", token=token)
    modulos = modulos_data if isinstance(modulos_data, list) else []

    # Construir lista de permisos desde el form (módulo + submódulos)
    permisos = []
    for modulo in modulos:
        codigo = modulo.get("codigo")
        tiene_acceso = request.form.get(f"permiso_{codigo}") == "on"
        permisos.append({"modulo": codigo, "tiene_acceso": tiene_acceso})

        # Submódulos
        for item in modulo.get("items", []):
            item_codigo = item.get("codigo")
            clave = f"{codigo}.{item_codigo}"
            tiene_acceso_item = request.form.get(f"permiso_{clave}") == "on"
            permisos.append({"modulo": clave, "tiene_acceso": tiene_acceso_item})

    data = {"permisos": permisos}
    result, status = api_request("PUT", f"/permisos/grupos/{id}/permisos", data, token=token)

    if status == 200:
        # Limpiar cache de permisos para que se recarguen
        session.pop("permisos_modulos", None)
        if request.headers.get("HX-Request"):
            return '<div class="p-4 rounded-xl bg-emerald-50 text-emerald-800 border border-emerald-200"><i data-lucide="check-circle" class="w-4 h-4 inline mr-2"></i>Permisos actualizados</div>'
        flash("Permisos actualizados", "success")
        return redirect(url_for("permisos.edit_grupo", id=id))

    error_block = error_html(result.get("detail"), "Error al asignar permisos")
    if request.headers.get("HX-Request"):
        return error_block, 400
    flash(format_api_error(result.get("detail"), "Error al asignar permisos"), "error")
    return redirect(url_for("permisos.edit_grupo", id=id))


# === ASIGNAR USUARIOS ===
@permisos_bp.route("/grupos/<id>/usuarios", methods=["POST"])
@require_permiso("configuracion.permisos")
def asignar_usuarios(id):
    api_request = get_api_request_func()
    token = session.get("token")

    # Obtener IDs de usuarios seleccionados
    usuario_ids = request.form.getlist("usuarios")

    data = {"usuario_ids": usuario_ids}
    result, status = api_request("PUT", f"/permisos/grupos/{id}/usuarios", data, token=token)

    if status == 200:
        if request.headers.get("HX-Request"):
            return '<div class="p-4 rounded-xl bg-emerald-50 text-emerald-800 border border-emerald-200"><i data-lucide="check-circle" class="w-4 h-4 inline mr-2"></i>Usuarios actualizados</div>'
        flash("Usuarios actualizados", "success")
        return redirect(url_for("permisos.edit_grupo", id=id))

    error_block = error_html(result.get("detail"), "Error al asignar usuarios")
    if request.headers.get("HX-Request"):
        return error_block, 400
    flash(format_api_error(result.get("detail"), "Error al asignar usuarios"), "error")
    return redirect(url_for("permisos.edit_grupo", id=id))


# === PERMISOS POR DEPARTAMENTO ===
@permisos_bp.route("/departamentos", methods=["GET"])
@require_permiso("configuracion.permisos")
def permisos_departamentos():
    """Vista de resumen de permisos agrupados por departamento."""
    api_request = get_api_request_func()
    token = session.get("token")
    data, _ = api_request("GET", "/permisos/departamentos-permisos", token=token)
    departamentos = data if isinstance(data, list) else []
    return render_template("permisos/departamentos.html", departamentos=departamentos)


# === OBTENER DEPARTAMENTOS DE UN GRUPO ===
@permisos_bp.route("/grupos/<id>/departamentos", methods=["GET"])
@require_permiso("configuracion.permisos")
def obtener_departamentos_grupo(id):
    """Obtiene los departamentos vinculados a un grupo."""
    api_request = get_api_request_func()
    token = session.get("token")
    data, _ = api_request("GET", f"/permisos/grupos/{id}/departamentos", token=token)
    return jsonify(data if isinstance(data, list) else [])


# === ASIGNAR DEPARTAMENTOS A UN GRUPO ===
@permisos_bp.route("/grupos/<id>/departamentos", methods=["POST"])
@require_permiso("configuracion.permisos")
def asignar_departamentos_grupo(id):
    """Asigna departamentos a un grupo para auto-suscripción."""
    api_request = get_api_request_func()
    token = session.get("token")

    # Obtener IDs de departamentos desde JSON
    departamento_ids = request.json.get("departamento_ids", []) if request.is_json else []

    data = {"departamento_ids": departamento_ids}
    result, status = api_request("PUT", f"/permisos/grupos/{id}/departamentos", data, token=token)

    if status == 200:
        if request.headers.get("HX-Request") or request.is_json:
            return '<div class="p-4 rounded-xl bg-emerald-50 text-emerald-800 border border-emerald-200"><i data-lucide="check-circle" class="w-4 h-4 inline mr-2"></i>Departamentos actualizados</div>'
        flash("Departamentos actualizados", "success")
        return redirect(url_for("permisos.edit_grupo", id=id))

    error_block = error_html(result.get("detail"), "Error al asignar departamentos")
    if request.headers.get("HX-Request") or request.is_json:
        return error_block, 400
    flash(format_api_error(result.get("detail"), "Error al asignar departamentos"), "error")
    return redirect(url_for("permisos.edit_grupo", id=id))


# === ELIMINAR GRUPO ===
@permisos_bp.route("/grupos/<id>/eliminar", methods=["DELETE"])
@require_permiso("configuracion.permisos")
def delete_grupo(id):
    api_request = get_api_request_func()
    token = session.get("token")
    result, status = api_request("DELETE", f"/permisos/grupos/{id}", token=token)

    if status == 200:
        return "", 200, {"HX-Trigger": "grupoDeleted"}
    return error_html(result.get("detail"), "Error al eliminar"), 400


# === RESTAURAR GRUPO ===
@permisos_bp.route("/grupos/<id>/restaurar", methods=["PUT"])
@require_permiso("configuracion.permisos")
def restore_grupo(id):
    api_request = get_api_request_func()
    token = session.get("token")
    result, status = api_request("PUT", f"/permisos/grupos/{id}/restaurar", token=token)

    if status == 200:
        return "", 200, {"HX-Trigger": "grupoRestored"}
    return error_html(result.get("detail"), "Error al restaurar"), 400
