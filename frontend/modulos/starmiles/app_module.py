"""
Módulo Star Miles - Blueprint Flask
Sistema de millas para empleados
"""

from urllib.parse import quote

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from modulos.auth_helpers import get_api_request_func, require_permiso
from modulos.error_helpers import error_html, format_api_error

starmiles_bp = Blueprint("starmiles", __name__, template_folder="templates", url_prefix="/starmiles")


# ============ HOME / PORTAL ============


@starmiles_bp.route("")
@require_permiso("starmiles.home")
def home():
    """Página principal con noticias y banners."""
    api_request = get_api_request_func()
    token = session.get("token")

    # Cargar contenido CMS visible
    cms_data, _ = api_request("GET", "/starmiles/cms?solo_visibles=true", token=token)
    contenidos = cms_data.get("items", []) if isinstance(cms_data, dict) else []

    # Separar por tipo (solo banners y noticias)
    banners = [c for c in contenidos if c.get("tipo") == "banner"]
    noticias = [c for c in contenidos if c.get("tipo") == "noticia"]

    # Cargar mis millas si tengo empleado_id
    mis_millas = None
    empleado_id = session.get("user", {}).get("empleado_id")
    tiene_empleado = bool(empleado_id)

    if empleado_id:
        millas_data, status = api_request("GET", f"/starmiles/mis-millas/{empleado_id}", token=token)
        if status == 200:
            mis_millas = millas_data

    return render_template(
        "starmiles/home.html", banners=banners, noticias=noticias, mis_millas=mis_millas, tiene_empleado=tiene_empleado
    )


# ============ DESAFIOS ============


@starmiles_bp.route("/desafios")
@require_permiso("starmiles.home")
def desafios_list():
    """Lista de desafíos disponibles."""
    api_request = get_api_request_func()
    token = session.get("token")

    buscar = request.args.get("search", "")
    categoria_id = request.args.get("categoria_id", "")
    alcance = request.args.get("alcance", "")
    ordenar_por = request.args.get("ordenar_por", "")
    ordenar_dir = request.args.get("ordenar_dir", "asc")
    solo_vigentes = request.args.get("solo_vigentes", "true") == "true"

    pagina = request.args.get("pagina", 1, type=int)
    por_pagina = 20

    params = f"?solo_vigentes={str(solo_vigentes).lower()}&pagina={pagina}&por_pagina={por_pagina}"
    if buscar:
        params += f"&buscar={quote(buscar)}"
    if categoria_id:
        params += f"&categoria_id={categoria_id}"
    if alcance:
        params += f"&alcance={quote(alcance)}"
    if ordenar_por:
        params += f"&ordenar_por={ordenar_por}&ordenar_dir={ordenar_dir}"

    data, _ = api_request("GET", f"/starmiles/desafios{params}", token=token)
    desafios = data.get("items", []) if isinstance(data, dict) else []
    total = data.get("total", 0) if isinstance(data, dict) else 0
    total_paginas = data.get("total_paginas", 1) if isinstance(data, dict) else 1

    # Cargar categorías para filtro
    cat_data, _ = api_request("GET", "/starmiles/categorias", token=token)
    categorias = cat_data if isinstance(cat_data, list) else []

    # Cargar alcances únicos para filtro
    alcances_data, _ = api_request("GET", "/starmiles/desafios-alcances", token=token)
    alcances = alcances_data if isinstance(alcances_data, list) else []

    # Mis inscripciones
    empleado_id = session.get("user", {}).get("empleado_id")
    mis_inscripciones = []
    if empleado_id:
        insc_data, _ = api_request("GET", f"/starmiles/inscripciones?empleado_id={empleado_id}", token=token)
        mis_inscripciones = insc_data.get("items", []) if isinstance(insc_data, dict) else []

    # IDs de desafíos donde ya estoy inscripto
    desafios_inscriptos = {i["desafio_id"] for i in mis_inscripciones if i["estado"] in ["pendiente", "aprobada"]}

    paginacion = {
        "pagina": pagina,
        "total_paginas": total_paginas,
        "total": total,
    }

    if request.headers.get("HX-Request"):
        return render_template(
            "starmiles/partials/desafios_content.html",
            desafios=desafios,
            desafios_inscriptos=desafios_inscriptos,
            **paginacion,
        )

    return render_template(
        "starmiles/desafios_list.html",
        desafios=desafios,
        categorias=categorias,
        alcances=alcances,
        desafios_inscriptos=desafios_inscriptos,
        **paginacion,
    )


@starmiles_bp.route("/desafios/<id>/inscribir", methods=["POST"])
@require_permiso("starmiles.home")
def inscribir_desafio(id):
    """Inscribirse a un desafío."""
    api_request = get_api_request_func()
    token = session.get("token")
    empleado_id = session.get("user", {}).get("empleado_id")

    if not empleado_id:
        if request.headers.get("HX-Request"):
            return '<div class="p-4 bg-red-50 text-red-700 rounded-xl">No tenés un empleado asociado</div>', 400
        flash("No tenés un empleado asociado", "error")
        return redirect(url_for("starmiles.desafios_list"))

    data = {"desafio_id": id, "comentario_solicitud": request.form.get("comentario", "")}

    result, status = api_request("POST", f"/starmiles/inscripciones?empleado_id={empleado_id}", data, token=token)

    if status in [200, 201]:
        flash("Inscripción enviada", "success")
        if request.headers.get("HX-Request"):
            return "", 200, {"HX-Redirect": url_for("starmiles.desafios_list")}
    else:
        err_block = error_html(result.get("detail"), "Error al inscribirse")
        if request.headers.get("HX-Request"):
            return err_block, 400
        flash(format_api_error(result.get("detail"), "Error al inscribirse"), "error")

    return redirect(url_for("starmiles.desafios_list"))


# ============ MIS INSCRIPCIONES ============


@starmiles_bp.route("/mis-inscripciones")
@require_permiso("starmiles.home")
def mis_inscripciones():
    """Mis inscripciones a desafíos."""
    api_request = get_api_request_func()
    token = session.get("token")
    empleado_id = session.get("user", {}).get("empleado_id")

    inscripciones = []
    if empleado_id:
        data, _ = api_request("GET", f"/starmiles/inscripciones?empleado_id={empleado_id}", token=token)
        inscripciones = data.get("items", []) if isinstance(data, dict) else []

    return render_template("starmiles/mis_inscripciones.html", inscripciones=inscripciones)


# ============ CANJES ============


@starmiles_bp.route("/canjes")
@require_permiso("starmiles.home")
def canjes_list():
    """Catálogo de items para canjear."""
    api_request = get_api_request_func()
    token = session.get("token")

    buscar = request.args.get("search", "")
    params = "?solo_activos=true"
    if buscar:
        params += f"&buscar={buscar}"

    data, _ = api_request("GET", f"/starmiles/items-canje{params}", token=token)
    items = data.get("items", []) if isinstance(data, dict) else []

    # Mis millas
    mis_millas = None
    empleado_id = session.get("user", {}).get("empleado_id")
    if empleado_id:
        millas_data, status = api_request("GET", f"/starmiles/mis-millas/{empleado_id}", token=token)
        if status == 200:
            mis_millas = millas_data

    if request.headers.get("HX-Request"):
        return render_template("starmiles/partials/canjes_grid.html", items=items, mis_millas=mis_millas)

    return render_template("starmiles/canjes_list.html", items=items, mis_millas=mis_millas)


@starmiles_bp.route("/canjes/<id>/canjear", methods=["POST"])
@require_permiso("starmiles.home")
def canjear_item(id):
    """Solicitar canje de un item."""
    api_request = get_api_request_func()
    token = session.get("token")
    empleado_id = session.get("user", {}).get("empleado_id")

    if not empleado_id:
        if request.headers.get("HX-Request"):
            return '<div class="p-4 bg-red-50 text-red-700 rounded-xl">No tenés un empleado asociado</div>', 400
        flash("No tenés un empleado asociado", "error")
        return redirect(url_for("starmiles.canjes_list"))

    data = {
        "item_id": id,
        "cantidad": int(request.form.get("cantidad", 1)),
        "comentario": request.form.get("comentario", ""),
    }

    # Agregar datos de MercadoLibre si vienen
    ml_url = request.form.get("mercadolibre_url")
    star_miles_calc = request.form.get("star_miles_calculado")
    ml_precio = request.form.get("mercadolibre_precio")

    if ml_url:
        data["mercadolibre_url"] = ml_url
    if star_miles_calc:
        data["star_miles_calculado"] = int(star_miles_calc)
    if ml_precio:
        data["mercadolibre_precio"] = float(ml_precio)

    result, status = api_request("POST", f"/starmiles/canjes?empleado_id={empleado_id}", data, token=token)

    if status in [200, 201]:
        flash("Canje solicitado", "success")
        if request.headers.get("HX-Request"):
            return "", 200, {"HX-Redirect": url_for("starmiles.canjes_list")}
    else:
        err_block = error_html(result.get("detail"), "Error al canjear")
        if request.headers.get("HX-Request"):
            return err_block, 400
        flash(format_api_error(result.get("detail"), "Error al canjear"), "error")

    return redirect(url_for("starmiles.canjes_list"))


@starmiles_bp.route("/mercadolibre/precio")
@require_permiso("starmiles.home")
def mercadolibre_precio():
    """Proxy para consultar precio de MercadoLibre desde el frontend."""
    api_request = get_api_request_func()
    token = session.get("token")

    url = request.args.get("url", "")
    if not url:
        return {"error": "URL requerida"}, 400

    result, status = api_request("GET", f"/starmiles/mercadolibre/precio?url={url}", token=token)

    if status == 200:
        return result
    else:
        error = result.get("detail", "Error al consultar MercadoLibre")
        return {"error": format_api_error(error)}, status


@starmiles_bp.route("/calcular-millas", methods=["POST"])
@require_permiso("starmiles.home")
def calcular_millas():
    """Calcula Star Miles desde precio en pesos usando cotización del dólar."""
    api_request = get_api_request_func()
    token = session.get("token")

    data = request.get_json()
    if not data or not data.get("precio"):
        return {"error": "Precio requerido"}, 400

    result, status = api_request("POST", "/starmiles/calcular-millas", data, token=token)

    if status == 200:
        return result
    else:
        error = result.get("detail", "Error al calcular millas")
        return {"error": format_api_error(error)}, status


# ============ MIS CANJES ============


@starmiles_bp.route("/mis-canjes")
@require_permiso("starmiles.home")
def mis_canjes():
    """Mis solicitudes de canje."""
    api_request = get_api_request_func()
    token = session.get("token")
    empleado_id = session.get("user", {}).get("empleado_id")

    canjes = []
    if empleado_id:
        data, _ = api_request("GET", f"/starmiles/canjes?empleado_id={empleado_id}", token=token)
        canjes = data.get("items", []) if isinstance(data, dict) else []

    return render_template("starmiles/mis_canjes.html", canjes=canjes)


# ============ ADMIN: DESAFIOS ============


@starmiles_bp.route("/admin/desafios")
@require_permiso("starmiles.admin_desafios")
def admin_desafios():
    """ABM de desafíos (admin)."""
    api_request = get_api_request_func()
    token = session.get("token")

    buscar = request.args.get("buscar", "")
    categoria_id = request.args.get("categoria_id", "")
    por_pagina = request.args.get("por_pagina", "100")

    params = f"?por_pagina={por_pagina}"
    if buscar:
        params += f"&buscar={quote(buscar)}"
    if categoria_id:
        params += f"&categoria_id={categoria_id}"

    data, _ = api_request("GET", f"/starmiles/desafios{params}", token=token)
    desafios = data.get("items", []) if isinstance(data, dict) else []

    cat_data, _ = api_request("GET", "/starmiles/categorias", token=token)
    categorias = cat_data if isinstance(cat_data, list) else []

    if request.headers.get("HX-Request"):
        return render_template("starmiles/partials/admin_desafios_table.html", desafios=desafios)

    return render_template("starmiles/admin_desafios.html", desafios=desafios, categorias=categorias)


@starmiles_bp.route("/admin/desafios/nuevo", methods=["GET", "POST"])
@require_permiso("starmiles.admin_desafios")
def admin_desafio_crear():
    """Crear desafío."""
    api_request = get_api_request_func()
    token = session.get("token")

    if request.method == "POST":
        data = {
            "nombre": request.form.get("nombre"),
            "descripcion": request.form.get("descripcion") or None,
            "alcance": request.form.get("alcance") or None,
            "star_miles": int(request.form.get("star_miles", 0)),
            "categoria_id": request.form.get("categoria_id") or None,
            "fecha_inicio": request.form.get("fecha_inicio") or None,
            "fecha_vencimiento": request.form.get("fecha_vencimiento") or None,
            "activo": request.form.get("activo") == "on",
            "inscripcion_unica_por_empleado": request.form.get("inscripcion_unica_por_empleado") == "on",
            "imagen_url": request.form.get("imagen_url") or None,
        }

        result, status = api_request("POST", "/starmiles/desafios", data, token=token)

        if status in [200, 201]:
            flash("Desafío creado", "success")
            if request.headers.get("HX-Request"):
                return "", 200, {"HX-Redirect": url_for("starmiles.admin_desafios")}
            return redirect(url_for("starmiles.admin_desafios"))

        err_block = error_html(result.get("detail"), "Error al crear")
        if request.headers.get("HX-Request"):
            return err_block
        flash(format_api_error(result.get("detail"), "Error al crear"), "error")

    cat_data, _ = api_request("GET", "/starmiles/categorias", token=token)
    categorias = cat_data if isinstance(cat_data, list) else []

    return render_template("starmiles/desafio_form.html", desafio=None, categorias=categorias)


@starmiles_bp.route("/admin/desafios/<id>/editar", methods=["GET", "POST"])
@require_permiso("starmiles.admin_desafios")
def admin_desafio_editar(id):
    """Editar desafío."""
    api_request = get_api_request_func()
    token = session.get("token")

    if request.method == "POST":
        data = {
            "nombre": request.form.get("nombre"),
            "descripcion": request.form.get("descripcion") or None,
            "alcance": request.form.get("alcance") or None,
            "star_miles": int(request.form.get("star_miles", 0)),
            "categoria_id": request.form.get("categoria_id") or None,
            "fecha_inicio": request.form.get("fecha_inicio") or None,
            "fecha_vencimiento": request.form.get("fecha_vencimiento") or None,
            "activo": request.form.get("activo") == "on",
            "inscripcion_unica_por_empleado": request.form.get("inscripcion_unica_por_empleado") == "on",
            "imagen_url": request.form.get("imagen_url") or None,
        }

        result, status = api_request("PUT", f"/starmiles/desafios/{id}", data, token=token)

        if status == 200:
            flash("Desafío actualizado", "success")
            if request.headers.get("HX-Request"):
                return "", 200, {"HX-Redirect": url_for("starmiles.admin_desafios")}
            return redirect(url_for("starmiles.admin_desafios"))

        err_block = error_html(result.get("detail"), "Error al actualizar")
        if request.headers.get("HX-Request"):
            return err_block
        flash(format_api_error(result.get("detail"), "Error al actualizar"), "error")

    desafio, _ = api_request("GET", f"/starmiles/desafios/{id}", token=token)
    cat_data, _ = api_request("GET", "/starmiles/categorias", token=token)
    categorias = cat_data if isinstance(cat_data, list) else []

    return render_template("starmiles/desafio_form.html", desafio=desafio, categorias=categorias)


@starmiles_bp.route("/admin/desafios/<id>/eliminar", methods=["DELETE"])
@require_permiso("starmiles.admin_desafios")
def admin_desafio_eliminar(id):
    """Eliminar desafío."""
    api_request = get_api_request_func()
    token = session.get("token")
    result, status = api_request("DELETE", f"/starmiles/desafios/{id}", token=token)

    if status == 200:
        return "", 200, {"HX-Trigger": "desafioDeleted"}
    return error_html(result.get("detail"), "Error al eliminar"), 400


# ============ ADMIN: ITEMS CANJE ============


@starmiles_bp.route("/admin/items-canje")
@require_permiso("starmiles.admin_canjes")
def admin_items_canje():
    """ABM de items de canje (admin)."""
    api_request = get_api_request_func()
    token = session.get("token")

    data, _ = api_request("GET", "/starmiles/items-canje", token=token)
    items = data.get("items", []) if isinstance(data, dict) else []

    if request.headers.get("HX-Request"):
        return render_template("starmiles/partials/admin_items_table.html", items=items)

    return render_template("starmiles/admin_items_canje.html", items=items)


@starmiles_bp.route("/admin/items-canje/nuevo", methods=["GET", "POST"])
@require_permiso("starmiles.admin_canjes")
def admin_item_crear():
    """Crear item de canje."""
    api_request = get_api_request_func()
    token = session.get("token")

    if request.method == "POST":
        stock_val = request.form.get("stock")
        star_miles_val = request.form.get("star_miles_costo")
        data = {
            "tipo": request.form.get("tipo", "producto"),
            "nombre": request.form.get("nombre"),
            "descripcion": request.form.get("descripcion") or None,
            "star_miles_costo": int(star_miles_val) if star_miles_val else None,
            "stock": int(stock_val) if stock_val else None,
            "imagen_url": request.form.get("imagen_url") or None,
            "activo": request.form.get("activo") == "on",
        }

        result, status = api_request("POST", "/starmiles/items-canje", data, token=token)

        if status in [200, 201]:
            flash("Item creado", "success")
            if request.headers.get("HX-Request"):
                return "", 200, {"HX-Redirect": url_for("starmiles.admin_items_canje")}
            return redirect(url_for("starmiles.admin_items_canje"))

        err_block = error_html(result.get("detail"), "Error al crear")
        if request.headers.get("HX-Request"):
            return err_block
        flash(format_api_error(result.get("detail"), "Error al crear"), "error")

    return render_template("starmiles/item_canje_form.html", item=None)


@starmiles_bp.route("/admin/items-canje/<id>/editar", methods=["GET", "POST"])
@require_permiso("starmiles.admin_canjes")
def admin_item_editar(id):
    """Editar item de canje."""
    api_request = get_api_request_func()
    token = session.get("token")

    if request.method == "POST":
        stock_val = request.form.get("stock")
        star_miles_val = request.form.get("star_miles_costo")
        data = {
            "tipo": request.form.get("tipo", "producto"),
            "nombre": request.form.get("nombre"),
            "descripcion": request.form.get("descripcion") or None,
            "star_miles_costo": int(star_miles_val) if star_miles_val else None,
            "stock": int(stock_val) if stock_val else None,
            "imagen_url": request.form.get("imagen_url") or None,
            "activo": request.form.get("activo") == "on",
        }

        result, status = api_request("PUT", f"/starmiles/items-canje/{id}", data, token=token)

        if status == 200:
            flash("Item actualizado", "success")
            if request.headers.get("HX-Request"):
                return "", 200, {"HX-Redirect": url_for("starmiles.admin_items_canje")}
            return redirect(url_for("starmiles.admin_items_canje"))

        err_block = error_html(result.get("detail"), "Error al actualizar")
        if request.headers.get("HX-Request"):
            return err_block
        flash(format_api_error(result.get("detail"), "Error al actualizar"), "error")

    item, _ = api_request("GET", f"/starmiles/items-canje/{id}", token=token)
    return render_template("starmiles/item_canje_form.html", item=item)


@starmiles_bp.route("/admin/items-canje/<id>/eliminar", methods=["DELETE"])
@require_permiso("starmiles.admin_canjes")
def admin_item_eliminar(id):
    """Eliminar item de canje."""
    api_request = get_api_request_func()
    token = session.get("token")
    result, status = api_request("DELETE", f"/starmiles/items-canje/{id}", token=token)

    if status == 200:
        return "", 200, {"HX-Trigger": "itemDeleted"}
    return error_html(result.get("detail"), "Error al eliminar"), 400


# ============ APROBADOR: INSCRIPCIONES ============


@starmiles_bp.route("/aprobador/inscripciones")
@require_permiso("starmiles.aprobar_inscripciones")
def aprobador_inscripciones():
    """Lista de inscripciones pendientes (aprobador)."""
    api_request = get_api_request_func()
    token = session.get("token")

    estado = request.args.get("estado", "pendiente")
    pagina = request.args.get("pagina", 1, type=int)
    por_pagina = 20
    buscar = request.args.get("buscar", "").strip()
    desafio_id = request.args.get("desafio_id", "").strip()
    fecha_desde = request.args.get("fecha_desde", "").strip()
    fecha_hasta = request.args.get("fecha_hasta", "").strip()

    params = f"?estado={quote(estado)}&pagina={pagina}&por_pagina={por_pagina}"
    if buscar:
        params += f"&buscar={quote(buscar)}"
    if desafio_id:
        params += f"&desafio_id={quote(desafio_id)}"
    if fecha_desde:
        params += f"&fecha_desde={quote(fecha_desde)}"
    if fecha_hasta:
        params += f"&fecha_hasta={quote(fecha_hasta)}"

    data, _ = api_request("GET", f"/starmiles/inscripciones{params}", token=token)
    inscripciones = data.get("items", []) if isinstance(data, dict) else []
    paginacion = {
        "pagina": data.get("pagina", pagina) if isinstance(data, dict) else pagina,
        "total_paginas": data.get("total_paginas", 1) if isinstance(data, dict) else 1,
        "total": data.get("total", 0) if isinstance(data, dict) else 0,
        "por_pagina": por_pagina,
    }
    filtros = {
        "estado": estado,
        "buscar": buscar,
        "desafio_id": desafio_id,
        "fecha_desde": fecha_desde,
        "fecha_hasta": fecha_hasta,
    }

    if request.headers.get("HX-Request"):
        return render_template(
            "starmiles/partials/inscripciones_table.html", inscripciones=inscripciones, filtros=filtros, **paginacion
        )

    desafios_data, _ = api_request("GET", "/starmiles/desafios?por_pagina=100", token=token)
    desafios = desafios_data.get("items", []) if isinstance(desafios_data, dict) else []

    return render_template(
        "starmiles/aprobador_inscripciones.html",
        inscripciones=inscripciones,
        desafios=desafios,
        estado_filtro=estado,
        filtros=filtros,
        **paginacion,
    )


@starmiles_bp.route("/aprobador/inscripciones/<id>/aprobar", methods=["POST"])
@require_permiso("starmiles.aprobar_inscripciones")
def aprobar_inscripcion(id):
    """Aprobar inscripción."""
    api_request = get_api_request_func()
    token = session.get("token")

    data = {"comentario_aprobador": request.form.get("comentario", "")}
    result, status = api_request("PUT", f"/starmiles/inscripciones/{id}/aprobar", data, token=token)

    if status == 200:
        return "", 200, {"HX-Trigger": "inscripcionUpdated"}
    return error_html(result.get("detail"), "Error al aprobar"), 400


@starmiles_bp.route("/aprobador/inscripciones/<id>/rechazar", methods=["POST"])
@require_permiso("starmiles.aprobar_inscripciones")
def rechazar_inscripcion(id):
    """Rechazar inscripción."""
    api_request = get_api_request_func()
    token = session.get("token")

    data = {"comentario_aprobador": request.form.get("comentario", "Rechazado")}
    result, status = api_request("PUT", f"/starmiles/inscripciones/{id}/rechazar", data, token=token)

    if status == 200:
        return "", 200, {"HX-Trigger": "inscripcionUpdated"}
    return error_html(result.get("detail"), "Error al rechazar"), 400


@starmiles_bp.route("/aprobador/inscripciones/<id>/finalizar", methods=["POST"])
@require_permiso("starmiles.aprobar_inscripciones")
def finalizar_inscripcion(id):
    """Finalizar desafío y acreditar millas."""
    api_request = get_api_request_func()
    token = session.get("token")

    data = {"comentario_aprobador": request.form.get("comentario", "")}
    result, status = api_request("PUT", f"/starmiles/inscripciones/{id}/finalizar", data, token=token)

    if status == 200:
        return "", 200, {"HX-Trigger": "inscripcionUpdated"}
    return error_html(result.get("detail"), "Error al finalizar"), 400


@starmiles_bp.route("/aprobador/inscripciones/<id>/incompleta", methods=["POST"])
@require_permiso("starmiles.aprobar_inscripciones")
def marcar_incompleta_inscripcion(id):
    """Marcar desafío como incompleto (no acredita millas)."""
    api_request = get_api_request_func()
    token = session.get("token")

    comentario = request.form.get("comentario", "").strip()
    if not comentario:
        return '<div class="p-4 bg-red-50 text-red-700 rounded-xl">El comentario es obligatorio</div>', 400

    data = {"comentario_aprobador": comentario}
    result, status = api_request("PUT", f"/starmiles/inscripciones/{id}/incompleta", data, token=token)

    if status == 200:
        return "", 200, {"HX-Trigger": "inscripcionUpdated"}
    return error_html(result.get("detail"), "Error al marcar incompleta"), 400


@starmiles_bp.route("/aprobador/inscripciones/<id>/cancelar", methods=["POST"])
@require_permiso("starmiles.aprobar_inscripciones")
def cancelar_inscripcion(id):
    api_request = get_api_request_func()
    token = session.get("token")
    comentario = request.form.get("comentario", "").strip()
    if not comentario:
        return error_html("El motivo es obligatorio", "Error al cancelar"), 400
    result, status = api_request(
        "PUT", f"/starmiles/inscripciones/{id}/cancelar", {"comentario_aprobador": comentario}, token=token
    )
    if status == 200:
        return "", 200, {"HX-Trigger": "inscripcionUpdated"}
    return error_html(result.get("detail"), "Error al cancelar"), 400


@starmiles_bp.route("/aprobador/inscripciones/<id>/revocar", methods=["POST"])
@require_permiso("starmiles.aprobar_inscripciones")
def revocar_inscripcion(id):
    api_request = get_api_request_func()
    token = session.get("token")
    comentario = request.form.get("comentario", "").strip()
    if not comentario:
        return error_html("El motivo es obligatorio", "Error al revocar"), 400
    result, status = api_request(
        "PUT", f"/starmiles/inscripciones/{id}/revocar", {"comentario_aprobador": comentario}, token=token
    )
    if status == 200:
        return "", 200, {"HX-Trigger": "inscripcionUpdated"}
    return error_html(result.get("detail"), "Error al revocar"), 400


# ============ APROBADOR: CANJES ============


@starmiles_bp.route("/aprobador/canjes")
@require_permiso("starmiles.aprobar_canjes")
def aprobador_canjes():
    """Lista de canjes pendientes (aprobador)."""
    api_request = get_api_request_func()
    token = session.get("token")

    estado = request.args.get("estado", "pendiente")
    data, _ = api_request("GET", f"/starmiles/canjes?estado={estado}", token=token)
    canjes = data.get("items", []) if isinstance(data, dict) else []

    if request.headers.get("HX-Request"):
        return render_template("starmiles/partials/canjes_table.html", canjes=canjes)

    return render_template("starmiles/aprobador_canjes.html", canjes=canjes, estado_filtro=estado)


@starmiles_bp.route("/aprobador/canjes/<id>/aprobar", methods=["POST"])
@require_permiso("starmiles.aprobar_canjes")
def aprobar_canje(id):
    """Aprobar canje."""
    api_request = get_api_request_func()
    token = session.get("token")

    data = {"comentario": request.form.get("comentario", "")}
    result, status = api_request("PUT", f"/starmiles/canjes/{id}/aprobar", data, token=token)

    if status == 200:
        return "", 200, {"HX-Trigger": "canjeUpdated"}
    return error_html(result.get("detail"), "Error al aprobar canje"), 400


@starmiles_bp.route("/aprobador/canjes/<id>/rechazar", methods=["POST"])
@require_permiso("starmiles.aprobar_canjes")
def rechazar_canje(id):
    """Rechazar canje."""
    api_request = get_api_request_func()
    token = session.get("token")

    data = {"comentario": request.form.get("comentario", "Rechazado")}
    result, status = api_request("PUT", f"/starmiles/canjes/{id}/rechazar", data, token=token)

    if status == 200:
        return "", 200, {"HX-Trigger": "canjeUpdated"}
    return error_html(result.get("detail"), "Error al rechazar canje"), 400


@starmiles_bp.route("/aprobador/canjes/<id>/rechazar-y-reintegrar", methods=["POST"])
@require_permiso("starmiles.aprobar_canjes")
def rechazar_y_reintegrar_canje(id):
    api_request = get_api_request_func()
    token = session.get("token")
    comentario = request.form.get("comentario", "").strip()
    if not comentario:
        return error_html("El motivo es obligatorio", "Error al reintegrar"), 400
    result, status = api_request(
        "PUT", f"/starmiles/canjes/{id}/rechazar-y-reintegrar", {"comentario": comentario}, token=token
    )
    if status == 200:
        return "", 200, {"HX-Trigger": "canjeUpdated"}
    return error_html(result.get("detail"), "Error al rechazar y reintegrar"), 400


@starmiles_bp.route("/aprobador/canjes/<id>/entregar", methods=["POST"])
@require_permiso("starmiles.aprobar_canjes")
def entregar_canje(id):
    """Marcar canje como entregado."""
    api_request = get_api_request_func()
    token = session.get("token")

    data = {"comentario": request.form.get("comentario", "")}
    result, status = api_request("PUT", f"/starmiles/canjes/{id}/entregar", data, token=token)

    if status == 200:
        return "", 200, {"HX-Trigger": "canjeUpdated"}
    return error_html(result.get("detail"), "Error al entregar canje"), 400


# ============ ADMIN: CMS ============


@starmiles_bp.route("/admin/cms")
@require_permiso("starmiles.admin_cms")
def admin_cms():
    """ABM de contenido CMS."""
    api_request = get_api_request_func()
    token = session.get("token")

    tipo = request.args.get("tipo", "")
    params = f"?tipo={tipo}" if tipo else ""

    data, _ = api_request("GET", f"/starmiles/cms{params}", token=token)
    contenidos = data.get("items", []) if isinstance(data, dict) else []

    if request.headers.get("HX-Request"):
        return render_template("starmiles/partials/cms_table.html", contenidos=contenidos)

    return render_template("starmiles/admin_cms.html", contenidos=contenidos)


@starmiles_bp.route("/admin/cms/nuevo", methods=["GET", "POST"])
@require_permiso("starmiles.admin_cms")
def admin_cms_crear():
    """Crear contenido CMS."""
    api_request = get_api_request_func()
    token = session.get("token")

    if request.method == "POST":
        data = {
            "tipo": request.form.get("tipo"),
            "titulo": request.form.get("titulo"),
            "contenido": request.form.get("contenido") or None,
            "imagen_url": request.form.get("imagen_url") or None,
            "empleado_id": request.form.get("empleado_id") or None,
            "orden": int(request.form.get("orden", 0)),
            "visible": request.form.get("visible") == "on",
        }

        result, status = api_request("POST", "/starmiles/cms", data, token=token)

        if status in [200, 201]:
            flash("Contenido creado", "success")
            if request.headers.get("HX-Request"):
                return "", 200, {"HX-Redirect": url_for("starmiles.admin_cms")}
            return redirect(url_for("starmiles.admin_cms"))

        err_block = error_html(result.get("detail"), "Error al crear")
        if request.headers.get("HX-Request"):
            return err_block
        flash(format_api_error(result.get("detail"), "Error al crear"), "error")

    # Cargar empleados para selector de ganadores
    emp_data, _ = api_request("GET", "/empleados?por_pagina=100", token=token)
    empleados = emp_data.get("items", []) if isinstance(emp_data, dict) else []

    return render_template("starmiles/cms_form.html", contenido=None, empleados=empleados)


@starmiles_bp.route("/admin/cms/<id>/editar", methods=["GET", "POST"])
@require_permiso("starmiles.admin_cms")
def admin_cms_editar(id):
    """Editar contenido CMS."""
    api_request = get_api_request_func()
    token = session.get("token")

    if request.method == "POST":
        data = {
            "tipo": request.form.get("tipo"),
            "titulo": request.form.get("titulo"),
            "contenido": request.form.get("contenido") or None,
            "imagen_url": request.form.get("imagen_url") or None,
            "empleado_id": request.form.get("empleado_id") or None,
            "orden": int(request.form.get("orden", 0)),
            "visible": request.form.get("visible") == "on",
        }

        result, status = api_request("PUT", f"/starmiles/cms/{id}", data, token=token)

        if status == 200:
            flash("Contenido actualizado", "success")
            if request.headers.get("HX-Request"):
                return "", 200, {"HX-Redirect": url_for("starmiles.admin_cms")}
            return redirect(url_for("starmiles.admin_cms"))

        err_block = error_html(result.get("detail"), "Error al actualizar")
        if request.headers.get("HX-Request"):
            return err_block
        flash(format_api_error(result.get("detail"), "Error al actualizar"), "error")

    contenido, _ = api_request("GET", f"/starmiles/cms/{id}", token=token)
    emp_data, _ = api_request("GET", "/empleados?por_pagina=100", token=token)
    empleados = emp_data.get("items", []) if isinstance(emp_data, dict) else []

    return render_template("starmiles/cms_form.html", contenido=contenido, empleados=empleados)


@starmiles_bp.route("/admin/cms/<id>/eliminar", methods=["DELETE"])
@require_permiso("starmiles.admin_cms")
def admin_cms_eliminar(id):
    """Eliminar contenido CMS."""
    api_request = get_api_request_func()
    token = session.get("token")
    result, status = api_request("DELETE", f"/starmiles/cms/{id}", token=token)

    if status == 200:
        return "", 200, {"HX-Trigger": "cmsDeleted"}
    return error_html(result.get("detail"), "Error al eliminar"), 400


# ============ ADMIN: CATEGORIAS ============


@starmiles_bp.route("/admin/categorias")
@require_permiso("starmiles.admin_categorias")
def admin_categorias():
    """ABM de categorías."""
    api_request = get_api_request_func()
    token = session.get("token")

    data, _ = api_request("GET", "/starmiles/categorias", token=token)
    categorias = data if isinstance(data, list) else []

    return render_template("starmiles/admin_categorias.html", categorias=categorias)


@starmiles_bp.route("/admin/categorias/nuevo", methods=["GET", "POST"])
@require_permiso("starmiles.admin_categorias")
def admin_categoria_crear():
    """Crear categoría."""
    api_request = get_api_request_func()
    token = session.get("token")

    if request.method == "POST":
        data = {
            "nombre": request.form.get("nombre"),
            "descripcion": request.form.get("descripcion") or None,
            "color": request.form.get("color", "#3B82F6"),
            "icono": request.form.get("icono", "star"),
        }

        result, status = api_request("POST", "/starmiles/categorias", data, token=token)

        if status in [200, 201]:
            flash("Categoría creada", "success")
            if request.headers.get("HX-Request"):
                return "", 200, {"HX-Redirect": url_for("starmiles.admin_categorias")}
            return redirect(url_for("starmiles.admin_categorias"))

        err_block = error_html(result.get("detail"), "Error al crear")
        if request.headers.get("HX-Request"):
            return err_block
        flash(format_api_error(result.get("detail"), "Error al crear"), "error")

    return render_template("starmiles/categoria_form.html", categoria=None)


@starmiles_bp.route("/admin/categorias/<id>/editar", methods=["GET", "POST"])
@require_permiso("starmiles.admin_categorias")
def admin_categoria_editar(id):
    """Editar categoría."""
    api_request = get_api_request_func()
    token = session.get("token")

    if request.method == "POST":
        data = {
            "nombre": request.form.get("nombre"),
            "descripcion": request.form.get("descripcion") or None,
            "color": request.form.get("color", "#3B82F6"),
            "icono": request.form.get("icono", "star"),
        }

        result, status = api_request("PUT", f"/starmiles/categorias/{id}", data, token=token)

        if status == 200:
            flash("Categoría actualizada", "success")
            if request.headers.get("HX-Request"):
                return "", 200, {"HX-Redirect": url_for("starmiles.admin_categorias")}
            return redirect(url_for("starmiles.admin_categorias"))

        err_block = error_html(result.get("detail"), "Error al actualizar")
        if request.headers.get("HX-Request"):
            return err_block
        flash(format_api_error(result.get("detail"), "Error al actualizar"), "error")

    # Obtener categoría
    cat_data, _ = api_request("GET", "/starmiles/categorias", token=token)
    categorias = cat_data if isinstance(cat_data, list) else []
    categoria = next((c for c in categorias if c.get("id") == id), None)

    return render_template("starmiles/categoria_form.html", categoria=categoria)


@starmiles_bp.route("/admin/categorias/<id>/eliminar", methods=["DELETE"])
@require_permiso("starmiles.admin_categorias")
def admin_categoria_eliminar(id):
    """Eliminar categoría."""
    api_request = get_api_request_func()
    token = session.get("token")
    result, status = api_request("DELETE", f"/starmiles/categorias/{id}", token=token)

    if status == 200:
        return "", 200, {"HX-Trigger": "categoriaDeleted"}
    return error_html(result.get("detail"), "Error al eliminar"), 400


# ============ ADMIN: GESTIONAR EMPLEADOS (VISTA 360) ============


@starmiles_bp.route("/admin/empleados")
@require_permiso("starmiles.admin_empleados")
def admin_empleados():
    """Vista 360 de empleados con Star Miles."""
    api_request = get_api_request_func()
    token = session.get("token")

    buscar = request.args.get("search", "")
    pagina = request.args.get("pagina", 1, type=int)
    # Ordenamiento (ranking). Por defecto: millas históricas desc.
    orden = request.args.get("orden", "millas_historicas")
    direccion = request.args.get("direccion", "desc")
    millas_min = request.args.get("millas_min", "")
    millas_max = request.args.get("millas_max", "")

    params = f"?pagina={pagina}&por_pagina=20&orden={orden}&direccion={direccion}"
    if buscar:
        params += f"&buscar={buscar}"
    if millas_min != "":
        params += f"&millas_min={millas_min}"
    if millas_max != "":
        params += f"&millas_max={millas_max}"

    data, _ = api_request("GET", f"/starmiles/empleados-360{params}", token=token)

    empleados = data.get("items", []) if isinstance(data, dict) else []
    total = data.get("total", 0)
    total_paginas = data.get("total_paginas", 1)

    # Resumen general
    resumen = {
        "total_millas_acreditadas": data.get("total_millas_acreditadas", 0),
        "total_millas_canjeadas": data.get("total_millas_canjeadas", 0),
        "total_inscripciones": data.get("total_inscripciones", 0),
        "total_canjes": data.get("total_canjes", 0),
    }

    # Estado de filtros/orden para reconstruir links y resaltar columnas en la UI
    filtros_estado = {
        "search": buscar,
        "orden": orden,
        "direccion": direccion,
        "millas_min": millas_min,
        "millas_max": millas_max,
    }

    if request.headers.get("HX-Request"):
        return render_template(
            "starmiles/partials/empleados_360_table.html",
            empleados=empleados,
            pagina=pagina,
            total_paginas=total_paginas,
            resumen=resumen,
            filtros=filtros_estado,
            total=total,
        )

    return render_template(
        "starmiles/admin_empleados.html",
        empleados=empleados,
        resumen=resumen,
        pagina=pagina,
        total_paginas=total_paginas,
        total=total,
        filtros=filtros_estado,
    )


@starmiles_bp.route("/admin/empleados/<empleado_id>")
@require_permiso("starmiles.admin_empleados")
def admin_empleado_detalle(empleado_id):
    """Detalle 360 de un empleado."""
    api_request = get_api_request_func()
    token = session.get("token")

    data, status = api_request("GET", f"/starmiles/empleados-360/{empleado_id}", token=token)

    if status != 200:
        return redirect(url_for("starmiles.admin_empleados"))

    return render_template("starmiles/admin_empleado_detalle.html", empleado=data)


# ============ PROXY UPLOAD IMAGEN (server-side) ============


@starmiles_bp.route("/upload-imagen", methods=["POST"])
@require_permiso("starmiles.admin_cms")
def upload_imagen_proxy():
    """Proxy para subir imagen sin exponer el JWT en el frontend."""
    import httpx
    from flask import current_app, jsonify

    if "file" not in request.files:
        return jsonify({"detail": "No se envió archivo"}), 400

    file = request.files["file"]
    context = request.form.get("context", "default")
    token = session.get("token")
    api_url = current_app.config["API_URL"]

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{api_url}/api/v1/starmiles/upload-imagen",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": (file.filename, file.read(), file.content_type)},
                data={"context": context},
            )
            return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({"detail": str(e)}), 500
