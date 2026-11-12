"""
Módulo Administración - Clientes, Auditoría y Recibos de Sueldo
"""

import logging
import os
from functools import wraps

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    render_template as _render_template,
    request,
    session,
    url_for,
)

from modulos.auth_helpers import get_api_request_func, require_permiso, respuesta_sin_sesion
from modulos.error_helpers import error_html, format_api_error

administracion_bp = Blueprint("administracion", __name__, template_folder="templates", url_prefix="/administracion")

# Alias: rutas de clientes requieren permiso 'admin_contable.clientes'
require_clientes = require_permiso("admin_contable.clientes")

# Auditoría: módulo independiente, no submódulo de admin_contable
require_auditoria = require_permiso("auditoria")


# ─── CLIENTES ─────────────────────────────────────────────────────────────────


@administracion_bp.route("/clientes")
@require_clientes
def clientes_list():
    api_request = get_api_request_func()
    token = session.get("token")

    buscar = request.args.get("buscar", "")
    pagina = request.args.get("pagina", 1, type=int)
    filtro_tipo = request.args.get("tipo", "")
    filtro_categoria = request.args.get("categoria_id", "")
    ordenar_por = request.args.get("ordenar_por", "")
    ordenar_dir = request.args.get("ordenar_dir", "asc")

    params = f"?pagina={pagina}&por_pagina=20"
    if buscar:
        params += f"&buscar={buscar}"
    if filtro_tipo:
        params += f"&tipo={filtro_tipo}"
    if filtro_categoria:
        params += f"&categoria_id={filtro_categoria}"
    if ordenar_por:
        params += f"&ordenar_por={ordenar_por}"
    if ordenar_dir:
        params += f"&ordenar_dir={ordenar_dir}"

    data, _ = api_request("GET", f"/clientes{params}", token=token)
    items = data.get("items", []) if isinstance(data, dict) else []
    total = data.get("total", 0) if isinstance(data, dict) else 0
    total_paginas = data.get("total_paginas", 1) if isinstance(data, dict) else 1

    if request.headers.get("HX-Request"):
        hx_target = request.headers.get("HX-Target", "")
        if hx_target == "clientes-cards":
            return render_template(
                "administracion/partials/clientes_cards.html",
                items=items,
                total=total,
                pagina=pagina,
                total_paginas=total_paginas,
            )
        return render_template(
            "administracion/partials/clientes_table.html",
            items=items,
            total=total,
            pagina=pagina,
            total_paginas=total_paginas,
        )

    categorias, _ = api_request("GET", "/clientes/categorias", token=token)

    return render_template(
        "administracion/clientes_list.html",
        items=items,
        total=total,
        pagina=pagina,
        total_paginas=total_paginas,
        buscar=buscar,
        categorias=categorias or [],
        filtro_tipo=filtro_tipo,
        filtro_categoria=filtro_categoria,
        ordenar_por=ordenar_por,
        ordenar_dir=ordenar_dir,
    )


@administracion_bp.route("/clientes/nuevo", methods=["GET", "POST"])
@require_clientes
def clientes_create():
    api_request = get_api_request_func()
    token = session.get("token")

    if request.method == "POST":
        data = _get_cliente_form_data()

        result, status = api_request("POST", "/clientes", data, token=token)

        if status in [200, 201]:
            cliente_id = result.get("id")

            # Si se subió un logo, enviarlo al endpoint de logo
            logo_file = request.files.get("logo_file")
            if logo_file and logo_file.filename and cliente_id:
                import httpx
                from flask import current_app

                api_url = current_app.config["API_URL"]
                headers = {"Authorization": f"Bearer {token}"}
                try:
                    with httpx.Client(timeout=30.0) as client:
                        files = {"logo": (logo_file.filename, logo_file.read(), logo_file.content_type)}
                        client.post(f"{api_url}/api/v1/clientes/{cliente_id}/logo", headers=headers, files=files)
                except Exception as e:
                    import logging

                    logging.getLogger(__name__).error(f"Error al subir logo en creación: {e}", exc_info=True)

            flash("Cliente creado exitosamente", "success")
            if request.headers.get("HX-Request"):
                return "", 200, {"HX-Redirect": url_for("administracion.clientes_list")}
            return redirect(url_for("administracion.clientes_list"))

        err = error_html(result.get("detail"), "Error al crear el cliente")
        if request.headers.get("HX-Request"):
            return err
        flash(format_api_error(result.get("detail"), "Error al crear el cliente"), "error")

    categorias, _ = api_request("GET", "/clientes/categorias?solo_activas=true", token=token)
    return render_template("administracion/clientes_form.html", item=None, categorias=categorias or [], selected_ids=[])


@administracion_bp.route("/clientes/<id>/editar", methods=["GET", "POST"])
@require_clientes
def clientes_edit(id):
    api_request = get_api_request_func()
    token = session.get("token")

    if request.method == "POST":
        data = _get_cliente_form_data(is_edit=True)

        result, status = api_request("PUT", f"/clientes/{id}", data, token=token)

        if status == 200:
            flash("Cliente actualizado exitosamente", "success")
            if request.headers.get("HX-Request"):
                return "", 200, {"HX-Redirect": url_for("administracion.clientes_list")}
            return redirect(url_for("administracion.clientes_list"))

        err = error_html(result.get("detail"), "Error al actualizar el cliente")
        if request.headers.get("HX-Request"):
            return err
        flash(format_api_error(result.get("detail"), "Error al actualizar el cliente"), "error")

    item, _ = api_request("GET", f"/clientes/{id}", token=token)
    categorias, _ = api_request("GET", "/clientes/categorias?solo_activas=true", token=token)
    selected_ids = [str(c.get("id", "")) for c in (item.get("categorias", []) if item else [])]
    return render_template(
        "administracion/clientes_form.html", item=item, categorias=categorias or [], selected_ids=selected_ids
    )


@administracion_bp.route("/clientes/<id>")
@require_clientes
def clientes_view(id):
    api_request = get_api_request_func()
    token = session.get("token")
    item, status = api_request("GET", f"/clientes/{id}", token=token)
    if status != 200:
        flash("Cliente no encontrado", "error")
        return redirect(url_for("administracion.clientes_list"))
    return render_template("administracion/clientes_view.html", item=item)


@administracion_bp.route("/clientes/<id>/eliminar", methods=["DELETE"])
@require_clientes
def clientes_delete(id):
    api_request = get_api_request_func()
    token = session.get("token")
    result, status = api_request("DELETE", f"/clientes/{id}", token=token)

    if status == 200:
        return "", 200, {"HX-Trigger": "clienteDeleted"}
    return error_html(result.get("detail"), "Error al eliminar"), 400


@administracion_bp.route("/clientes/<id>/domicilios/nuevo", methods=["GET", "POST"])
@require_clientes
def clientes_domicilio_add(id):
    api_request = get_api_request_func()
    token = session.get("token")

    if request.method == "POST":
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

        result, status = api_request("POST", f"/clientes/{id}/domicilios", data, token=token)

        if status in [200, 201]:
            flash("Domicilio agregado exitosamente", "success")
            if request.headers.get("HX-Request"):
                return "", 200, {"HX-Redirect": url_for("administracion.clientes_edit", id=id)}
            return redirect(url_for("administracion.clientes_edit", id=id))

        err = error_html(result.get("detail"), "Error al agregar domicilio")
        if request.headers.get("HX-Request"):
            return err
        flash(format_api_error(result.get("detail"), "Error al agregar domicilio"), "error")

    cliente, _ = api_request("GET", f"/clientes/{id}", token=token)
    return render_template("administracion/clientes_domicilio_form.html", cliente=cliente)


# ─── LOGO DE CLIENTE ──────────────────────────────────────────────────────────


@administracion_bp.route("/clientes/<id>/logo", methods=["POST"])
@require_clientes
def clientes_logo_upload(id):
    """Sube el logo de un cliente via multipart al backend."""
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
    url = f"{api_url}/api/v1/clientes/{id}/logo"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        with httpx.Client(timeout=30.0) as client:
            files = {"logo": (logo_file.filename, logo_file.read(), logo_file.content_type)}
            response = client.post(url, headers=headers, files=files)

            if response.status_code == 200:
                data = response.json()
                logo_url = data.get("logo", "")
                upload_url = url_for("administracion.clientes_logo_upload", id=id)
                delete_url = url_for("administracion.clientes_logo_delete", id=id)
                return f'''
                <div id="logo-container" class="flex flex-col items-center gap-3">
                    <div class="w-40 h-28 rounded-2xl overflow-hidden border-2 border-dark-200 bg-dark-50 flex items-center justify-center p-2">
                        <img src="{logo_url}" alt="Logo del cliente" class="max-w-full max-h-full object-contain">
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
                <script>lucide.createIcons();</script>
                '''
            else:
                detail = response.json().get("detail", "Error al subir el logo")
                return (
                    f'<div class="p-3 rounded-xl bg-red-50 text-red-800 border border-red-200 text-sm">{detail}</div>',
                    400,
                )
    except Exception as e:
        import logging

        logging.getLogger(__name__).error(f"Error al subir logo de cliente: {e}", exc_info=True)
        return (
            '<div class="p-3 rounded-xl bg-red-50 text-red-800 border border-red-200 text-sm">Error al subir el logo. Intentá de nuevo.</div>',
            500,
        )


@administracion_bp.route("/clientes/<id>/logo", methods=["DELETE"])
@require_clientes
def clientes_logo_delete(id):
    """Elimina el logo de un cliente."""
    import httpx
    from flask import current_app

    token = session.get("token")
    api_url = current_app.config["API_URL"]
    url = f"{api_url}/api/v1/clientes/{id}/logo"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.delete(url, headers=headers)

            if response.status_code == 200:
                upload_url = url_for("administracion.clientes_logo_upload", id=id)
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
                <script>lucide.createIcons();</script>
                '''
            else:
                detail = response.json().get("detail", "Error al eliminar el logo")
                return (
                    f'<div class="p-3 rounded-xl bg-red-50 text-red-800 border border-red-200 text-sm">{detail}</div>',
                    400,
                )
    except Exception as e:
        import logging

        logging.getLogger(__name__).error(f"Error al eliminar logo de cliente: {e}", exc_info=True)
        return (
            '<div class="p-3 rounded-xl bg-red-50 text-red-800 border border-red-200 text-sm">Error al eliminar el logo.</div>',
            500,
        )


@administracion_bp.route("/categorias-cliente")
@require_clientes
def categorias_list():
    api_request = get_api_request_func()
    token = session.get("token")
    categorias, _ = api_request("GET", "/clientes/categorias", token=token)

    if request.headers.get("HX-Request"):
        return render_template("administracion/partials/categorias_table.html", categorias=categorias or [])

    return render_template("administracion/categorias_list.html", categorias=categorias or [])


@administracion_bp.route("/clientes/categorias-partial")
@require_clientes
def clientes_categorias_partial():
    """Devuelve solo los checkboxes de categorías para refrescar via HTMX."""
    api_request = get_api_request_func()
    token = session.get("token")
    categorias, _ = api_request("GET", "/clientes/categorias?solo_activas=true", token=token)
    return render_template(
        "administracion/partials/clientes_categorias_checkboxes.html", categorias=categorias or [], selected_ids=[]
    )


@administracion_bp.route("/categorias-cliente/guardar", methods=["POST"])
@require_clientes
def categorias_save():
    api_request = get_api_request_func()
    token = session.get("token")

    categoria_id = request.form.get("categoria_id") or None
    data = {
        "nombre": request.form.get("nombre"),
        "descripcion": request.form.get("descripcion") or None,
    }

    if categoria_id:
        result, status = api_request("PUT", f"/clientes/categorias/{categoria_id}", data, token=token)
        msg_ok = "Categoría actualizada"
        msg_err = "Error al actualizar la categoría"
    else:
        result, status = api_request("POST", "/clientes/categorias", data, token=token)
        msg_ok = "Categoría creada"
        msg_err = "Error al crear la categoría"

    if status in [200, 201]:
        flash(msg_ok, "success")
        if request.headers.get("HX-Request"):
            return "", 200, {"HX-Redirect": url_for("administracion.categorias_list")}
        return redirect(url_for("administracion.categorias_list"))

    err = error_html(result.get("detail"), msg_err)
    if request.headers.get("HX-Request"):
        return err
    flash(format_api_error(result.get("detail"), msg_err), "error")
    return redirect(url_for("administracion.categorias_list"))


@administracion_bp.route("/categorias-cliente/<id>/eliminar", methods=["DELETE"])
@require_clientes
def categorias_delete(id):
    api_request = get_api_request_func()
    token = session.get("token")
    result, status = api_request("DELETE", f"/clientes/categorias/{id}", token=token)

    if status == 200:
        return "", 200, {"HX-Trigger": "categoriaEliminada"}
    return error_html(result.get("detail"), "Error al eliminar"), 400


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _parse_date(date_str):
    """Convierte yyyy-mm-dd (input type=date) a yyyy-mm-dd para el backend."""
    if not date_str:
        return None
    return date_str  # el input type=date ya manda yyyy-mm-dd


def _get_cliente_form_data(is_edit: bool = False) -> dict:
    """Extrae y arma el payload del formulario de cliente."""
    categoria_ids = request.form.getlist("categoria_ids")

    data = {
        "tipo": request.form.get("tipo"),
        "cuit": request.form.get("cuit"),
        "razon_social": request.form.get("razon_social"),
        "nombre_fantasia": request.form.get("nombre_fantasia") or None,
        "responsabilidad_afip": request.form.get("responsabilidad_afip"),
        "sitio_web": request.form.get("sitio_web") or None,
        "observaciones": request.form.get("observaciones") or None,
        "categoria_ids": categoria_ids,
        "nro_ingresos_brutos": request.form.get("nro_ingresos_brutos") or None,
        "fecha_inicio_actividades": _parse_date(request.form.get("fecha_inicio_actividades")),
        "nro_inscripcion_municipal": request.form.get("nro_inscripcion_municipal") or None,
        "regimen_retencion": request.form.get("regimen_retencion") or None,
    }

    if is_edit:
        activo = request.form.get("activo")
        data["activo"] = activo == "true"
    else:
        # Domicilio inicial (opcional)
        calle = request.form.get("dom_calle")
        if calle:
            data["domicilio"] = {
                "calle": calle,
                "numero": request.form.get("dom_numero") or None,
                "piso": request.form.get("dom_piso") or None,
                "departamento": request.form.get("dom_departamento") or None,
                "localidad": request.form.get("dom_localidad") or "",
                "provincia": request.form.get("dom_provincia") or "",
                "pais": request.form.get("dom_pais") or "Argentina",
                "codigo_postal": request.form.get("dom_codigo_postal") or None,
            }

    return data


# ─── AUDITORÍA ────────────────────────────────────────────────────────────────


@administracion_bp.route("/auditoria")
@require_auditoria
def auditoria_list():
    api_request = get_api_request_func()
    token = session.get("token")

    pagina = request.args.get("pagina", 1, type=int)
    buscar_email = request.args.get("buscar_email", "")
    buscar_modulo = request.args.get("buscar_modulo", "")
    buscar_ruta = request.args.get("buscar_ruta", "")
    desde = request.args.get("desde", "")
    hasta = request.args.get("hasta", "")

    params = f"?pagina={pagina}&por_pagina=50"
    if buscar_email:
        params += f"&buscar_email={buscar_email}"
    if buscar_modulo:
        params += f"&buscar_modulo={buscar_modulo}"
    if buscar_ruta:
        params += f"&buscar_ruta={buscar_ruta}"
    if desde:
        params += f"&desde={desde}"
    if hasta:
        params += f"&hasta={hasta}"

    data, _ = api_request("GET", f"/auditoria{params}", token=token)
    items = data.get("items", []) if isinstance(data, dict) else []
    total = data.get("total", 0) if isinstance(data, dict) else 0
    total_paginas = data.get("total_paginas", 1) if isinstance(data, dict) else 1

    ctx = dict(
        items=items,
        total=total,
        pagina=pagina,
        total_paginas=total_paginas,
        buscar_email=buscar_email,
        buscar_modulo=buscar_modulo,
        buscar_ruta=buscar_ruta,
        desde=desde,
        hasta=hasta,
    )

    if request.headers.get("HX-Request"):
        return render_template("administracion/partials/auditoria_table.html", **ctx)

    return render_template("administracion/auditoria_list.html", **ctx)


# ─── Export Recibos por Cliente ───────────────────────────────────────────────

_logger_export = logging.getLogger(__name__)


def _get_recibos_allowed_emails():
    raw = os.getenv("RECIBOS_ADMIN_ALLOWED_EMAILS", "")
    if not raw.strip():
        return []
    return [e.strip().lower() for e in raw.split(",") if e.strip()]


def require_export_recibos(f):
    """
    Doble check para export-recibos: permiso admin_contable.export_recibos
    + email del usuario en RECIBOS_ADMIN_ALLOWED_EMAILS.
    No hay bypass por rol admin — la whitelist es obligatoria para todos.
    """

    @wraps(f)
    def decorated(*args, **kwargs):
        if "token" not in session:
            return respuesta_sin_sesion()

        user = session.get("user", {})
        email = (user.get("email") or "").lower()

        # 1) Whitelist obligatoria (sin bypass por admin)
        allowed = _get_recibos_allowed_emails()
        if not allowed or email not in allowed:
            _logger_export.warning(f"[EXPORT_RECIBOS] Whitelist denegada para {email}")
            if request.headers.get("HX-Request"):
                return (
                    '<div class="p-4 rounded-xl bg-red-50 text-red-800 border border-red-200">No tenés acceso a este módulo</div>',
                    403,
                )
            return _render_template("core/403.html", modulo="administracion/export-recibos"), 403

        # 2) Permiso admin_contable.export_recibos (admin pasa por rol)
        if user.get("rol") != "admin":
            api_request = get_api_request_func()
            token = session.get("token")
            data, status = api_request("GET", "/permisos/mis-permisos", token=token)
            permisos = (data or {}).get("permisos", {}) if isinstance(data, dict) else {}
            if not permisos.get("admin_contable.export_recibos", False):
                if request.headers.get("HX-Request"):
                    return (
                        '<div class="p-4 rounded-xl bg-red-50 text-red-800 border border-red-200">No tenés acceso a este módulo</div>',
                        403,
                    )
                return _render_template("core/403.html", modulo="administracion/export-recibos"), 403

        return f(*args, **kwargs)

    return decorated


@administracion_bp.route("/export-recibos")
@require_export_recibos
def export_recibos_list():
    """Vista agrupada de recibos por cliente y mes para exportar."""
    api_request = get_api_request_func()
    token = session.get("token")
    data, status = api_request("GET", "/administracion/export-recibos/preview", token=token)

    if status != 200 or not isinstance(data, dict):
        flash(format_api_error(data, "No se pudo cargar el listado"), "error")
        data = {"clientes": [], "total_clientes": 0, "total_empleados": 0, "total_recibos": 0}

    return render_template("administracion/export_recibos.html", data=data)


@administracion_bp.route("/export-recibos/descargar")
@require_export_recibos
def export_recibos_descargar():
    """Proxy de descarga del ZIP por (cliente, periodo, tipo). Reenvía Bearer token."""
    import httpx
    from flask import Response, current_app

    cliente = request.args.get("cliente", "").strip()
    periodo = request.args.get("periodo", "").strip()
    tipo_liquidacion = request.args.get("tipo_liquidacion", "").strip()

    if not cliente or not periodo:
        flash("Cliente y periodo son obligatorios", "error")
        return redirect(url_for("administracion.export_recibos_list"))

    token = session.get("token")
    api_url = current_app.config["API_URL"]
    url = f"{api_url}/api/v1/administracion/export-recibos/descargar"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"cliente": cliente, "periodo": periodo}
    if tipo_liquidacion:
        params["tipo_liquidacion"] = tipo_liquidacion

    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.get(url, headers=headers, params=params)
            if response.status_code == 200:
                resp_headers = {
                    "Content-Type": response.headers.get("content-type", "application/zip"),
                }
                cd = response.headers.get("content-disposition")
                if cd:
                    resp_headers["Content-Disposition"] = cd
                return Response(response.content, status=200, headers=resp_headers)
            else:
                detail = "No se pudo generar el ZIP"
                try:
                    detail = response.json().get("detail", detail)
                except Exception:
                    pass
                flash(detail, "error")
                return redirect(url_for("administracion.export_recibos_list"))
    except Exception:
        flash("Error al descargar el ZIP", "error")
        return redirect(url_for("administracion.export_recibos_list"))


@administracion_bp.route("/export-recibos/recibo/<recibo_id>")
@require_export_recibos
def export_recibos_descargar_individual(recibo_id):
    """Proxy de descarga individual de un recibo PDF."""
    import httpx
    from flask import Response, current_app

    token = session.get("token")
    api_url = current_app.config["API_URL"]
    url = f"{api_url}/api/v1/administracion/export-recibos/recibo/{recibo_id}"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.get(url, headers=headers)
            if response.status_code == 200:
                resp_headers = {
                    "Content-Type": response.headers.get("content-type", "application/pdf"),
                }
                cd = response.headers.get("content-disposition")
                if cd:
                    resp_headers["Content-Disposition"] = cd
                return Response(response.content, status=200, headers=resp_headers)
            else:
                detail = "No se pudo descargar el recibo"
                try:
                    detail = response.json().get("detail", detail)
                except Exception:
                    pass
                flash(detail, "error")
                return redirect(url_for("administracion.export_recibos_list"))
    except Exception:
        flash("Error al descargar el recibo", "error")
        return redirect(url_for("administracion.export_recibos_list"))


# Proveedores y su evaluación (F18): rutas en su propio archivo, mismo blueprint
from modulos.administracion import proveedores_routes  # noqa: E402,F401
