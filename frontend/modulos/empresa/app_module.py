"""
Módulo Empresa - Gestión de Empresas (CRUD completo)
Incluye domicilios y usuarios asociados.
Acceso restringido a rol admin (permiso 'configuracion').
"""

import logging

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from modulos.auth_helpers import get_api_request_func, require_permiso
from modulos.error_helpers import error_html, format_api_error

logger = logging.getLogger(__name__)

empresa_bp = Blueprint("empresa", __name__, template_folder="templates", url_prefix="/empresa")

# Todas las rutas requieren permiso 'configuracion' (mismo que backend require_modulo)
login_required = require_permiso("configuracion")


# ─── LISTAR EMPRESAS ──────────────────────────────────────────────────────────


@empresa_bp.route("")
@login_required
def empresas_list():
    api_request = get_api_request_func()
    token = session.get("token")

    buscar = request.args.get("buscar", "")
    pagina = request.args.get("pagina", 1, type=int)
    filtro_activo = request.args.get("activo", "")

    params = f"?pagina={pagina}&por_pagina=20"
    if buscar:
        params += f"&buscar={buscar}"
    if filtro_activo:
        params += f"&activo={'true' if filtro_activo == 'activo' else 'false'}"

    data, status = api_request("GET", f"/empresas{params}", token=token)

    items = data.get("items", []) if isinstance(data, dict) else []
    total = data.get("total", 0) if isinstance(data, dict) else 0
    total_paginas = data.get("total_paginas", 1) if isinstance(data, dict) else 1

    if request.headers.get("HX-Request"):
        return render_template(
            "empresa/partials/table.html",
            items=items,
            total=total,
            pagina=pagina,
            total_paginas=total_paginas,
            buscar=buscar,
            filtro_activo=filtro_activo,
        )

    return render_template(
        "empresa/list.html",
        items=items,
        total=total,
        pagina=pagina,
        total_paginas=total_paginas,
        buscar=buscar,
        filtro_activo=filtro_activo,
    )


# ─── CREAR EMPRESA ────────────────────────────────────────────────────────────


@empresa_bp.route("/nuevo", methods=["GET", "POST"])
@login_required
def empresas_create():
    api_request = get_api_request_func()
    token = session.get("token")

    if request.method == "POST":
        data = _get_empresa_form_data()

        result, status = api_request("POST", "/empresas", data, token=token)

        if status in [200, 201]:
            # Si se subió un logo, enviarlo al endpoint de logo
            empresa_id = result.get("id")
            logo_file = request.files.get("logo_file")
            if logo_file and logo_file.filename and empresa_id:
                import httpx
                from flask import current_app

                api_url = current_app.config["API_URL"]
                headers = {"Authorization": f"Bearer {token}"}
                try:
                    with httpx.Client(timeout=30.0) as client:
                        files = {"logo": (logo_file.filename, logo_file.read(), logo_file.content_type)}
                        client.post(f"{api_url}/api/v1/empresas/{empresa_id}/logo", headers=headers, files=files)
                except Exception as e:
                    logger.error(f"Error al subir logo en creación: {e}", exc_info=True)

            flash("Empresa creada exitosamente", "success")
            if request.headers.get("HX-Request"):
                return "", 200, {"HX-Redirect": url_for("empresa.empresas_list")}
            return redirect(url_for("empresa.empresas_list"))

        error = format_api_error(result.get("detail"), "Error al crear la empresa")
        if request.headers.get("HX-Request"):
            return error_html(error)
        flash(error, "error")

    return render_template("empresa/form.html", item=None)


# ─── EDITAR EMPRESA ───────────────────────────────────────────────────────────


@empresa_bp.route("/<id>/editar", methods=["GET", "POST"])
@login_required
def empresas_edit(id):
    api_request = get_api_request_func()
    token = session.get("token")

    if request.method == "POST":
        data = _get_empresa_form_data(is_edit=True)

        result, status = api_request("PUT", f"/empresas/{id}", data, token=token)

        if status == 200:
            flash("Empresa actualizada exitosamente", "success")
            if request.headers.get("HX-Request"):
                return "", 200, {"HX-Redirect": url_for("empresa.empresas_view", id=id)}
            return redirect(url_for("empresa.empresas_view", id=id))

        error = format_api_error(result.get("detail"), "Error al actualizar la empresa")
        if request.headers.get("HX-Request"):
            return error_html(error)
        flash(error, "error")

    item, _ = api_request("GET", f"/empresas/{id}", token=token)
    return render_template("empresa/form.html", item=item)


# ─── DETALLE EMPRESA ──────────────────────────────────────────────────────────


@empresa_bp.route("/<id>")
@login_required
def empresas_view(id):
    api_request = get_api_request_func()
    token = session.get("token")

    item, status = api_request("GET", f"/empresas/{id}", token=token)
    if status != 200:
        flash("Empresa no encontrada", "error")
        return redirect(url_for("empresa.empresas_list"))

    # Cargar usuarios asociados
    usuarios, _ = api_request("GET", f"/empresas/{id}/usuarios", token=token)
    if not isinstance(usuarios, list):
        usuarios = []

    return render_template("empresa/view.html", item=item, usuarios=usuarios)


# ─── ELIMINAR EMPRESA (soft delete) ──────────────────────────────────────────


@empresa_bp.route("/<id>/eliminar", methods=["DELETE"])
@login_required
def empresas_delete(id):
    api_request = get_api_request_func()
    token = session.get("token")

    result, status = api_request("DELETE", f"/empresas/{id}", token=token)

    if status == 200:
        return "", 200, {"HX-Trigger": "empresaDeleted"}

    error = format_api_error(result.get("detail"), "Error al eliminar la empresa")
    return error_html(error), 400


# ─── CAMBIAR ESTADO (activar/desactivar) ─────────────────────────────────────


@empresa_bp.route("/<id>/estado/<nuevo_estado>", methods=["PUT"])
@login_required
def empresas_cambiar_estado(id, nuevo_estado):
    api_request = get_api_request_func()
    token = session.get("token")

    activo = nuevo_estado.lower() == "true"
    result, status = api_request("PUT", f"/empresas/{id}", {"activo": activo}, token=token)

    if status == 200:
        return "", 200, {"HX-Trigger": "empresaEstadoCambiado"}

    error = format_api_error(result.get("detail"), "Error al cambiar estado")
    return error_html(error), 400


# ─── DOMICILIOS ───────────────────────────────────────────────────────────────


@empresa_bp.route("/<id>/domicilios/nuevo", methods=["POST"])
@login_required
def domicilio_add(id):
    api_request = get_api_request_func()
    token = session.get("token")

    data = {
        "calle": request.form.get("calle"),
        "numero": request.form.get("numero") or None,
        "piso": request.form.get("piso") or None,
        "departamento": request.form.get("departamento") or None,
        "localidad": request.form.get("localidad"),
        "provincia": request.form.get("provincia"),
        "pais": request.form.get("pais") or "Argentina",
        "codigo_postal": request.form.get("codigo_postal") or None,
    }

    result, status = api_request("POST", f"/empresas/{id}/domicilios", data, token=token)

    if status in [200, 201]:
        flash("Domicilio agregado exitosamente", "success")
        if request.headers.get("HX-Request"):
            return "", 200, {"HX-Redirect": url_for("empresa.empresas_view", id=id)}
        return redirect(url_for("empresa.empresas_view", id=id))

    error = format_api_error(result.get("detail"), "Error al agregar domicilio")
    if request.headers.get("HX-Request"):
        return error_html(error)
    flash(error, "error")
    return redirect(url_for("empresa.empresas_view", id=id))


@empresa_bp.route("/<id>/domicilios/<dom_id>/eliminar", methods=["DELETE"])
@login_required
def domicilio_delete(id, dom_id):
    api_request = get_api_request_func()
    token = session.get("token")

    result, status = api_request("DELETE", f"/empresas/{id}/domicilios/{dom_id}", token=token)

    if status == 200:
        return "", 200, {"HX-Trigger": "domicilioDeleted"}

    error = format_api_error(result.get("detail"), "Error al eliminar domicilio")
    return error_html(error), 400


# ─── USUARIOS ASOCIADOS ──────────────────────────────────────────────────────


@empresa_bp.route("/<id>/usuarios/agregar", methods=["POST"])
@login_required
def usuario_add(id):
    api_request = get_api_request_func()
    token = session.get("token")

    usuario_id = request.form.get("usuario_id")
    if not usuario_id:
        if request.headers.get("HX-Request"):
            return error_html("Debe seleccionar un usuario")
        flash("Debe seleccionar un usuario", "error")
        return redirect(url_for("empresa.empresas_view", id=id))

    result, status = api_request("POST", f"/empresas/{id}/usuarios?usuario_id={usuario_id}", token=token)

    if status in [200, 201]:
        flash("Usuario asociado exitosamente", "success")
        if request.headers.get("HX-Request"):
            return "", 200, {"HX-Redirect": url_for("empresa.empresas_view", id=id)}
        return redirect(url_for("empresa.empresas_view", id=id))

    error = format_api_error(result.get("detail"), "Error al asociar usuario")
    if request.headers.get("HX-Request"):
        return error_html(error)
    flash(error, "error")
    return redirect(url_for("empresa.empresas_view", id=id))


@empresa_bp.route("/<id>/usuarios/<user_id>/quitar", methods=["DELETE"])
@login_required
def usuario_remove(id, user_id):
    api_request = get_api_request_func()
    token = session.get("token")

    result, status = api_request("DELETE", f"/empresas/{id}/usuarios/{user_id}", token=token)

    if status == 200:
        return "", 200, {"HX-Trigger": "usuarioRemoved"}

    error = format_api_error(result.get("detail"), "Error al desasociar usuario")
    return error_html(error), 400


# ─── LOGO DE EMPRESA ──────────────────────────────────────────────────────────


@empresa_bp.route("/<id>/logo", methods=["POST"])
@login_required
def empresas_logo_upload(id):
    """Sube el logo de una empresa via multipart al backend."""
    import httpx
    from flask import current_app

    token = session.get("token")
    logo_file = request.files.get("logo_file")

    if not logo_file:
        return (
            '<div class="p-3 rounded-xl bg-red-50 text-red-800 border border-red-200 text-sm">No se seleccionó ningún archivo</div>',
            400,
        )

    api_url = current_app.config["API_URL"]
    url = f"{api_url}/api/v1/empresas/{id}/logo"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        with httpx.Client(timeout=30.0) as client:
            files = {"logo": (logo_file.filename, logo_file.read(), logo_file.content_type)}
            response = client.post(url, headers=headers, files=files)

            if response.status_code == 200:
                data = response.json()
                logo_url = data.get("logo", "")
                upload_url = url_for("empresa.empresas_logo_upload", id=id)
                delete_url = url_for("empresa.empresas_logo_delete", id=id)

                return f'''
                <div id="logo-container" class="flex flex-col items-center gap-3">
                    <div class="w-40 h-28 rounded-2xl overflow-hidden border-2 border-dark-200 bg-dark-50 flex items-center justify-center p-2">
                        <img src="{logo_url}" alt="Logo de la empresa" class="max-w-full max-h-full object-contain">
                    </div>
                    <div class="flex gap-2">
                        <label class="flex items-center px-3 py-1.5 text-xs font-medium text-primary-600 bg-primary-50 border border-primary-200 rounded-lg hover:bg-primary-100 transition-colors cursor-pointer">
                            <i data-lucide="upload" class="w-3 h-3 mr-1"></i>
                            Cambiar logo
                            <input type="file" name="logo_file" accept=".jpg,.jpeg,.png,.webp,.svg" class="hidden"
                                   hx-post="{upload_url}"
                                   hx-target="#logo-container"
                                   hx-swap="outerHTML"
                                   hx-encoding="multipart/form-data"
                                   hx-trigger="change">
                        </label>
                        <button type="button"
                                hx-delete="{delete_url}"
                                hx-target="#logo-container"
                                hx-swap="outerHTML"
                                hx-confirm="¿Eliminar el logo?"
                                class="flex items-center px-3 py-1.5 text-xs font-medium text-red-600 bg-red-50 border border-red-200 rounded-lg hover:bg-red-100 transition-colors">
                            <i data-lucide="trash-2" class="w-3 h-3 mr-1"></i>
                            Eliminar
                        </button>
                    </div>
                </div>
                '''
            else:
                detail = response.json().get("detail", "Error al subir el logo")
                return (
                    f'<div class="p-3 rounded-xl bg-red-50 text-red-800 border border-red-200 text-sm">{detail}</div>',
                    400,
                )
    except Exception as e:
        logger.error(f"Error al subir logo de empresa: {e}", exc_info=True)
        return (
            '<div class="p-3 rounded-xl bg-red-50 text-red-800 border border-red-200 text-sm">Error al subir el logo. Intentá de nuevo.</div>',
            500,
        )


@empresa_bp.route("/<id>/logo", methods=["DELETE"])
@login_required
def empresas_logo_delete(id):
    """Elimina el logo de una empresa."""
    import httpx
    from flask import current_app

    token = session.get("token")
    api_url = current_app.config["API_URL"]
    url = f"{api_url}/api/v1/empresas/{id}/logo"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.delete(url, headers=headers)

            if response.status_code == 200:
                upload_url = url_for("empresa.empresas_logo_upload", id=id)

                return f'''
                <div id="logo-container" class="flex flex-col items-center gap-3">
                    <div class="w-40 h-28 rounded-2xl overflow-hidden border-2 border-dashed border-dark-300 bg-dark-50 flex flex-col items-center justify-center gap-2">
                        <i data-lucide="building-2" class="w-10 h-10 text-dark-300"></i>
                        <span class="text-xs text-dark-400">Sin logo</span>
                    </div>
                    <label class="flex items-center px-3 py-1.5 text-xs font-medium text-primary-600 bg-primary-50 border border-primary-200 rounded-lg hover:bg-primary-100 transition-colors cursor-pointer">
                        <i data-lucide="upload" class="w-3 h-3 mr-1"></i>
                        Subir logo
                        <input type="file" name="logo_file" accept=".jpg,.jpeg,.png,.webp,.svg" class="hidden"
                               hx-post="{upload_url}"
                               hx-target="#logo-container"
                               hx-swap="outerHTML"
                               hx-encoding="multipart/form-data"
                               hx-trigger="change">
                    </label>
                    <p class="text-xs text-dark-400">JPG, PNG, WebP o SVG. Máx 2MB</p>
                </div>
                '''
            else:
                detail = response.json().get("detail", "Error al eliminar el logo")
                return (
                    f'<div class="p-3 rounded-xl bg-red-50 text-red-800 border border-red-200 text-sm">{detail}</div>',
                    400,
                )
    except Exception as e:
        logger.error(f"Error al eliminar logo de empresa: {e}", exc_info=True)
        return (
            '<div class="p-3 rounded-xl bg-red-50 text-red-800 border border-red-200 text-sm">Error al eliminar el logo. Intentá de nuevo.</div>',
            500,
        )


# ─── BÚSQUEDA DE USUARIOS (para select de asociación) ────────────────────────


@empresa_bp.route("/usuarios-buscar")
@login_required
def usuarios_buscar():
    """Busca usuarios para el select de asociación. Devuelve JSON."""
    from flask import jsonify

    api_request = get_api_request_func()
    token = session.get("token")

    q = request.args.get("q", "").strip()
    if len(q) < 1:
        return jsonify([])

    data, status = api_request("GET", f"/usuarios/buscar/?q={q}&limite=15", token=token)

    if status == 200 and isinstance(data, dict):
        usuarios = data.get("usuarios", [])
        resultado = [{"id": u.get("id"), "nombre": u.get("nombre", ""), "email": u.get("email", "")} for u in usuarios]
        return jsonify(resultado)

    return jsonify([])


# ─── HELPERS ──────────────────────────────────────────────────────────────────


def _get_empresa_form_data(is_edit=False):
    """Extrae los datos del formulario de empresa."""
    data = {
        "cuit": request.form.get("cuit"),
        "razon_social": request.form.get("razon_social"),
        "nombre_fantasia": request.form.get("nombre_fantasia") or None,
        "responsabilidad_afip": request.form.get("responsabilidad_afip"),
        "sitio_web": request.form.get("sitio_web") or None,
        "telefono": request.form.get("telefono") or None,
        "email_contacto": request.form.get("email_contacto") or None,
        "observaciones": request.form.get("observaciones") or None,
        # Datos fiscales
        "nro_ingresos_brutos": request.form.get("nro_ingresos_brutos") or None,
        "fecha_inicio_actividades": request.form.get("fecha_inicio_actividades") or None,
        "nro_inscripcion_municipal": request.form.get("nro_inscripcion_municipal") or None,
        "regimen_retencion": request.form.get("regimen_retencion") or None,
    }

    # Dominios de email
    dominios_raw = request.form.get("dominios_email", "").strip()
    if dominios_raw:
        data["dominios_email"] = [d.strip().lower() for d in dominios_raw.split(",") if d.strip()]
    else:
        data["dominios_email"] = []

    if is_edit:
        activo = request.form.get("activo")
        if activo is not None:
            data["activo"] = activo == "true"

    return data


# ─── DOMINIOS DE EMAIL ────────────────────────────────────────────────────────


@empresa_bp.route("/<id>/dominios", methods=["POST"])
@login_required
def dominios_update(id):
    """Actualiza la lista de dominios de email de la empresa."""
    api_request = get_api_request_func()
    token = session.get("token")

    dominios_raw = request.form.get("dominios_email", "").strip()
    if dominios_raw:
        dominios = [d.strip().lower() for d in dominios_raw.split(",") if d.strip()]
    else:
        dominios = []

    result, status = api_request("PUT", f"/empresas/{id}", {"dominios_email": dominios}, token=token)

    if status == 200:
        flash("Dominios actualizados", "success")
        if request.headers.get("HX-Request"):
            return "", 200, {"HX-Redirect": url_for("empresa.empresas_view", id=id)}
        return redirect(url_for("empresa.empresas_view", id=id))

    error = format_api_error(result.get("detail"), "Error al actualizar dominios")
    if request.headers.get("HX-Request"):
        return error_html(error)
    flash(error, "error")
    return redirect(url_for("empresa.empresas_view", id=id))
