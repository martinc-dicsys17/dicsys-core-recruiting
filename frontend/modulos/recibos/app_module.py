"""
Módulo Recibos de Sueldo.

Dos blueprints:
- recibos_admin_bp: Gestión de recibos (admin/RRHH) → /administracion/recibos
- recibos_portal_bp: Mis Recibos (portal empleado) → /recibos
"""

import logging
import os
from functools import wraps

from flask import Blueprint, Response, flash, redirect, render_template, request, session, url_for

from modulos.audit_helpers import registrar_auditoria
from modulos.auth_helpers import get_api_request_func, require_permiso, respuesta_sin_sesion
from modulos.error_helpers import error_html, format_api_error

logger = logging.getLogger(__name__)


def _get_recibos_allowed_emails():
    """Obtiene la lista de emails permitidos para el módulo admin de recibos."""
    raw = os.getenv("RECIBOS_ADMIN_ALLOWED_EMAILS", "")
    if not raw.strip():
        return []
    return [e.strip().lower() for e in raw.split(",") if e.strip()]


def require_recibos_whitelist(f):
    """
    Decorador que verifica login + whitelist de emails para /administracion/recibos.
    No hay bypass por rol — el whitelist es obligatorio para todos.
    Registra auditoría solo cuando el acceso es efectivamente concedido.
    """

    @wraps(f)
    def decorated(*args, **kwargs):
        if "token" not in session:
            return respuesta_sin_sesion()

        allowed = _get_recibos_allowed_emails()
        if not allowed:
            logger.warning("[RECIBOS_WHITELIST] Variable RECIBOS_ADMIN_ALLOWED_EMAILS vacía, acceso denegado")
            if request.headers.get("HX-Request"):
                return (
                    '<div class="p-4 rounded-xl bg-red-50 text-red-800 border border-red-200">No tenés acceso a este módulo</div>',
                    403,
                )
            return render_template("core/403.html", modulo="administracion/recibos"), 403

        user = session.get("user", {})
        email = (user.get("email") or "").lower()
        if email not in allowed:
            logger.warning(f"[RECIBOS_WHITELIST] Acceso denegado para {email}")
            if request.headers.get("HX-Request"):
                return (
                    '<div class="p-4 rounded-xl bg-red-50 text-red-800 border border-red-200">No tenés acceso a este módulo</div>',
                    403,
                )
            return render_template("core/403.html", modulo="administracion/recibos"), 403

        # Acceso concedido → registrar auditoría (solo requests completos, no HTMX parciales)
        if not request.headers.get("HX-Request") and session.get("empresa_id"):
            registrar_auditoria(modulo="administracion/recibos")

        return f(*args, **kwargs)

    return decorated


# ─── Blueprint Admin (RRHH) ──────────────────────────────────────────────────
recibos_admin_bp = Blueprint(
    "administracion_recibos",
    __name__,
    template_folder="../administracion/templates",
    url_prefix="/administracion/recibos",
)
require_admin_recibos = require_recibos_whitelist

# ─── Blueprint Portal (empleado) ─────────────────────────────────────────────
recibos_portal_bp = Blueprint("recibos_portal", __name__, template_folder="templates", url_prefix="/recibos")
require_mis_recibos = require_permiso("recibos.mis_recibos")


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN: Gestión de recibos
# ══════════════════════════════════════════════════════════════════════════════


@recibos_admin_bp.route("")
@require_admin_recibos
def recibos_list():
    api_request = get_api_request_func()
    token = session.get("token")

    pagina = request.args.get("pagina", 1, type=int)
    periodo = request.args.get("periodo", "")
    estado = request.args.get("estado", "")
    tipo_liquidacion = request.args.get("tipo_liquidacion", "")

    params = f"?pagina={pagina}&por_pagina=20"
    if periodo:
        params += f"&periodo={periodo}"
    if estado:
        params += f"&estado={estado}"
    if tipo_liquidacion:
        params += f"&tipo_liquidacion={tipo_liquidacion}"

    data, status = api_request("GET", f"/recibos/lotes{params}", token=token)
    items = data.get("items", []) if isinstance(data, dict) else []
    total = data.get("total", 0) if isinstance(data, dict) else 0
    total_paginas = data.get("total_paginas", 1) if isinstance(data, dict) else 1

    if request.headers.get("HX-Request"):
        return render_template(
            "administracion/partials/recibos_table.html",
            items=items,
            total=total,
            pagina=pagina,
            total_paginas=total_paginas,
            periodo=periodo,
            estado=estado,
            tipo_liquidacion=tipo_liquidacion,
        )

    return render_template(
        "administracion/recibos_list.html",
        items=items,
        total=total,
        pagina=pagina,
        total_paginas=total_paginas,
        periodo=periodo,
        estado=estado,
        tipo_liquidacion=tipo_liquidacion,
    )


@recibos_admin_bp.route("/subir", methods=["GET", "POST"])
@require_admin_recibos
def recibos_upload():
    if request.method == "POST":
        import httpx
        from flask import current_app

        token = session.get("token")
        api_url = current_app.config["API_URL"]

        archivo = request.files.get("archivo")
        periodo = request.form.get("periodo", "").strip()
        tipo_liquidacion = request.form.get("tipo_liquidacion", "").strip()

        if not archivo or not archivo.filename:
            if request.headers.get("HX-Request"):
                return error_html("Debe seleccionar un archivo PDF")
            flash("Debe seleccionar un archivo PDF", "error")
            return render_template("administracion/recibos_upload.html")

        url = f"{api_url}/api/v1/recibos/lotes"
        headers = {"Authorization": f"Bearer {token}"}

        try:
            with httpx.Client(timeout=120.0) as client:
                files = {"archivo": (archivo.filename, archivo.read(), archivo.content_type)}
                form_data = {"periodo": periodo, "tipo_liquidacion": tipo_liquidacion}
                response = client.post(url, headers=headers, files=files, data=form_data)

                if response.status_code in [200, 201]:
                    result = response.json()
                    recibo_id = result.get("id")
                    flash("PDF procesado exitosamente", "success")
                    if request.headers.get("HX-Request"):
                        return "", 200, {"HX-Redirect": url_for("administracion_recibos.recibos_detail", id=recibo_id)}
                    return redirect(url_for("administracion_recibos.recibos_detail", id=recibo_id))
                else:
                    detail = response.json().get("detail", "Error al procesar el PDF")
                    error = format_api_error(detail, "Error al procesar el PDF")
                    if request.headers.get("HX-Request"):
                        return error_html(error)
                    flash(error, "error")
        except Exception as e:
            logger.error(f"Error al subir PDF masivo: {e}", exc_info=True)
            if request.headers.get("HX-Request"):
                return error_html("Error al subir el archivo. Intentá de nuevo.")
            flash("Error al subir el archivo. Intentá de nuevo.", "error")

    return render_template("administracion/recibos_upload.html")


@recibos_admin_bp.route("/<id>")
@require_admin_recibos
def recibos_detail(id):
    api_request = get_api_request_func()
    token = session.get("token")

    data, status = api_request("GET", f"/recibos/lotes/{id}", token=token)
    if status != 200:
        detail = data.get("detail") if isinstance(data, dict) else None
        msg = format_api_error(detail, "No se pudo cargar el lote")
        flash(msg, "error" if status >= 500 else "warning")
        return redirect(url_for("administracion_recibos.recibos_list"))

    pagina = request.args.get("pagina", 1, type=int)
    buscar = request.args.get("buscar", "")
    estado = request.args.get("estado", "")
    params = f"?pagina={pagina}&por_pagina=50"
    if buscar:
        params += f"&buscar={buscar}"
    if estado:
        params += f"&estado={estado}"
    recibos_data, recibos_status = api_request("GET", f"/recibos/lotes/{id}/recibos{params}", token=token)
    if recibos_status != 200:
        flash(
            format_api_error(
                recibos_data.get("detail") if isinstance(recibos_data, dict) else None,
                "No se pudieron cargar los recibos del lote",
            ),
            "warning",
        )
        recibos_data = {}
    recibos = recibos_data.get("items", []) if isinstance(recibos_data, dict) else []
    recibos_total = recibos_data.get("total", 0) if isinstance(recibos_data, dict) else 0
    recibos_total_paginas = recibos_data.get("total_paginas", 1) if isinstance(recibos_data, dict) else 1

    return render_template(
        "administracion/recibos_detail.html",
        lote=data,
        recibos=recibos,
        recibos_total=recibos_total,
        recibos_pagina=pagina,
        recibos_total_paginas=recibos_total_paginas,
        buscar=buscar,
        estado=estado,
    )


@recibos_admin_bp.route("/<id>", methods=["DELETE"])
@require_admin_recibos
def recibos_delete(id):
    api_request = get_api_request_func()
    token = session.get("token")
    result, status = api_request("DELETE", f"/recibos/lotes/{id}", token=token)
    if status == 200:
        return "", 200, {"HX-Trigger": "reciboDeleted"}
    error = format_api_error(result.get("detail") if isinstance(result, dict) else None, "Error al eliminar")
    return error_html(error), 400


@recibos_admin_bp.route("/<id>/descargar-pdf")
@require_admin_recibos
def recibos_descargar_pdf(id):
    import httpx
    from flask import current_app

    token = session.get("token")
    api_url = current_app.config["API_URL"]
    url = f"{api_url}/api/v1/recibos/lotes/{id}/descargar-pdf"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.get(url, headers=headers)
            if response.status_code == 200:
                content_type = response.headers.get("content-type", "application/pdf")
                content_disposition = response.headers.get("content-disposition", "")
                resp_headers = {"Content-Type": content_type}
                if content_disposition:
                    resp_headers["Content-Disposition"] = content_disposition
                return Response(response.content, status=200, headers=resp_headers)
            else:
                flash("No se pudo descargar el archivo", "error")
                return redirect(url_for("administracion_recibos.recibos_detail", id=id))
    except Exception as e:
        logger.error(f"Error al descargar PDF {id}: {e}", exc_info=True)
        flash("Error al descargar el archivo", "error")
        return redirect(url_for("administracion_recibos.recibos_detail", id=id))


@recibos_admin_bp.route("/<id>/reprocesar", methods=["POST"])
@require_admin_recibos
def recibos_reprocesar(id):
    api_request = get_api_request_func()
    token = session.get("token")
    result, status = api_request("POST", f"/recibos/lotes/{id}/reprocesar", token=token)
    if status == 200:
        flash("Reprocesado exitosamente", "success")
        if request.headers.get("HX-Request"):
            return "", 200, {"HX-Redirect": url_for("administracion_recibos.recibos_detail", id=id)}
        return redirect(url_for("administracion_recibos.recibos_detail", id=id))
    error = format_api_error(result.get("detail") if isinstance(result, dict) else None, "Error al reprocesar")
    if request.headers.get("HX-Request"):
        return error_html(error)
    flash(error, "error")
    return redirect(url_for("administracion_recibos.recibos_detail", id=id))


@recibos_admin_bp.route("/<id>/actualizar", methods=["POST"])
@require_admin_recibos
def recibos_actualizar(id):
    import httpx
    from flask import current_app

    token = session.get("token")
    api_url = current_app.config["API_URL"]

    archivo = request.files.get("archivo")
    if not archivo or not archivo.filename:
        msg = "Debe seleccionar un archivo PDF con los recibos a actualizar"
        if request.headers.get("HX-Request"):
            return error_html(msg)
        flash(msg, "error")
        return redirect(url_for("administracion_recibos.recibos_detail", id=id))

    url = f"{api_url}/api/v1/recibos/lotes/{id}/actualizar"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        with httpx.Client(timeout=180.0) as client:
            files = {"archivo": (archivo.filename, archivo.read(), archivo.content_type)}
            response = client.post(url, headers=headers, files=files)

            if response.status_code in (200, 201):
                data = response.json()
                cuils = data.get("cuils_actualizados", []) or []
                eliminados = data.get("recibos_eliminados", 0)
                creados = data.get("recibos_creados", 0)
                flash(
                    f"Actualización completada: {creados} recibo(s) nuevo(s) cargado(s), "
                    f"{eliminados} recibo(s) anterior(es) reemplazado(s) "
                    f"({len(cuils)} CUIL/es: {', '.join(cuils) if cuils else '-'})",
                    "success",
                )
                if request.headers.get("HX-Request"):
                    return "", 200, {"HX-Redirect": url_for("administracion_recibos.recibos_detail", id=id)}
                return redirect(url_for("administracion_recibos.recibos_detail", id=id))
            else:
                detail = None
                try:
                    detail = response.json().get("detail")
                except Exception:
                    detail = response.text
                error = format_api_error(detail, "Error al actualizar los recibos")
                if request.headers.get("HX-Request"):
                    return error_html(error)
                flash(error, "error")
                return redirect(url_for("administracion_recibos.recibos_detail", id=id))
    except Exception as e:
        logger.error(f"Error al actualizar recibos del lote {id}: {e}", exc_info=True)
        msg = "Error al subir el archivo. Intentá de nuevo."
        if request.headers.get("HX-Request"):
            return error_html(msg)
        flash(msg, "error")
        return redirect(url_for("administracion_recibos.recibos_detail", id=id))


@recibos_admin_bp.route("/descargar/<recibo_id>/<tipo>")
@require_admin_recibos
def recibo_descargar(recibo_id, tipo):
    import httpx
    from flask import current_app

    token = session.get("token")
    api_url = current_app.config["API_URL"]
    url = f"{api_url}/api/v1/recibos/admin/descargar/{recibo_id}/{tipo}"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url, headers=headers)
            if response.status_code == 200:
                content_type = response.headers.get("content-type", "application/pdf")
                content_disposition = response.headers.get("content-disposition", "")
                resp_headers = {"Content-Type": content_type}
                if content_disposition:
                    resp_headers["Content-Disposition"] = content_disposition
                return Response(response.content, status=200, headers=resp_headers)
            else:
                flash("No se pudo descargar el archivo", "error")
                return redirect(request.referrer or url_for("administracion_recibos.recibos_list"))
    except Exception as e:
        logger.error(f"Error al descargar recibo {recibo_id}/{tipo}: {e}", exc_info=True)
        flash("Error al descargar el archivo. Intentá de nuevo.", "error")
        return redirect(request.referrer or url_for("administracion_recibos.recibos_list"))


# ══════════════════════════════════════════════════════════════════════════════
# PORTAL: Mis Recibos (empleado)
# ══════════════════════════════════════════════════════════════════════════════


@recibos_portal_bp.route("/mis-recibos")
@require_mis_recibos
def mis_recibos():
    api_request = get_api_request_func()
    token = session.get("token")
    user = session.get("user", {})
    tiene_empleado = bool(user.get("empleado_id"))

    recibos = []
    total = 0
    pagina = request.args.get("pagina", 1, type=int)
    total_paginas = 1

    if tiene_empleado:
        data, status = api_request("GET", f"/recibos/mis-recibos?pagina={pagina}&por_pagina=20", token=token)
        if status == 200 and isinstance(data, dict):
            recibos = data.get("items", [])
            total = data.get("total", 0)
            total_paginas = data.get("total_paginas", 1)
        elif status == 404:
            tiene_empleado = False

    return render_template(
        "recibos/mis_recibos.html",
        recibos=recibos,
        total=total,
        pagina=pagina,
        total_paginas=total_paginas,
        tiene_empleado=tiene_empleado,
    )


@recibos_portal_bp.route("/mis-recibos/descargar/<recibo_id>/<tipo>")
@require_mis_recibos
def mis_recibos_descargar(recibo_id, tipo):
    import httpx
    from flask import current_app

    token = session.get("token")
    api_url = current_app.config["API_URL"]
    url = f"{api_url}/api/v1/recibos/descargar/{recibo_id}/{tipo}"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url, headers=headers)
            if response.status_code == 200:
                content_type = response.headers.get("content-type", "application/pdf")
                content_disposition = response.headers.get("content-disposition", "")
                resp_headers = {"Content-Type": content_type}
                if content_disposition:
                    resp_headers["Content-Disposition"] = content_disposition
                return Response(response.content, status=200, headers=resp_headers)
            else:
                flash("No se pudo descargar el archivo", "error")
                return redirect(url_for("recibos_portal.mis_recibos"))
    except Exception as e:
        logger.error(f"Error al descargar recibo {recibo_id}/{tipo}: {e}", exc_info=True)
        flash("Error al descargar el archivo. Intentá de nuevo.", "error")
        return redirect(url_for("recibos_portal.mis_recibos"))


@recibos_portal_bp.route("/mis-recibos/<recibo_id>/firma-posicion")
@require_mis_recibos
def mis_recibos_firma_posicion(recibo_id):
    """Dónde estampar la firma, calculado por el backend leyendo el PDF.

    En los recibos sin duplicado el bloque de firmas se corre según la cantidad
    de conceptos, así que la posición no se puede hardcodear en el JS.
    """
    import httpx
    from flask import current_app, jsonify

    token = session.get("token")
    api_url = current_app.config["API_URL"]
    url = f"{api_url}/api/v1/recibos/{recibo_id}/firma-posicion"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url, headers=headers)
            if response.status_code == 200:
                return jsonify(response.json())
            logger.warning(f"firma-posicion {recibo_id}: backend respondió {response.status_code}")
    except Exception as e:
        logger.error(f"Error al pedir la posición de firma de {recibo_id}: {e}", exc_info=True)
    # Sin posición el front usa su ubicación por defecto: la firma no se bloquea.
    return jsonify({"posicion": None, "empleado_nombre": None})


@recibos_portal_bp.route("/mis-recibos/<recibo_id>/firmar", methods=["POST"])
@require_mis_recibos
def mis_recibos_firmar(recibo_id):
    import httpx
    from flask import current_app

    token = session.get("token")
    api_url = current_app.config["API_URL"]
    archivo = request.files.get("archivo")
    if not archivo or not archivo.filename:
        if request.headers.get("HX-Request"):
            return error_html("Debe seleccionar un archivo PDF")
        flash("Debe seleccionar un archivo PDF", "error")
        return redirect(url_for("recibos_portal.mis_recibos"))

    url = f"{api_url}/api/v1/recibos/{recibo_id}/firmar"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        with httpx.Client(timeout=60.0) as client:
            files = {"archivo": (archivo.filename, archivo.read(), archivo.content_type)}
            response = client.post(url, headers=headers, files=files)
            if response.status_code in [200, 201]:
                flash("Recibo firmado exitosamente", "success")
                if request.headers.get("HX-Request"):
                    return "", 200, {"HX-Redirect": url_for("recibos_portal.mis_recibos")}
                return redirect(url_for("recibos_portal.mis_recibos"))
            else:
                detail = response.json().get("detail", "Error al firmar el recibo")
                error = format_api_error(detail, "Error al firmar el recibo")
                if request.headers.get("HX-Request"):
                    return error_html(error)
                flash(error, "error")
    except Exception as e:
        logger.error(f"Error al firmar recibo {recibo_id}: {e}", exc_info=True)
        if request.headers.get("HX-Request"):
            return error_html("Error al subir el archivo. Intentá de nuevo.")
        flash("Error al subir el archivo. Intentá de nuevo.", "error")
    return redirect(url_for("recibos_portal.mis_recibos"))


@recibos_portal_bp.route("/mis-recibos/dashboard-partial")
@require_mis_recibos
def mis_recibos_dashboard_partial():
    api_request = get_api_request_func()
    token = session.get("token")
    user = session.get("user", {})

    if not user.get("empleado_id"):
        return '<p class="p-6 text-dark-400 text-sm text-center">No tenés un empleado vinculado</p>'

    data, status = api_request("GET", "/recibos/mis-recibos?pagina=1&por_pagina=5", token=token)
    recibos = data.get("items", []) if status == 200 and isinstance(data, dict) else []

    if not recibos:
        return """<div class="p-8 text-center">
            <i data-lucide="file-text" class="w-8 h-8 text-dark-300 mx-auto mb-2"></i>
            <p class="text-dark-500 text-sm">No tenés recibos de sueldo disponibles</p>
        </div>"""

    html = ['<div class="divide-y divide-dark-100">']
    for r in recibos:
        periodo = r.get("periodo", "-")
        tipo = r.get("tipo_liquidacion", "-")
        estado = r.get("estado", "")
        recibo_id = r.get("id", "")

        if estado == "firmado":
            badge = '<span class="px-2 py-0.5 text-xs font-semibold bg-primary-100 text-primary-700 rounded-lg">Firmado</span>'
        elif estado == "asignado":
            badge = '<span class="px-2 py-0.5 text-xs font-semibold bg-emerald-100 text-emerald-700 rounded-lg">Disponible</span>'
        else:
            badge = (
                '<span class="px-2 py-0.5 text-xs font-semibold bg-dark-100 text-dark-500 rounded-lg">'
                + estado
                + "</span>"
            )

        download_orig = url_for("recibos_portal.mis_recibos_descargar", recibo_id=recibo_id, tipo="original")
        mis_recibos_url = url_for("recibos_portal.mis_recibos")

        # El duplicado es opcional: el recibo puede venir en una sola hoja.
        if r.get("archivo_duplicado"):
            download_dup = url_for("recibos_portal.mis_recibos_descargar", recibo_id=recibo_id, tipo="duplicado")
            dup_btn = f'''<a href="{download_dup}" class="p-1.5 text-dark-400 hover:text-primary-600 hover:bg-primary-50 rounded-lg transition-colors" title="Duplicado">
                    <i data-lucide="copy" class="w-4 h-4"></i>
                </a>'''
        else:
            dup_btn = ""

        if estado != "firmado":
            firma_btn = f'''<a href="{mis_recibos_url}" class="px-2 py-1 text-xs font-semibold bg-primary-50 text-primary-700 hover:bg-primary-100 rounded-lg transition-colors" title="Firmar recibo">
                    <i data-lucide="pen-line" class="w-3.5 h-3.5 inline mr-0.5"></i>Firmar
                </a>'''
        else:
            firma_btn = ""

        html.append(f'''
        <div class="px-6 py-3 flex items-center justify-between hover:bg-dark-50/50 transition-colors">
            <div class="flex items-center gap-4">
                <div class="w-9 h-9 bg-cyan-100 rounded-lg flex items-center justify-center flex-shrink-0">
                    <i data-lucide="file-text" class="w-4 h-4 text-cyan-600"></i>
                </div>
                <div>
                    <p class="font-medium text-dark-900 text-sm">{periodo} — {tipo}</p>
                    {badge}
                </div>
            </div>
            <div class="flex items-center gap-1">
                {firma_btn}
                <a href="{download_orig}" class="p-1.5 text-dark-400 hover:text-primary-600 hover:bg-primary-50 rounded-lg transition-colors" title="Original">
                    <i data-lucide="file-down" class="w-4 h-4"></i>
                </a>
                {dup_btn}
            </div>
        </div>''')

    html.append("</div>")
    return "".join(html)


# ============================================================
# Helpers compartidos: logs y reversión de firma
# ============================================================

ACCION_LABELS = {
    "creacion": ("Creación del recibo", "file-plus", "text-primary-600 bg-primary-50"),
    "firma": ("Firma del recibo", "pen-line", "text-emerald-600 bg-emerald-50"),
    "reversion_firma": ("Reversión de firma", "rotate-ccw", "text-amber-600 bg-amber-50"),
    "descarga_original": ("Descarga (empleado) - Original", "file-down", "text-dark-500 bg-dark-50"),
    "descarga_duplicado": ("Descarga (empleado) - Duplicado", "copy", "text-dark-500 bg-dark-50"),
    "descarga_firmado": ("Descarga (empleado) - Firmado", "file-check-2", "text-dark-500 bg-dark-50"),
    "descarga_admin_original": ("Descarga (admin) - Original", "file-down", "text-dark-500 bg-dark-50"),
    "descarga_admin_duplicado": ("Descarga (admin) - Duplicado", "copy", "text-dark-500 bg-dark-50"),
    "descarga_admin_firmado": ("Descarga (admin) - Firmado", "file-check-2", "text-dark-500 bg-dark-50"),
}


def _render_logs_html(recibo_id, endpoint_api):
    """Devuelve HTML del listado de auditoría para un recibo."""
    api_request = get_api_request_func()
    token = session.get("token")
    data, status = api_request("GET", endpoint_api, token=token)
    if status != 200:
        msg = format_api_error(data, status)
        return error_html(msg)

    logs = data if isinstance(data, list) else []
    if not logs:
        return '<div class="px-6 py-8 text-center text-sm text-dark-500">Sin actividad registrada.</div>'

    out = ['<div class="divide-y divide-dark-100">']
    for log in logs:
        accion = log.get("accion") or ""
        label, icon, color = ACCION_LABELS.get(accion, (accion, "activity", "text-dark-500 bg-dark-50"))
        usuario = log.get("usuario_nombre") or log.get("usuario_email") or "Sistema"
        email = log.get("usuario_email") or ""
        ip = log.get("ip") or ""
        detalle = log.get("detalle") or ""
        fecha = (log.get("created_at") or "").replace("T", " ")[:19]
        out.append(f'''
        <div class="px-5 py-3 flex items-start gap-3">
            <div class="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0 {color}">
                <i data-lucide="{icon}" class="w-4 h-4"></i>
            </div>
            <div class="flex-1 min-w-0">
                <p class="text-sm font-medium text-dark-900">{label}</p>
                <p class="text-xs text-dark-600 mt-0.5">{usuario}{f" &lt;{email}&gt;" if email and email != usuario else ""}</p>
                {f'<p class="text-xs text-dark-500 mt-0.5">{detalle}</p>' if detalle else ""}
                <div class="flex items-center gap-3 mt-1 text-xs text-dark-400">
                    <span><i data-lucide="clock" class="w-3 h-3 inline mr-1"></i>{fecha}</span>
                    {f'<span><i data-lucide="globe" class="w-3 h-3 inline mr-1"></i>{ip}</span>' if ip else ""}
                </div>
            </div>
        </div>''')
    out.append("</div>")
    out.append("<script>if(window.lucide){window.lucide.createIcons();}</script>")
    return "".join(out)


def _revertir_firma_response(recibo_id, endpoint_api):
    """Llama al endpoint de reversión y devuelve respuesta HTMX (HX-Trigger)."""
    api_request = get_api_request_func()
    token = session.get("token")
    data, status = api_request("POST", endpoint_api, token=token)
    if status not in (200, 204):
        msg = format_api_error(data, status)
        flash(msg, "error")
        return error_html(msg), 200
    flash("Firma revertida exitosamente", "success")
    return "", 200, {"HX-Trigger": "firmaRevertida"}


# ============================================================
# Vistas admin (whitelist): logs y reversión de firma
# ============================================================


@recibos_admin_bp.route("/logs/<recibo_id>")
@require_admin_recibos
def recibo_logs_admin(recibo_id):
    return _render_logs_html(recibo_id, f"/recibos/admin/recibos/{recibo_id}/logs")


@recibos_admin_bp.route("/revertir-firma/<recibo_id>", methods=["POST"])
@require_admin_recibos
def revertir_firma_admin(recibo_id):
    return _revertir_firma_response(recibo_id, f"/recibos/admin/recibos/{recibo_id}/revertir-firma")


# ============================================================
# Blueprint Nómina: recibos de empleado (permiso nomina.empleados)
# ============================================================

recibos_nomina_bp = Blueprint(
    "recibos_nomina",
    __name__,
    template_folder="../nomina/templates",
    url_prefix="/nomina/recibos",
)


@recibos_nomina_bp.route("/empleado/<empleado_id>/partial")
@require_permiso("nomina.empleados")
def empleado_recibos_partial(empleado_id):
    api_request = get_api_request_func()
    token = session.get("token")
    pagina = request.args.get("pagina", 1, type=int)
    data, status = api_request(
        "GET",
        f"/recibos/empleado/{empleado_id}?pagina={pagina}&por_pagina=20",
        token=token,
    )
    recibos = data.get("items", []) if isinstance(data, dict) else []
    total = data.get("total", 0) if isinstance(data, dict) else 0
    total_paginas = data.get("total_paginas", 1) if isinstance(data, dict) else 1
    return render_template(
        "nomina/partials/recibos_empleado.html",
        recibos=recibos,
        total=total,
        pagina=pagina,
        total_paginas=total_paginas,
        empleado_id=empleado_id,
    )


@recibos_nomina_bp.route("/logs/<recibo_id>")
@require_permiso("nomina.empleados")
def recibo_logs(recibo_id):
    return _render_logs_html(recibo_id, f"/recibos/nomina/recibos/{recibo_id}/logs")


@recibos_nomina_bp.route("/revertir-firma/<recibo_id>", methods=["POST"])
@require_permiso("nomina.empleados")
def revertir_firma(recibo_id):
    return _revertir_firma_response(recibo_id, f"/recibos/nomina/recibos/{recibo_id}/revertir-firma")
