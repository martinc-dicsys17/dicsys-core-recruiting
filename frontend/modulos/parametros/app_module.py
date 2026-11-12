"""
Módulo Parámetros - Configuración de parámetros del sistema.
Acceso restringido al submódulo 'configuracion.parametros'.

Vistas:
- parametros.listar        : UI principal con tabla agrupada por categoría y edición inline del valor.
- parametros.editar        : edición de la definición de un parámetro (modal HTMX).
- parametros.editar_valor  : edición inline del valor (HTMX).
- parametros.eliminar      : soft delete (HTMX).

Nota: base.html fuerza el swap también en respuestas 4xx, por eso los errores
devuelven la tabla re-renderizada + toast (si no, el target quedaría vacío).
"""

import json
import logging
from collections import OrderedDict
from urllib.parse import urlencode

from flask import Blueprint, render_template, request, session

from modulos.auth_helpers import get_api_request_func, require_permiso
from modulos.error_helpers import error_html

logger = logging.getLogger(__name__)

parametros_bp = Blueprint("parametros", __name__, template_folder="templates", url_prefix="/parametros")

# Todas las rutas requieren permiso 'configuracion.parametros'.
login_required = require_permiso("configuracion.parametros")


def _toast_success(mensaje):
    """Script que dispara un toast de éxito (sistema global de Alpine.js)."""
    msg = mensaje.replace("\\", "\\\\").replace("'", "\\'")
    return f"""
    <script>
    (function() {{
        if (typeof Alpine !== 'undefined' && Alpine.store('toasts')) {{
            Alpine.store('toasts').success('{msg}', 4000);
        }}
    }})();
    </script>
    """


def _detalle(result):
    """Extrae el detail de una respuesta de la API de forma segura."""
    return result.get("detail") if isinstance(result, dict) else None


def _agrupar(items):
    """Agrupa los parámetros por categoría → subcategoría (preserva el orden del backend)."""
    grupos = OrderedDict()
    for p in items:
        cat = p.get("categoria") or "Sin categoría"
        sub = p.get("subcategoria") or ""
        grupos.setdefault(cat, OrderedDict()).setdefault(sub, []).append(p)
    return grupos


def _obtener_listado(api_request, token):
    """Obtiene el listado desde la API aplicando los filtros del request actual."""
    query = {"por_pagina": 100}  # todos en una página: la pantalla los agrupa por categoría
    for f in ("buscar", "categoria"):
        valor = request.values.get(f, "").strip()
        if valor:
            query[f] = valor

    endpoint = f"/parametros?{urlencode(query)}"

    data, _ = api_request("GET", endpoint, token=token)
    if not isinstance(data, dict):
        data = {}

    return {
        "grupos": _agrupar(data.get("items", [])),
        "total": data.get("total", 0),
        "categorias": data.get("categorias", []),
        "filtros": {f: request.values.get(f, "") for f in ("buscar", "categoria")},
    }


def _render_tabla(api_request, token):
    """Re-renderiza el partial de la tabla con los filtros actuales."""
    ctx = _obtener_listado(api_request, token)
    return render_template("parametros/partials/tabla.html", **ctx)


def _form_data():
    """Arma el payload de creación/edición desde el form."""
    return {
        "categoria": request.form.get("categoria"),
        "subcategoria": request.form.get("subcategoria") or None,
        "nombre": request.form.get("nombre"),
        "key": request.form.get("key"),
        "descripcion": request.form.get("descripcion") or None,
        "valor_default": request.form.get("valor_default") or None,
        "valor": request.form.get("valor") or None,
    }


# ─── UI PRINCIPAL: LISTADO + CREAR ───────────────────────────────────────────


@parametros_bp.route("", methods=["GET", "POST"])
@login_required
def listar():
    api_request = get_api_request_func()
    token = session.get("token")

    # POST: crear nuevo parámetro (modal HTMX)
    if request.method == "POST":
        result, status = api_request("POST", "/parametros", _form_data(), token=token)

        if status in (200, 201):
            return _render_tabla(api_request, token) + _toast_success("Parámetro creado")

        return _render_tabla(api_request, token) + error_html(_detalle(result), "Error al crear el parámetro"), 400

    # GET
    ctx = _obtener_listado(api_request, token)
    if request.headers.get("HX-Request"):
        return render_template("parametros/partials/tabla.html", **ctx)
    return render_template("parametros/list.html", **ctx)


# ─── EDITAR DEFINICIÓN (MODAL) ───────────────────────────────────────────────


@parametros_bp.route("/<id>/editar", methods=["GET", "POST"])
@login_required
def editar(id):
    api_request = get_api_request_func()
    token = session.get("token")

    if request.method == "POST":
        result, status = api_request("PUT", f"/parametros/{id}", _form_data(), token=token)

        if status == 200:
            # refrescar tabla, cerrar el modal y avisar
            return (
                _render_tabla(api_request, token)
                + '<script>document.getElementById("modal-editar").innerHTML = "";</script>'
                + _toast_success("Parámetro actualizado")
            )

        return _render_tabla(api_request, token) + error_html(_detalle(result), "Error al actualizar el parámetro"), 400

    # GET: devolver el modal de edición
    parametro, status = api_request("GET", f"/parametros/{id}", token=token)
    if status != 200 or not isinstance(parametro, dict) or "id" not in parametro:
        return error_html("Parámetro no encontrado"), 404

    return render_template("parametros/partials/form_editar.html", p=parametro)


# ─── EDITAR VALOR INLINE ─────────────────────────────────────────────────────


@parametros_bp.route("/<id>/valor", methods=["POST"])
@login_required
def editar_valor(id):
    api_request = get_api_request_func()
    token = session.get("token")

    if request.form.get("restaurar") == "1":
        valor = None
        mensaje = "Valor restaurado al default"
    else:
        valor = request.form.get("valor") or None
        mensaje = "Valor actualizado"

    result, status = api_request("PUT", f"/parametros/{id}/valor", {"valor": valor}, token=token)

    if status == 200:
        return _render_tabla(api_request, token) + _toast_success(mensaje)

    return _render_tabla(api_request, token) + error_html(_detalle(result), "Error al actualizar el valor"), 400


# ─── SELECTOR DE ESPACIOS WEBEX (multi-opción) ───────────────────────────────


@parametros_bp.route("/<id>/webex-espacios", methods=["GET"])
@login_required
def webex_espacios(id):
    """Modal multi-select: lista los espacios del team (API) y marca los elegidos."""
    api_request = get_api_request_func()
    token = session.get("token")

    parametro, st = api_request("GET", f"/parametros/{id}", token=token)
    if st != 200 or not isinstance(parametro, dict) or "id" not in parametro:
        return error_html("Parámetro no encontrado"), 404

    # Selección actual: ids ya guardados (para pre-marcar y como fallback).
    seleccion = []
    try:
        seleccion = [e for e in json.loads(parametro.get("valor") or "[]") if isinstance(e, dict) and e.get("id")]
    except ValueError, TypeError:
        seleccion = []
    seleccion_ids = {e["id"] for e in seleccion}

    # Lista completa desde la API de Webex (con timeout en el backend).
    data, _ = api_request("GET", "/parametros/webex-rooms", token=token)
    api_ok = isinstance(data, dict) and data.get("success")
    rooms = data.get("rooms", []) if isinstance(data, dict) else []
    api_error = (data.get("error") if isinstance(data, dict) else None) or "No se pudo conectar con Webex"

    # Fallback: si la API falla, mostramos al menos lo ya seleccionado.
    if not api_ok and not rooms:
        rooms = seleccion

    return render_template(
        "parametros/partials/webex_espacios_modal.html",
        p=parametro,
        rooms=rooms,
        seleccion_ids=seleccion_ids,
        api_ok=api_ok,
        api_error=api_error,
    )


@parametros_bp.route("/<id>/webex-espacios", methods=["POST"])
@login_required
def guardar_webex_espacios(id):
    """Guarda la selección (JSON [{id, nombre}]) en el valor del parámetro."""
    api_request = get_api_request_func()
    token = session.get("token")

    seleccion = []
    for raw in request.form.getlist("espacio"):
        try:
            e = json.loads(raw)
        except ValueError, TypeError:
            continue
        if isinstance(e, dict) and e.get("id"):
            seleccion.append({"id": e["id"], "nombre": e.get("nombre")})

    valor = json.dumps(seleccion, ensure_ascii=False)
    result, status = api_request("PUT", f"/parametros/{id}/valor", {"valor": valor}, token=token)

    if status == 200:
        return (
            _render_tabla(api_request, token)
            + '<script>document.getElementById("modal-editar").innerHTML = "";</script>'
            + _toast_success(f"{len(seleccion)} espacio(s) seleccionado(s)")
        )

    return _render_tabla(api_request, token) + error_html(_detalle(result), "Error al guardar los espacios"), 400


# ─── ELIMINAR ────────────────────────────────────────────────────────────────


@parametros_bp.route("/<id>/eliminar", methods=["DELETE"])
@login_required
def eliminar(id):
    api_request = get_api_request_func()
    token = session.get("token")

    result, status = api_request("DELETE", f"/parametros/{id}", token=token)

    if status == 200:
        return _render_tabla(api_request, token) + _toast_success("Parámetro eliminado")

    return _render_tabla(api_request, token) + error_html(_detalle(result), "Error al eliminar el parámetro"), 400
