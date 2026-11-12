"""
Módulo Nómina - Empleados CRUD
"""

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from modulos.auth_helpers import get_api_request_func, require_permiso
from modulos.error_helpers import error_html, format_api_error

nomina_bp = Blueprint("nomina", __name__, template_folder="templates", url_prefix="/nomina")


# === LISTAR EMPLEADOS ===
@nomina_bp.route("/empleados")
@require_permiso("nomina.empleados")
def empleados_list():
    api_request = get_api_request_func()
    token = session.get("token")

    # Parámetros de búsqueda, filtros y paginación
    buscar = request.args.get("buscar", "")
    pagina = request.args.get("pagina", 1, type=int)
    agrupar_por = request.args.get("agrupar_por", "")
    ordenar_por = request.args.get("ordenar_por", "")
    ordenar_dir = request.args.get("ordenar_dir", "asc")

    # Filtros
    filtro_departamento = request.args.get("departamento_id", "")
    filtro_perfil = request.args.get("perfil_id", "")
    filtro_activo = request.args.get("activo", "true")  # Por defecto solo activos
    filtro_seniority = request.args.get("seniority", "")
    filtro_antiguedad = request.args.get("antiguedad_rango", "")

    params = f"?pagina={pagina}&por_pagina=50"
    if buscar:
        params += f"&buscar={buscar}"
    if filtro_departamento:
        params += f"&departamento_id={filtro_departamento}"
    if filtro_perfil:
        params += f"&perfil_id={filtro_perfil}"
    if filtro_activo:
        params += f"&activo={filtro_activo}"
    if filtro_seniority:
        params += f"&seniority={filtro_seniority}"
    if filtro_antiguedad:
        params += f"&antiguedad_rango={filtro_antiguedad}"
    if agrupar_por:
        params += f"&agrupar_por={agrupar_por}"
    if ordenar_por:
        params += f"&ordenar_por={ordenar_por}"
    if ordenar_dir:
        params += f"&ordenar_dir={ordenar_dir}"

    data, status = api_request("GET", f"/nomina/empleados{params}", token=token)

    items = data.get("items", []) if isinstance(data, dict) else []
    total = data.get("total", 0) if isinstance(data, dict) else 0
    total_paginas = data.get("total_paginas", 1) if isinstance(data, dict) else 1
    grupos = data.get("grupos", []) if isinstance(data, dict) else []

    # Cargar catálogos para filtros
    departamentos, _ = api_request("GET", "/nomina/departamentos/todos", token=token)
    perfiles, _ = api_request("GET", "/nomina/perfiles/todos", token=token)

    if request.headers.get("HX-Request"):
        view = request.args.get("view", "")
        if view == "cards":
            return render_template(
                "nomina/partials/empleados_cards.html",
                items=items,
                total=total,
                pagina=pagina,
                total_paginas=total_paginas,
                buscar=buscar,
                grupos=grupos,
                agrupar_por=agrupar_por,
            )
        return render_template(
            "nomina/partials/empleados_table.html",
            items=items,
            total=total,
            pagina=pagina,
            total_paginas=total_paginas,
            buscar=buscar,
            grupos=grupos,
            agrupar_por=agrupar_por,
            filtro_departamento=filtro_departamento,
            filtro_perfil=filtro_perfil,
            filtro_activo=filtro_activo,
            filtro_seniority=filtro_seniority,
            filtro_antiguedad=filtro_antiguedad,
            ordenar_por=ordenar_por,
            ordenar_dir=ordenar_dir,
        )

    return render_template(
        "nomina/empleados_list.html",
        items=items,
        total=total,
        pagina=pagina,
        total_paginas=total_paginas,
        buscar=buscar,
        departamentos=departamentos or [],
        perfiles=perfiles or [],
        grupos=grupos,
        agrupar_por=agrupar_por,
        filtro_departamento=filtro_departamento,
        filtro_perfil=filtro_perfil,
        filtro_activo=filtro_activo,
        filtro_seniority=filtro_seniority,
        filtro_antiguedad=filtro_antiguedad,
        ordenar_por=ordenar_por,
        ordenar_dir=ordenar_dir,
    )


# === VER EMPLEADO ===
@nomina_bp.route("/empleados/<id>")
@require_permiso("nomina.empleados")
def empleados_view(id):
    api_request = get_api_request_func()
    token = session.get("token")
    item, status = api_request("GET", f"/nomina/empleados/{id}", token=token)
    if not item or status != 200:
        flash("Empleado no encontrado", "error")
        return redirect(url_for("nomina.empleados_list"))
    return render_template("nomina/empleados_view.html", item=item)


# === CREAR EMPLEADO ===
@nomina_bp.route("/empleados/nuevo", methods=["GET", "POST"])
@require_permiso("nomina.empleados")
def empleados_create():
    api_request = get_api_request_func()
    token = session.get("token")

    if request.method == "POST":
        data = _get_empleado_form_data()

        result, status = api_request("POST", "/nomina/empleados", data, token=token)

        if status in [200, 201]:
            new_id = result.get("id") if isinstance(result, dict) else None
            redirect_url = url_for("nomina.empleados_edit", id=new_id) if new_id else url_for("nomina.empleados_list")
            flash("Empleado creado exitosamente. Podés agregar la foto ahora.", "success")
            if request.headers.get("HX-Request"):
                return "", 200, {"HX-Redirect": redirect_url}
            return redirect(redirect_url)

        err_block = error_html(result.get("detail"), "Error al crear empleado")
        if request.headers.get("HX-Request"):
            return err_block
        flash(format_api_error(result.get("detail"), "Error al crear empleado"), "error")

    # Cargar catálogos
    departamentos, _ = api_request("GET", "/nomina/departamentos/todos", token=token)
    perfiles, _ = api_request("GET", "/nomina/perfiles/todos", token=token)
    carreras, _ = api_request("GET", "/nomina/carreras/todos", token=token)
    empleados_activos, _ = api_request("GET", "/nomina/empleados/buscar-select", token=token)
    hrbps, _ = api_request("GET", "/nomina/empleados/buscar-hrbp", token=token)

    return render_template(
        "nomina/empleados_form.html",
        item=None,
        departamentos=departamentos or [],
        perfiles=perfiles or [],
        carreras=carreras or [],
        empleados_activos=empleados_activos or [],
        hrbps=hrbps or [],
    )


# === EDITAR EMPLEADO ===
@nomina_bp.route("/empleados/<id>/editar", methods=["GET", "POST"])
@require_permiso("nomina.empleados")
def empleados_edit(id):
    api_request = get_api_request_func()
    token = session.get("token")

    if request.method == "POST":
        data = _get_empleado_form_data()

        result, status = api_request("PUT", f"/nomina/empleados/{id}", data, token=token)

        if status == 200:
            flash("Empleado actualizado exitosamente", "success")
            if request.headers.get("HX-Request"):
                return "", 200, {"HX-Redirect": url_for("nomina.empleados_list")}
            return redirect(url_for("nomina.empleados_list"))

        err_block = error_html(result.get("detail"), "Error al actualizar empleado")
        if request.headers.get("HX-Request"):
            return err_block
        flash(format_api_error(result.get("detail"), "Error al actualizar empleado"), "error")

    item, _ = api_request("GET", f"/nomina/empleados/{id}", token=token)
    departamentos, _ = api_request("GET", "/nomina/departamentos/todos", token=token)
    perfiles, _ = api_request("GET", "/nomina/perfiles/todos", token=token)
    carreras, _ = api_request("GET", "/nomina/carreras/todos", token=token)
    empleados_activos, _ = api_request("GET", "/nomina/empleados/buscar-select", token=token)
    hrbps, _ = api_request("GET", "/nomina/empleados/buscar-hrbp", token=token)

    return render_template(
        "nomina/empleados_form.html",
        item=item,
        departamentos=departamentos or [],
        perfiles=perfiles or [],
        carreras=carreras or [],
        empleados_activos=empleados_activos or [],
        hrbps=hrbps or [],
    )


# === DAR DE BAJA EMPLEADO ===
@nomina_bp.route("/empleados/<id>/baja", methods=["POST"])
@require_permiso("nomina.empleados")
def empleados_baja(id):
    api_request = get_api_request_func()
    token = session.get("token")

    fecha_baja = request.form.get("fecha_baja")
    motivo_baja = request.form.get("motivo_baja")

    # Convertir fecha dd/mm/yyyy a yyyy-mm-dd
    if fecha_baja:
        try:
            parts = fecha_baja.split("/")
            if len(parts) == 3:
                fecha_baja = f"{parts[2]}-{parts[1]}-{parts[0]}"
        except Exception:
            pass

    data = {"fecha_baja": fecha_baja, "motivo_baja": motivo_baja}

    result, status = api_request("PUT", f"/nomina/empleados/{id}/baja", data, token=token)

    if status == 200:
        return "", 200, {"HX-Trigger": "empleadoBaja"}

    return error_html(result.get("detail"), "Error al dar de baja"), 400


# === REACTIVAR EMPLEADO ===
@nomina_bp.route("/empleados/<id>/reactivar", methods=["PUT"])
@require_permiso("nomina.empleados")
def empleados_reactivar(id):
    api_request = get_api_request_func()
    token = session.get("token")
    result, status = api_request("PUT", f"/nomina/empleados/{id}/reactivar", token=token)

    if status == 200:
        return "", 200, {"HX-Trigger": "empleadoReactivado"}
    return error_html(result.get("detail"), "Error al reactivar"), 400


# === ELIMINAR EMPLEADO ===
@nomina_bp.route("/empleados/<id>/eliminar", methods=["DELETE"])
@require_permiso("nomina.empleados")
def empleados_delete(id):
    api_request = get_api_request_func()
    token = session.get("token")
    result, status = api_request("DELETE", f"/nomina/empleados/{id}", token=token)

    if status == 200:
        return "", 200, {"HX-Trigger": "empleadoDeleted"}
    return error_html(result.get("detail"), "Error al eliminar"), 400


# === RESTAURAR EMPLEADO ===
@nomina_bp.route("/empleados/<id>/restaurar", methods=["PUT"])
@require_permiso("nomina.empleados")
def empleados_restore(id):
    api_request = get_api_request_func()
    token = session.get("token")
    result, status = api_request("PUT", f"/nomina/empleados/{id}/restaurar", token=token)

    if status == 200:
        return "", 200, {"HX-Trigger": "empleadoRestored"}
    return error_html(result.get("detail"), "Error al restaurar"), 400


# ============ DEPARTAMENTOS ============


@nomina_bp.route("/departamentos")
@require_permiso("nomina.departamentos")
def departamentos_list():
    """Lista de departamentos con perfiles que tienen empleados."""
    api_request = get_api_request_func()
    token = session.get("token")

    buscar = request.args.get("buscar", "")
    pagina = request.args.get("pagina", 1, type=int)

    params = f"?pagina={pagina}&por_pagina=20"
    if buscar:
        params += f"&buscar={buscar}"

    data, status = api_request("GET", f"/nomina/departamentos{params}", token=token)

    items = data.get("items", []) if isinstance(data, dict) else []
    total = data.get("total", 0) if isinstance(data, dict) else 0
    total_paginas = data.get("total_paginas", 1) if isinstance(data, dict) else 1

    # Para cada departamento, traer perfiles con empleados
    for dept in items:
        emp_data, emp_status = api_request(
            "GET", f"/nomina/empleados?departamento_id={dept['id']}&por_pagina=100", token=token
        )
        perfiles_count = {}
        if emp_data and emp_status == 200:
            for emp in emp_data.get("items", []):
                perfil = emp.get("perfil_nombre")
                if perfil:
                    if perfil not in perfiles_count:
                        perfiles_count[perfil] = 0
                    perfiles_count[perfil] += 1
        dept["perfiles"] = perfiles_count
        dept["total_empleados"] = sum(perfiles_count.values())

    if request.headers.get("HX-Request"):
        return render_template(
            "nomina/partials/departamentos_table.html",
            items=items,
            total=total,
            pagina=pagina,
            total_paginas=total_paginas,
            buscar=buscar,
        )

    return render_template(
        "nomina/departamentos_list.html",
        items=items,
        total=total,
        pagina=pagina,
        total_paginas=total_paginas,
        buscar=buscar,
    )


@nomina_bp.route("/departamentos/<id>")
@require_permiso("nomina.departamentos")
def departamentos_view(id):
    """Detalle de un departamento con empleados agrupados por perfil."""
    api_request = get_api_request_func()
    token = session.get("token")

    item, status = api_request("GET", f"/nomina/departamentos/{id}", token=token)
    if not item or status != 200:
        flash("Departamento no encontrado", "error")
        return redirect(url_for("nomina.departamentos_list"))

    # Traer empleados del departamento (todos, sin paginar)
    empleados_data, emp_status = api_request(
        "GET", f"/nomina/empleados?departamento_id={id}&por_pagina=100", token=token
    )

    # Agrupar empleados por perfil
    empleados_por_perfil = {}
    if empleados_data and emp_status == 200:
        for emp in empleados_data.get("items", []):
            perfil = emp.get("perfil_nombre") or "Sin Perfil"
            if perfil not in empleados_por_perfil:
                empleados_por_perfil[perfil] = []
            empleados_por_perfil[perfil].append(emp)
        # Ordenar perfiles alfabéticamente, "Sin Perfil" al final
        empleados_por_perfil = dict(sorted(empleados_por_perfil.items(), key=lambda x: (x[0] == "Sin Perfil", x[0])))

    total_empleados = empleados_data.get("total", 0) if empleados_data and emp_status == 200 else 0

    return render_template(
        "nomina/departamentos_view.html",
        item=item,
        empleados_por_perfil=empleados_por_perfil,
        total_empleados=total_empleados,
    )


@nomina_bp.route("/departamentos/nuevo", methods=["GET", "POST"])
@require_permiso("nomina.departamentos")
def departamentos_create():
    """Crear nuevo departamento."""
    api_request = get_api_request_func()
    token = session.get("token")

    if request.method == "POST":
        data = {
            "nombre": request.form.get("nombre"),
            "descripcion": request.form.get("descripcion") or None,
            "manager_id": request.form.get("manager_id") or None,
        }

        result, status = api_request("POST", "/nomina/departamentos", data, token=token)

        if status in [200, 201]:
            flash("Departamento creado exitosamente", "success")
            if request.headers.get("HX-Request"):
                return "", 200, {"HX-Redirect": url_for("nomina.departamentos_list")}
            return redirect(url_for("nomina.departamentos_list"))
        err_block = error_html(result.get("detail"), "Error al crear departamento")
        if request.headers.get("HX-Request"):
            return err_block
        flash(format_api_error(result.get("detail"), "Error al crear departamento"), "error")

    # Cargar empleados con perfil tipo MANAGER para el select de manager
    empleados_activos, _ = api_request("GET", "/nomina/empleados/buscar-select?perfil_tipo=MANAGER", token=token)

    return render_template("nomina/departamentos_form.html", item=None, empleados_activos=empleados_activos or [])


@nomina_bp.route("/departamentos/<id>/editar", methods=["GET", "POST"])
@require_permiso("nomina.departamentos")
def departamentos_edit(id):
    """Editar departamento existente."""
    api_request = get_api_request_func()
    token = session.get("token")

    if request.method == "POST":
        data = {
            "nombre": request.form.get("nombre"),
            "descripcion": request.form.get("descripcion") or None,
            "manager_id": request.form.get("manager_id") or None,
        }

        result, status = api_request("PUT", f"/nomina/departamentos/{id}", data, token=token)

        if status == 200:
            flash("Departamento actualizado exitosamente", "success")
            if request.headers.get("HX-Request"):
                return "", 200, {"HX-Redirect": url_for("nomina.departamentos_list")}
            return redirect(url_for("nomina.departamentos_list"))

        err_block = error_html(result.get("detail"), "Error al actualizar departamento")
        if request.headers.get("HX-Request"):
            return err_block
        flash(format_api_error(result.get("detail"), "Error al actualizar departamento"), "error")

    item, _ = api_request("GET", f"/nomina/departamentos/{id}", token=token)
    empleados_activos, _ = api_request("GET", "/nomina/empleados/buscar-select?perfil_tipo=MANAGER", token=token)

    return render_template("nomina/departamentos_form.html", item=item, empleados_activos=empleados_activos or [])


@nomina_bp.route("/departamentos/<id>/eliminar", methods=["DELETE"])
@require_permiso("nomina.departamentos")
def departamentos_delete(id):
    """Eliminar departamento (soft delete)."""
    api_request = get_api_request_func()
    token = session.get("token")
    result, status = api_request("DELETE", f"/nomina/departamentos/{id}", token=token)

    if status == 200:
        return "", 200, {"HX-Trigger": "departamentoDeleted"}
    return error_html(result.get("detail"), "Error al eliminar departamento"), 400


# ============ PERFILES ============


@nomina_bp.route("/perfiles")
@require_permiso("nomina.perfiles")
def perfiles_list():
    """Lista de perfiles/puestos."""
    api_request = get_api_request_func()
    token = session.get("token")

    buscar = request.args.get("buscar", "")
    pagina = request.args.get("pagina", 1, type=int)
    filtro_departamento = request.args.get("departamento_id", "")
    filtro_categoria = request.args.get("categoria_id", "")
    filtro_tipo = request.args.get("tipo", "")

    params = f"?pagina={pagina}&por_pagina=100"
    if buscar:
        params += f"&buscar={buscar}"
    if filtro_departamento:
        params += f"&departamento_id={filtro_departamento}"
    if filtro_categoria:
        params += f"&categoria_id={filtro_categoria}"
    if filtro_tipo:
        params += f"&tipo={filtro_tipo}"

    data, status = api_request("GET", f"/nomina/perfiles{params}", token=token)

    items = data.get("items", []) if isinstance(data, dict) else []
    total = data.get("total", 0) if isinstance(data, dict) else 0
    total_paginas = data.get("total_paginas", 1) if isinstance(data, dict) else 1

    # Cargar catálogos para filtros
    departamentos, _ = api_request("GET", "/nomina/departamentos/todos", token=token)
    categorias, _ = api_request("GET", "/nomina/categorias/todos", token=token)

    # Enriquecer perfiles con conteo de empleados
    for perfil in items:
        emp_data, emp_st = api_request(
            "GET", f"/nomina/empleados?perfil_id={perfil['id']}&por_pagina=1&activo=true", token=token
        )
        perfil["total_empleados"] = emp_data.get("total", 0) if isinstance(emp_data, dict) and emp_st == 200 else 0

    if request.headers.get("HX-Request"):
        return render_template(
            "nomina/partials/perfiles_table.html",
            items=items,
            total=total,
            pagina=pagina,
            total_paginas=total_paginas,
            buscar=buscar,
            filtro_departamento=filtro_departamento,
            filtro_categoria=filtro_categoria,
            filtro_tipo=filtro_tipo,
        )

    return render_template(
        "nomina/perfiles_list.html",
        items=items,
        total=total,
        pagina=pagina,
        total_paginas=total_paginas,
        buscar=buscar,
        departamentos=departamentos or [],
        categorias=categorias or [],
        filtro_departamento=filtro_departamento,
        filtro_categoria=filtro_categoria,
        filtro_tipo=filtro_tipo,
    )


@nomina_bp.route("/perfiles/<id>")
@require_permiso("nomina.perfiles")
def perfiles_view(id):
    """Detalle de un perfil con sus empleados asignados."""
    api_request = get_api_request_func()
    token = session.get("token")

    item, status = api_request("GET", f"/nomina/perfiles/{id}", token=token)
    if not item or status != 200:
        flash("Perfil no encontrado", "error")
        return redirect(url_for("nomina.perfiles_list"))

    # Obtener empleados con este perfil
    emp_data, _ = api_request("GET", f"/nomina/empleados?perfil_id={id}&por_pagina=100&activo=", token=token)
    empleados = emp_data.get("items", []) if isinstance(emp_data, dict) else []

    return render_template("nomina/perfiles_view.html", item=item, empleados=empleados)


@nomina_bp.route("/perfiles/nuevo", methods=["GET", "POST"])
@require_permiso("nomina.perfiles")
def perfiles_create():
    """Crear nuevo perfil."""
    api_request = get_api_request_func()
    token = session.get("token")

    if request.method == "POST":
        data = {
            "nombre": request.form.get("nombre"),
            "tipo": request.form.get("tipo") or None,
            "categoria_id": request.form.get("categoria_id") or None,
            "descripcion": request.form.get("descripcion") or None,
        }

        result, status = api_request("POST", "/nomina/perfiles", data, token=token)

        if status in [200, 201]:
            flash("Perfil creado exitosamente", "success")
            if request.headers.get("HX-Request"):
                return "", 200, {"HX-Redirect": url_for("nomina.perfiles_list")}
            return redirect(url_for("nomina.perfiles_list"))

        err_block = error_html(result.get("detail"), "Error al crear perfil")
        if request.headers.get("HX-Request"):
            return err_block
        flash(format_api_error(result.get("detail"), "Error al crear perfil"), "error")

    categorias, _ = api_request("GET", "/nomina/categorias/todos", token=token)
    departamentos, _ = api_request("GET", "/nomina/departamentos/todos", token=token)
    return render_template(
        "nomina/perfiles_form.html", item=None, categorias=categorias or [], departamentos=departamentos or []
    )


@nomina_bp.route("/perfiles/<id>/editar", methods=["GET", "POST"])
@require_permiso("nomina.perfiles")
def perfiles_edit(id):
    """Editar perfil existente."""
    api_request = get_api_request_func()
    token = session.get("token")

    if request.method == "POST":
        data = {
            "nombre": request.form.get("nombre"),
            "tipo": request.form.get("tipo") or None,
            "categoria_id": request.form.get("categoria_id") or None,
            "descripcion": request.form.get("descripcion") or None,
        }

        result, status = api_request("PUT", f"/nomina/perfiles/{id}", data, token=token)

        if status == 200:
            flash("Perfil actualizado exitosamente", "success")
            if request.headers.get("HX-Request"):
                return "", 200, {"HX-Redirect": url_for("nomina.perfiles_list")}
            return redirect(url_for("nomina.perfiles_list"))

        err_block = error_html(result.get("detail"), "Error al actualizar perfil")
        if request.headers.get("HX-Request"):
            return err_block
        flash(format_api_error(result.get("detail"), "Error al actualizar perfil"), "error")

    item, _ = api_request("GET", f"/nomina/perfiles/{id}", token=token)
    categorias, _ = api_request("GET", "/nomina/categorias/todos", token=token)
    departamentos, _ = api_request("GET", "/nomina/departamentos/todos", token=token)
    return render_template(
        "nomina/perfiles_form.html", item=item, categorias=categorias or [], departamentos=departamentos or []
    )


@nomina_bp.route("/perfiles/<id>/eliminar", methods=["DELETE"])
@require_permiso("nomina.perfiles")
def perfiles_delete(id):
    """Eliminar perfil (soft delete)."""
    api_request = get_api_request_func()
    token = session.get("token")
    result, status = api_request("DELETE", f"/nomina/perfiles/{id}", token=token)

    if status == 200:
        return "", 200, {"HX-Trigger": "perfilDeleted"}
    return error_html(result.get("detail"), "Error al eliminar perfil"), 400


# ============ CATEGORIAS ============


@nomina_bp.route("/categorias")
@require_permiso("nomina.categorias")
def categorias_list():
    """Lista de categorías de perfiles."""
    api_request = get_api_request_func()
    token = session.get("token")

    buscar = request.args.get("buscar", "")
    pagina = request.args.get("pagina", 1, type=int)
    filtro_departamento = request.args.get("departamento_id", "")
    ordenar_por = request.args.get("ordenar_por", "")
    ordenar_dir = request.args.get("ordenar_dir", "asc")

    params = f"?pagina={pagina}&por_pagina=20"
    if buscar:
        params += f"&buscar={buscar}"
    if filtro_departamento:
        params += f"&departamento_id={filtro_departamento}"
    if ordenar_por:
        params += f"&ordenar_por={ordenar_por}"
    if ordenar_dir:
        params += f"&ordenar_dir={ordenar_dir}"

    data, status = api_request("GET", f"/nomina/categorias{params}", token=token)

    items = data.get("items", []) if isinstance(data, dict) else []
    total = data.get("total", 0) if isinstance(data, dict) else 0
    total_paginas = data.get("total_paginas", 1) if isinstance(data, dict) else 1

    # Cargar departamentos para filtros
    departamentos, _ = api_request("GET", "/nomina/departamentos/todos", token=token)

    if request.headers.get("HX-Request"):
        return render_template(
            "nomina/partials/categorias_table.html",
            items=items,
            total=total,
            pagina=pagina,
            total_paginas=total_paginas,
            buscar=buscar,
            filtro_departamento=filtro_departamento,
            ordenar_por=ordenar_por,
            ordenar_dir=ordenar_dir,
        )

    return render_template(
        "nomina/categorias_list.html",
        items=items,
        total=total,
        pagina=pagina,
        total_paginas=total_paginas,
        buscar=buscar,
        departamentos=departamentos or [],
        filtro_departamento=filtro_departamento,
        ordenar_por=ordenar_por,
        ordenar_dir=ordenar_dir,
    )


@nomina_bp.route("/categorias/<id>")
@require_permiso("nomina.categorias")
def categorias_view(id):
    """Detalle de una categoría con sus perfiles."""
    api_request = get_api_request_func()
    token = session.get("token")

    item, status = api_request("GET", f"/nomina/categorias/{id}", token=token)
    if not item or status != 200:
        flash("Categoría no encontrada", "error")
        return redirect(url_for("nomina.categorias_list"))

    # Obtener perfiles de esta categoría
    perfiles_data, _ = api_request("GET", f"/nomina/perfiles?categoria_id={id}&por_pagina=100", token=token)
    perfiles = perfiles_data.get("items", []) if isinstance(perfiles_data, dict) else []

    return render_template("nomina/categorias_view.html", item=item, perfiles=perfiles)


@nomina_bp.route("/categorias/nuevo", methods=["GET", "POST"])
@require_permiso("nomina.categorias")
def categorias_create():
    """Crear nueva categoría."""
    api_request = get_api_request_func()
    token = session.get("token")

    if request.method == "POST":
        data = {
            "nombre": request.form.get("nombre"),
            "descripcion": request.form.get("descripcion") or None,
            "departamento_id": request.form.get("departamento_id") or None,
        }

        result, status = api_request("POST", "/nomina/categorias", data, token=token)

        if status in [200, 201]:
            flash("Categoría creada exitosamente", "success")
            if request.headers.get("HX-Request"):
                return "", 200, {"HX-Redirect": url_for("nomina.categorias_list")}
            return redirect(url_for("nomina.categorias_list"))

        err_block = error_html(result.get("detail"), "Error al crear categoría")
        if request.headers.get("HX-Request"):
            return err_block
        flash(format_api_error(result.get("detail"), "Error al crear categoría"), "error")

    departamentos, _ = api_request("GET", "/nomina/departamentos/todos", token=token)
    return render_template("nomina/categorias_form.html", item=None, departamentos=departamentos or [])


@nomina_bp.route("/categorias/<id>/editar", methods=["GET", "POST"])
@require_permiso("nomina.categorias")
def categorias_edit(id):
    """Editar categoría existente."""
    api_request = get_api_request_func()
    token = session.get("token")

    if request.method == "POST":
        data = {
            "nombre": request.form.get("nombre"),
            "descripcion": request.form.get("descripcion") or None,
            "departamento_id": request.form.get("departamento_id") or None,
        }

        result, status = api_request("PUT", f"/nomina/categorias/{id}", data, token=token)

        if status == 200:
            flash("Categoría actualizada exitosamente", "success")
            if request.headers.get("HX-Request"):
                return "", 200, {"HX-Redirect": url_for("nomina.categorias_list")}
            return redirect(url_for("nomina.categorias_list"))

        err_block = error_html(result.get("detail"), "Error al actualizar categoría")
        if request.headers.get("HX-Request"):
            return err_block
        flash(format_api_error(result.get("detail"), "Error al actualizar categoría"), "error")

    item, _ = api_request("GET", f"/nomina/categorias/{id}", token=token)
    departamentos, _ = api_request("GET", "/nomina/departamentos/todos", token=token)
    return render_template("nomina/categorias_form.html", item=item, departamentos=departamentos or [])


@nomina_bp.route("/categorias/<id>/eliminar", methods=["DELETE"])
@require_permiso("nomina.categorias")
def categorias_delete(id):
    """Eliminar categoría (soft delete)."""
    api_request = get_api_request_func()
    token = session.get("token")
    result, status = api_request("DELETE", f"/nomina/categorias/{id}", token=token)

    if status == 200:
        return "", 200, {"HX-Trigger": "categoriaDeleted"}
    return error_html(result.get("detail"), "Error al eliminar categoría"), 400


# ============ CARRERAS ============
@nomina_bp.route("/carreras")
@require_permiso("nomina.carreras")
def carreras_list():
    """Listado de carreras."""
    api_request = get_api_request_func()
    token = session.get("token")
    data, _ = api_request("GET", "/nomina/carreras", token=token)
    items = data.get("items", []) if isinstance(data, dict) else []

    if request.headers.get("HX-Request"):
        return render_template("nomina/partials/carreras_table.html", items=items)
    return render_template("nomina/carreras_list.html", items=items)


@nomina_bp.route("/carreras/nuevo", methods=["GET", "POST"])
@require_permiso("nomina.carreras")
def carreras_create():
    """Crear carrera."""
    api_request = get_api_request_func()
    token = session.get("token")

    if request.method == "POST":
        data = {
            "nombre": request.form.get("nombre"),
            "descripcion": request.form.get("descripcion") or None,
        }
        result, status = api_request("POST", "/nomina/carreras", data, token=token)

        if status in [200, 201]:
            flash("Carrera creada exitosamente", "success")
            if request.headers.get("HX-Request"):
                return "", 200, {"HX-Redirect": url_for("nomina.carreras_list")}
            return redirect(url_for("nomina.carreras_list"))

        err_block = error_html(result.get("detail"), "Error al crear carrera")
        if request.headers.get("HX-Request"):
            return err_block
        flash(format_api_error(result.get("detail"), "Error al crear carrera"), "error")

    return render_template("nomina/carreras_form.html", item=None)


@nomina_bp.route("/carreras/<id>/editar", methods=["GET", "POST"])
@require_permiso("nomina.carreras")
def carreras_edit(id):
    """Editar carrera."""
    api_request = get_api_request_func()
    token = session.get("token")

    if request.method == "POST":
        data = {
            "nombre": request.form.get("nombre"),
            "descripcion": request.form.get("descripcion") or None,
        }
        result, status = api_request("PUT", f"/nomina/carreras/{id}", data, token=token)

        if status == 200:
            flash("Carrera actualizada", "success")
            if request.headers.get("HX-Request"):
                return "", 200, {"HX-Redirect": url_for("nomina.carreras_list")}
            return redirect(url_for("nomina.carreras_list"))

        err_block = error_html(result.get("detail"), "Error al actualizar carrera")
        if request.headers.get("HX-Request"):
            return err_block
        flash(format_api_error(result.get("detail"), "Error al actualizar carrera"), "error")

    item, _ = api_request("GET", f"/nomina/carreras/{id}", token=token)
    return render_template("nomina/carreras_form.html", item=item)


@nomina_bp.route("/carreras/<id>/eliminar", methods=["DELETE"])
@require_permiso("nomina.carreras")
def carreras_delete(id):
    """Eliminar carrera (soft delete)."""
    api_request = get_api_request_func()
    token = session.get("token")
    result, status = api_request("DELETE", f"/nomina/carreras/{id}", token=token)

    if status == 200:
        return "", 200, {"HX-Trigger": "carreraDeleted"}
    return error_html(result.get("detail"), "Error al eliminar carrera"), 400


# === SUBIR FOTO EMPLEADO ===
@nomina_bp.route("/empleados/<id>/foto", methods=["POST"])
@require_permiso("nomina.empleados")
def empleados_foto_upload(id):
    """Sube la foto de un empleado via multipart al backend."""
    import httpx
    from flask import current_app

    token = session.get("token")
    foto = request.files.get("foto")

    if not foto:
        return (
            '<div class="p-3 rounded-xl bg-red-50 text-red-800 border border-red-200 text-sm">No se seleccionó ningún archivo</div>',
            400,
        )

    api_url = current_app.config["API_URL"]
    url = f"{api_url}/api/v1/nomina/empleados/{id}/foto"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        with httpx.Client(timeout=30.0) as client:
            files = {"foto": (foto.filename, foto.read(), foto.content_type)}
            response = client.post(url, headers=headers, files=files)

            if response.status_code == 200:
                data = response.json()
                foto_url = data.get("foto", "")
                # Devolver el HTML actualizado del componente de foto
                return f'''
                <div id="foto-container" class="flex flex-col items-center gap-3">
                    <div class="w-32 h-32 rounded-2xl overflow-hidden border-2 border-dark-200 bg-dark-50">
                        <img src="{foto_url}" alt="Foto empleado" class="w-full h-full object-cover">
                    </div>
                    <button type="button" 
                            hx-delete="/nomina/empleados/{id}/foto" 
                            hx-target="#foto-container" 
                            hx-swap="outerHTML"
                            hx-confirm="¿Eliminar la foto?"
                            class="flex items-center px-3 py-1.5 text-xs font-medium text-red-600 bg-red-50 border border-red-200 rounded-lg hover:bg-red-100 transition-colors">
                        <i data-lucide="trash-2" class="w-3 h-3 mr-1"></i>
                        Eliminar foto
                    </button>
                </div>
                <script>lucide.createIcons();</script>
                '''
            else:
                detail = response.json().get("detail", "Error al subir foto")
                return (
                    f'<div class="p-3 rounded-xl bg-red-50 text-red-800 border border-red-200 text-sm">{detail}</div>',
                    400,
                )
    except Exception as e:
        return (
            f'<div class="p-3 rounded-xl bg-red-50 text-red-800 border border-red-200 text-sm">Error: {str(e)}</div>',
            500,
        )


# === ELIMINAR FOTO EMPLEADO ===
@nomina_bp.route("/empleados/<id>/foto", methods=["DELETE"])
@require_permiso("nomina.empleados")
def empleados_foto_delete(id):
    """Elimina la foto de un empleado."""
    import httpx
    from flask import current_app

    token = session.get("token")
    api_url = current_app.config["API_URL"]
    url = f"{api_url}/api/v1/nomina/empleados/{id}/foto"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.delete(url, headers=headers)

            if response.status_code == 200:
                return f"""
                <div id="foto-container" class="flex flex-col items-center gap-3">
                    <div class="w-32 h-32 rounded-2xl overflow-hidden border-2 border-dashed border-dark-300 bg-dark-50 flex items-center justify-center">
                        <i data-lucide="camera" class="w-10 h-10 text-dark-300"></i>
                    </div>
                    <label class="flex items-center px-3 py-1.5 text-xs font-medium text-primary-600 bg-primary-50 border border-primary-200 rounded-lg hover:bg-primary-100 transition-colors cursor-pointer">
                        <i data-lucide="upload" class="w-3 h-3 mr-1"></i>
                        Subir foto
                        <input type="file" name="foto" accept=".jpg,.jpeg,.png,.webp" class="hidden"
                               hx-post="/nomina/empleados/{id}/foto"
                               hx-target="#foto-container"
                               hx-swap="outerHTML"
                               hx-encoding="multipart/form-data">
                    </label>
                    <p class="text-xs text-dark-400">JPG, PNG o WebP. Máx 2MB</p>
                </div>
                <script>lucide.createIcons();</script>
                """
            else:
                detail = response.json().get("detail", "Error al eliminar foto")
                return (
                    f'<div class="p-3 rounded-xl bg-red-50 text-red-800 border border-red-200 text-sm">{detail}</div>',
                    400,
                )
    except Exception as e:
        return (
            f'<div class="p-3 rounded-xl bg-red-50 text-red-800 border border-red-200 text-sm">Error: {str(e)}</div>',
            500,
        )


def _get_empleado_form_data():
    """Extrae los datos del formulario de empleado."""

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

    return {
        "codigo": request.form.get("codigo") or None,
        "cuil": int("".join(filter(str.isdigit, request.form.get("cuil", "")))) if request.form.get("cuil") else None,
        "apellido": request.form.get("apellido") or None,
        "nombre": request.form.get("nombre") or None,
        "fecha_nacimiento": parse_date(request.form.get("fecha_nacimiento")),
        "dni": request.form.get("dni") or None,
        "genero": request.form.get("genero") or None,
        "nacionalidad": request.form.get("nacionalidad") or None,
        "estado_civil": request.form.get("estado_civil") or None,
        "nivel_estudio": request.form.get("nivel_estudio") or None,
        "carrera_id": request.form.get("carrera_id") or None,
        "telefono_personal": request.form.get("telefono_personal") or None,
        "email_personal": request.form.get("email_personal") or None,
        # Dirección Laboral
        "dir_laboral_pais": request.form.get("dir_laboral_pais") or None,
        "dir_laboral_provincia": request.form.get("dir_laboral_provincia") or None,
        "dir_laboral_localidad": request.form.get("dir_laboral_localidad") or None,
        "dir_laboral_codigo_postal": request.form.get("dir_laboral_codigo_postal") or None,
        "dir_laboral_barrio": request.form.get("dir_laboral_barrio") or None,
        "dir_laboral_calle": request.form.get("dir_laboral_calle") or None,
        "dir_laboral_numero": request.form.get("dir_laboral_numero") or None,
        "dir_laboral_piso": request.form.get("dir_laboral_piso") or None,
        "dir_laboral_departamento": request.form.get("dir_laboral_departamento") or None,
        # Dirección de Obsequios
        "usar_direccion_laboral": request.form.get("usar_direccion_laboral") == "true",
        "dir_obsequios_pais": request.form.get("dir_obsequios_pais") or None,
        "dir_obsequios_provincia": request.form.get("dir_obsequios_provincia") or None,
        "dir_obsequios_localidad": request.form.get("dir_obsequios_localidad") or None,
        "dir_obsequios_codigo_postal": request.form.get("dir_obsequios_codigo_postal") or None,
        "dir_obsequios_barrio": request.form.get("dir_obsequios_barrio") or None,
        "dir_obsequios_calle": request.form.get("dir_obsequios_calle") or None,
        "dir_obsequios_numero": request.form.get("dir_obsequios_numero") or None,
        "dir_obsequios_piso": request.form.get("dir_obsequios_piso") or None,
        "dir_obsequios_departamento": request.form.get("dir_obsequios_departamento") or None,
        # Ocasiones Especiales
        "preferencia_alimentaria": request.form.get("preferencia_alimentaria") or None,
        "instrucciones_entrega": request.form.get("instrucciones_entrega") or None,
        "contacto_emergencia": request.form.get("contacto_emergencia") or None,
        "numero_emergencia": request.form.get("numero_emergencia") or None,
        "parentesco": request.form.get("parentesco") or None,
        "fecha_alta": parse_date(request.form.get("fecha_alta")),
        "fecha_baja": parse_date(request.form.get("fecha_baja")),
        "motivo_baja": request.form.get("motivo_baja") or None,
        # El email corporativo no va: es copia del email de la cuenta (Configuración › Usuarios, F22)
        "departamento_id": request.form.get("departamento_id") or None,
        "perfil_id": request.form.get("perfil_id") or None,
        "puesto": request.form.get("puesto") or None,
        "hrbp_id": request.form.get("hrbp_id") or None,
        "seniority": request.form.get("seniority") or None,
    }
