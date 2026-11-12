"""
Módulo Usuarios - CRUD de usuarios
"""

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from modulos.auth_helpers import get_api_request_func, require_permiso
from modulos.error_helpers import error_html, format_api_error

usuarios_bp = Blueprint("usuarios", __name__, template_folder="templates", url_prefix="/usuarios")


@usuarios_bp.route("")
@require_permiso("configuracion.usuarios")
def list():
    api_request = get_api_request_func()
    token = session.get("token")

    # Parámetros de paginación y búsqueda
    pagina = request.args.get("pagina", 1, type=int)
    por_pagina = request.args.get("por_pagina", 20, type=int)
    buscar = request.args.get("buscar", "")

    # Parámetros de filtros
    filtro_rol = request.args.get("rol", "")
    filtro_activo = request.args.get("activo", "")

    # Parámetros de ordenamiento
    ordenar_por = request.args.get("ordenar_por", "")
    ordenar_dir = request.args.get("ordenar_dir", "asc")

    # Parámetro de agrupación (solo frontend)
    agrupar_por = request.args.get("agrupar_por", "")

    params = f"?pagina={pagina}&por_pagina={por_pagina}"
    if buscar:
        params += f"&buscar={buscar}"
    if filtro_rol:
        params += f"&rol={filtro_rol}"
    if filtro_activo:
        params += f"&activo={filtro_activo}"
    if ordenar_por:
        params += f"&ordenar_por={ordenar_por}&ordenar_dir={ordenar_dir}"

    data, _ = api_request("GET", f"/usuarios{params}", token=token)

    usuarios = data.get("usuarios", []) if isinstance(data, dict) else []
    total = data.get("total", 0) if isinstance(data, dict) else 0
    total_paginas = data.get("total_paginas", 1) if isinstance(data, dict) else 1

    template_vars = {
        "usuarios": usuarios,
        "pagina": pagina,
        "por_pagina": por_pagina,
        "total": total,
        "total_paginas": total_paginas,
        "buscar": buscar,
        "filtro_rol": filtro_rol,
        "filtro_activo": filtro_activo,
        "ordenar_por": ordenar_por,
        "ordenar_dir": ordenar_dir,
        "agrupar_por": agrupar_por,
    }

    if request.headers.get("HX-Request"):
        return render_template("usuarios/partials/table.html", **template_vars)
    return render_template("usuarios/list.html", **template_vars)


@usuarios_bp.route("/nuevo", methods=["GET", "POST"])
@require_permiso("configuracion.usuarios")
def create():
    api_request = get_api_request_func()
    token = session.get("token")

    if request.method == "POST":
        solicitar_password = request.form.get("solicitar_password") == "on"

        # Limpiar DNI (quitar puntos) y convertir a int
        dni_raw = request.form.get("dni", "").replace(".", "").strip()
        dni = int(dni_raw) if dni_raw else None

        data = {
            "email": request.form.get("email"),
            "email_secundario": request.form.get("email_secundario") or None,
            "nombre": request.form.get("nombre"),
            "apellido": request.form.get("apellido") or None,
            "dni": dni,
            "telefono": request.form.get("telefono") or None,
            "rol": request.form.get("rol", "usuario"),
            "solicitar_password": solicitar_password,
            "grupo_ids": request.form.getlist("grupo_ids"),
            "empresa_id": request.form.get("empresa_id") or None,
            "totp_required": request.form.get("totp_required") == "on",
        }

        # Solo incluir password si no se solicita al usuario
        if not solicitar_password:
            data["password"] = request.form.get("password")

        result, status = api_request("POST", "/usuarios", data, token=token)

        if status in [200, 201]:
            if request.headers.get("HX-Request"):
                return "", 200, {"HX-Redirect": url_for("usuarios.list")}
            msg = (
                "Usuario creado. Se envió email de bienvenida." if solicitar_password else "Usuario creado exitosamente"
            )
            flash(msg, "success")
            return redirect(url_for("usuarios.list"))

        err_block = error_html(result.get("detail"), "Error al crear usuario")
        if request.headers.get("HX-Request"):
            return err_block, 200
        flash(format_api_error(result.get("detail"), "Error al crear usuario"), "error")

    # Cargar grupos disponibles
    grupos_data, _ = api_request("GET", "/permisos/grupos?solo_activos=true", token=token)
    grupos = grupos_data.get("grupos", []) if isinstance(grupos_data, dict) else []

    # Cargar empresas disponibles para asociar
    empresas_data, _ = api_request("GET", "/empresas?por_pagina=100", token=token)
    empresas = empresas_data.get("items", []) if isinstance(empresas_data, dict) else []

    # Empresa activa por defecto
    empresa_activa_id = session.get("empresa_id", "")
    empresa_activa_nombre = session.get("empresa_nombre", "")

    # Cargar dominios de la empresa activa
    dominios_email = []
    if empresa_activa_id:
        empresa_data, emp_status = api_request("GET", f"/empresas/{empresa_activa_id}", token=token)
        if emp_status == 200 and isinstance(empresa_data, dict):
            dominios_email = empresa_data.get("dominios_email") or []

    return render_template(
        "usuarios/form.html",
        usuario=None,
        grupos=grupos,
        empresas=empresas,
        empresa_activa_id=empresa_activa_id,
        empresa_activa_nombre=empresa_activa_nombre,
        dominios_email=dominios_email,
    )


@usuarios_bp.route("/<id>/editar", methods=["GET", "POST"])
@require_permiso("configuracion.usuarios")
def edit(id):
    api_request = get_api_request_func()
    token = session.get("token")

    # Cargar dominios de la empresa activa
    dominios_email = []
    empresa_id = session.get("empresa_id")
    if empresa_id:
        empresa_data, emp_status = api_request("GET", f"/empresas/{empresa_id}", token=token)
        if emp_status == 200 and isinstance(empresa_data, dict):
            dominios_email = empresa_data.get("dominios_email") or []

    if request.method == "POST":
        # Limpiar DNI (quitar puntos) y convertir a int
        dni_raw = request.form.get("dni", "").replace(".", "").strip()
        dni = int(dni_raw) if dni_raw else None

        data = {
            "email": request.form.get("email"),
            "email_secundario": request.form.get("email_secundario") or None,
            "nombre": request.form.get("nombre"),
            "apellido": request.form.get("apellido") or None,
            "dni": dni,
            "telefono": request.form.get("telefono") or None,
            "rol": request.form.get("rol"),
            "activo": request.form.get("activo") == "on",
            "grupo_ids": request.form.getlist("grupo_ids"),
            "totp_required": request.form.get("totp_required") == "on",
        }

        result, status = api_request("PUT", f"/usuarios/{id}", data, token=token)

        if status != 200:
            err_block = error_html(result.get("detail"), "Error al actualizar")
            if request.headers.get("HX-Request"):
                return err_block
            flash(format_api_error(result.get("detail"), "Error al actualizar"), "error")
            usuario, _ = api_request("GET", f"/usuarios/{id}", token=token)
            grupos_data, _ = api_request("GET", "/permisos/grupos?solo_activos=true", token=token)
            grupos = grupos_data.get("grupos", []) if isinstance(grupos_data, dict) else []
            return render_template("usuarios/form.html", usuario=usuario, grupos=grupos, dominios_email=dominios_email)

        # Si se marcó editar password, actualizar el password
        editar_password = request.form.get("editar_password") == "on"
        password = request.form.get("password")

        if editar_password and password:
            pwd_result, pwd_status = api_request(
                "PUT", f"/usuarios/{id}/set-password", {"password": password}, token=token
            )
            if pwd_status != 200:
                err_block = error_html(pwd_result.get("detail"), "Error al cambiar contraseña")
                if request.headers.get("HX-Request"):
                    return err_block
                flash(format_api_error(pwd_result.get("detail"), "Error al cambiar contraseña"), "error")
                usuario, _ = api_request("GET", f"/usuarios/{id}", token=token)
                grupos_data, _ = api_request("GET", "/permisos/grupos?solo_activos=true", token=token)
                grupos = grupos_data.get("grupos", []) if isinstance(grupos_data, dict) else []
                return render_template(
                    "usuarios/form.html", usuario=usuario, grupos=grupos, dominios_email=dominios_email
                )

        # Mensaje de éxito
        msg = "Usuario actualizado correctamente"
        if editar_password and password:
            msg = "Usuario y contraseña actualizados correctamente"

        flash(msg, "success")
        if request.headers.get("HX-Request"):
            return "", 200, {"HX-Redirect": url_for("usuarios.list")}
        return redirect(url_for("usuarios.list"))

    usuario, _ = api_request("GET", f"/usuarios/{id}", token=token)

    # Cargar grupos disponibles
    grupos_data, _ = api_request("GET", "/permisos/grupos?solo_activos=true", token=token)
    grupos = grupos_data.get("grupos", []) if isinstance(grupos_data, dict) else []

    return render_template("usuarios/form.html", usuario=usuario, grupos=grupos, dominios_email=dominios_email)


@usuarios_bp.route("/<id>/eliminar", methods=["DELETE"])
@require_permiso("configuracion.usuarios")
def delete(id):
    api_request = get_api_request_func()
    token = session.get("token")
    result, status = api_request("DELETE", f"/usuarios/{id}", token=token)

    if status == 200:
        return "", 200, {"HX-Trigger": "usuarioDeleted"}
    return error_html(result.get("detail"), "Error al eliminar"), 400


@usuarios_bp.route("/<id>/reset-2fa", methods=["POST"])
@require_permiso("configuracion.usuarios")
def reset_2fa(id):
    """Resetea el 2FA de un usuario (admin)."""
    api_request = get_api_request_func()
    token = session.get("token")
    result, status = api_request("POST", f"/usuarios/{id}/reset-2fa", token=token)
    if status == 200:
        return "", 200
    return error_html("Error al resetear 2FA"), 400


@usuarios_bp.route("/<id>/restaurar", methods=["PUT"])
@require_permiso("configuracion.usuarios")
def restore(id):
    api_request = get_api_request_func()
    token = session.get("token")
    result, status = api_request("PUT", f"/usuarios/{id}/restaurar", token=token)

    if status == 200:
        return "", 200, {"HX-Trigger": "usuarioRestored"}
    return error_html(result.get("detail"), "Error al restaurar"), 400


@usuarios_bp.route("/<id>/avatar", methods=["POST"])
@require_permiso("configuracion.usuarios")
def upload_avatar(id):
    """Sube avatar del usuario via proxy al backend."""
    import httpx
    from flask import current_app, jsonify

    if "file" not in request.files:
        return jsonify({"error": "No se envió archivo"}), 400

    file = request.files["file"]
    token = session.get("token")
    api_url = current_app.config["API_URL"]

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{api_url}/api/v1/usuarios/{id}/avatar",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": (file.filename, file.read(), file.content_type)},
            )
            return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500
