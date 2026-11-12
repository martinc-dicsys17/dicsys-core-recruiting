"""
Administración → Proveedores (F18): registro, Evaluación de Proveedores y
Configuración (de la evaluación).

Las páginas son Alpine y hablan con la API a través de relays JSON de este
módulo: cada relay exige el permiso de su pantalla y usa api_request, que
reenvía la IP y el navegador del usuario para la auditoría del backend.
"""

from urllib.parse import quote

import httpx
from flask import Response, current_app, flash, jsonify, redirect, render_template, request, session, url_for

from modulos.administracion.app_module import administracion_bp
from modulos.auth_helpers import get_api_request_func, require_permiso
from modulos.error_helpers import format_api_error

require_proveedores = require_permiso("admin_contable.proveedores")
require_evaluacion = require_permiso("admin_contable.evaluacion_proveedores")
require_config = require_permiso("admin_contable.evaluacion_config")

# Rutas de la API de evaluación que usa cada pantalla
RUTAS_TABLERO = ("tablero", "items", "candidatos")  # items: evaluar (PUT items/<id>) y agregar (POST items)
RUTAS_CONFIG = ("configuracion", "evaluaciones", "importaciones", "seguimiento", "avisos", "autogeneracion")


def _relay(endpoint: str, fallback: str):
    """Pasa el pedido JSON a la API con el token de la sesión y devuelve su respuesta."""
    api_request = get_api_request_func()
    if request.query_string:
        endpoint = f"{endpoint}?{request.query_string.decode()}"
    datos = request.get_json(silent=True) if request.method in ("POST", "PUT") else None
    resultado, status = api_request(request.method, endpoint, datos, token=session.get("token"))
    if status and status < 400:
        return jsonify(resultado), status
    detalle = resultado.get("detail") if isinstance(resultado, dict) else None
    return jsonify({"detail": format_api_error(detalle, fallback)}), status or 500


def _permitida(ruta: str, prefijos) -> bool:
    return any(ruta == p.rstrip("/") or ruta.startswith(p.rstrip("/") + "/") for p in prefijos)


def _cabeceras() -> dict:
    """Las mismas que api_request, para los pedidos que no son JSON (adjunto)."""
    cabeceras = {"Authorization": f"Bearer {session.get('token', '')}"}
    if request.remote_addr:
        cabeceras["X-Cliente-IP"] = request.remote_addr
    if request.headers.get("User-Agent"):
        cabeceras["X-Cliente-User-Agent"] = request.headers["User-Agent"][:500]
    return cabeceras


# ─── Páginas ────────────────────────────────────────────────────────────────────


@administracion_bp.route("/proveedores")
@require_proveedores
def proveedores_list():
    return render_template("administracion/proveedores_list.html")


def _proveedor(proveedor_id):
    """Ficha del proveedor desde la API, o None si no existe (o es de otra empresa)."""
    item, status = get_api_request_func()("GET", f"/proveedores/{quote(proveedor_id)}", token=session.get("token"))
    return item if status == 200 and isinstance(item, dict) else None


# Como Nómina → Empleados: vista y edición en páginas completas
@administracion_bp.route("/proveedores/<proveedor_id>")
@require_proveedores
def proveedores_view(proveedor_id):
    item = _proveedor(proveedor_id)
    if item is None:
        flash("Proveedor no encontrado", "error")
        return redirect(url_for("administracion.proveedores_list"))
    if request.args.get("ok") == "guardado":
        flash("Proveedor actualizado", "success")
    return render_template("administracion/proveedores_view.html", item=item)


@administracion_bp.route("/proveedores/nuevo")
@require_proveedores
def proveedores_create():
    return render_template("administracion/proveedores_form.html", item=None)


PESTANAS_EDICION = ("datos", "contacto", "seguridad", "oficinas", "contactos", "documentos")
AVISOS_EDICION = {
    "creado": "Proveedor creado. Ahora podés cargar oficinas, contactos y documentos.",
    "oficina": "Oficina guardada",
    "contacto": "Contacto guardado",
}


@administracion_bp.route("/proveedores/<proveedor_id>/editar")
@require_proveedores
def proveedores_edit(proveedor_id):
    item = _proveedor(proveedor_id)
    if item is None:
        flash("Proveedor no encontrado", "error")
        return redirect(url_for("administracion.proveedores_list"))
    if request.args.get("ok") in AVISOS_EDICION:
        flash(AVISOS_EDICION[request.args["ok"]], "success")
    tab = request.args.get("tab") if request.args.get("tab") in PESTANAS_EDICION else "datos"
    return render_template("administracion/proveedores_form.html", item=item, tab=tab)


def _de_la_ficha(item, coleccion, hijo_id):
    return next((h for h in item.get(coleccion) or [] if str(h.get("id")) == hijo_id), None)


# Oficinas y contactos: alta y edición en su propia página, como el domicilio en Clientes
@administracion_bp.route("/proveedores/<proveedor_id>/oficinas/nueva", endpoint="proveedores_oficina_form")
@administracion_bp.route(
    "/proveedores/<proveedor_id>/oficinas/<oficina_id>/editar", endpoint="proveedores_oficina_form"
)
@require_proveedores
def proveedores_oficina_form(proveedor_id, oficina_id=None):
    return _pagina_hijo(proveedor_id, "oficinas", oficina_id, "oficina", "Oficina no encontrada")


@administracion_bp.route("/proveedores/<proveedor_id>/contactos/nuevo", endpoint="proveedores_contacto_form")
@administracion_bp.route(
    "/proveedores/<proveedor_id>/contactos/<contacto_id>/editar", endpoint="proveedores_contacto_form"
)
@require_proveedores
def proveedores_contacto_form(proveedor_id, contacto_id=None):
    return _pagina_hijo(proveedor_id, "contactos", contacto_id, "contacto", "Contacto no encontrado")


def _pagina_hijo(proveedor_id, coleccion, hijo_id, nombre, no_encontrado):
    item = _proveedor(proveedor_id)
    if item is None:
        flash("Proveedor no encontrado", "error")
        return redirect(url_for("administracion.proveedores_list"))
    volver = url_for("administracion.proveedores_edit", proveedor_id=item["id"], tab=coleccion)
    hijo = None
    if hijo_id:
        hijo = _de_la_ficha(item, coleccion, hijo_id)
        if hijo is None:
            flash(no_encontrado, "error")
            return redirect(volver)
    return render_template(f"administracion/proveedores_{nombre}_form.html", item=item, volver=volver, **{nombre: hijo})


@administracion_bp.route("/evaluaciones-proveedores")
@require_evaluacion
def evaluaciones_proveedores():
    return render_template("administracion/evaluaciones_proveedores.html")


def _evaluacion_item(item_id):
    """(evaluación completa, mensaje de error) desde la API: solo para el admin o el referente."""
    item, status = get_api_request_func()(
        "GET", f"/evaluaciones-proveedores/items/{quote(item_id)}", token=session.get("token")
    )
    if status == 200 and isinstance(item, dict):
        return item, None
    detalle = item.get("detail") if isinstance(item, dict) else None
    return None, format_api_error(detalle, "Evaluación no encontrada")


@administracion_bp.route("/evaluaciones-proveedores/<item_id>")
@require_evaluacion
def evaluaciones_proveedores_item(item_id):
    item, error = _evaluacion_item(item_id)
    if item is None:
        flash(error, "error")
        return redirect(url_for("administracion.evaluaciones_proveedores"))
    if request.args.get("ok") == "guardado":
        flash(f"Evaluación de «{item['proveedor']['nombre']}» guardada", "success")
    return render_template("administracion/evaluacion_proveedor_view.html", item=item)


@administracion_bp.route("/evaluaciones-proveedores/<item_id>/editar")
@require_evaluacion
def evaluaciones_proveedores_item_edit(item_id):
    item, error = _evaluacion_item(item_id)
    if item is None:
        flash(error, "error")
        return redirect(url_for("administracion.evaluaciones_proveedores"))
    if not item.get("puede_editar"):
        flash(
            "Esta evaluación no se puede editar: solo el usuario referente o el admin, con la evaluación abierta",
            "error",
        )
        return redirect(url_for("administracion.evaluaciones_proveedores_item", item_id=item_id))
    return render_template("administracion/evaluacion_proveedor_form.html", item=item)


PESTANAS_CONFIG = ("evaluaciones", "autogeneracion", "seguimiento", "fuente", "recordatorios", "canales")


@administracion_bp.route("/config-evaluaciones-proveedores")
@require_config
def config_evaluaciones_proveedores():
    tab = request.args.get("tab") if request.args.get("tab") in PESTANAS_CONFIG else "evaluaciones"
    return render_template("administracion/config_evaluaciones_proveedores.html", tab=tab)


@administracion_bp.route("/config-evaluaciones-proveedores/importar")
@require_config
def config_evaluaciones_proveedores_importar():
    """Importación del Sheet en su propia página: vista previa y confirmación."""
    return render_template("administracion/config_evaluaciones_importar.html")


# ─── Relays JSON ────────────────────────────────────────────────────────────────


@administracion_bp.route("/proveedores/api", methods=["GET", "POST"])
@administracion_bp.route("/proveedores/api/<path:ruta>", methods=["GET", "POST", "PUT", "DELETE"])
@require_proveedores
def proveedores_api(ruta=""):
    return _relay(f"/proveedores/{ruta}".rstrip("/"), "Error en el registro de proveedores")


@administracion_bp.route("/evaluaciones-proveedores/api/<path:ruta>", methods=["GET", "POST", "PUT"])
@require_evaluacion
def evaluaciones_proveedores_api(ruta):
    if not _permitida(ruta, RUTAS_TABLERO):
        return jsonify({"detail": "Ruta no disponible"}), 404
    return _relay(f"/evaluaciones-proveedores/{ruta}", "Error en la evaluación de proveedores")


@administracion_bp.route("/config-evaluaciones-proveedores/api/<path:ruta>", methods=["GET", "POST", "PUT", "DELETE"])
@require_config
def config_evaluaciones_proveedores_api(ruta):
    if not _permitida(ruta, RUTAS_CONFIG):
        return jsonify({"detail": "Ruta no disponible"}), 404
    return _relay(f"/evaluaciones-proveedores/{ruta}", "Error en la configuración de evaluaciones")


# ─── Adjunto de política/NDA (multipart y binario) ─────────────────────────────


def _respuesta_json(respuesta, fallback: str):
    try:
        cuerpo = respuesta.json()
    except ValueError:
        cuerpo = {}
    if respuesta.status_code < 400:
        return jsonify(cuerpo), respuesta.status_code
    return jsonify({"detail": format_api_error(cuerpo.get("detail"), fallback)}), respuesta.status_code


@administracion_bp.route("/proveedores/nuevo/con-adjunto", methods=["POST"])
@require_proveedores
def proveedores_alta_con_adjunto():
    """Alta con acuerdo firmado: los datos (JSON) y el adjunto viajan juntos a la API."""
    archivo = request.files.get("archivo")
    if archivo is None:
        return jsonify({"detail": "Con acuerdo de servicio firmado hay que adjuntar el archivo del acuerdo / NDA"}), 422
    url = f"{current_app.config['API_URL']}/api/v1/proveedores/con-adjunto"
    try:
        with httpx.Client(timeout=60.0) as cliente:
            respuesta = cliente.post(
                url,
                headers=_cabeceras(),
                data={"datos": request.form.get("datos", "{}")},
                files={
                    "archivo": (archivo.filename, archivo.read(), archivo.content_type or "application/octet-stream")
                },
            )
    except httpx.HTTPError:
        return jsonify({"detail": "Error de comunicación con el servidor"}), 502
    return _respuesta_json(respuesta, "Error al crear el proveedor")


def _archivo_del_backend(url: str):
    """Pasa un archivo binario de la API (descarga o miniatura) con sus cabeceras."""
    try:
        with httpx.Client(timeout=60.0) as cliente:
            respuesta = cliente.get(url, headers=_cabeceras())
    except httpx.HTTPError:
        return jsonify({"detail": "Error de comunicación con el servidor"}), 502
    if respuesta.status_code != 200:
        return _respuesta_json(respuesta, "No se encontró el archivo")
    cabeceras = {
        k: respuesta.headers[k]
        for k in ("Content-Disposition", "Cache-Control", "X-Content-Type-Options")
        if k in respuesta.headers
    }
    return Response(
        respuesta.content,
        status=200,
        headers=cabeceras,
        content_type=respuesta.headers.get("content-type", "application/octet-stream"),
    )


def _url_documentos(proveedor_id: str, *partes: str) -> str:
    sufijo = "".join(f"/{quote(p)}" for p in partes)
    return f"{current_app.config['API_URL']}/api/v1/proveedores/{quote(proveedor_id)}/documentos{sufijo}"


@administracion_bp.route("/proveedores/<proveedor_id>/documentos", methods=["POST"])
@require_proveedores
def proveedores_documentos_subir(proveedor_id):
    """Uno o varios documentos (campo `archivos`): la API los valida, los sube y arma las miniaturas."""
    archivos = request.files.getlist("archivos")
    if not archivos:
        return jsonify({"detail": "Elegí al menos un archivo"}), 422
    try:
        # Varios archivos de hasta 10 MB, cada uno con su miniatura
        with httpx.Client(timeout=120.0) as cliente:
            respuesta = cliente.post(
                _url_documentos(proveedor_id),
                headers=_cabeceras(),
                files=[
                    ("archivos", (a.filename, a.read(), a.content_type or "application/octet-stream")) for a in archivos
                ],
            )
    except httpx.HTTPError:
        return jsonify({"detail": "Error de comunicación con el servidor"}), 502
    return _respuesta_json(respuesta, "Error al subir los documentos")


@administracion_bp.route("/proveedores/<proveedor_id>/documentos/<documento_id>")
@require_proveedores
def proveedores_documento_descargar(proveedor_id, documento_id):
    return _archivo_del_backend(_url_documentos(proveedor_id, documento_id))


@administracion_bp.route("/proveedores/<proveedor_id>/documentos/<documento_id>/miniatura")
@require_proveedores
def proveedores_documento_miniatura(proveedor_id, documento_id):
    return _archivo_del_backend(_url_documentos(proveedor_id, documento_id, "miniatura"))


@administracion_bp.route("/proveedores/<proveedor_id>/nda", methods=["GET", "POST"])
@require_proveedores
def proveedores_nda(proveedor_id):
    url = f"{current_app.config['API_URL']}/api/v1/proveedores/{quote(proveedor_id)}/nda"
    try:
        with httpx.Client(timeout=60.0) as cliente:
            if request.method == "POST":
                archivo = request.files.get("archivo")
                if archivo is None:
                    return jsonify({"detail": "Elegí un archivo"}), 422
                respuesta = cliente.post(
                    url,
                    headers=_cabeceras(),
                    files={
                        "archivo": (
                            archivo.filename,
                            archivo.read(),
                            archivo.content_type or "application/octet-stream",
                        )
                    },
                )
            else:
                respuesta = cliente.get(url, headers=_cabeceras())
    except httpx.HTTPError:
        return jsonify({"detail": "Error de comunicación con el servidor"}), 502

    if request.method == "GET" and respuesta.status_code == 200:
        cabeceras = {
            k: respuesta.headers[k]
            for k in ("Content-Disposition", "Cache-Control", "X-Content-Type-Options")
            if k in respuesta.headers
        }
        return Response(
            respuesta.content,
            status=200,
            headers=cabeceras,
            content_type=respuesta.headers.get("content-type", "application/octet-stream"),
        )
    return _respuesta_json(respuesta, "Error con el adjunto")
