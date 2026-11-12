"""
Módulo de Soporte Técnico - Panel para usuarios de soporte.
"""

from datetime import datetime
from typing import Any, Optional

import httpx
from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session, url_for

# Importar decoradores de autenticación y permisos
from modulos.auth_helpers import require_permiso
from modulos.error_helpers import error_html, format_api_error

soporte_bp = Blueprint("soporte", __name__, template_folder="templates", url_prefix="/soporte")


def get_api_request_func():
    from flask import current_app

    return current_app.config.get("api_request")


def _build_url(base: str, params: dict = None) -> str:
    """Construye URL con query params filtrando None."""
    if not params:
        return base
    parts = [f"{k}={v}" for k, v in params.items() if v is not None]
    return f"{base}?{'&'.join(parts)}" if parts else base


def _redirect_stock():
    """Redirige según el tipo de activo (Con especificaciones -> Notebooks, Sin -> Insumos)."""
    req_spec = request.form.get("req_spec") == "true"
    if req_spec:
        return redirect(url_for("soporte.stock_list"))  # Tab de Notebooks
    return redirect(url_for("soporte.stock_insumos"))


def _get_stock_data(api_request, token, tipo=None, estado=None, buscar=None):
    """Auxiliar para obtener datos de stock con filtros comunes."""
    params = []
    if tipo:
        params.append(f"tipo={tipo}")
    if estado:
        params.append(f"estado={estado}")
    if buscar:
        params.append(f"buscar={buscar}")

    api_url = "/soporte/activos"
    if params:
        api_url += "?" + "&".join(params)

    data, status = api_request("GET", api_url, token=token)
    items = data.get("items", []) if isinstance(data, dict) else []
    stats = data.get("stats", {}) if isinstance(data, dict) else {}

    return items, stats


def _upload_evidence(file_obj, token):
    """Auxiliar para subir archivos de evidencia al backend."""
    import httpx
    from flask import current_app

    if not file_obj or not file_obj.filename:
        return ""

    api_url = current_app.config["API_URL"]
    try:
        # Algunos archivos pueden necesitar read() si son FileStorage de Flask
        content = file_obj.read()
        if not content:
            return ""
        file_obj.seek(0)  # Reset para futuras lecturas si aplica

        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{api_url}/api/v1/soporte/historial/evidencias",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": (file_obj.filename, content, file_obj.content_type)},
            )
            if resp.status_code == 200:
                return resp.json().get("url", "")
    except Exception:
        pass
    return ""


def _get_acuerdo_data(api_request, token, colaborador_id, equipo_id):
    """Auxiliar para obtener datos comunes de acuerdos (entrega/devolución)."""
    colaborador_data, _ = api_request("GET", f"/nomina/empleados/{colaborador_id}", token=token)
    item_data, status = api_request("GET", f"/soporte/activos/{equipo_id}", token=token)

    if status != 200 or not isinstance(item_data, dict):
        return None, None, None

    dni_colaborador = colaborador_data.get("dni") if isinstance(colaborador_data, dict) else "_____________"
    nombre_colaborador = (
        f"{colaborador_data.get('nombre', '')} {colaborador_data.get('apellido', '')}".strip()
        if isinstance(colaborador_data, dict)
        else ""
    )

    return item_data, dni_colaborador, nombre_colaborador


def _upload_evidence_list(files_list, token):
    """Auxiliar para subir una lista de archivos de evidencia."""
    urls = []
    if not files_list:
        return urls
    for f in files_list:
        if f and f.filename:
            url = _upload_evidence(f, token)
            if url:
                urls.append(url)
    return urls


# Fallback mínimo si el backend no responde (mismo contrato que /soporte/tipos-ticket).
_TIPOS_TICKET_FALLBACK = [
    {"clave": "generico", "label": "Genérico", "color": "gray"},
    {"clave": "reparacion", "label": "Reparación", "color": "red"},
    {"clave": "alta_baja", "label": "Alta/Baja", "color": "blue"},
    {"clave": "mantenimiento", "label": "Mantenimiento", "color": "amber"},
]


def _get_tipos_ticket(api_request, token):
    """Obtiene los tipos de ticket desde el backend (fuente única: enum TipoTicket).

    Devuelve lista de dicts {clave, label, color}. Ante cualquier error usa un
    fallback para no romper el render.
    """
    try:
        data, status = api_request("GET", "/soporte/tipos-ticket", token=token)
        if status == 200 and isinstance(data, dict):
            tipos = data.get("tipos")
            if isinstance(tipos, list) and tipos:
                return tipos
    except Exception:
        pass
    return _TIPOS_TICKET_FALLBACK


# ─── Capa de Compatibilidad v28.0 ──────────────────────────────────


def _resolve_master_id(db_list: Any, key: str, field: str = "clave") -> Optional[str]:
    """Busca un ID en una lista de maestros (o respuesta paginada v28.0 items/total) por clave o nombre."""
    if not db_list or not key:
        return None

    # Extraer items si es una respuesta paginada v28.0
    items = db_list.get("items", []) if isinstance(db_list, dict) else db_list
    if not items or not isinstance(items, list):
        return None

    for item in items:
        # Asegurar que item sea un diccionario antes de llamar a get()
        if not isinstance(item, dict):
            continue
        if str(item.get(field, "")).lower() == str(key).lower():
            return str(item.get("id"))
    return None


def _get_masters(api_request, token):
    """Obtiene estados y categorías para mapeo v28.0."""
    estados_data, _ = api_request("GET", "/soporte/estados-maestros", token=token)
    categorias_data, _ = api_request("GET", "/soporte/categorias", token=token)

    # Normalizar resultados que vienen envueltos en diccionarios v28.0
    estados = estados_data or []
    if isinstance(estados_data, dict):
        estados = estados_data.get("items") or estados_data.get("estados") or []

    categorias = categorias_data or []
    if isinstance(categorias_data, dict):
        categorias = categorias_data.get("categorias") or categorias_data.get("items") or []

    return estados, categorias


def _get_matriz_estado(request_form):
    """Estructura la matriz para el backend v28.0."""
    return {
        "pantalla": request_form.get("pantalla")
        or request_form.get("st_pantalla")
        or request_form.get("estado_pantalla")
        or "Excelente",
        "teclado": request_form.get("teclado")
        or request_form.get("st_teclado")
        or request_form.get("estado_teclado")
        or "Excelente",
        "bateria": request_form.get("bateria")
        or request_form.get("st_bateria")
        or request_form.get("estado_bateria")
        or "Excelente",
        "carcasa_superior": request_form.get("carcasa_superior")
        or request_form.get("st_carcasa_superior")
        or request_form.get("st_carcasa")
        or request_form.get("estado_carcasa")
        or "Excelente",
        "carcasa_inferior": request_form.get("carcasa_inferior")
        or request_form.get("st_carcasa_inferior")
        or request_form.get("st_carcasa")
        or request_form.get("estado_carcasa")
        or "Excelente",
        "touchpad": request_form.get("touchpad")
        or request_form.get("st_touchpad")
        or request_form.get("estado_audio_camara")
        or "Excelente",
        "puertos": request_form.get("puertos")
        or request_form.get("st_puertos")
        or request_form.get("estado_puertos")
        or "Excelente",
        "cargador": request_form.get("cargador") or request_form.get("st_cargador") or "Excelente",
    }


# ─── Dashboard principal ───────────────────────────────────────────
@soporte_bp.route("")
@require_permiso("soporte.dashboard")
def dashboard():
    """Panel principal de soporte técnico."""
    return render_template("soporte/dashboard.html")


# ─── Panel del Usuario (Mis Solicitudes) ──────────────────────────
@soporte_bp.route("/mis-solicitudes")
@require_permiso("soporte.mis_solicitudes")
def mis_solicitudes():
    """Panel del empleado: ver sus solicitudes de soporte."""
    api_request = get_api_request_func()
    token = session.get("token")

    # Obtener mis tickets resolviendo ID del empleado
    data, status = api_request("GET", "/soporte/tickets/mis-tickets", token=token)
    tickets = data.get("items", []) if isinstance(data, dict) else []

    # Determinar si el usuario puede gestionar alta/baja (manager de Reclutamiento o admin)
    cats_data, _ = api_request("GET", "/soporte/categorias-disponibles", token=token)
    categorias = cats_data.get("categorias", []) if isinstance(cats_data, dict) else []
    puede_alta_baja = any(cat.get("tipo_ticket_asociado") == "alta_baja" for cat in categorias)

    return render_template("soporte/mis_solicitudes.html", tickets=tickets, puede_alta_baja=puede_alta_baja)


@soporte_bp.route("/mis-solicitudes/crear", methods=["POST"])
@require_permiso("soporte.mis_solicitudes")
def crear_solicitud():
    """Empleado crea una nueva solicitud mapeando strings a UUIDs v28.0."""
    api_request = get_api_request_func()
    token = session.get("token")
    user = session.get("user", {})

    # Resolver Subcategoría usando categorias-disponibles (accesible sin permiso de tickets_kanban)
    cats_data, _ = api_request("GET", "/soporte/categorias-disponibles", token=token)
    categorias = cats_data.get("categorias", []) if isinstance(cats_data, dict) else []
    sub_nombre = request.form.get("categoria", "").strip()
    sub_id = None

    for cat in categorias:
        if not isinstance(cat, dict):
            continue
        for sub in cat.get("subcategorias", []):
            if not isinstance(sub, dict):
                continue
            if sub.get("nombre_normalizado") == sub_nombre or sub.get("nombre", "").lower() == sub_nombre.lower():
                sub_id = sub["id"]
                break

    if not sub_id and categorias and categorias[0].get("subcategorias"):
        sub_id = categorias[0]["subcategorias"][0]["id"]

    datos = {
        "titulo": request.form.get("titulo", "").strip(),
        "descripcion": request.form.get("descripcion", "").strip(),
        "prioridad": request.form.get("prioridad", "media"),
        "subcategoria_id": sub_id,
        "solicitante_id": user.get("empleado_id") or user.get("id", ""),
        "activo_id": request.form.get("activo_id").strip() if request.form.get("activo_id") else None,
        "colaborador_id": request.form.get("colaborador_id") or None,
        "fecha_programada": request.form.get("fecha_programada") or None,
        # Campos proceso de alta IT
        "modalidad_trabajo": request.form.get("modalidad_trabajo") or None,
        "requiere_nextcloud": request.form.get("requiere_nextcloud") == "1",
        "listas_correo": request.form.get("listas_correo") or None,
        "necesita_computadora": request.form.get("necesita_computadora") == "1",
        "gama_computadora": request.form.get("gama_computadora") or None,
        "cliente_servicio": request.form.get("cliente_servicio") or None,
        "sistemas_habilitados": request.form.getlist("sistemas_habilitados"),
    }

    result, status = api_request("POST", "/soporte/tickets", data=datos, token=token)

    if status in (200, 201) and isinstance(result, dict):
        ticket_id = result.get("id")

        # Subir imagen si se adjuntó una
        archivo = request.files.get("imagen")
        if archivo and archivo.filename and ticket_id:
            api_url = current_app.config["API_URL"]
            try:
                with httpx.Client(timeout=30.0) as client:
                    resp = client.post(
                        f"{api_url}/api/v1/soporte/tickets/{ticket_id}/imagen",
                        headers={"Authorization": f"Bearer {token}"},
                        files={"file": (archivo.filename, archivo.read(), archivo.content_type)},
                    )
                    if resp.status_code != 200:
                        flash("Solicitud creada pero hubo un error al subir la imagen", "warning")
            except Exception:
                flash("Solicitud creada pero hubo un error al subir la imagen", "warning")

        flash("Solicitud enviada", "success")
    else:
        error_detail = (
            result.get("detail", "Error al enviar solicitud")
            if isinstance(result, dict)
            else "Error al enviar solicitud"
        )
        error = format_api_error(error_detail, "Error al enviar solicitud")
        flash(error, "error")

    if request.headers.get("HX-Request"):
        return "", 200, {"HX-Redirect": url_for("soporte.mis_solicitudes")}
    return redirect(url_for("soporte.mis_solicitudes"))


@soporte_bp.route("/mis-solicitudes/<ticket_id>/cancelar", methods=["POST"])
@require_permiso("soporte.mis_solicitudes")
def cancelar_solicitud(ticket_id):
    """Empleado cancela su propia solicitud.

    Usa el endpoint dedicado POST /soporte/tickets/{id}/cancelar-propia que valida
    ownership en el backend (solicitante.dni == current_user.dni).
    """
    api_request = get_api_request_func()
    token = session.get("token")

    result, status = api_request("POST", f"/soporte/tickets/{ticket_id}/cancelar-propia", token=token)

    if status == 200:
        flash("Solicitud cancelada", "success")
    else:
        error = format_api_error(result.get("detail"), "Error al cancelar")
        flash(error, "error")

    if request.headers.get("HX-Request"):
        return "", 200, {"HX-Redirect": url_for("soporte.mis_solicitudes")}
    return redirect(url_for("soporte.mis_solicitudes"))


# ─── Dashboard partials (HTMX) ────────────────────────────────────
@soporte_bp.route("/dashboard/metrics")
@require_permiso("soporte.dashboard")
def dashboard_metrics_partial():
    """Métricas avanzadas para el Centro de Mando (HTMX partial)."""
    api_request = get_api_request_func()
    token = session.get("token")

    data, status = api_request("GET", "/soporte/dashboard-metrics", token=token)
    metrics = data if isinstance(data, dict) else {}

    return render_template("soporte/partials/dashboard_metrics.html", metrics=metrics)


@soporte_bp.route("/dashboard/tickets-recientes")
@require_permiso("soporte.dashboard")
def tickets_recientes_partial():
    """Tickets recientes para el dashboard (HTMX partial)."""
    api_request = get_api_request_func()
    token = session.get("token")

    # Obtener abiertos y en progreso de forma eficiente
    data, _ = api_request("GET", "/soporte/tickets?estado=abierto", token=token)
    tickets = data.get("items", [])[:5] if isinstance(data, dict) else []

    data2, _ = api_request("GET", "/soporte/tickets?estado=en_progreso", token=token)
    tickets_progreso = data2.get("items", [])[:5] if isinstance(data2, dict) else []

    todos = sorted(tickets + tickets_progreso, key=lambda t: t.get("created_at", ""), reverse=True)
    return render_template("soporte/partials/tickets_recientes.html", tickets=todos[:8])


# ─── Tickets Kanban ────────────────────────────────────────────────
@soporte_bp.route("/tickets")
@require_permiso("soporte.tickets_kanban")
def tickets_kanban():
    """Vista Kanban de tickets."""
    api_request = get_api_request_func()
    token = session.get("token")

    params = {
        "categoria_id": request.args.get("categoria_id", "").strip() or None,
        "buscar": request.args.get("buscar", "").strip() or None,
    }

    data, _ = api_request("GET", _build_url("/soporte/tickets/kanban", params), token=token)
    kanban = data.get("kanban", {}) if isinstance(data, dict) else {}
    stats = data.get("stats", {}) if isinstance(data, dict) else {}

    users_data, _ = api_request("GET", "/soporte/usuarios-lista", token=token)
    usuarios = users_data.get("usuarios", []) if isinstance(users_data, dict) else []

    # Categorías para el FILTRO de visualización (SIN filtrar - todos deben ver todas)
    categorias_filtro_data, _ = api_request("GET", "/soporte/categorias", token=token)
    categorias_principales = (
        categorias_filtro_data.get("categorias", []) if isinstance(categorias_filtro_data, dict) else []
    )

    # Categorías para el MODAL de creación (CON filtro de permisos)
    categorias_crear_data, _ = api_request("GET", "/soporte/categorias-disponibles", token=token)
    todas_categorias = categorias_crear_data.get("categorias", []) if isinstance(categorias_crear_data, dict) else []

    # Obtener activos del usuario actual para el formulario de creación
    mis_activos_data, _ = api_request("GET", "/soporte/mis-dispositivos", token=token)
    mis_activos = mis_activos_data.get("dispositivos", []) if isinstance(mis_activos_data, dict) else []

    # Buscar el nombre de la categoría seleccionada para mostrarlo en el botón
    filtro_categoria_nombre = None
    if params["categoria_id"]:
        for cat in categorias_principales:
            if cat["id"] == params["categoria_id"]:
                filtro_categoria_nombre = cat["nombre"]
                break
            if cat.get("subcategorias"):
                for sub in cat["subcategorias"]:
                    if sub["id"] == params["categoria_id"]:
                        filtro_categoria_nombre = sub["nombre"]
                        break
                if filtro_categoria_nombre:
                    break

    return render_template(
        "soporte/tickets.html",
        kanban=kanban,
        stats=stats,
        usuarios=usuarios,
        categorias_principales=categorias_principales,
        todas_categorias=todas_categorias,
        mis_activos=mis_activos,
        tipos_ticket=_get_tipos_ticket(api_request, token),
        filtro_categoria=params["categoria_id"],
        filtro_categoria_nombre=filtro_categoria_nombre,
        buscar=params["buscar"],
    )


# ─── Vista Tabla de Tickets ────────────────────────────────────────
@soporte_bp.route("/tickets/tabla")
@require_permiso("soporte.tickets_kanban")
def tickets_table():
    """Vista de tabla de tickets (más eficiente que kanban)."""
    api_request = get_api_request_func()
    token = session.get("token")

    # Parámetros de filtro
    params = {
        "estado": request.args.get("estado", ""),
        "categoria_id": request.args.get("categoria_id", ""),
        "buscar": request.args.get("buscar", ""),
    }

    # Obtener tickets con filtros
    data, _ = api_request("GET", _build_url("/soporte/tickets", params), token=token)
    tickets = data.get("items", []) if isinstance(data, dict) else []

    # Stats
    stats_data, _ = api_request("GET", "/soporte/tickets/stats", token=token)
    stats = stats_data if isinstance(stats_data, dict) else {}

    # Usuarios para asignación
    users_data, _ = api_request("GET", "/soporte/usuarios-lista", token=token)
    usuarios = users_data.get("usuarios", []) if isinstance(users_data, dict) else []

    # Categorías para el FILTRO de visualización (SIN filtrar - todos deben ver todas)
    categorias_filtro_data, _ = api_request("GET", "/soporte/categorias", token=token)
    categorias_principales = (
        categorias_filtro_data.get("categorias", []) if isinstance(categorias_filtro_data, dict) else []
    )

    # Categorías para el MODAL de creación (CON filtro de permisos)
    categorias_crear_data, _ = api_request("GET", "/soporte/categorias-disponibles", token=token)
    todas_categorias = categorias_crear_data.get("categorias", []) if isinstance(categorias_crear_data, dict) else []

    # Activos del usuario
    mis_activos_data, _ = api_request("GET", "/soporte/mis-dispositivos", token=token)
    mis_activos = mis_activos_data.get("dispositivos", []) if isinstance(mis_activos_data, dict) else []

    # Buscar el nombre de la categoría seleccionada para mostrarlo en el filtro
    filtro_categoria_nombre = None
    if params["categoria_id"]:
        for cat in categorias_principales:
            if cat["id"] == params["categoria_id"]:
                filtro_categoria_nombre = cat["nombre"]
                break
            if cat.get("subcategorias"):
                for sub in cat["subcategorias"]:
                    if sub["id"] == params["categoria_id"]:
                        filtro_categoria_nombre = sub["nombre"]
                        break
                if filtro_categoria_nombre:
                    break

    return render_template(
        "soporte/tickets_table.html",
        tickets=tickets,
        stats=stats,
        usuarios=usuarios,
        categorias_principales=categorias_principales,
        todas_categorias=todas_categorias,
        mis_activos=mis_activos,
        tipos_ticket=_get_tipos_ticket(api_request, token),
        filtro_estado=params["estado"],
        filtro_categoria=params["categoria_id"],
        filtro_categoria_nombre=filtro_categoria_nombre,
        buscar=params["buscar"],
    )


# ─── Crear Ticket ──────────────────────────────────────────────────
@soporte_bp.route("/tickets/crear", methods=["POST"])
@require_permiso("soporte.tickets_kanban")
def crear_ticket():
    """Crea un nuevo ticket mapeando a v28.0 (UUIDs)."""
    api_request = get_api_request_func()
    token = session.get("token")
    user = session.get("user", {})

    # Resolver Subcategoría (Compatibilidad: el form envía 'categoria' como string)
    _, categorias = _get_masters(api_request, token)
    sub_nombre = request.form.get("categoria", "").strip()
    sub_id = None
    for cat in categorias:
        if not isinstance(cat, dict):
            continue
        for sub in cat.get("subcategorias", []):
            if not isinstance(sub, dict):
                continue
            if sub.get("nombre_normalizado") == sub_nombre or sub.get("nombre", "").lower() == sub_nombre.lower():
                sub_id = sub["id"]
                break

    # Si no hay match, usamos la primera válida
    if not sub_id and categorias and categorias[0].get("subcategorias"):
        sub_id = categorias[0]["subcategorias"][0]["id"]

    # Resolver Estado Inicial (Abierto)
    estados, _ = _get_masters(api_request, token)
    estado_id = _resolve_master_id(estados, "abierto")

    # Obtener solicitante_id: del formulario o del usuario actual
    solicitante_id = request.form.get("solicitante_id")
    if not solicitante_id:
        solicitante_id = user.get("empleado_id") or user.get("id", "")

    datos = {
        "titulo": request.form.get("titulo", "").strip(),
        "descripcion": request.form.get("descripcion", "").strip(),
        "prioridad": request.form.get("prioridad", "media"),
        "subcategoria_id": sub_id,
        "solicitante_id": solicitante_id,
        "asignado_id": request.form.get("asignado_id") or None,
        "estado_id": estado_id,
        "activo_id": request.form.get("activo_id") or None,
        "colaborador_id": request.form.get("colaborador_id") or None,
        "fecha_programada": request.form.get("fecha_programada") or None,
        # Campos proceso de alta IT
        "modalidad_trabajo": request.form.get("modalidad_trabajo") or None,
        "requiere_nextcloud": request.form.get("requiere_nextcloud") == "1",
        "listas_correo": request.form.get("listas_correo") or None,
        "necesita_computadora": request.form.get("necesita_computadora") == "1",
        "gama_computadora": request.form.get("gama_computadora") or None,
        "cliente_servicio": request.form.get("cliente_servicio") or None,
        "sistemas_habilitados": request.form.getlist("sistemas_habilitados"),
    }

    result, status = api_request("POST", "/soporte/tickets", data=datos, token=token)

    if status in (200, 201):
        flash("Ticket creado", "success")
    else:
        error = format_api_error(result.get("detail"), "Error al crear ticket")
        flash(error, "error")

    if request.headers.get("HX-Request"):
        return "", 200, {"HX-Redirect": url_for("soporte.tickets_kanban")}
    return redirect(url_for("soporte.tickets_kanban"))


# ─── Cambiar Estado ────────────────────────────────────────────────
@soporte_bp.route("/tickets/<ticket_id>/estado", methods=["PUT", "POST"])
@require_permiso("soporte.tickets_kanban")
def cambiar_estado(ticket_id):
    """Cambia el estado de un ticket mapeando a UUID v28.0."""
    api_request = get_api_request_func()
    token = session.get("token")

    nuevo_estado_nombre = request.form.get("estado", "")
    resolucion = request.form.get("resolucion", "").strip() or None

    # Resolver ID de estado
    estados, _ = _get_masters(api_request, token)
    estado_id = _resolve_master_id(estados, nuevo_estado_nombre)

    # Si no hay match por nombre, probamos si ya es un UUID (directo del select)
    if not estado_id:
        estado_id = nuevo_estado_nombre

    datos = {"nuevo_estado_id": estado_id}
    if resolucion:
        datos["resolucion"] = resolucion

    result, status = api_request("PUT", f"/soporte/tickets/{ticket_id}/estado", data=datos, token=token)

    if status == 200:
        flash("Ticket actualizado", "success")
    else:
        error = format_api_error(result.get("detail"), "Error al actualizar estado")
        flash(error, "error")

    if request.headers.get("HX-Request"):
        if status == 200:
            return "", 200, {"HX-Redirect": request.referrer or url_for("soporte.tickets_kanban")}
        else:
            detail = result.get("detail", "Error") if isinstance(result, dict) else "Error"
            return f'<div class="p-3 bg-red-50 text-red-700 rounded-xl text-sm">{detail}</div>', status

    return redirect(request.referrer or url_for("soporte.tickets_kanban"))


@soporte_bp.route("/tickets/<ticket_id>/iniciar-peritaje", methods=["POST"])
@require_permiso("soporte.tickets_kanban")
def iniciar_peritaje_ticket(ticket_id):
    """Endpoint unificado: inicia el peritaje de reparación para cualquier ticket (genérico con falla o ya reparación)."""
    api_request = get_api_request_func()
    token = session.get("token")

    matriz_datos = {
        "pantalla": request.form.get("pantalla", "Excelente"),
        "teclado": request.form.get("teclado", "Excelente"),
        "bateria": request.form.get("bateria", "Excelente"),
        "carcasa_superior": request.form.get("carcasa_superior", "Excelente"),
        "carcasa_inferior": request.form.get("carcasa_inferior", "Excelente"),
        "touchpad": request.form.get("touchpad", "Excelente"),
        "puertos": request.form.get("puertos", "Excelente"),
        "cargador": request.form.get("cargador", "Excelente"),
    }

    payload = {
        "diagnostico": request.form.get("diagnostico", "").strip(),
        "matriz_datos": matriz_datos,
    }
    # activo_id es opcional: solo hace falta cuando el ticket es genérico y aún no lo tiene vinculado
    activo_id = request.form.get("activo_id", "").strip()
    if activo_id:
        payload["activo_id"] = activo_id

    result, status = api_request("POST", f"/soporte/tickets/{ticket_id}/iniciar-peritaje", data=payload, token=token)

    if status == 200:
        # Si viene con insumo y hay stock, registrar consumo (solo aplica cuando el ticket ya era de reparación)
        insumo_id = request.form.get("insumo_id")
        insumo_cantidad = int(request.form.get("insumo_cantidad", 1) or 1)
        if insumo_id:
            consumo_payload = {"insumo_id": insumo_id, "cantidad": insumo_cantidad, "generar_pedido": False}
            api_request("POST", f"/soporte/tickets/{ticket_id}/insumos", data=consumo_payload, token=token)
        flash("Peritaje iniciado. El equipo ahora está en taller.", "success")
    else:
        error = format_api_error(result.get("detail"), "Error al iniciar el peritaje")
        flash(error, "error")

    return redirect(request.referrer or url_for("soporte.tickets_kanban"))


@soporte_bp.route("/tickets/<ticket_id>/generar-pedido", methods=["POST"])
@require_permiso("soporte.tickets_kanban")
def generar_pedido_reparacion(ticket_id):
    """Genera un pedido de compra vinculado a un ticket de reparación."""
    api_request = get_api_request_func()
    token = session.get("token")

    payload = {
        "tipo_pedido": request.form.get("tipo_pedido"),
        "descripcion": request.form.get("descripcion", "").strip(),
        "monto_estimado": float(request.form.get("monto_estimado", 0) or 0),
        "insumo_id": request.form.get("insumo_id") or None,
        "cantidad_solicitada": int(request.form.get("cantidad_solicitada", 0) or 0),
    }

    result, status = api_request("POST", f"/soporte/tickets/{ticket_id}/generar-pedido", data=payload, token=token)

    if status == 200:
        pedido_numero = result.get("pedido_numero", "")
        flash(f"Pedido de compra {pedido_numero} creado exitosamente.", "success")
    else:
        error = format_api_error(result.get("detail"), "Error al generar pedido")
        flash(error, "error")

    return redirect(request.referrer or url_for("soporte.tickets_kanban"))


# ─── Detalle Ticket ────────────────────────────────────────────────
@soporte_bp.route("/tickets/<ticket_id>")
@require_permiso("soporte.tickets_kanban")
def detalle_ticket(ticket_id):
    """Detalle de un ticket (partial HTMX)."""
    api_request = get_api_request_func()
    token = session.get("token")

    data, status = api_request("GET", f"/soporte/tickets/{ticket_id}", token=token)

    if status != 200:
        return '<div class="p-4 text-red-600">Ticket no encontrado</div>', 404

    # v28.0: Reconstruir nombre del activo asociado para mostrarlo en el detalle
    data["activo_nombre"] = None
    if data.get("activo"):
        act = data["activo"]
        # Reconstrucción amigable: Notebook Dell Inspiron (SN-123)
        t_nombre = act.get("tipo_rel", {}).get("nombre", "Equipo") if act.get("tipo_rel") else "Equipo"
        m_nombre = act.get("marca_rel", {}).get("nombre", "") if act.get("marca_rel") else ""
        mod = act.get("modelo", "")
        sn = act.get("numero_serie", "")
        data["activo_nombre"] = f"{t_nombre} {m_nombre} {mod} ({sn})".replace("  ", " ").strip()

    usuarios_data, _ = api_request("GET", "/soporte/usuarios-lista", token=token)
    usuarios = usuarios_data.get("usuarios", []) if isinstance(usuarios_data, dict) else []

    # Obtener lista de empleados para el selector de técnico asignado
    empleados, _ = api_request("GET", "/soporte/tecnicos-soporte", token=token)

    # Activos asignados al solicitante para posible reparación
    activos = []
    if data.get("tipo_ticket") == "generico" and data.get("es_falla"):
        solic_id = data.get("solicitante_id") or (
            data.get("solicitante", {}).get("id") if data.get("solicitante") else None
        )
        if solic_id:
            # Filtramos por equipos asignados al colaborador solicitante
            activos_data, _ = api_request("GET", f"/soporte/activos?asignado_id={solic_id}", token=token)
            activos = activos_data.get("items", []) if isinstance(activos_data, dict) else []

    # Filtrar evidencias del acuerdo firmado para el template
    evidencias_acuerdo = [e for e in data.get("evidencias", []) if e.get("categoria") == "acuerdo_firmado"]

    # Para tickets alta/baja: obtener la última matriz de estado del activo del colaborador
    ultima_matriz_activo = {}
    if data.get("tipo_ticket") == "alta_baja" and data.get("colaborador_id"):
        colab_id = data["colaborador_id"]
        activos_colab, _ = api_request("GET", f"/soporte/activos?asignado_id={colab_id}", token=token)
        items_colab = activos_colab.get("items", []) if isinstance(activos_colab, dict) else []
        if items_colab and items_colab[0].get("matriz_estado"):
            ultima_matriz_activo = items_colab[0]["matriz_estado"]

    return render_template(
        "soporte/partials/ticket_detalle.html",
        ticket=data,
        usuarios=usuarios,
        activos=activos,
        evidencias_acuerdo=evidencias_acuerdo,
        ultima_matriz_activo=ultima_matriz_activo,
        empleados=empleados or [],
    )


@soporte_bp.route("/usuarios-lista", methods=["GET"])
@require_permiso("soporte.tickets_kanban")
def get_usuarios_lista():
    """Proxy local para obtener la lista de usuarios."""
    api_request = get_api_request_func()
    token = session.get("token")

    usuarios_data, status = api_request("GET", "/soporte/usuarios-lista", token=token)
    if status == 200:
        return jsonify(usuarios_data)
    else:
        return jsonify({"usuarios": []}), status


@soporte_bp.route("/empleados-lista", methods=["GET"])
@require_permiso("soporte.tickets_kanban")
def get_empleados_lista():
    """Proxy local para obtener la lista de empleados."""
    api_request = get_api_request_func()
    token = session.get("token")

    empleados_data, status = api_request("GET", "/soporte/empleados-lista", token=token)
    if status == 200:
        return jsonify(empleados_data)
    else:
        return jsonify({"empleados": []}), status


@soporte_bp.route("/buscar-empleado", methods=["GET"])
@require_permiso("soporte.mis_solicitudes")
def buscar_empleado():
    """Proxy local para buscar empleados (unificado: asignación, colaborador en alta/baja, etc.)."""
    api_request = get_api_request_func()
    token = session.get("token")

    q = request.args.get("q", "").strip()
    if not q or len(q) < 2:
        return jsonify({"items": []}), 200

    empleados_data, status = api_request("GET", f"/soporte/buscar-empleado?q={q}", token=token)
    if status == 200:
        return jsonify(empleados_data)
    else:
        return jsonify({"items": []}), status


@soporte_bp.route("/mis-dispositivos", methods=["GET"])
@require_permiso("soporte.mis_solicitudes")
def get_mis_dispositivos():
    """Proxy local para obtener dispositivos del usuario actual."""
    api_request = get_api_request_func()
    token = session.get("token")

    dispositivos_data, status = api_request("GET", "/soporte/mis-dispositivos", token=token)
    if status == 200:
        return jsonify(dispositivos_data)
    else:
        return jsonify({"dispositivos": []}), status


@soporte_bp.route("/tickets/<ticket_id>/estado-fisico", methods=["GET"])
@require_permiso("soporte.tickets_kanban")
def obtener_estado_fisico_ticket(ticket_id):
    """Obtiene el estado físico de un ticket resuelto para pre-cargar en reparación."""
    api_request = get_api_request_func()
    token = session.get("token")

    estado_data, status = api_request("GET", f"/soporte/tickets/{ticket_id}/estado-fisico", token=token)
    if status == 200:
        return jsonify(estado_data)
    else:
        return jsonify({"error": "No se pudo obtener el estado del ticket"}), status


# ─── Asignar Técnico ───────────────────────────────────────────────
@soporte_bp.route("/tickets/<ticket_id>/asignar-tecnico", methods=["POST"])
@require_permiso("soporte.tickets_kanban")
def asignar_tecnico(ticket_id):
    """Asigna o desasigna un técnico a un ticket (solo en estado abierto)."""
    api_request = get_api_request_func()
    token = session.get("token")

    asignado_id = request.form.get("asignado_id", "").strip()

    # Preparar datos para el backend
    datos = {"asignado_id": asignado_id if asignado_id else None}

    result, status = api_request("PUT", f"/soporte/tickets/{ticket_id}", datos, token=token)

    if status == 200:
        # Obtener el ticket actualizado
        ticket, _ = api_request("GET", f"/soporte/tickets/{ticket_id}", token=token)

        # Obtener lista de técnicos de Soporte IT para el select
        empleados, _ = api_request("GET", "/soporte/tecnicos-soporte", token=token)

        # Renderizar el partial actualizado
        return render_template("soporte/partials/asignado_select.html", ticket=ticket, empleados=empleados or [])

    # En caso de error, devolver mensaje
    error = format_api_error(result.get("detail"), "Error al asignar técnico")
    return f'<div class="p-3 bg-red-50 text-red-700 rounded-xl text-sm">{error}</div>', status


# ─── Eliminar Ticket ──────────────────────────────────────────────
@soporte_bp.route("/tickets/<ticket_id>/eliminar", methods=["DELETE", "POST"])
@require_permiso("soporte.tickets_kanban")
def eliminar_ticket(ticket_id):
    """Elimina un ticket."""
    api_request = get_api_request_func()
    token = session.get("token")

    result, status = api_request("DELETE", f"/soporte/tickets/{ticket_id}", token=token)

    # Determinar a dónde volver según el Referer
    referer = request.headers.get("Referer", "")
    if "/soporte/tickets/tabla" in referer:
        redirect_url = url_for("soporte.tickets_table")
    else:
        redirect_url = url_for("soporte.tickets_kanban")

    if request.headers.get("HX-Request"):
        if status == 200:
            return "", 200, {"HX-Redirect": redirect_url}
        return '<div class="p-3 bg-red-50 text-red-700 rounded-xl text-sm">Error al eliminar</div>', status

    return redirect(redirect_url)


# ─── Stock ─────────────────────────────────────────────────────────


@soporte_bp.route("/stock")
@require_permiso("soporte.stock_list")
def stock_list():
    """Lista de stock de equipos - vista principal (notebooks)."""
    api_request = get_api_request_func()
    token = session.get("token")

    tipo = request.args.get("tipo", "").strip() or "notebook"
    estado = request.args.get("estado", "").strip() or None
    buscar = request.args.get("buscar", "").strip() or None

    items, stats = _get_stock_data(api_request, token, tipo=tipo, estado=estado, buscar=buscar)

    return render_template(
        "soporte/stock.html",
        items=items,
        stats=stats,
        filtro_tipo=tipo,
        filtro_estado=estado,
        buscar=buscar,
        vista="notebooks",
    )


@soporte_bp.route("/insumos")
@require_permiso("soporte.stock_list")
def insumos_list():
    """Lista de insumos (consumibles, componentes, refacciones)."""
    api_request = get_api_request_func()
    token = session.get("token")

    buscar = request.args.get("buscar", "").strip() or None
    categoria = request.args.get("categoria", "").strip() or None
    stock_bajo = request.args.get("stock_bajo", "").strip() or None

    params = {}
    if buscar:
        params["buscar"] = buscar
    if categoria:
        params["categoria"] = categoria
    if stock_bajo:
        params["stock_bajo"] = "true"

    data, status = api_request("GET", _build_url("/soporte/insumos", params), token=token)
    items = data.get("items", []) if isinstance(data, dict) else []
    total = data.get("total", 0) if isinstance(data, dict) else 0

    if request.headers.get("HX-Request"):
        return render_template("soporte/partials/insumos_table.html", items=items)

    return render_template(
        "soporte/insumos_list.html",
        items=items,
        total=total,
        buscar=buscar or "",
        categoria=categoria or "",
        stock_bajo=stock_bajo,
    )


@soporte_bp.route("/insumos-consumos")
@require_permiso("soporte.stock_list")
def insumos_consumos_list():
    """Lista de consumos de insumos."""
    api_request = get_api_request_func()
    token = session.get("token")

    insumo_id = request.args.get("insumo_id", "").strip() or None
    equipo_id = request.args.get("equipo_id", "").strip() or None
    empleado_id = request.args.get("empleado_id", "").strip() or None

    params = {}
    if insumo_id:
        params["insumo_id"] = insumo_id
    if equipo_id:
        params["equipo_id"] = equipo_id
    if empleado_id:
        params["empleado_id"] = empleado_id

    data, status = api_request("GET", _build_url("/soporte/insumos-consumos", params), token=token)
    consumos = data.get("items", []) if isinstance(data, dict) else []
    total = data.get("total", 0) if isinstance(data, dict) else 0

    # Obtener lista de insumos para el filtro
    insumos_data, _ = api_request("GET", "/soporte/insumos", token=token)
    insumos = insumos_data.get("items", []) if isinstance(insumos_data, dict) else []

    if request.headers.get("HX-Request"):
        return render_template("soporte/partials/consumos_insumo_table.html", consumos=consumos)

    return render_template(
        "soporte/insumos_consumos_list.html",
        consumos=consumos,
        total=total,
        insumos=insumos,
        insumo_id=insumo_id,
        equipo_id=equipo_id,
        empleado_id=empleado_id,
    )


@soporte_bp.route("/insumos/crear", methods=["GET", "POST"])
@require_permiso("soporte.stock_list")
def insumos_create():
    """Crea un nuevo insumo."""
    api_request = get_api_request_func()
    token = session.get("token")

    if request.method == "POST":
        datos = {
            "nombre": request.form.get("nombre", "").strip(),
            "descripcion": request.form.get("descripcion", "").strip() or None,
            "stock_actual": int(request.form.get("stock_actual", 0)),
            "stock_minimo": int(request.form.get("stock_minimo", 0)),
        }

        result, status = api_request("POST", "/soporte/insumos", data=datos, token=token)

        if status in (200, 201):
            if request.headers.get("HX-Request"):
                return "", 200, {"HX-Redirect": url_for("soporte.insumos_list")}
            flash("Insumo creado", "success")
            return redirect(url_for("soporte.insumos_list"))

        error = result.get("detail", "Error al crear insumo") if isinstance(result, dict) else "Error"
        if request.headers.get("HX-Request"):
            return f'<div class="p-4 rounded-xl bg-red-50 text-red-800 border border-red-200 mb-4">{error}</div>'
        return render_template("soporte/insumo_form.html", error=error, item=None)

    return render_template("soporte/insumo_form.html", item=None)


@soporte_bp.route("/insumos/<id>/editar", methods=["GET", "POST"])
@require_permiso("soporte.stock_list")
def insumos_edit(id):
    """Edita un insumo existente."""
    api_request = get_api_request_func()
    token = session.get("token")

    if request.method == "POST":
        datos = {
            "nombre": request.form.get("nombre", "").strip(),
            "descripcion": request.form.get("descripcion", "").strip() or None,
            "stock_minimo": int(request.form.get("stock_minimo", 0)),
        }

        result, status = api_request("PUT", f"/soporte/insumos/{id}", data=datos, token=token)

        if status == 200:
            if request.headers.get("HX-Request"):
                return "", 200, {"HX-Redirect": url_for("soporte.insumos_list")}
            flash("Insumo actualizado", "success")
            return redirect(url_for("soporte.insumos_list"))

        error = result.get("detail", "Error al actualizar insumo") if isinstance(result, dict) else "Error"
        if request.headers.get("HX-Request"):
            return f'<div class="p-4 rounded-xl bg-red-50 text-red-800 border border-red-200 mb-4">{error}</div>'
        return render_template("soporte/insumo_form.html", error=error, item=None)

    # GET: obtener el insumo
    data, status = api_request("GET", f"/soporte/insumos/{id}", token=token)
    if status == 200 and isinstance(data, dict):
        return render_template("soporte/insumo_form.html", item=data)

    flash("Insumo no encontrado", "error")
    return redirect(url_for("soporte.insumos_list"))


@soporte_bp.route("/insumos/<id>/eliminar", methods=["DELETE", "POST"])
@require_permiso("soporte.stock_list")
def insumos_eliminar(id):
    """Elimina un insumo (soft delete)."""
    api_request = get_api_request_func()
    token = session.get("token")

    result, status = api_request("DELETE", f"/soporte/insumos/{id}", token=token)

    if request.headers.get("HX-Request"):
        if status == 200:
            return "", 200, {"HX-Trigger": "insumoDeleted"}
        return '<div class="p-3 bg-red-50 text-red-700 rounded-xl text-sm">Error al eliminar</div>', status

    if status == 200:
        flash("Insumo eliminado", "success")
    else:
        flash("Error al eliminar insumo", "error")
    return redirect(url_for("soporte.insumos_list"))


@soporte_bp.route("/insumos/<id>/ajustar-stock", methods=["POST"])
@require_permiso("soporte.stock_list")
def insumos_ajustar_stock(id):
    """Ajusta el stock de un insumo."""
    api_request = get_api_request_func()
    token = session.get("token")

    datos = {
        "cantidad": int(request.form.get("cantidad", 0)),
        "motivo": request.form.get("motivo", "").strip() or None,
    }

    result, status = api_request("POST", f"/soporte/insumos/{id}/ajustar-stock", data=datos, token=token)

    if request.headers.get("HX-Request"):
        if status == 200:
            return "", 200, {"HX-Trigger": "stockInsumoAjustado"}
        error = result.get("detail", "Error al ajustar stock") if isinstance(result, dict) else "Error"
        return f'<div class="p-3 bg-red-50 text-red-700 rounded-xl text-sm">{error}</div>', status

    if status == 200:
        flash("Stock ajustado", "success")
    else:
        flash("Error al ajustar stock", "error")
    return redirect(url_for("soporte.insumos_list"))


@soporte_bp.route("/insumos/consumos/crear", methods=["GET", "POST"])
@require_permiso("soporte.stock_list")
def insumos_consumos_create():
    """Registra un nuevo consumo de insumo."""
    api_request = get_api_request_func()
    token = session.get("token")

    if request.method == "POST":
        datos = {
            "insumo_id": request.form.get("insumo_id", "").strip(),
            "equipo_id": request.form.get("equipo_id", "").strip() or None,
            "empleado_id": request.form.get("empleado_id", "").strip() or None,
            "cantidad": int(request.form.get("cantidad", 1)),
            "motivo": request.form.get("motivo", "").strip() or None,
        }

        result, status = api_request("POST", "/soporte/insumos-consumos", data=datos, token=token)

        if status in (200, 201):
            if request.headers.get("HX-Request"):
                return "", 200, {"HX-Redirect": url_for("soporte.insumos_consumos_list")}
            flash("Consumo registrado", "success")
            return redirect(url_for("soporte.insumos_consumos_list"))

        error = result.get("detail", "Error al registrar consumo") if isinstance(result, dict) else "Error"
        if request.headers.get("HX-Request"):
            return f'<div class="p-4 rounded-xl bg-red-50 text-red-800 border border-red-200 mb-4">{error}</div>'
        flash(error, "error")

    # GET: obtener listas para los selects
    insumos_data, _ = api_request("GET", "/soporte/insumos", token=token)
    insumos = insumos_data.get("items", []) if isinstance(insumos_data, dict) else []

    stock_data, _ = api_request("GET", "/soporte/activos", token=token)
    equipos = stock_data.get("items", []) if isinstance(stock_data, dict) else []

    empleados_data, _ = api_request("GET", "/soporte/empleados-lista", token=token)
    empleados = empleados_data.get("empleados", []) if isinstance(empleados_data, dict) else []

    return render_template("soporte/insumo_consumo_form.html", insumos=insumos, equipos=equipos, empleados=empleados)


@soporte_bp.route("/insumos/consumos/<id>/eliminar", methods=["DELETE", "POST"])
@require_permiso("soporte.stock_list")
def insumos_consumos_eliminar(id):
    """Anula un consumo de insumo (devuelve stock)."""
    api_request = get_api_request_func()
    token = session.get("token")

    result, status = api_request("DELETE", f"/soporte/insumos-consumos/{id}", token=token)

    if request.headers.get("HX-Request"):
        if status == 200:
            return "", 200, {"HX-Trigger": "consumoDeleted"}
        return '<div class="p-3 bg-red-50 text-red-700 rounded-xl text-sm">Error al anular consumo</div>', status

    if status == 200:
        flash("Consumo anulado, stock devuelto", "success")
    else:
        flash("Error al anular consumo", "error")
    return redirect(url_for("soporte.insumos_consumos_list"))


@soporte_bp.route("/stock/insumos")
@require_permiso("soporte.stock_list")
def stock_insumos():
    """Lista de stock de insumos (periféricos, servidores, impresoras, etc)."""
    api_request = get_api_request_func()
    token = session.get("token")

    tipo = request.args.get("tipo", "").strip() or None
    estado = request.args.get("estado", "").strip() or None
    buscar = request.args.get("buscar", "").strip() or None

    items, stats = _get_stock_data(api_request, token, tipo=tipo, estado=estado, buscar=buscar)

    # Filtrar: excluir notebooks si no se especifica tipo
    if not tipo:
        # Buscar el tipo notebook para excluirlo
        tipo_notebook_clave = "notebook"
        items = [i for i in items if i.get("tipo", "").lower() != tipo_notebook_clave]

    return render_template(
        "soporte/stock.html",
        items=items,
        stats=stats,
        filtro_tipo=tipo,
        filtro_estado=estado,
        buscar=buscar,
        vista="insumos",
    )


@soporte_bp.route("/stock/refacciones")
@require_permiso("soporte.stock_list")
def stock_refacciones():
    """Lista de stock de refacciones y repuestos para reparaciones."""
    api_request = get_api_request_func()
    token = session.get("token")

    estado = request.args.get("estado", "").strip() or None
    buscar = request.args.get("buscar", "").strip() or None

    items, stats = _get_stock_data(api_request, token, tipo="refaccion", estado=estado, buscar=buscar)

    # Obtener notebooks para asignar refacciones
    nb_items, _ = _get_stock_data(api_request, token, tipo="notebook")

    return render_template(
        "soporte/stock.html",
        items=items,
        stats=stats,
        filtro_tipo="refaccion",
        filtro_estado=estado,
        buscar=buscar,
        vista="refacciones",
        notebooks_lista=nb_items,
    )


@soporte_bp.route("/stock/crear", methods=["POST"])
@require_permiso("soporte.stock_list")
def stock_crear():
    """Crea un nuevo activo resolviendo maestros v28.0."""
    api_request = get_api_request_func()
    token = session.get("token")

    # Resolver IDs maestros
    # El formulario ahora envía tipo_id directamente desde el select de Alpine
    tipo_id = request.form.get("tipo_id")

    # Para la marca todavía usamos resolución por nombre si viene del input de texto
    marcas_data, _ = api_request("GET", "/soporte/marcas", token=token)
    marca_nom = request.form.get("marca", "").strip()
    marca_id = _resolve_master_id(marcas_data, marca_nom, "nombre")

    datos = {
        "nombre": request.form.get("nombre", "").strip(),
        "tipo_id": tipo_id,
        "marca_id": marca_id,
        "marca": request.form.get("marca", "").strip() or None,
        "modelo": request.form.get("modelo", "").strip() or None,
        "numero_serie": request.form.get("numero_serie", "").strip() or None,
        "numero_inventario": request.form.get("numero_inventario", "").strip() or None,
        "procesador": request.form.get("procesador", "").strip() or None,
        "memoria": request.form.get("memoria", "").strip() or None,
        "disco_principal": request.form.get("disco_principal", "").strip() or None,
        "disco_secundario": request.form.get("disco_secundario", "").strip() or None,
        "mac_ethernet": request.form.get("mac_ethernet", "").strip() or None,
        "mac_wifi": request.form.get("mac_wifi", "").strip() or None,
        "estado": request.form.get("estado", "disponible"),
        "asignado_id": request.form.get("asignado_id") or None,
        "notas": request.form.get("notas", "").strip() or None,
    }

    result, status = api_request("POST", "/soporte/activos", data=datos, token=token)

    if status in (200, 201):
        flash("Activo registrado", "success")
    else:
        detail = result.get("detail", "Error al crear activo") if isinstance(result, dict) else "Error"
        flash(detail, "error")

    return _redirect_stock()


@soporte_bp.route("/stock/<item_id>/editar", methods=["POST"])
@require_permiso("soporte.stock_list")
def stock_editar(item_id):
    """Actualiza un item de stock."""
    api_request = get_api_request_func()
    token = session.get("token")

    tipo_id = request.form.get("tipo_id", "").strip()

    datos = {
        "nombre": request.form.get("nombre", "").strip(),
        "tipo_id": tipo_id,
        "marca": request.form.get("marca", "").strip() or None,
        "modelo": request.form.get("modelo", "").strip() or None,
        "numero_serie": request.form.get("numero_serie", "").strip() or None,
        "numero_inventario": request.form.get("numero_inventario", "").strip() or None,
        "procesador": request.form.get("procesador", "").strip() or None,
        "memoria": request.form.get("memoria", "").strip() or None,
        "disco_principal": request.form.get("disco_principal", "").strip() or None,
        "disco_secundario": request.form.get("disco_secundario", "").strip() or None,
        "mac_ethernet": request.form.get("mac_ethernet", "").strip() or None,
        "mac_wifi": request.form.get("mac_wifi", "").strip() or None,
        "estado": request.form.get("estado", "disponible"),
        "asignado_id": request.form.get("asignado_id") or None,
        "notas": request.form.get("notas", "").strip() or None,
    }

    result, status = api_request("PUT", f"/soporte/activos/{item_id}", data=datos, token=token)

    if status == 200:
        flash("Item actualizado", "success")
    else:
        detail = result.get("detail", "Error al actualizar") if isinstance(result, dict) else "Error"
        flash(detail, "error")

    return _redirect_stock()


@soporte_bp.route("/stock/<item_id>/cantidad", methods=["POST"])
@require_permiso("soporte.stock_list")
def stock_actualizar_cantidad(item_id):
    """Actualiza la cantidad de un item de stock (HTMX)."""
    api_request = get_api_request_func()
    token = session.get("token")
    incremento = request.args.get("incremento", type=int)

    if incremento is None:
        return "Falta incremento", 400

    result, status = api_request("POST", f"/soporte/activos/{item_id}/cantidad?incremento={incremento}", token=token)

    if status == 200:
        return "", 200
    return "Error", 400


@soporte_bp.route("/stock/<item_id>/eliminar", methods=["POST"])
@require_permiso("soporte.stock_list")
def stock_eliminar(item_id):
    """Elimina un item de stock."""
    api_request = get_api_request_func()
    token = session.get("token")

    result, status = api_request("DELETE", f"/soporte/activos/{item_id}", token=token)

    if status == 200:
        flash("Item eliminado", "success")
    else:
        detail = result.get("detail", "Error al eliminar") if isinstance(result, dict) else "Error"
        flash(detail, "error")

    # Redirigir de vuelta a la última pestaña si es posible
    if request.referrer:
        return redirect(request.referrer)
    return redirect(url_for("soporte.stock_list"))


@soporte_bp.route("/stock/<item_id>/historial", methods=["GET", "POST"])
@require_permiso("soporte.stock_list")
def stock_historial(item_id):
    """Registra un nuevo historial para el item de stock."""
    api_request = get_api_request_func()
    token = session.get("token")

    if request.method == "GET":
        # Cargar los datos del item
        item_data, status = api_request("GET", f"/soporte/activos/{item_id}", token=token)
        if status != 200:
            flash("Error al cargar datos del equipo", "error")
            return redirect(url_for("soporte.stock_list"))

        usuarios_data, _ = api_request("GET", "/soporte/usuarios-lista", token=token)
        usuarios_list = usuarios_data.get("usuarios", []) if isinstance(usuarios_data, dict) else []

        return render_template("soporte/stock_historial_form.html", item=item_data, usuarios_list=usuarios_list)

    token = session.get("token")
    foto_superior = _upload_evidence(request.files.get("foto_superior"), token)
    foto_inferior = _upload_evidence(request.files.get("foto_inferior"), token)
    foto_trasero = _upload_evidence(request.files.get("foto_trasero"), token)
    foto_adicional_1 = _upload_evidence(request.files.get("foto_adicional_1"), token)
    foto_adicional_2 = _upload_evidence(request.files.get("foto_adicional_2"), token)
    foto_acuerdo = _upload_evidence(request.files.get("foto_acuerdo"), token)

    # Listas de fotos para reparaciones
    fotos_factura = _upload_evidence_list(request.files.getlist("foto_factura[]"), token)
    fotos_evidencias = _upload_evidence_list(request.files.getlist("foto_evidencias[]"), token)

    # Si faltan las fotos requeridas mandamos un placeholder vacío que va a fallar en la API o validamos en form.
    # Por ahora simplemente enviamos las URLs

    id_colaborador = request.form.get("colaborador_id") or request.form.get("id_colaborador")  # compat: alias viejo
    if id_colaborador == "":
        id_colaborador = None

    tipo_evento = request.form.get("tipo_evento", "Mantenimiento Preventivo")
    notas_base = request.form.get("notas_adicionales", "").strip()

    # Concatenar campos dinámicos
    notas_agregadas = []
    if tipo_evento == "Alta":
        tecnico = request.form.get("tecnico_entrega", "").strip()
        perifericos = request.form.get("perifericos_entregados", "").strip()
        if tecnico:
            notas_agregadas.append(f"Técnico: {tecnico}")
        if perifericos:
            notas_agregadas.append(f"Periféricos: {perifericos}")
    elif tipo_evento in ["Mantenimiento Preventivo", "Reparacion"]:
        t_mant = request.form.get("tipo_mantenimiento", "").strip()
        trabajo = request.form.get("trabajo_realizado", "").strip()
        if t_mant:
            notas_agregadas.append(f"Tipo: {t_mant}")
        if trabajo:
            notas_agregadas.append(f"Trabajo: {trabajo}")
    # 'Actualizacion Estado' usa notas_adicionales directamente (notas_base)

    if notas_agregadas:
        notas_final = " | ".join(notas_agregadas) + (f"\nNotas: {notas_base}" if notas_base else "")
    else:
        notas_final = notas_base

    payload = {
        "equipo_id": item_id,
        "colaborador_id": id_colaborador,
        "tipo_evento": tipo_evento,
        "notas_adicionales": notas_final or None,
        # Campos de Reparación
        "costo_reparacion": float(request.form.get("costo_reparacion", 0) or 0),
        "matriz_estado": {
            "pantalla": int(request.form.get("estado_pantalla", 1)),
            "carcasa": int(request.form.get("estado_carcasa", 1)),
            "bateria": int(request.form.get("estado_bateria", 1)),
            "puertos": int(request.form.get("estado_puertos", 1)),
            "teclado_trackpad": int(request.form.get("estado_teclado_trackpad", 1)),
            "audio_camara": int(request.form.get("estado_audio_camara", 1)),
        },
        "evidencia_fotografica": {
            "foto_superior": foto_superior or None,
            "foto_inferior": foto_inferior or None,
            "foto_trasero": foto_trasero or None,
            "foto_adicional_1": foto_adicional_1 or None,
            "foto_adicional_2": foto_adicional_2 or None,
            "foto_acuerdo": foto_acuerdo or None,
            "fotos_factura": fotos_factura,
            "fotos_evidencias": fotos_evidencias,
        },
    }

    result, status = api_request("POST", "/soporte/historial", data=payload, token=token)

    if status in (200, 201):
        flash("Historial registrado", "success")
    else:
        detail = result.get("detail", "Error al registrar historial") if isinstance(result, dict) else "Error"
        flash(detail, "error")

    if tipo_evento == "Actualizacion Estado":
        return redirect(url_for("soporte.stock_detalle", item_id=item_id))
    return redirect(url_for("soporte.stock_list"))


@soporte_bp.route("/stock/<item_id>")
@require_permiso("soporte.stock_list")
def stock_detalle(item_id):
    """Página de detalles de un equipo junto con su historial completo."""
    api_request = get_api_request_func()
    token = session.get("token")

    # Obtener el Item Original
    item_data, status = api_request("GET", f"/soporte/activos/{item_id}", token=token)

    if status != 200:
        flash("Equipo no encontrado", "error")
        return redirect(url_for("soporte.stock_list"))

    # Obtener listado de Usuarios activos para renderizar los nombres (responsable IT)
    usuarios_data, _ = api_request("GET", "/soporte/usuarios-lista", token=token)
    usuarios_list = usuarios_data.get("usuarios", []) if isinstance(usuarios_data, dict) else []

    # Crear un diccionario para encontrar nombres por ID rapido (ID_STR > NOMBRE_STR)
    usuarios_map = {str(u["id"]): u["nombre"] for u in usuarios_list}

    # Obtener Historial del item
    historial_data, status_hist = api_request("GET", f"/soporte/activos/{item_id}/historial", token=token)
    historial_list = historial_data if status_hist == 200 and isinstance(historial_data, list) else []

    # Transformar evidencias al formato esperado por el template
    for hist in historial_list:
        if "evidencias" in hist and hist["evidencias"]:
            # Crear estructura evidencia_fotografica
            hist["evidencia_fotografica"] = {"fotos_evidencias": [ev["url"] for ev in hist["evidencias"]]}

    # Extraer último estado de la matriz del historial más reciente
    ultimo_estado = {}
    if historial_list:
        ultimo = historial_list[0]  # Ya viene ordenado por fecha desc
        ultimo_estado = ultimo.get("matriz_estado", {})

    # Obtener ticket_id si viene como parámetro (para pre-cargar estado en reparación)
    ticket_id = request.args.get("ticket_id")

    return render_template(
        "soporte/stock_detalle.html",
        item=item_data,
        historial=historial_list,
        usuarios_map=usuarios_map,
        ticket_id=ticket_id,
        ultimo_estado=ultimo_estado,
    )


@soporte_bp.route("/imprimir-acuerdo")
@require_permiso("soporte.tickets_kanban")
def imprimir_acuerdo():
    """Genera la vista de impresión del Acuerdo de Custodia de Equipos."""
    api_request = get_api_request_func()
    token = session.get("token")

    colaborador_id = request.args.get("colaborador_id")
    equipo_id = request.args.get("equipo_id")

    if not colaborador_id or not equipo_id:
        flash("Faltan parámetros requeridos", "error")
        return redirect(url_for("soporte.stock_list"))

    item_data, dni_colaborador, nombre_colaborador = _get_acuerdo_data(api_request, token, colaborador_id, equipo_id)

    if not item_data:
        flash("Equipo o empleado no encontrado", "error")
        return redirect(url_for("soporte.stock_list"))

    matriz_estado = _get_matriz_estado(request.args)
    entrega_kit = request.args.get("entrega_kit") == "1"

    return render_template(
        "soporte/acuerdo_impresion.html",
        item=item_data,
        colaborador_nombre=nombre_colaborador or "[Nombre y Apellido del Usuario]",
        colaborador_dni=dni_colaborador,
        entrega_kit=entrega_kit,
        matriz_estado=matriz_estado,
        fecha_actual=datetime.now().strftime("%d/%m/%Y"),
    )


@soporte_bp.route("/colaborador-alta-info/<colaborador_id>", methods=["GET"])
@require_permiso("soporte.mis_solicitudes")
def colaborador_alta_info(colaborador_id):
    """Devuelve datos del colaborador para precargar el formulario de alta IT."""
    api_request = get_api_request_func()
    token = session.get("token")
    data, status = api_request("GET", f"/soporte/colaborador-alta-info/{colaborador_id}", token=token)
    return jsonify(data if status == 200 else {}), status


@soporte_bp.route("/sistemas-disponibles", methods=["GET"])
@require_permiso("soporte.mis_solicitudes")
def sistemas_disponibles():
    """Devuelve el catálogo de sistemas habilitables."""
    api_request = get_api_request_func()
    token = session.get("token")
    data, status = api_request("GET", "/soporte/sistemas-disponibles", token=token)
    return jsonify(data if status == 200 else {"sistemas": []}), status


@soporte_bp.route("/imprimir-devolucion")
@require_permiso("soporte.tickets_kanban")
def imprimir_devolucion():
    """Genera la vista de impresión del Acuerdo de Devolución de Equipos."""
    api_request = get_api_request_func()
    token = session.get("token")

    colaborador_id = request.args.get("colaborador_id")
    equipo_id = request.args.get("equipo_id")

    if not colaborador_id or not equipo_id:
        flash("Faltan parámetros requeridos", "error")
        return redirect(url_for("soporte.stock_list"))

    item_data, dni_colaborador, nombre_colaborador = _get_acuerdo_data(api_request, token, colaborador_id, equipo_id)

    if not item_data:
        flash("Equipo o empleado no encontrado", "error")
        return redirect(url_for("soporte.stock_list"))

    matriz_estado = _get_matriz_estado(request.args)
    devuelve_headset = request.args.get("devuelve_headset") == "1"
    devuelve_mouse = request.args.get("devuelve_mouse") == "1"

    return render_template(
        "soporte/acuerdo_devolucion.html",
        item=item_data,
        colaborador_nombre=nombre_colaborador or "[Nombre y Apellido del Usuario]",
        colaborador_dni=dni_colaborador,
        matriz_estado=matriz_estado,
        devuelve_headset=devuelve_headset,
        devuelve_mouse=devuelve_mouse,
        fecha_actual=datetime.now().strftime("%d/%m/%Y"),
    )


@soporte_bp.route("/tickets/<ticket_id>/procesar-alta", methods=["POST"])
@require_permiso("soporte.tickets_kanban")
def procesar_alta_colaborador(ticket_id):
    """Procesa el alta de un colaborador: asigna equipo y genera PDF del acuerdo."""
    api_request = get_api_request_func()
    token = session.get("token")

    # Obtener datos del ticket
    ticket_data, status = api_request("GET", f"/soporte/tickets/{ticket_id}", token=token)
    if status != 200 or not isinstance(ticket_data, dict):
        flash("Ticket no encontrado", "error")
        return redirect(url_for("soporte.tickets_kanban"))

    # Obtener datos del formulario
    equipo_id = request.form.get("equipo_id")
    entrega_kit = request.form.get("entrega_kit") == "1"
    colaborador_id = ticket_data.get("colaborador_id")

    if not equipo_id or not colaborador_id:
        flash("Faltan datos requeridos", "error")
        return redirect(url_for("soporte.detalle_ticket", ticket_id=ticket_id))

    # Crear matriz de estado desde el formulario
    matriz_data = {
        "pantalla": request.form.get("pantalla"),
        "teclado": request.form.get("teclado"),
        "bateria": request.form.get("bateria"),
        "carcasa_superior": request.form.get("carcasa_superior"),
        "carcasa_inferior": request.form.get("carcasa_inferior"),
        "touchpad": request.form.get("touchpad"),
        "puertos": request.form.get("puertos"),
        "cargador": request.form.get("cargador"),
    }

    # Crear matriz de estado en el backend
    matriz_result, matriz_status = api_request("POST", "/soporte/matriz-estado", matriz_data, token=token)
    if matriz_status not in [200, 201]:
        flash("Error al crear matriz de estado", "error")
        return redirect(url_for("soporte.detalle_ticket", ticket_id=ticket_id))

    matriz_id = matriz_result.get("id")

    # Guardar equipo seleccionado y matriz en el ticket (SIN asignar el equipo al colaborador todavía)
    # La asignación real ocurre cuando el ticket se resuelve
    ticket_update = {"activo_id": equipo_id, "matriz_estado_id": matriz_id, "entrega_kit_bienvenida": entrega_kit}
    update_result, update_status = api_request("PUT", f"/soporte/tickets/{ticket_id}", ticket_update, token=token)

    if update_status not in [200, 201]:
        error_msg = (
            update_result.get("detail", "Error desconocido") if isinstance(update_result, dict) else str(update_result)
        )
        flash(f"Error al guardar datos del ticket: {error_msg}", "error")
        return redirect(url_for("soporte.tickets_kanban"))

    # Redirigir a la impresión del acuerdo
    return redirect(
        url_for(
            "soporte.imprimir_acuerdo",
            colaborador_id=colaborador_id,
            equipo_id=equipo_id,
            entrega_kit="1" if entrega_kit else "0",
            **{f"st_{k}": v for k, v in matriz_data.items()},
        )
    )


@soporte_bp.route("/tickets/<ticket_id>/procesar-baja", methods=["POST"])
@require_permiso("soporte.tickets_kanban")
def procesar_baja_colaborador(ticket_id):
    """Procesa la baja de un colaborador: guarda datos en el ticket y genera acta de devolución."""
    api_request = get_api_request_func()
    token = session.get("token")

    # Obtener datos del ticket
    ticket_data, status = api_request("GET", f"/soporte/tickets/{ticket_id}", token=token)
    if status != 200 or not isinstance(ticket_data, dict):
        flash("Ticket no encontrado", "error")
        return redirect(url_for("soporte.tickets_kanban"))

    colaborador_id = ticket_data.get("colaborador_id")
    if not colaborador_id:
        flash("El ticket no tiene colaborador asociado", "error")
        return redirect(url_for("soporte.detalle_ticket", ticket_id=ticket_id))

    # Buscar el equipo asignado al colaborador
    activos_data, _ = api_request("GET", f"/soporte/activos?asignado_id={colaborador_id}", token=token)
    activos = activos_data.get("items", []) if isinstance(activos_data, dict) else []

    if not activos:
        flash("El colaborador no tiene equipos asignados", "error")
        return redirect(url_for("soporte.detalle_ticket", ticket_id=ticket_id))

    equipo = activos[0]
    equipo_id = equipo.get("id")

    # Crear matriz de estado de devolución
    matriz_data = {
        "pantalla": request.form.get("pantalla"),
        "teclado": request.form.get("teclado"),
        "bateria": request.form.get("bateria"),
        "carcasa_superior": request.form.get("carcasa_superior"),
        "carcasa_inferior": request.form.get("carcasa_inferior"),
        "touchpad": request.form.get("touchpad"),
        "puertos": request.form.get("puertos"),
        "cargador": request.form.get("cargador"),
    }

    matriz_result, matriz_status = api_request("POST", "/soporte/matriz-estado", matriz_data, token=token)
    if matriz_status not in [200, 201]:
        flash("Error al crear matriz de estado", "error")
        return redirect(url_for("soporte.detalle_ticket", ticket_id=ticket_id))

    matriz_id = matriz_result.get("id")

    # Guardar equipo y matriz en el ticket (SIN desasignar todavía, eso ocurre al resolver)
    ticket_update = {"activo_id": equipo_id, "matriz_estado_id": matriz_id}
    update_result, update_status = api_request("PUT", f"/soporte/tickets/{ticket_id}", ticket_update, token=token)
    if update_status not in [200, 201]:
        error_msg = (
            update_result.get("detail", "Error desconocido") if isinstance(update_result, dict) else str(update_result)
        )
        flash(f"Error al guardar datos del ticket: {error_msg}", "error")
        return redirect(url_for("soporte.tickets_kanban"))

    # Obtener datos de periféricos devueltos
    devuelve_headset = request.form.get("devuelve_headset") == "1"
    devuelve_mouse = request.form.get("devuelve_mouse") == "1"

    # Redirigir a la impresión del acta de devolución
    return redirect(
        url_for(
            "soporte.imprimir_devolucion",
            colaborador_id=colaborador_id,
            equipo_id=equipo_id,
            devuelve_headset="1" if devuelve_headset else "0",
            devuelve_mouse="1" if devuelve_mouse else "0",
            **{f"st_{k}": v for k, v in matriz_data.items()},
        )
    )


# ─── Categorías ────────────────────────────────────────────────────


@soporte_bp.route("/categorias")
@require_permiso("soporte.tickets_kanban")
def listar_categorias():
    """Lista categorías con subcategorías (HTMX partial)."""
    api_request = get_api_request_func()
    token = session.get("token")

    data, status = api_request("GET", "/soporte/categorias", token=token)

    if status != 200:
        if request.headers.get("HX-Request"):
            return '<div class="p-4 text-red-600">Error al cargar categorías</div>', 500
        flash("Error al cargar categorías", "error")
        return redirect(url_for("soporte.tickets_kanban"))

    categorias = data.get("categorias", []) if isinstance(data, dict) else []

    if request.headers.get("HX-Request"):
        return render_template(
            "soporte/partials/categorias_table.html",
            categorias=categorias,
            tipos_ticket=_get_tipos_ticket(api_request, token),
        )

    # No existe template standalone, redirigir a tickets
    return redirect(url_for("soporte.tickets_kanban"))


@soporte_bp.route("/categorias/crear", methods=["POST"])
@require_permiso("soporte.tickets_kanban")
def crear_categoria():
    """Crea una nueva categoría."""
    api_request = get_api_request_func()
    token = session.get("token")

    nombre = request.form.get("nombre", "").strip()
    parent_id = request.form.get("parent_id") or None
    tipo_ticket_asociado = request.form.get("tipo_ticket_asociado", "generico").strip()

    if not nombre:
        if request.headers.get("HX-Request"):
            return error_html("El nombre es obligatorio")
        flash("El nombre es obligatorio", "error")
        return redirect(url_for("soporte.tickets_kanban"))

    data = {"nombre": nombre, "tipo_ticket_asociado": tipo_ticket_asociado}
    if parent_id:
        data["parent_id"] = parent_id

    result, status = api_request("POST", "/soporte/categorias", data=data, token=token)

    if status in [200, 201]:
        if request.headers.get("HX-Request"):
            return "", 200, {"HX-Trigger": "categoriaCreated"}
        flash("Categoría creada", "success")
    else:
        error = format_api_error(result.get("detail"), "Error al crear categoría")
        if request.headers.get("HX-Request"):
            return error_html(error)
        flash(error, "error")

    return redirect(url_for("soporte.tickets_kanban"))


@soporte_bp.route("/categorias/<categoria_id>/editar", methods=["POST", "PUT"])
@require_permiso("soporte.tickets_kanban")
def editar_categoria(categoria_id):
    """Edita una categoría existente."""
    api_request = get_api_request_func()
    token = session.get("token")

    nombre = request.form.get("nombre", "").strip()
    tipo_ticket_asociado = request.form.get("tipo_ticket_asociado", "generico").strip()

    if not nombre:
        if request.headers.get("HX-Request"):
            return error_html("El nombre es obligatorio")
        flash("El nombre es obligatorio", "error")
        return redirect(url_for("soporte.tickets_kanban"))

    data = {"nombre": nombre, "tipo_ticket_asociado": tipo_ticket_asociado}

    result, status = api_request("PUT", f"/soporte/categorias/{categoria_id}", data=data, token=token)

    if status == 200:
        if request.headers.get("HX-Request"):
            return "", 200, {"HX-Trigger": "categoriaUpdated"}
        flash("Categoría actualizada", "success")
    else:
        error = format_api_error(result.get("detail"), "Error al actualizar categoría")
        if request.headers.get("HX-Request"):
            return error_html(error)
        flash(error, "error")

    return redirect(url_for("soporte.tickets_kanban"))


@soporte_bp.route("/categorias/<categoria_id>/eliminar", methods=["DELETE", "POST"])
@require_permiso("soporte.tickets_kanban")
def eliminar_categoria(categoria_id):
    """Elimina una categoría."""
    api_request = get_api_request_func()
    token = session.get("token")

    result, status = api_request("DELETE", f"/soporte/categorias/{categoria_id}", token=token)

    if status == 200:
        if request.headers.get("HX-Request"):
            return "", 200, {"HX-Trigger": "categoriaDeleted"}
        flash("Categoría eliminada", "success")
    else:
        error = format_api_error(result.get("detail"), "Error al eliminar categoría")
        if request.headers.get("HX-Request"):
            return error_html(error)
        flash(error, "error")

    return redirect(url_for("soporte.tickets_kanban"))


@soporte_bp.route("/categorias-api")
@require_permiso("soporte.mis_solicitudes")
def categorias_api():
    """API proxy para obtener categorías filtradas por permisos del usuario."""
    api_request = get_api_request_func()
    token = session.get("token")

    data, status = api_request("GET", "/soporte/categorias-disponibles", token=token)

    if status == 200:
        return jsonify(data)
    else:
        return jsonify({"categorias": [], "error": "No se pudieron cargar las categorías"}), status


@soporte_bp.route("/valores-matriz-api")
@require_permiso("soporte.stock_list")
def valores_matriz_api():
    """API proxy para obtener valores de matriz de estado (usado por JavaScript)."""
    api_request = get_api_request_func()
    token = session.get("token")

    data, status = api_request("GET", "/soporte/valores-matriz", token=token)

    if status == 200:
        return jsonify(data)
    else:
        return jsonify({"valores": [], "error": "No se pudieron cargar los valores de matriz"}), status


@soporte_bp.route("/buscar-equipo-disponible")
@require_permiso("soporte.mis_solicitudes")
def buscar_equipo_disponible():
    """Proxy para buscar equipos disponibles (usado por JS vanilla en el modal)."""
    api_request = get_api_request_func()
    token = session.get("token")

    q = request.args.get("q", "").strip()
    if not q or len(q) < 2:
        return jsonify([])

    data, status = api_request("GET", f"/soporte/activos/disponibles/buscar?q={q}", token=token)
    if status == 200:
        return jsonify(data)
    return jsonify([])


# ─── Evidencias de Acuerdo Firmado ─────────────────────────────────


@soporte_bp.route("/tickets/<ticket_id>/subir-acuerdo", methods=["POST"])
@require_permiso("soporte.tickets_kanban")
def subir_imagen_acuerdo(ticket_id):
    """Sube una imagen del acuerdo firmado al ticket de alta."""
    import httpx
    from flask import current_app

    token = session.get("token")
    file = request.files.get("archivo")

    if not file:
        if request.headers.get("HX-Request"):
            return '<div class="p-3 rounded-lg bg-red-50 text-red-700 text-sm">Seleccioná un archivo</div>', 400
        flash("Seleccioná un archivo", "error")
        return redirect(url_for("soporte.detalle_ticket", ticket_id=ticket_id))

    api_url = current_app.config["API_URL"]
    url = f"{api_url}/api/v1/soporte/tickets/{ticket_id}/imagen?categoria=acuerdo_firmado"

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                url,
                headers={"Authorization": f"Bearer {token}"},
                files={"file": (file.filename, file.stream, file.content_type)},
            )

        if resp.status_code in (200, 201):
            if request.headers.get("HX-Request"):
                # Recargar la sección de evidencias
                return _render_evidencias_acuerdo(ticket_id)
            flash("Imagen del acuerdo subida correctamente", "success")
        else:
            error_detail = (
                resp.json().get("detail", "Error al subir imagen")
                if resp.headers.get("content-type", "").startswith("application/json")
                else "Error al subir imagen"
            )
            if request.headers.get("HX-Request"):
                return f'<div class="p-3 rounded-lg bg-red-50 text-red-700 text-sm">{error_detail}</div>', 400
            flash(error_detail, "error")
    except Exception as e:
        if request.headers.get("HX-Request"):
            return f'<div class="p-3 rounded-lg bg-red-50 text-red-700 text-sm">Error: {str(e)}</div>', 500
        flash(f"Error al subir imagen: {str(e)}", "error")

    return redirect(url_for("soporte.detalle_ticket", ticket_id=ticket_id))


@soporte_bp.route("/tickets/<ticket_id>/eliminar-evidencia/<evidencia_id>", methods=["DELETE", "POST"])
@require_permiso("soporte.tickets_kanban")
def eliminar_evidencia_acuerdo(ticket_id, evidencia_id):
    """Elimina una evidencia del acuerdo firmado."""
    api_request = get_api_request_func()
    token = session.get("token")

    result, status = api_request("DELETE", f"/soporte/tickets/{ticket_id}/evidencia/{evidencia_id}", token=token)

    if status == 200:
        if request.headers.get("HX-Request"):
            return _render_evidencias_acuerdo(ticket_id)
        flash("Evidencia eliminada", "success")
    else:
        error = result.get("detail", "Error al eliminar evidencia")
        if request.headers.get("HX-Request"):
            return f'<div class="p-3 rounded-lg bg-red-50 text-red-700 text-sm">{error}</div>', 400
        flash(error, "error")

    return redirect(url_for("soporte.detalle_ticket", ticket_id=ticket_id))


def _render_evidencias_acuerdo(ticket_id):
    """Helper: renderiza el partial de evidencias del acuerdo para HTMX swap."""
    api_request = get_api_request_func()
    token = session.get("token")

    data, status = api_request("GET", f"/soporte/tickets/{ticket_id}", token=token)
    if status != 200:
        return '<div class="p-3 text-red-600 text-sm">Error al recargar evidencias</div>', 500

    evidencias_acuerdo = [e for e in data.get("evidencias", []) if e.get("categoria") == "acuerdo_firmado"]
    return render_template(
        "soporte/partials/evidencias_acuerdo.html", ticket=data, evidencias_acuerdo=evidencias_acuerdo
    )


# ─── Pedidos de Compra ─────────────────────────────────────────────


@soporte_bp.route("/pedidos")
@require_permiso("soporte.tickets_kanban")
def pedidos_list():
    """Listado de pedidos de compra."""
    api_request = get_api_request_func()
    token = session.get("token")

    estado = request.args.get("estado", "")
    params = {"estado": estado} if estado else {}

    data, _ = api_request("GET", _build_url("/soporte/pedidos", params), token=token)
    pedidos = data.get("items", []) if isinstance(data, dict) else []

    if request.headers.get("HX-Request"):
        return render_template("soporte/partials/pedidos_table.html", pedidos=pedidos)

    return render_template("soporte/pedidos.html", pedidos=pedidos, filtro_estado=estado)


@soporte_bp.route("/pedidos/<pedido_id>")
@require_permiso("soporte.tickets_kanban")
def pedido_detalle(pedido_id):
    """Detalle de un pedido de compra (partial HTMX o página completa)."""
    api_request = get_api_request_func()
    token = session.get("token")

    data, status = api_request("GET", f"/soporte/pedidos/{pedido_id}", token=token)
    if status != 200:
        if request.headers.get("HX-Request"):
            return '<div class="p-4 text-red-600">Pedido no encontrado</div>', 404
        flash("Pedido no encontrado", "error")
        return redirect(url_for("soporte.pedidos_list"))

    return render_template("soporte/partials/pedido_detalle.html", pedido=data)


@soporte_bp.route("/pedidos/<pedido_id>/estado", methods=["POST"])
@require_permiso("soporte.tickets_kanban")
def cambiar_estado_pedido(pedido_id):
    """Cambia el estado de un pedido (enviar a aprobación, cancelar)."""
    api_request = get_api_request_func()
    token = session.get("token")

    estado = request.form.get("estado")
    result, status = api_request("PUT", f"/soporte/pedidos/{pedido_id}/estado", data={"estado": estado}, token=token)

    if status == 200:
        if request.headers.get("HX-Request"):
            # Cerrar el modal del pedido y refrescar el kanban/tabla
            response = current_app.response_class(response="", status=200)
            response.headers["HX-Trigger"] = "pedidoEnviado,ticketEstadoCambiado"
            response.headers["HX-Reswap"] = "none"
            return response
        flash("Estado del pedido actualizado", "success")
    else:
        error = format_api_error(result.get("detail"), "Error al cambiar estado")
        if request.headers.get("HX-Request"):
            return error_html(error), 400
        flash(error, "error")

    return redirect(url_for("soporte.pedidos_list"))


@soporte_bp.route("/pedidos/<pedido_id>/presupuestos/<presupuesto_id>/seleccionar", methods=["POST"])
@require_permiso("soporte.tickets_kanban")
def seleccionar_presupuesto(pedido_id, presupuesto_id):
    """Marca un presupuesto como el elegido por el técnico."""
    api_request = get_api_request_func()
    token = session.get("token")

    result, status = api_request(
        "PUT", f"/soporte/pedidos/{pedido_id}/presupuestos/{presupuesto_id}/seleccionar", token=token
    )

    if status == 200:
        if request.headers.get("HX-Request"):
            data, _ = api_request("GET", f"/soporte/pedidos/{pedido_id}", token=token)
            return render_template("soporte/partials/pedido_detalle.html", pedido=data)
        flash("Presupuesto seleccionado", "success")
    else:
        error = format_api_error(result.get("detail"), "Error al seleccionar presupuesto")
        if request.headers.get("HX-Request"):
            return error_html(error), 400
        flash(error, "error")

    return redirect(url_for("soporte.pedidos_list"))


@soporte_bp.route("/pedidos/<pedido_id>/presupuesto", methods=["POST"])
@require_permiso("soporte.tickets_kanban")
def agregar_presupuesto(pedido_id):
    """Agrega un presupuesto a un pedido de compra."""
    api_request = get_api_request_func()
    token = session.get("token")
    api_url = current_app.config["API_URL"]

    proveedor = request.form.get("proveedor", "").strip() or None
    articulo_descripcion = request.form.get("articulo_descripcion", "").strip() or None
    monto_raw = request.form.get("monto", "").strip()
    monto = float(monto_raw) if monto_raw else None

    archivo = request.files.get("archivo")

    try:
        import httpx

        with httpx.Client(timeout=30.0) as client:
            files = {}
            if archivo and archivo.filename:
                files["archivo"] = (archivo.filename, archivo.read(), archivo.content_type)

            resp = client.post(
                f"{api_url}/api/v1/soporte/pedidos/{pedido_id}/presupuestos",
                headers={"Authorization": f"Bearer {token}"},
                data={
                    "proveedor": proveedor or "",
                    "articulo_descripcion": articulo_descripcion or "",
                    "monto": str(monto) if monto is not None else "",
                    "es_obligatorio": "true",
                },
                files=files if files else None,
            )
            status = resp.status_code
            result = resp.json() if resp.content else {}
    except Exception as e:
        result = {"detail": str(e)}
        status = 500

    if status in (200, 201):
        if request.headers.get("HX-Request"):
            # Recargar el detalle del pedido
            data, _ = api_request("GET", f"/soporte/pedidos/{pedido_id}", token=token)
            return render_template("soporte/partials/pedido_detalle.html", pedido=data)
        flash("Presupuesto agregado", "success")
    else:
        error = format_api_error(result.get("detail"), "Error al agregar presupuesto")
        if request.headers.get("HX-Request"):
            return error_html(error), 400
        flash(error, "error")

    return redirect(url_for("soporte.pedidos_list"))


# ─── Checklist Alta/Baja ───────────────────────────────────────────


@soporte_bp.route("/tickets/<ticket_id>/checklist")
@require_permiso("soporte.tickets_kanban")
def obtener_checklist(ticket_id):
    api_request = get_api_request_func()
    token = session.get("token")
    data, status = api_request("GET", f"/soporte/tickets/{ticket_id}/checklist", token=token)
    return jsonify(data if status == 200 else {"items": []}), status


@soporte_bp.route("/checklist/<item_id>/toggle", methods=["PUT", "POST"])
@require_permiso("soporte.tickets_kanban")
def toggle_checklist_item(item_id):
    api_request = get_api_request_func()
    token = session.get("token")
    result, status = api_request("PUT", f"/soporte/checklist/{item_id}/toggle", token=token)
    return jsonify(result if status == 200 else {}), status


@soporte_bp.route("/insumos-api")
@require_permiso("soporte.stock_list")
def insumos_api():
    """Devuelve insumos como JSON para selects dinamicos."""
    api_request = get_api_request_func()
    token = session.get("token")
    data, status = api_request("GET", "/soporte/insumos", token=token)
    items = data.get("items", []) if isinstance(data, dict) else []
    return jsonify({"items": items}), status
