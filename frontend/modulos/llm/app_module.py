"""
Módulo LLM Usage - Dashboard de uso de modelos de lenguaje (Gemini).
Acceso restringido al submódulo 'configuracion.llm'.

Vistas:
- llm.usage    : dashboard de resumen por mes y módulo (acordeón expandible).
- llm.requests : tabla detallada de core_llm_requests con filtros, orden y paginación.
- llm.raw      : sirve el raw request/response de un registro.
"""

import logging
from urllib.parse import urlencode

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from modulos.auth_helpers import get_api_request_func, require_permiso
from modulos.error_helpers import format_api_error

logger = logging.getLogger(__name__)

llm_bp = Blueprint("llm", __name__, template_folder="templates", url_prefix="/llm")

# Todas las rutas requieren permiso 'configuracion.llm'.
login_required = require_permiso("configuracion.llm")


# ─── DASHBOARD: RESUMEN POR MES Y MÓDULO ──────────────────────────────────────


@llm_bp.route("")
@login_required
def usage():
    api_request = get_api_request_func()
    token = session.get("token")

    periodo = request.args.get("periodo", "")
    params = f"?periodo={periodo}" if periodo else ""

    data, status = api_request("GET", f"/llm/usage{params}", token=token)
    if not isinstance(data, dict):
        data = {}

    return render_template(
        "llm/usage.html",
        periodos_disponibles=data.get("periodos_disponibles", []),
        periodos=data.get("periodos", []),
        total_requests=data.get("total_requests", 0),
        total_tokens=data.get("total_tokens", 0),
        total_costo_usd=data.get("total_costo_usd", 0),
        periodo=periodo,
    )


@llm_bp.route("/example-call", methods=["POST"])
@login_required
def example_call():
    api_request = get_api_request_func()
    token = session.get("token")

    data, status = api_request("POST", "/llm/example-call", token=token)
    if status == 200 and isinstance(data, dict):
        result = data.get("result") or {}
        texto = (result.get("text") or "").strip() or "(sin texto)"
        modelo = result.get("model_name") or "-"
        flash(f"Llamada de ejemplo ejecutada con {modelo}. Respuesta: {texto}", "success")
        return redirect(url_for("llm.usage"))

    detalle = data.get("detail") if isinstance(data, dict) else None
    flash(format_api_error(detalle, "Error al ejecutar la llamada de ejemplo"), "error")
    return redirect(url_for("llm.usage"))


# ─── TABLA DETALLADA ──────────────────────────────────────────────────────────

_FILTROS = (
    "buscar",
    "modulo",
    "periodo",
    "model_name",
    "status",
    "fecha_desde",
    "fecha_hasta",
    "orden_por",
    "orden_dir",
)


@llm_bp.route("/requests")
@login_required
def requests_list():
    api_request = get_api_request_func()
    token = session.get("token")

    pagina = request.args.get("pagina", 1, type=int)
    por_pagina = request.args.get("por_pagina", 20, type=int)

    query = {"pagina": pagina, "por_pagina": por_pagina}
    for f in _FILTROS:
        valor = request.args.get(f, "").strip()
        if valor:
            query[f] = valor

    data, status = api_request("GET", f"/llm/requests?{urlencode(query)}", token=token)
    if not isinstance(data, dict):
        data = {}

    ctx = {
        "items": data.get("items", []),
        "total": data.get("total", 0),
        "pagina": data.get("pagina", pagina),
        "por_pagina": data.get("por_pagina", por_pagina),
        "total_paginas": data.get("total_paginas", 1),
        "filtros": {f: request.args.get(f, "") for f in _FILTROS},
        "orden_por": request.args.get("orden_por", "created_at"),
        "orden_dir": request.args.get("orden_dir", "desc"),
    }

    if request.headers.get("HX-Request"):
        return render_template("llm/partials/table.html", **ctx)

    return render_template("llm/requests.html", **ctx)


# ─── RAW REQUEST / RESPONSE ───────────────────────────────────────────────────


@llm_bp.route("/requests/<id>/raw/<tipo>")
@login_required
def raw(id, tipo):
    if tipo not in ("request", "response"):
        abort(404)
    api_request = get_api_request_func()
    token = session.get("token")

    data, status = api_request("GET", f"/llm/requests/{id}/raw/{tipo}", token=token)
    if status != 200:
        abort(404)

    import json

    if isinstance(data, str):
        contenido = data
    else:
        contenido = json.dumps(data, ensure_ascii=False, indent=2)
    return render_template(
        "llm/partials/raw_viewer.html",
        contenido=contenido,
        tipo=tipo,
        request_id=id,
    )
