"""
Módulo Innovación - Resumen, Mi Path, Administración y Gestión de Licencias
"""

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for

from modulos.auth_helpers import get_api_request_func, require_permiso
from modulos.error_helpers import error_html, format_api_error

innovacion_bp = Blueprint("innovacion", __name__, template_folder="templates", url_prefix="/innovacion")


def parse_date(date_str):
    """Convierte dd/mm/yyyy o yyyy-mm-dd a yyyy-mm-dd para el backend."""
    if not date_str:
        return None
    try:
        from datetime import datetime as dt

        # Intentar dd/mm/yyyy
        if "/" in date_str:
            parsed = dt.strptime(date_str, "%d/%m/%Y")
            return parsed.strftime("%Y-%m-%d")
        # Ya viene como yyyy-mm-dd (input type=date)
        dt.strptime(date_str, "%Y-%m-%d")
        return date_str
    except ValueError:
        return None


# === RESUMEN (Dashboard) ===
@innovacion_bp.route("/resumen")
@require_permiso("innovacion.resumen")
def resumen():
    api_request = get_api_request_func()
    token = session.get("token")
    data, _ = api_request("GET", "/innovacion/resumen", token=token)
    return render_template("innovacion/resumen.html", resumen=data or {})


@innovacion_bp.route("/asistentes-eventos")
@require_permiso("innovacion.resumen")
def asistentes_eventos():
    """Vista de asistentes con mayor participación en eventos."""
    from urllib.parse import urlencode

    api_request = get_api_request_func()
    token = session.get("token")
    buscar = request.args.get("buscar", "")
    equipo_id = request.args.get("equipo_id", "")
    evento_id = request.args.get("evento_id", "")
    sin_participacion = request.args.get("sin_participacion", "")
    agrupar_equipo = request.args.get("agrupar_equipo", "")
    pagina = request.args.get("pagina", 1, type=int)
    # Tag por defecto: Track#1 cuando no viene el parámetro en la URL.
    # Si llega vacío ('') es porque el usuario eligió "Todos los tags".
    TAG_DEFAULT = "Track#1"
    tag = request.args.get("tag", None)
    if tag is None:
        tag = TAG_DEFAULT

    params = {
        "pagina": pagina,
        "por_pagina": 50,
    }
    if buscar:
        params["buscar"] = buscar
    if equipo_id:
        params["equipo_id"] = equipo_id
    if evento_id:
        params["evento_id"] = evento_id
    if sin_participacion:
        params["sin_participacion"] = "true"
    if tag:
        params["tag"] = tag

    data, _ = api_request("GET", f"/innovacion/eventos/asistentes-ranking?{urlencode(params)}", token=token)
    items = data.get("items", []) if isinstance(data, dict) else []
    total = data.get("total", 0) if isinstance(data, dict) else 0
    total_paginas = data.get("total_paginas", 1) if isinstance(data, dict) else 1
    resumen_data, _ = api_request("GET", "/innovacion/resumen", token=token)
    equipos = resumen_data.get("por_equipo", []) if isinstance(resumen_data, dict) else []
    equipos = [eq for eq in equipos if eq.get("id")]
    equipos.append({"id": "__sin_equipo__", "nombre": "Sin Equipo"})
    eventos_data, _ = api_request("GET", "/innovacion/eventos/opciones", token=token)
    eventos = eventos_data if isinstance(eventos_data, list) else []
    tags_data, _ = api_request("GET", "/innovacion/eventos/tags-opciones", token=token)
    tags = tags_data if isinstance(tags_data, list) else []
    agrupado = None
    if agrupar_equipo:
        params_grupo = {}
        if buscar:
            params_grupo["buscar"] = buscar
        if equipo_id:
            params_grupo["equipo_id"] = equipo_id
        if evento_id:
            params_grupo["evento_id"] = evento_id
        if tag:
            params_grupo["tag"] = tag
        query = f"?{urlencode(params_grupo)}" if params_grupo else ""
        agrupado, _ = api_request("GET", f"/innovacion/eventos/asistentes-por-equipo{query}", token=token)
        agrupado = agrupado if isinstance(agrupado, dict) else None

    return render_template(
        "innovacion/asistentes_eventos.html",
        items=items,
        total=total,
        pagina=pagina,
        total_paginas=total_paginas,
        buscar=buscar,
        equipos=equipos,
        filtro_equipo=equipo_id,
        eventos=eventos,
        filtro_evento=evento_id,
        tags=tags,
        filtro_tag=tag,
        sin_participacion=bool(sin_participacion),
        agrupar_equipo=bool(agrupar_equipo),
        agrupado=agrupado,
    )


# === MI PATH DE CERTIFICACIÓN ===
@innovacion_bp.route("/mi-path")
@require_permiso("innovacion.mi_path")
def mi_path():
    api_request = get_api_request_func()
    token = session.get("token")
    user_data = session.get("user", {})
    empleado_id = user_data.get("empleado_id")
    tiene_empleado = bool(empleado_id)

    cert = None
    tipos = []
    mis_eventos = []

    if tiene_empleado:
        cert_data, status = api_request("GET", "/innovacion/certificaciones/mi-path", token=token)
        # Si la API devuelve error (ej: 404 con detail), tratar como sin cert
        if status == 200 and isinstance(cert_data, dict) and "detail" not in cert_data:
            cert = cert_data
        tipos, _ = api_request("GET", "/innovacion/tipos", token=token)
        mis_eventos, _ = api_request("GET", "/innovacion/eventos/mis-eventos", token=token)
        tipos = tipos or []
        mis_eventos = mis_eventos or []

    return render_template(
        "innovacion/mi_path.html", cert=cert, tipos=tipos, mis_eventos=mis_eventos, tiene_empleado=tiene_empleado
    )


@innovacion_bp.route("/mi-path/iniciar", methods=["POST"])
@require_permiso("innovacion.mi_path")
def mi_path_iniciar():
    api_request = get_api_request_func()
    token = session.get("token")
    data = {
        "tipo_certificacion": request.form.get("tipo_certificacion"),
    }
    result, status = api_request("POST", "/innovacion/certificaciones", data, token=token)
    if status in [200, 201]:
        flash("Path de certificación iniciado", "success")
        if request.headers.get("HX-Request"):
            return "", 200, {"HX-Redirect": url_for("innovacion.mi_path")}
        return redirect(url_for("innovacion.mi_path"))
    err = format_api_error(result.get("detail"), "Error al iniciar path")
    if request.headers.get("HX-Request"):
        return error_html(err)
    flash(err, "error")
    return redirect(url_for("innovacion.mi_path"))


@innovacion_bp.route("/mi-path/volver-edicion", methods=["POST"])
@require_permiso("innovacion.mi_path")
def mi_path_volver_edicion():
    api_request = get_api_request_func()
    token = session.get("token")
    result, status = api_request("POST", "/innovacion/certificaciones/mi-path/volver-edicion", {}, token=token)
    if status == 200:
        flash("Path reabierto para edición", "success")
        if request.headers.get("HX-Request"):
            return "", 200, {"HX-Redirect": url_for("innovacion.mi_path")}
        return redirect(url_for("innovacion.mi_path"))
    err = format_api_error(result.get("detail"), "No se pudo volver a edición")
    if request.headers.get("HX-Request"):
        return error_html(err)
    flash(err, "error")
    return redirect(url_for("innovacion.mi_path"))


@innovacion_bp.route("/mi-path/<id>/actualizar", methods=["POST"])
@require_permiso("innovacion.mi_path")
def mi_path_actualizar(id):
    api_request = get_api_request_func()
    token = session.get("token")

    # Recoger tecnologías como lista desde el form
    tecnologias_raw = request.form.get("tecnologias", "")
    tecnologias = [t.strip() for t in tecnologias_raw.split(",") if t.strip()] if tecnologias_raw else []

    # Parsear fechas dd/mm/yyyy -> yyyy-mm-dd
    fecha_presentacion = parse_date(request.form.get("fecha_presentacion"))

    data = {
        "titulo": request.form.get("titulo") or None,
        "descripcion": request.form.get("descripcion") or None,
        "repo_presentacion": request.form.get("repo_presentacion") or None,
        "repo_demo": request.form.get("repo_demo") or None,
        "tematica": request.form.get("tematica") or None,
        "tecnologias": tecnologias if tecnologias else None,
        "fecha_presentacion": fecha_presentacion,
        # Training: origen y fechas
        "cert_noncode_origen": request.form.get("cert_noncode_origen") or None,
        "cert_noncode_fecha": parse_date(request.form.get("cert_noncode_fecha")),
        "cert_n8n_origen": request.form.get("cert_n8n_origen") or None,
        "cert_n8n_fecha": parse_date(request.form.get("cert_n8n_fecha")),
        "cert_ruta1_fecha": parse_date(request.form.get("cert_ruta1_fecha")),
        "cert_ruta2_fecha": parse_date(request.form.get("cert_ruta2_fecha")),
        "cert_ruta3_fecha": parse_date(request.form.get("cert_ruta3_fecha")),
    }

    # Guardado de borrador (Siguiente/Guardar del wizard): persiste sin finalizar
    # ni redirigir, para que el wizard mantenga su posición.
    es_borrador = bool(request.form.get("_stay"))

    # Usar endpoint self-service (sin estado ni fecha_aprobacion)
    endpoint = "/innovacion/certificaciones/mi-path"
    if es_borrador:
        endpoint += "?finalizar=false"
    result, status = api_request("PUT", endpoint, data, token=token)
    if status == 200:
        if es_borrador:
            return "", 204
        flash("Path actualizado correctamente", "success")
        if request.headers.get("HX-Request"):
            return "", 200, {"HX-Redirect": url_for("innovacion.mi_path")}
        return redirect(url_for("innovacion.mi_path"))
    err = format_api_error(result.get("detail"), "Error al actualizar")
    if es_borrador:
        return err, 422
    if request.headers.get("HX-Request"):
        return error_html(err)
    flash(err, "error")
    return redirect(url_for("innovacion.mi_path"))


# === UPLOAD / DELETE CERTIFICADOS TRAINING ===
CAMPOS_CERT_VALIDOS = {
    "cert_noncode_imagen",
    "cert_n8n_imagen",
    "cert_ruta1_imagen",
    "cert_ruta2_imagen",
    "cert_ruta3_imagen",
    "cert_noncode_plan",
    "cert_n8n_plan",
}
# Campos de plan de estudio usan estilo amber en vez de emerald
CAMPOS_PLAN = {"cert_noncode_plan", "cert_n8n_plan"}


@innovacion_bp.route("/mi-path/certificado/<campo>/upload", methods=["POST"])
@require_permiso("innovacion.mi_path")
def mi_path_cert_upload(campo):
    """Sube una imagen de certificado via multipart al backend."""
    import httpx
    from flask import current_app

    if campo not in CAMPOS_CERT_VALIDOS:
        return (
            '<div class="p-3 rounded-xl bg-red-50 text-red-800 border border-red-200 text-sm">Campo inválido</div>',
            400,
        )

    token = session.get("token")
    archivo = request.files.get("archivo")

    if not archivo:
        return (
            '<div class="p-3 rounded-xl bg-red-50 text-red-800 border border-red-200 text-sm">No se seleccionó ningún archivo</div>',
            400,
        )

    api_url = current_app.config["API_URL"]
    url = f"{api_url}/api/v1/innovacion/certificaciones/mi-path/certificado/{campo}"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        with httpx.Client(timeout=30.0) as client:
            files = {"archivo": (archivo.filename, archivo.read(), archivo.content_type)}
            response = client.post(url, headers=headers, files=files)

            if response.status_code == 200:
                data = response.json()
                imagen_url = data.get("url", "")
                fecha_auto = data.get("fecha_auto")
                is_pdf = imagen_url.lower().endswith(".pdf")
                is_plan = campo in CAMPOS_PLAN
                # Planes y certificados con archivo subido → emerald (verde)
                # La distinción amber solo aplica al estado vacío (sin archivo)
                border_color = "emerald-200"
                bg_color = "emerald-50"
                icon_color = "emerald-600"
                alt_text = "Plan de Estudio" if is_plan else "Certificado"
                btn_color = "primary-600 bg-primary-50 border border-primary-200 hover:bg-primary-100"
                delete_label = "Eliminar este plan de estudio" if is_plan else "Eliminar este certificado"
                # Si el backend auto-seteó la fecha, generar script para actualizar el input
                fecha_script = ""
                if fecha_auto:
                    from datetime import date

                    hoy = date.today().isoformat()
                    campo_fecha = fecha_auto  # ej: cert_noncode_fecha
                    fecha_script = f'''<script>
                        var fechaInput = document.querySelector('input[name="{campo_fecha}"]');
                        if (fechaInput && !fechaInput.value) fechaInput.value = '{hoy}';
                    </script>'''

                if is_pdf:
                    preview_html = f"""<div class="w-full h-full flex flex-col items-center justify-center text-{icon_color}">
                            <i data-lucide="file-text" class="w-10 h-10 mb-1"></i>
                            <span class="text-xs font-medium">PDF</span>
                        </div>"""
                else:
                    preview_html = f'<img src="{imagen_url}" alt="{alt_text}" class="w-full h-full object-contain group-hover/img:scale-105 transition-transform duration-200">'

                return f'''
                <div id="{campo}-container" class="flex flex-col items-center gap-2">
                    <div class="w-full h-32 rounded-xl overflow-hidden border-2 border-{border_color} bg-{bg_color} relative cursor-pointer group/img"
                         @click="lightboxSrc = '{imagen_url}'; lightboxAlt = '{alt_text}'; lightboxIsPdf = {"true" if is_pdf else "false"}; lightboxOpen = true">
                        {preview_html}
                        <div class="absolute inset-0 bg-dark-900/0 group-hover/img:bg-dark-900/10 transition-colors flex items-center justify-center">
                            <i data-lucide="maximize-2" class="w-5 h-5 text-white opacity-0 group-hover/img:opacity-100 transition-opacity drop-shadow-lg"></i>
                        </div>
                    </div>
                    <div class="flex gap-2">
                        <label class="flex items-center px-3 py-1.5 text-xs font-medium text-{btn_color} rounded-lg transition-colors cursor-pointer">
                            <i data-lucide="upload" class="w-3 h-3 mr-1"></i>Cambiar
                            <input type="file" name="archivo" accept=".jpg,.jpeg,.png,.webp,.pdf" class="hidden"
                                   hx-post="/innovacion/mi-path/certificado/{campo}/upload"
                                   hx-target="#{campo}-container"
                                   hx-swap="outerHTML"
                                   hx-encoding="multipart/form-data"
                                   hx-trigger="change">
                        </label>
                        <button type="button"
                                hx-delete="/innovacion/mi-path/certificado/{campo}/delete"
                                hx-target="#{campo}-container"
                                hx-swap="outerHTML"
                                hx-confirm="¿{delete_label}?"
                                class="flex items-center px-3 py-1.5 text-xs font-medium text-red-600 bg-red-50 border border-red-200 rounded-lg hover:bg-red-100 transition-colors">
                            <i data-lucide="trash-2" class="w-3 h-3 mr-1"></i>Eliminar
                        </button>
                    </div>
                </div>
                <script>
                    lucide.createIcons();
                    (function() {{
                        var container = document.getElementById('{campo}-container');
                        if (container) {{
                            var scope = container.closest('[x-data]');
                            if (scope && typeof Alpine !== 'undefined') Alpine.$data(scope).{campo} = true;
                        }}
                    }})();
                </script>
                {fecha_script}
                '''
            else:
                # Intentar obtener el detalle del error
                try:
                    error_data = response.json()
                    detail = error_data.get("detail", f"Error al subir certificado (HTTP {response.status_code})")
                except Exception:
                    detail = f"Error al subir certificado (HTTP {response.status_code}): {response.text[:200]}"

                # Log para debugging
                import logging

                logging.getLogger(__name__).error(f"Error upload {campo}: {response.status_code} - {response.text}")

                # Mantener el input de archivo para poder reintentar
                is_plan = campo in CAMPOS_PLAN
                if is_plan:
                    return (
                        f'''
                    <div id="{campo}-container" class="flex flex-col items-center gap-2">
                        <div class="w-full h-24 rounded-xl overflow-hidden border-2 border-dashed border-amber-300 bg-amber-50 flex items-center justify-center">
                            <i data-lucide="file-text" class="w-8 h-8 text-amber-300"></i>
                        </div>
                        <div class="p-3 rounded-xl bg-red-50 text-red-800 border border-red-200 text-sm w-full">{detail}</div>
                        <label class="flex items-center px-3 py-1.5 text-xs font-medium text-amber-700 bg-amber-100 border border-amber-300 rounded-lg hover:bg-amber-200 transition-colors cursor-pointer">
                            <i data-lucide="upload" class="w-3 h-3 mr-1"></i>Subir plan de estudio
                            <input type="file" name="archivo" accept=".jpg,.jpeg,.png,.webp,.pdf" class="hidden"
                                   hx-post="/innovacion/mi-path/certificado/{campo}/upload"
                                   hx-target="#{campo}-container"
                                   hx-swap="outerHTML"
                                   hx-encoding="multipart/form-data"
                                   hx-trigger="change">
                        </label>
                        <p class="text-xs text-amber-500">JPG, PNG, WebP o PDF. Máx 5MB</p>
                    </div>
                    <script>lucide.createIcons();</script>
                    ''',
                        response.status_code,
                    )
                else:
                    return (
                        f'''
                    <div id="{campo}-container" class="flex flex-col items-center gap-2">
                        <div class="w-full h-32 rounded-xl overflow-hidden border-2 border-dashed border-dark-300 bg-dark-50 flex items-center justify-center">
                            <i data-lucide="image" class="w-8 h-8 text-dark-300"></i>
                        </div>
                        <div class="p-3 rounded-xl bg-red-50 text-red-800 border border-red-200 text-sm w-full">{detail}</div>
                        <label class="flex items-center px-3 py-1.5 text-xs font-medium text-primary-600 bg-primary-50 border border-primary-200 rounded-lg hover:bg-primary-100 transition-colors cursor-pointer">
                            <i data-lucide="upload" class="w-3 h-3 mr-1"></i>Subir certificado
                            <input type="file" name="archivo" accept=".jpg,.jpeg,.png,.webp,.pdf" class="hidden"
                                   hx-post="/innovacion/mi-path/certificado/{campo}/upload"
                                   hx-target="#{campo}-container"
                                   hx-swap="outerHTML"
                                   hx-encoding="multipart/form-data"
                                   hx-trigger="change">
                        </label>
                        <p class="text-xs text-dark-400">JPG, PNG, WebP o PDF. Máx 5MB</p>
                    </div>
                    <script>lucide.createIcons();</script>
                    ''',
                        response.status_code,
                    )
    except Exception as e:
        import traceback

        traceback.print_exc()
        error_msg = str(e)
        # Mantener el input de archivo para poder reintentar
        is_plan = campo in CAMPOS_PLAN
        if is_plan:
            return (
                f'''
            <div id="{campo}-container" class="flex flex-col items-center gap-2">
                <div class="w-full h-24 rounded-xl overflow-hidden border-2 border-dashed border-amber-300 bg-amber-50 flex items-center justify-center">
                    <i data-lucide="file-text" class="w-8 h-8 text-amber-300"></i>
                </div>
                <div class="p-3 rounded-xl bg-red-50 text-red-800 border border-red-200 text-sm w-full">Error: {error_msg}</div>
                <label class="flex items-center px-3 py-1.5 text-xs font-medium text-amber-700 bg-amber-100 border border-amber-300 rounded-lg hover:bg-amber-200 transition-colors cursor-pointer">
                    <i data-lucide="upload" class="w-3 h-3 mr-1"></i>Subir plan de estudio
                    <input type="file" name="archivo" accept=".jpg,.jpeg,.png,.webp,.pdf" class="hidden"
                           hx-post="/innovacion/mi-path/certificado/{campo}/upload"
                           hx-target="#{campo}-container"
                           hx-swap="outerHTML"
                           hx-encoding="multipart/form-data"
                           hx-trigger="change">
                </label>
                <p class="text-xs text-amber-500">JPG, PNG, WebP o PDF. Máx 5MB</p>
            </div>
            <script>lucide.createIcons();</script>
            ''',
                500,
            )
        else:
            return (
                f'''
            <div id="{campo}-container" class="flex flex-col items-center gap-2">
                <div class="w-full h-32 rounded-xl overflow-hidden border-2 border-dashed border-dark-300 bg-dark-50 flex items-center justify-center">
                    <i data-lucide="image" class="w-8 h-8 text-dark-300"></i>
                </div>
                <div class="p-3 rounded-xl bg-red-50 text-red-800 border border-red-200 text-sm w-full">Error: {error_msg}</div>
                <label class="flex items-center px-3 py-1.5 text-xs font-medium text-primary-600 bg-primary-50 border border-primary-200 rounded-lg hover:bg-primary-100 transition-colors cursor-pointer">
                    <i data-lucide="upload" class="w-3 h-3 mr-1"></i>Subir certificado
                    <input type="file" name="archivo" accept=".jpg,.jpeg,.png,.webp,.pdf" class="hidden"
                           hx-post="/innovacion/mi-path/certificado/{campo}/upload"
                           hx-target="#{campo}-container"
                           hx-swap="outerHTML"
                           hx-encoding="multipart/form-data"
                           hx-trigger="change">
                </label>
                <p class="text-xs text-dark-400">JPG, PNG, WebP o PDF. Máx 5MB</p>
            </div>
            <script>lucide.createIcons();</script>
            ''',
                500,
            )


@innovacion_bp.route("/mi-path/certificado/<campo>/delete", methods=["DELETE"])
@require_permiso("innovacion.mi_path")
def mi_path_cert_delete(campo):
    """Elimina una imagen de certificado."""
    import httpx
    from flask import current_app

    if campo not in CAMPOS_CERT_VALIDOS:
        return (
            '<div class="p-3 rounded-xl bg-red-50 text-red-800 border border-red-200 text-sm">Campo inválido</div>',
            400,
        )

    token = session.get("token")
    api_url = current_app.config["API_URL"]
    url = f"{api_url}/api/v1/innovacion/certificaciones/mi-path/certificado/{campo}"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.delete(url, headers=headers)

            if response.status_code == 200:
                is_plan = campo in CAMPOS_PLAN
                if is_plan:
                    # Estilo amber para plan de estudio vacío
                    return f'''
                    <div id="{campo}-container" class="flex flex-col items-center gap-2">
                        <div class="w-full h-24 rounded-xl overflow-hidden border-2 border-dashed border-amber-300 bg-amber-50 flex items-center justify-center">
                            <i data-lucide="file-text" class="w-8 h-8 text-amber-300"></i>
                        </div>
                        <label class="flex items-center px-3 py-1.5 text-xs font-medium text-amber-700 bg-amber-100 border border-amber-300 rounded-lg hover:bg-amber-200 transition-colors cursor-pointer">
                            <i data-lucide="upload" class="w-3 h-3 mr-1"></i>Subir plan de estudio
                            <input type="file" name="archivo" accept=".jpg,.jpeg,.png,.webp,.pdf" class="hidden"
                                   hx-post="/innovacion/mi-path/certificado/{campo}/upload"
                                   hx-target="#{campo}-container"
                                   hx-swap="outerHTML"
                                   hx-encoding="multipart/form-data"
                                   hx-trigger="change">
                        </label>
                        <p class="text-xs text-amber-500">JPG, PNG, WebP o PDF. Máx 5MB</p>
                    </div>
                    <script>
                        lucide.createIcons();
                        (function() {{
                            var container = document.getElementById('{campo}-container');
                            if (container) {{
                                var scope = container.closest('[x-data]');
                                if (scope && typeof Alpine !== 'undefined') Alpine.$data(scope).{campo} = false;
                            }}
                        }})();
                    </script>
                    '''
                else:
                    return f'''
                    <div id="{campo}-container" class="flex flex-col items-center gap-2">
                        <div class="w-full h-32 rounded-xl overflow-hidden border-2 border-dashed border-dark-300 bg-dark-50 flex items-center justify-center">
                            <i data-lucide="image" class="w-8 h-8 text-dark-300"></i>
                        </div>
                        <label class="flex items-center px-3 py-1.5 text-xs font-medium text-primary-600 bg-primary-50 border border-primary-200 rounded-lg hover:bg-primary-100 transition-colors cursor-pointer">
                            <i data-lucide="upload" class="w-3 h-3 mr-1"></i>Subir certificado
                            <input type="file" name="archivo" accept=".jpg,.jpeg,.png,.webp,.pdf" class="hidden"
                                   hx-post="/innovacion/mi-path/certificado/{campo}/upload"
                                   hx-target="#{campo}-container"
                                   hx-swap="outerHTML"
                                   hx-encoding="multipart/form-data"
                                   hx-trigger="change">
                        </label>
                        <p class="text-xs text-dark-400">JPG, PNG, WebP o PDF. Máx 5MB</p>
                    </div>
                    <script>
                        lucide.createIcons();
                        (function() {{
                            var container = document.getElementById('{campo}-container');
                            if (container) {{
                                var scope = container.closest('[x-data]');
                                if (scope && typeof Alpine !== 'undefined') Alpine.$data(scope).{campo} = false;
                            }}
                        }})();
                    </script>
                    '''
            else:
                detail = response.json().get("detail", "Error al eliminar certificado")
                return (
                    f'<div class="p-3 rounded-xl bg-red-50 text-red-800 border border-red-200 text-sm">{detail}</div>',
                    400,
                )
    except Exception as e:
        import traceback

        traceback.print_exc()
        return (
            f'<div class="p-3 rounded-xl bg-red-50 text-red-800 border border-red-200 text-sm">Error al eliminar el certificado: {str(e)}</div>',
            500,
        )


# === ADMINISTRACIÓN: CRUD de Certificaciones ===
@innovacion_bp.route("/admin")
@require_permiso("innovacion.admin_certificaciones")
def admin_list():
    api_request = get_api_request_func()
    token = session.get("token")
    buscar = request.args.get("buscar", "")
    estado = request.args.get("estado", "")
    tipo = request.args.get("tipo_certificacion", "")
    pagina = request.args.get("pagina", 1, type=int)

    params = f"?pagina={pagina}&por_pagina=20"
    if buscar:
        params += f"&buscar={buscar}"
    if estado:
        params += f"&estado={estado}"
    if tipo:
        params += f"&tipo_certificacion={tipo}"

    data, _ = api_request("GET", f"/innovacion/certificaciones{params}", token=token)
    items = data.get("items", []) if isinstance(data, dict) else []
    total = data.get("total", 0) if isinstance(data, dict) else 0
    total_paginas = data.get("total_paginas", 1) if isinstance(data, dict) else 1

    tipos, _ = api_request("GET", "/innovacion/tipos", token=token)

    if request.headers.get("HX-Request"):
        return render_template(
            "innovacion/partials/admin_table.html",
            items=items,
            total=total,
            pagina=pagina,
            total_paginas=total_paginas,
            buscar=buscar,
            filtro_estado=estado,
            filtro_tipo=tipo,
        )

    return render_template(
        "innovacion/admin_list.html",
        items=items,
        total=total,
        pagina=pagina,
        total_paginas=total_paginas,
        buscar=buscar,
        tipos=tipos or [],
        filtro_estado=estado,
        filtro_tipo=tipo,
    )


@innovacion_bp.route("/cards")
@require_permiso("innovacion.resumen")
def cards():
    """Vista de cards de certificaciones filtrada por estado."""
    api_request = get_api_request_func()
    token = session.get("token")
    estado = request.args.get("estado", "")
    tipo = request.args.get("tipo_certificacion", "")
    equipo_id = request.args.get("equipo_id", "")
    sin_equipo = request.args.get("sin_equipo", "")
    buscar = request.args.get("buscar", "")
    pagina = request.args.get("pagina", 1, type=int)

    params = f"?pagina={pagina}&por_pagina=50"
    if estado:
        params += f"&estado={estado}"
    if tipo:
        params += f"&tipo_certificacion={tipo}"
    if equipo_id:
        params += f"&equipo_id={equipo_id}"
    if sin_equipo:
        params += "&sin_equipo=true"
    if buscar:
        params += f"&buscar={buscar}"

    data, _ = api_request("GET", f"/innovacion/certificaciones{params}", token=token)
    items = data.get("items", []) if isinstance(data, dict) else []
    total = data.get("total", 0) if isinstance(data, dict) else 0
    total_paginas = data.get("total_paginas", 1) if isinstance(data, dict) else 1

    # Cargar equipos para el filtro
    equipos_data, _ = api_request("GET", "/operaciones/equipos?por_pagina=100&activo=true", token=token)
    equipos = equipos_data.get("items", []) if isinstance(equipos_data, dict) else []

    # Cargar tipos de certificación para el filtro
    tipos_data, _ = api_request("GET", "/innovacion/tipos", token=token)
    tipos_cert = tipos_data if isinstance(tipos_data, list) else []

    estado_labels = {
        "iniciado": "Registrados",
        "en_progreso": "En Progreso",
        "en_revision": "En Revisión",
        "en_progreso,en_revision": "En Progreso",
        "completada": "Aprobados",
        "": "Todas las Certificaciones",
    }

    return render_template(
        "innovacion/admin_cards.html",
        items=items,
        total=total,
        pagina=pagina,
        total_paginas=total_paginas,
        filtro_estado=estado,
        filtro_tipo=tipo,
        filtro_equipo=equipo_id,
        buscar=buscar,
        equipos=equipos,
        tipos_cert=tipos_cert,
        titulo_filtro=estado_labels.get(estado, "Certificaciones"),
    )


@innovacion_bp.route("/profile/<id>")
@require_permiso("innovacion.resumen")
def profile(id):
    """Vista de perfil de logros de un empleado (read-only).

    `id` puede ser un id de EMPLEADO (links del listado de asistentes) o de
    CERTIFICACIÓN (links del admin). Se intenta primero por empleado y, si no
    existe, se cae al perfil por certificación.
    """
    api_request = get_api_request_func()
    token = session.get("token")
    data, status = api_request("GET", f"/innovacion/empleados/{id}/perfil-logros", token=token)
    if status != 200 or not data:
        data, status = api_request("GET", f"/innovacion/certificaciones/{id}/perfil-logros", token=token)
    if status != 200 or not data:
        flash("No se pudo obtener el perfil de logros", "error")
        return redirect(url_for("innovacion.admin_list"))
    return render_template(
        "innovacion/admin_logros.html",
        empleado=data.get("empleado", {}),
        equipos=data.get("equipos", []),
        cert=data.get("cert", {}),
        campos_requeridos=data.get("campos_requeridos", []),
        eventos=data.get("eventos", []),
    )


@innovacion_bp.route("/admin/<id>/editar", methods=["GET", "POST"])
@require_permiso("innovacion.admin_certificaciones")
def admin_edit(id):
    api_request = get_api_request_func()
    token = session.get("token")

    if request.method == "POST":
        data = {
            "titulo": request.form.get("titulo") or None,
            "descripcion": request.form.get("descripcion") or None,
            "estado": request.form.get("estado") or None,
            "fecha_aprobacion": parse_date(request.form.get("fecha_aprobacion")),
            "enviar_notificacion_webex": bool(request.form.get("enviar_notificacion_webex")),
        }
        result, status = api_request("PUT", f"/innovacion/certificaciones/{id}", data, token=token)
        if status == 200:
            flash("Certificación actualizada", "success")
            if request.headers.get("HX-Request"):
                return "", 200, {"HX-Redirect": url_for("innovacion.admin_list")}
            return redirect(url_for("innovacion.admin_list"))
        err = format_api_error(result.get("detail"), "Error al actualizar")
        if request.headers.get("HX-Request"):
            return error_html(err)
        flash(err, "error")

    item, _ = api_request("GET", f"/innovacion/certificaciones/{id}", token=token)
    return render_template("innovacion/admin_form.html", item=item)


@innovacion_bp.route("/admin/<id>/eliminar", methods=["DELETE"])
@require_permiso("innovacion.admin_certificaciones")
def admin_delete(id):
    api_request = get_api_request_func()
    token = session.get("token")
    result, status = api_request("DELETE", f"/innovacion/certificaciones/{id}", token=token)
    if status == 200:
        return "", 200, {"HX-Trigger": "certificacionDeleted"}
    return error_html(result.get("detail"), "Error al eliminar"), 400


# === ADMINISTRACIÓN: CRUD de Eventos ===
@innovacion_bp.route("/eventos")
@require_permiso("innovacion.admin_eventos")
def eventos_list():
    api_request = get_api_request_func()
    token = session.get("token")
    buscar = request.args.get("buscar", "")
    pagina = request.args.get("pagina", 1, type=int)

    params = f"?pagina={pagina}&por_pagina=20"
    if buscar:
        params += f"&buscar={buscar}"

    data, _ = api_request("GET", f"/innovacion/eventos{params}", token=token)
    items = data.get("items", []) if isinstance(data, dict) else []
    total = data.get("total", 0) if isinstance(data, dict) else 0
    total_paginas = data.get("total_paginas", 1) if isinstance(data, dict) else 1

    if request.headers.get("HX-Request"):
        return render_template(
            "innovacion/partials/eventos_table.html",
            items=items,
            total=total,
            pagina=pagina,
            total_paginas=total_paginas,
            buscar=buscar,
        )

    return render_template(
        "innovacion/eventos_list.html",
        items=items,
        total=total,
        pagina=pagina,
        total_paginas=total_paginas,
        buscar=buscar,
    )


@innovacion_bp.route("/eventos/nuevo", methods=["GET", "POST"])
@require_permiso("innovacion.admin_eventos")
def eventos_create():
    api_request = get_api_request_func()
    token = session.get("token")

    if request.method == "POST":
        # Recoger tags como lista desde el form
        tags_raw = request.form.get("tags", "")
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []

        data = {
            "nombre": request.form.get("nombre"),
            "fecha": parse_date(request.form.get("fecha")),
            "duenio": request.form.get("duenio") or None,
            "tags": tags if tags else None,
        }
        result, status = api_request("POST", "/innovacion/eventos", data, token=token)
        if status in [200, 201]:
            flash("Evento creado exitosamente", "success")
            if request.headers.get("HX-Request"):
                return "", 200, {"HX-Redirect": url_for("innovacion.eventos_list")}
            return redirect(url_for("innovacion.eventos_list"))
        err = format_api_error(result.get("detail"), "Error al crear evento")
        if request.headers.get("HX-Request"):
            return error_html(err)
        flash(err, "error")

    return render_template("innovacion/eventos_form.html", item=None)


@innovacion_bp.route("/eventos/<id>/editar", methods=["GET", "POST"])
@require_permiso("innovacion.admin_eventos")
def eventos_edit(id):
    api_request = get_api_request_func()
    token = session.get("token")

    if request.method == "POST":
        # Recoger tags como lista desde el form
        tags_raw = request.form.get("tags", "")
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()] if tags_raw else []

        data = {
            "nombre": request.form.get("nombre"),
            "fecha": parse_date(request.form.get("fecha")),
            "duenio": request.form.get("duenio") or None,
            "tags": tags if tags else None,
        }
        result, status = api_request("PUT", f"/innovacion/eventos/{id}", data, token=token)
        if status == 200:
            flash("Evento actualizado", "success")
            if request.headers.get("HX-Request"):
                return "", 200, {"HX-Redirect": url_for("innovacion.eventos_list")}
            return redirect(url_for("innovacion.eventos_list"))
        err = format_api_error(result.get("detail"), "Error al actualizar evento")
        if request.headers.get("HX-Request"):
            return error_html(err)
        flash(err, "error")

    item, _ = api_request("GET", f"/innovacion/eventos/{id}", token=token)
    return render_template("innovacion/eventos_form.html", item=item)


@innovacion_bp.route("/eventos/<id>/eliminar", methods=["DELETE"])
@require_permiso("innovacion.admin_eventos")
def eventos_delete(id):
    api_request = get_api_request_func()
    token = session.get("token")
    result, status = api_request("DELETE", f"/innovacion/eventos/{id}", token=token)
    if status == 200:
        return "", 200, {"HX-Trigger": "eventoDeleted"}
    return error_html(result.get("detail"), "Error al eliminar"), 400


@innovacion_bp.route("/eventos/<id>/asistentes", methods=["GET", "POST"])
@require_permiso("innovacion.admin_eventos")
def eventos_asistentes(id):
    api_request = get_api_request_func()
    token = session.get("token")

    if request.method == "POST":
        # Recoger empleado_ids del form (CSV desde Alpine)
        csv_raw = request.form.get("empleado_ids_csv", "")
        empleado_ids = [eid.strip() for eid in csv_raw.split(",") if eid.strip()]
        if not empleado_ids:
            err = "Seleccioná al menos un empleado"
            if request.headers.get("HX-Request"):
                return error_html(err)
            flash(err, "error")
            return redirect(url_for("innovacion.eventos_asistentes", id=id))
        data = {"empleado_ids": empleado_ids}
        result, status = api_request("PUT", f"/innovacion/eventos/{id}/asistentes", data, token=token)
        if status == 200:
            flash("Asistentes actualizados", "success")
            if request.headers.get("HX-Request"):
                return "", 200, {"HX-Redirect": url_for("innovacion.eventos_asistentes", id=id)}
            return redirect(url_for("innovacion.eventos_asistentes", id=id))
        err = format_api_error(result.get("detail"), "Error al asignar asistentes")
        if request.headers.get("HX-Request"):
            return error_html(err)
        flash(err, "error")

    # Obtener evento
    evento, _ = api_request("GET", f"/innovacion/eventos/{id}", token=token)
    # Obtener asistentes actuales
    asistentes, _ = api_request("GET", f"/innovacion/eventos/{id}/asistentes", token=token)
    asistentes = asistentes if isinstance(asistentes, list) else []
    asistentes_ids = [a["id"] for a in asistentes]
    # Obtener todos los empleados activos
    empleados_data, _ = api_request("GET", "/innovacion/eventos/empleados", token=token)
    empleados = empleados_data if isinstance(empleados_data, list) else []

    return render_template(
        "innovacion/eventos_asistentes.html",
        evento=evento,
        asistentes=asistentes,
        asistentes_ids=asistentes_ids,
        empleados=empleados,
    )


# ─── LICENCIAS ─────────────────────────────────────────


# === LISTAR LICENCIAS ===
@innovacion_bp.route("/licencias")
@require_permiso("innovacion.licencias")
def licencias_list():
    from urllib.parse import urlencode

    api_request = get_api_request_func()
    token = session.get("token")

    # Parámetros de búsqueda, filtros y paginación
    buscar = request.args.get("buscar", "")
    pagina = request.args.get("pagina", 1, type=int)
    vista = "equipos" if request.args.get("vista") == "equipos" else "empleados"

    # Filtros
    filtro_equipos = list(dict.fromkeys(valor.strip() for valor in request.args.getlist("equipo_id") if valor.strip()))
    filtro_proveedor = request.args.get("proveedor_id", "")
    filtro_empleados = list(
        dict.fromkeys(valor.strip() for valor in request.args.getlist("empleado_id") if valor.strip())
    )

    params = {"pagina": pagina, "por_pagina": 25}
    if buscar:
        params["buscar"] = buscar
    if filtro_equipos:
        params["equipo_id"] = filtro_equipos
    if filtro_proveedor:
        params["proveedor_id"] = filtro_proveedor
    if filtro_empleados:
        params["empleado_id"] = filtro_empleados

    agrupacion = "por-equipo" if vista == "equipos" else "por-empleado"
    data, status = api_request(
        "GET", f"/innovacion/licencias/{agrupacion}?{urlencode(params, doseq=True)}", token=token
    )

    items = data.get("items", []) if isinstance(data, dict) else []
    total = data.get("total", 0) if isinstance(data, dict) else 0
    total_empleados = data.get("total_empleados", total) if isinstance(data, dict) else 0
    total_paginas = data.get("total_paginas", 1) if isinstance(data, dict) else 1
    metricas = data.get("metricas") if isinstance(data, dict) else None
    metricas = metricas or {"mes_actual": [], "mes_anterior": [], "delta": []}

    contexto = dict(
        items=items,
        total=total,
        total_empleados=total_empleados,
        vista=vista,
        pagina=pagina,
        total_paginas=total_paginas,
        buscar=buscar,
        metricas=metricas,
        filtro_equipos=filtro_equipos,
        filtro_proveedor=filtro_proveedor,
        filtro_empleados=filtro_empleados,
    )

    if request.headers.get("HX-Request"):
        return render_template("innovacion/partials/licencias_table.html", **contexto)

    # Los fragmentos solo necesitan el listado; los catálogos viven en el estado Alpine.
    herramientas, _ = api_request("GET", "/innovacion/herramientas", token=token)
    proveedores, _ = api_request("GET", "/innovacion/proveedores", token=token)
    equipos, _ = api_request("GET", "/innovacion/licencias/equipos", token=token)
    empleados, _ = api_request("GET", "/innovacion/licencias/empleados", token=token)

    return render_template(
        "innovacion/licencias_list.html",
        herramientas=herramientas or [],
        proveedores=proveedores or [],
        equipos=equipos or [],
        empleados=empleados or [],
        **contexto,
    )


# === CREAR PROVEEDOR (modal de herramienta) ===
@innovacion_bp.route("/proveedores", methods=["POST"])
@require_permiso("innovacion.licencias")
def proveedores_create():
    api_request = get_api_request_func()
    token = session.get("token")

    datos = request.get_json(silent=True) or {}
    payload = {"nombre": (datos.get("nombre") or "").strip()}

    result, status = api_request("POST", "/innovacion/proveedores", payload, token=token)
    if status in (200, 201):
        return jsonify(result), 201

    detalle = result.get("detail") if isinstance(result, dict) else None
    return jsonify({"detail": format_api_error(detalle, "Error al crear el proveedor")}), status or 400


# === CATALOGO: corregir y borrar ===
@innovacion_bp.route("/proveedores/<id>", methods=["PUT"])
@require_permiso("innovacion.licencias")
def proveedores_update(id):
    api_request = get_api_request_func()
    datos = request.get_json(silent=True) or {}
    payload = {"nombre": (datos.get("nombre") or "").strip()}
    result, status = api_request("PUT", f"/innovacion/proveedores/{id}", payload, token=session.get("token"))
    if status == 200:
        return jsonify(result), 200
    detalle = result.get("detail") if isinstance(result, dict) else None
    return jsonify({"detail": format_api_error(detalle, "Error al actualizar el proveedor")}), status or 400


@innovacion_bp.route("/herramientas/<id>", methods=["PUT"])
@require_permiso("innovacion.licencias")
def herramientas_update(id):
    """Corrige la herramienta. Reapuntar el proveedor desbloquea su borrado."""
    api_request = get_api_request_func()
    token = session.get("token")

    datos = request.get_json(silent=True) or {}
    payload = {}
    if datos.get("nombre"):
        payload["nombre"] = datos["nombre"].strip()
    if "proveedor_id" in datos:
        payload["proveedor_id"] = datos["proveedor_id"] or None
    if "proveedor_nombre" in datos:
        payload["proveedor_nombre"] = (datos["proveedor_nombre"] or "").strip() or None
    if "costo_referencia" in datos:
        costo = datos["costo_referencia"]
        payload["costo_referencia"] = (costo.strip().replace(",", ".") or None) if isinstance(costo, str) else costo
    if "moneda" in datos:
        payload["moneda"] = datos["moneda"]

    result, status = api_request("PUT", f"/innovacion/herramientas/{id}", payload, token=token)
    if status == 200:
        return jsonify(result), 200

    detalle = result.get("detail") if isinstance(result, dict) else None
    return jsonify({"detail": format_api_error(detalle, "Error al actualizar")}), status or 400


@innovacion_bp.route("/herramientas/<id>", methods=["DELETE"])
@require_permiso("innovacion.licencias")
def herramientas_delete(id):
    api_request = get_api_request_func()
    result, status = api_request("DELETE", f"/innovacion/herramientas/{id}", token=session.get("token"))
    if status in (200, 204):
        return "", 204

    detalle = result.get("detail") if isinstance(result, dict) else None
    return jsonify({"detail": format_api_error(detalle, "No se pudo borrar")}), status or 400


@innovacion_bp.route("/proveedores/<id>", methods=["DELETE"])
@require_permiso("innovacion.licencias")
def proveedores_delete(id):
    api_request = get_api_request_func()
    result, status = api_request("DELETE", f"/innovacion/proveedores/{id}", token=session.get("token"))
    if status in (200, 204):
        return "", 204

    detalle = result.get("detail") if isinstance(result, dict) else None
    return jsonify({"detail": format_api_error(detalle, "No se pudo borrar")}), status or 400


@innovacion_bp.route("/licencias/revocacion/preview", methods=["POST"])
@innovacion_bp.route("/licencias/revocacion", methods=["DELETE"])
@require_permiso("innovacion.licencias")
def licencias_revocacion():
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        return jsonify({"detail": "Se requiere una selección de licencias"}), 400
    endpoint = "/innovacion/licencias/revocacion" + ("/preview" if request.method == "POST" else "")
    result, status = get_api_request_func()(request.method, endpoint, datos, token=session.get("token"))
    return jsonify(result), status or 502


@innovacion_bp.route("/licencias/<id>", methods=["DELETE"])
@require_permiso("innovacion.licencias")
def licencias_delete(id):
    api_request = get_api_request_func()
    result, status = api_request("DELETE", f"/innovacion/licencias/{id}", token=session.get("token"))
    if status in (200, 204):
        # El listado se refresca con el mismo evento que el toggle de activa.
        return "", 200, {"HX-Trigger": "licenciaEstadoCambiado"}

    detalle = result.get("detail") if isinstance(result, dict) else None
    return jsonify({"detail": format_api_error(detalle, "No se pudo borrar la licencia")}), status or 400


@innovacion_bp.route("/licencias/lote", methods=["POST"])
@require_permiso("innovacion.licencias")
def licencias_create_lote():
    datos = request.get_json(silent=True)
    if not isinstance(datos, dict):
        return jsonify({"detail": "Se requiere un objeto JSON con las licencias a asignar"}), 400

    if "licencias" in datos:
        payload = datos
    else:
        try:
            payload = _get_licencia_form_data(datos)
        except ValueError as e:
            return jsonify({"detail": str(e)}), 422
        payload.pop("empleado_id")
        payload["empleado_ids"] = datos.get("empleado_ids") or []
    result, status = get_api_request_func()("POST", "/innovacion/licencias/lote", payload, token=session.get("token"))
    if status in (200, 201):
        return jsonify(result), 201

    detalle = result.get("detail") if isinstance(result, dict) else None
    if isinstance(detalle, list):
        # Los validadores del lote ya explican el problema; el mapa genérico
        # interpreta value_error como un error de URL y perdería ese mensaje.
        detalle = [
            error.get("msg", "Valor inválido").removeprefix("Value error, ")
            if isinstance(error, dict) and error.get("type") == "value_error"
            else error
            for error in detalle
        ]
    return jsonify({"detail": format_api_error(detalle, "Error al asignar las licencias")}), status or 400


# === EDITAR LICENCIA ===
@innovacion_bp.route("/licencias/<id>/editar", methods=["GET", "POST"])
@require_permiso("innovacion.licencias")
def licencias_edit(id):
    api_request = get_api_request_func()
    token = session.get("token")

    if request.method == "POST":
        try:
            data = _get_licencia_form_data()
            result, status = api_request("PUT", f"/innovacion/licencias/{id}", data, token=token)
        except ValueError as e:
            result, status = {"detail": str(e)}, 400

        if status == 200:
            flash("Licencia actualizada exitosamente", "success")
            if request.headers.get("HX-Request"):
                return "", 200, {"HX-Redirect": url_for("innovacion.licencias_list")}
            return redirect(url_for("innovacion.licencias_list"))

        err_block = error_html(result.get("detail"), "Error al actualizar licencia")
        if request.headers.get("HX-Request"):
            return err_block
        flash(format_api_error(result.get("detail"), "Error al actualizar licencia"), "error")

    item, status = api_request("GET", f"/innovacion/licencias/{id}", token=token)
    if not item or status != 200:
        flash("Licencia no encontrada", "error")
        return redirect(url_for("innovacion.licencias_list"))
    empleados, _ = api_request("GET", "/nomina/empleados/buscar-select", token=token)
    herramientas, _ = api_request("GET", "/innovacion/herramientas", token=token)
    return render_template(
        "innovacion/licencias_form.html", item=item, empleados=empleados or [], herramientas=herramientas or []
    )


# === CREAR HERRAMIENTA (modal del form de licencia) ===
@innovacion_bp.route("/herramientas", methods=["POST"])
@require_permiso("innovacion.licencias")
def herramientas_create():
    api_request = get_api_request_func()
    token = session.get("token")

    datos = request.get_json(silent=True) or {}
    costo = datos.get("costo_referencia")
    if isinstance(costo, str):
        costo = costo.strip().replace(",", ".") or None

    payload = {
        "nombre": (datos.get("nombre") or "").strip(),
        "proveedor_id": datos.get("proveedor_id") or None,
        "proveedor_nombre": (datos.get("proveedor_nombre") or "").strip() or None,
        "costo_referencia": costo,
        "moneda": datos.get("moneda") or "ARS",
    }

    result, status = api_request("POST", "/innovacion/herramientas", payload, token=token)
    if status in (200, 201):
        return jsonify(result), 201

    detalle = result.get("detail") if isinstance(result, dict) else None
    return jsonify({"detail": format_api_error(detalle, "Error al crear la herramienta")}), status or 400


# === ACTIVAR / DESACTIVAR ===
@innovacion_bp.route("/licencias/<id>/activa/<activa>", methods=["PUT"])
@require_permiso("innovacion.licencias")
def licencias_cambiar_activa(id, activa):
    api_request = get_api_request_func()
    token = session.get("token")
    result, status = api_request("PUT", f"/innovacion/licencias/{id}/activa/{activa}", token=token)

    if status == 200:
        return "", 200, {"HX-Trigger": "licenciaEstadoCambiado"}
    return error_html(result.get("detail"), "Error al cambiar el estado"), 400


def _get_licencia_form_data(datos=None):
    """Normaliza los campos comunes del formulario o del alta JSON por lote."""
    from math import isfinite

    datos = request.form if datos is None else datos

    def parse_date(date_str):
        """Convierte dd/mm/yyyy a yyyy-mm-dd para la API."""
        if not date_str:
            return None
        try:
            parts = date_str.split("/")
            if len(parts) == 3:
                return f"{parts[2]}-{parts[1]}-{parts[0]}"
        except Exception:
            pass
        return date_str

    costo = datos.get("costo_mensual")
    if costo is None or (isinstance(costo, str) and not costo.strip()):
        costo = None
    else:
        try:
            costo = float(str(costo).replace(",", "."))
            if not isfinite(costo):
                raise ValueError
        except ValueError:
            raise ValueError("Ingresá un costo válido, por ejemplo 1000,50") from None

    return {
        "herramienta_id": datos.get("herramienta_id"),
        "empleado_id": datos.get("empleado_id"),
        "fecha_inicio": parse_date(datos.get("fecha_inicio")),
        "fecha_fin": parse_date(datos.get("fecha_fin")) or None,
        "costo_mensual": costo,
        "moneda": datos.get("moneda") or "ARS",
        "nro_pedido_compra": datos.get("nro_pedido_compra") or None,
    }


# === BLUEPRINT PÚBLICO (sin autenticación) ===
certificates_bp = Blueprint("certificates", __name__, template_folder="templates", url_prefix="/certificates")


def _fetch_public_cert(cert_id):
    """Trae el certificado público desde el backend. Devuelve dict o None."""
    import httpx
    from flask import current_app

    api_url = current_app.config["API_URL"]
    url = f"{api_url}/api/v1/innovacion/certificaciones/{cert_id}/public"
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url)
            if response.status_code == 200:
                return response.json()
    except Exception:
        return None
    return None


def _slugify_name(name):
    """nombre -> minúsculas, sin tildes, espacios -> '_'. (igual que el backend)"""
    import re
    import unicodedata

    if not name:
        return "certificado"
    n = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    n = re.sub(r"[^a-z0-9]+", "_", n.lower().strip())
    return re.sub(r"_+", "_", n).strip("_") or "certificado"


@certificates_bp.route("/<cert_id>")
def certificate_public(cert_id):
    """Página pública para verificar un certificado por UUID."""
    cert = _fetch_public_cert(cert_id)
    if not cert:
        return render_template("innovacion/certificate_not_found.html"), 404
    og_slug = _slugify_name(cert.get("empleado_nombre"))
    return render_template("innovacion/certificate_public.html", cert=cert, og_slug=og_slug)


@certificates_bp.route("/<cert_id>/<slug>.png")
def certificate_og_image(cert_id, slug):
    """Banner og:image del certificado. PROXEA la imagen que genera y cachea el
    backend (en su volumen), igual que /storage, /files, /fotos.

    El `slug` está en la URL solo para que el nombre del archivo sea legible
    (URL canónica); el backend calcula el suyo a partir del nombre real.
    """
    from urllib.parse import quote

    import httpx
    from flask import Response, abort, current_app, url_for

    api_url = current_app.config["API_URL"]
    verify_url = url_for("certificates.certificate_public", cert_id=cert_id, _external=True)
    backend_url = (
        f"{api_url}/api/v1/innovacion/certificaciones/{cert_id}/og-image.png?verify={quote(verify_url, safe='')}"
    )
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.get(backend_url)
    except Exception:
        abort(502)
    if r.status_code != 200:
        abort(r.status_code)
    return Response(
        r.content,
        status=200,
        content_type=r.headers.get("content-type", "image/png"),
        headers={"Cache-Control": r.headers.get("cache-control", "public, max-age=86400")},
    )
