"""
Módulo Recruiting: Dashboard, Manager Dashboard, Candidatos y Búsquedas. Pipeline y Parámetros se migran después.
"""

import logging
import re
import unicodedata
from urllib.parse import quote, unquote, urlencode, urlsplit

import httpx
from flask import (
    Blueprint,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from modulos.auth_helpers import _obtener_permisos_usuario, get_api_request_func, require_permiso

recruiting_bp = Blueprint("recruiting", __name__, template_folder="templates", url_prefix="/recruiting")

ERROR_DASHBOARD = "No se pudo cargar el Dashboard de Recruiting. Probá de nuevo en unos minutos."


def _es_admin():
    """Solo orienta la interfaz (qué dashboard mostrar): el acceso real lo valida el backend con require_admin en cada
    llamada al Manager Dashboard. En el módulo original esto era el email admin@admin.com; en el Core es el rol."""
    return (session.get("user") or {}).get("rol") == "admin"


def _ve_candidatos():
    """Si el usuario tiene el ítem Candidatos: el Dashboard solo enlaza a las pantallas a las que puede entrar."""
    if _es_admin():
        return True
    permisos = _obtener_permisos_usuario()
    return bool(permisos.get("recruiting") and permisos.get("recruiting.candidatos"))


# === DASHBOARD ===
# /recruiting/dashboard va primero: es la URL que arma url_for('recruiting.dashboard') para el menú.
# El administrador entra por el mismo ítem del menú y ve el Manager Dashboard, como en el módulo original.
@recruiting_bp.route("/")
@recruiting_bp.route("/dashboard")
@require_permiso("recruiting.dashboard")
def dashboard():
    if _es_admin():
        return redirect(url_for("recruiting.manager_dashboard"))

    api_request = get_api_request_func()
    data, status = api_request("GET", "/recruiting/dashboard", token=session.get("token"))

    if status != 200 or not isinstance(data, dict):
        # Sin datos no se muestran ceros: se avisa que no se pudo cargar
        detalle = data.get("detail") if isinstance(data, dict) else None
        return render_template("recruiting/dashboard.html", dashboard=None, error=detalle or ERROR_DASHBOARD)

    return render_template("recruiting/dashboard.html", dashboard=data, error=None, tiene_candidatos=_ve_candidatos())


# === MANAGER DASHBOARD (solo administradores) ===
# Cuelga de /recruiting/dashboard para que el ítem "Dashboard" del menú siga resaltado (el menú compara el prefijo).
@recruiting_bp.route("/dashboard/manager")
@require_permiso("recruiting.dashboard")
def manager_dashboard():
    if not _es_admin():
        return render_template("core/403.html", modulo="recruiting.manager_dashboard"), 403
    return render_template("recruiting/manager_dashboard.html")


@recruiting_bp.route("/dashboard/manager/datos")
@require_permiso("recruiting.dashboard")
def manager_dashboard_datos():
    """Proxy de los indicadores: el backend valida el acceso (require_admin) y responde 403 si corresponde."""
    api_request = get_api_request_func()
    consulta = request.query_string.decode("utf-8")
    endpoint = "/recruiting/manager-dashboard" + (f"?{consulta}" if consulta else "")
    try:
        data, status = api_request("GET", endpoint, token=session.get("token"))
    except Exception:
        return jsonify({"error": "Error de comunicación con el servidor"}), 500
    if status == 200 and isinstance(data, dict):
        return jsonify(data), 200
    detalle = data.get("detail") if isinstance(data, dict) else None
    if isinstance(detalle, list):
        detalle = "Filtros inválidos"
    return jsonify({"error": detalle or "Error al obtener el Manager Dashboard"}), status or 500


# === NAVEGACIÓN: el parámetro "volver" (solo rutas internas de Recruiting) ===
def _volver_valido(destino):
    """Destino de retorno seguro: solo rutas internas de Recruiting (nunca URLs externas ni destinos arbitrarios)."""
    if not destino or not isinstance(destino, str):
        return None
    destino = destino.strip()
    if len(destino) > 1000 or destino.startswith("//") or "\\" in destino or any(ord(c) < 32 for c in destino):
        return None
    partes = urlsplit(destino)
    if partes.scheme or partes.netloc:
        return None
    if partes.path != "/recruiting" and not partes.path.startswith("/recruiting/"):
        return None
    if ".." in unquote(partes.path).split("/"):
        return None
    return destino


@recruiting_bp.context_processor
def _utilidades_navegacion():
    """Helpers de plantilla para que «Volver» regrese a la pantalla de origen (parámetro «volver» validado)."""

    def volver_a(default):
        return _volver_valido(request.args.get("volver")) or default

    def con_volver(url):
        actual = request.full_path.rstrip("?")
        return f"{url}{'&' if '?' in url else '?'}volver={quote(actual, safe='')}"

    return {"volver_a": volver_a, "con_volver": con_volver}


# === CANDIDATOS ===
# Todas las rutas exigen 'recruiting.candidatos'; el backend valida el acceso de verdad en cada llamada y esta capa solo
# orienta la interfaz. Hasta que se migren Búsquedas y Pipeline, el listado no asigna candidatos a una búsqueda ni
# enlaza a su pipeline.

MENSAJE_ERROR_GENERICO = "No se pudo completar la operación. Intentá nuevamente"
EXTENSIONES_CV = (".pdf", ".doc", ".docx")
EXTENSIONES_COMPRIMIDOS = (".zip", ".rar")
MAX_CV_BYTES = 2 * 1024 * 1024
MAX_CV_CARGA_BYTES = 5 * 1024 * 1024
MAX_CARGA_MASIVA_BYTES = 500 * 1024 * 1024
MAX_CVS_INDIVIDUALES = 100


def _detalle_de_error(data, por_defecto):
    """Texto para mostrar de un error del backend ({"detail": "..."}); los 422 de validación traen además `errores`."""
    if isinstance(data, dict):
        detalle = data.get("detail")
        if isinstance(detalle, str) and detalle:
            return detalle
    return por_defecto


def _permisos_candidatos():
    """Acciones que el usuario ve en la pantalla; restrictivo si no se puede consultar el backend."""
    permisos = {"puede_eliminar_candidatos": False, "puede_cargar_cv_general": False, "puede_carga_masiva": False}
    try:
        data, status = get_api_request_func()("GET", "/recruiting/candidatos/permisos", token=session.get("token"))
        if status == 200 and isinstance(data, dict):
            for clave in permisos:
                permisos[clave] = bool(data.get(clave))
    except Exception:
        pass
    return permisos


def _clave_catalogo(texto):
    """Clave de comparación sin tildes ni mayúsculas (para nombres de provincias y ciudades)."""
    sin_tildes = "".join(c for c in unicodedata.normalize("NFKD", texto or "") if not unicodedata.combining(c))
    return sin_tildes.casefold().strip()


_ORDEN_PROVINCIAS = ["cordoba", "buenos aires"]

# Registro interno de recruiting_provincias que representa la categoría «Otros»: se muestra con ese nombre
_PROVINCIA_GENERICA_CLAVE = "no identificada"
_PROVINCIA_GENERICA_VISIBLE = "Otros"


def _nombre_visible_provincia(nombre):
    return _PROVINCIA_GENERICA_VISIBLE if _clave_catalogo(nombre) == _PROVINCIA_GENERICA_CLAVE else nombre


def _orden_provincia(nombre):
    """Orden de visualización de provincias: Córdoba, Buenos Aires y luego el resto alfabéticamente."""
    clave = _clave_catalogo(nombre)
    return (_ORDEN_PROVINCIAS.index(clave) if clave in _ORDEN_PROVINCIAS else len(_ORDEN_PROVINCIAS), clave)


def _entero_o_none(valor):
    try:
        return int(valor) if valor not in (None, "") else None
    except TypeError, ValueError:
        return None


def normalizar_fecha(valor):
    """Fecha de nacimiento como AAAA-MM-DD (acepta también DD/MM/AAAA y DD-MM-AAAA); None si no se entiende."""
    if not valor:
        return None
    texto = str(valor).strip()
    if not texto or texto in {"-", "--", "—", "null", "None", "undefined"}:
        return None
    if "T" in texto or " " in texto:
        texto = texto.split("T")[0].split(" ")[0].strip()
    dia_primero = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", texto)
    if dia_primero:
        d, m, a = dia_primero.groups()
        return f"{a}-{int(m):02d}-{int(d):02d}"
    anio_primero = re.match(r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})$", texto)
    if anio_primero:
        a, m, d = anio_primero.groups()
        return f"{a}-{int(m):02d}-{int(d):02d}"
    return None


def _lista_de_nombres(api_request, token, endpoint, ordenar=True):
    """Nombres de un catálogo de solo lectura; lista vacía si el backend no responde."""
    try:
        data, status = api_request("GET", endpoint, token=token)
        if status == 200 and isinstance(data, list):
            nombres = [i["nombre"] for i in data if isinstance(i, dict) and i.get("nombre")]
            return sorted(nombres, key=lambda s: s.lower()) if ordenar else nombres
    except Exception:
        pass
    return []


def _cargar_catalogos_ubicacion(api_request, token):
    """Provincias y ciudades del catálogo, para los combos Provincia y Ciudad."""
    provincias, ciudades = [], []
    try:
        prov_data, prov_status = api_request("GET", "/recruiting/provincias", token=token)
        if prov_status == 200 and isinstance(prov_data, list):
            provincias = sorted(
                [
                    {"provincia_id": p["provincia_id"], "nombre": _nombre_visible_provincia(p["nombre"])}
                    for p in prov_data
                    if isinstance(p, dict) and p.get("nombre") and p.get("provincia_id") is not None
                ],
                key=lambda p: _orden_provincia(p["nombre"]),
            )
        ciu_data, ciu_status = api_request("GET", "/recruiting/ciudades", token=token)
        if ciu_status == 200 and isinstance(ciu_data, list):
            ciudades = [
                {"ciudad_id": c["ciudad_id"], "nombre": c["nombre"], "provincia_id": c["provincia_id"]}
                for c in ciu_data
                if isinstance(c, dict) and c.get("nombre") and c.get("ciudad_id") is not None
            ]
    except Exception:
        provincias, ciudades = [], []
    return provincias, ciudades


def _cargar_perfiles_puesto(api_request, token):
    """Perfiles de puesto activos para el combo «Puesto»; devuelve (nombres, consulta_ok)."""
    try:
        data, status = api_request("GET", "/recruiting/candidatos/perfiles-puesto", token=token)
        if status == 200 and isinstance(data, list):
            return [p for p in data if isinstance(p, str) and p.strip()], True
    except Exception:
        pass
    return [], False


def _contexto_de_formulario(api_request, token):
    """Catálogos que comparten el formulario de alta y la ficha de un candidato."""
    perfiles, perfiles_ok = _cargar_perfiles_puesto(api_request, token)
    provincias, ciudades = _cargar_catalogos_ubicacion(api_request, token)
    return {
        "perfiles_puesto_catalogo": perfiles,
        "perfiles_puesto_ok": perfiles_ok,
        "provincias_catalogo": provincias,
        "ciudades_catalogo": ciudades,
        "skills_catalogo": _lista_de_nombres(api_request, token, "/recruiting/skills"),
        "habilidades_catalogo": _lista_de_nombres(api_request, token, "/recruiting/habilidades"),
    }


def _opciones_de_filtros(api_request, token):
    """Opciones de los filtros del listado: provincias, categorías de skills (y sus skills), seniority y perfiles."""
    provincias = []
    try:
        data, status = api_request("GET", "/recruiting/provincias", token=token)
        if status == 200 and isinstance(data, list):
            provincias = sorted(
                [
                    p["nombre"]
                    for p in data
                    # La provincia genérica se filtra con la opción fija «Otros» de la plantilla
                    if isinstance(p, dict)
                    and p.get("nombre")
                    and _clave_catalogo(p["nombre"]) != _PROVINCIA_GENERICA_CLAVE
                ],
                key=_orden_provincia,
            )
    except Exception:
        provincias = []

    categorias, skills_por_categoria = [], {}
    try:
        data, status = api_request("GET", "/recruiting/skills", token=token)
        if status == 200 and isinstance(data, list):
            vistas = {}
            for skill in data:
                if not isinstance(skill, dict):
                    continue
                original = " ".join((skill.get("categoria") or "").split())
                if not original:
                    continue
                vistas.setdefault(original.casefold(), original)
                nombre = " ".join((skill.get("nombre") or "").split())
                if nombre:
                    skills_por_categoria.setdefault(vistas[original.casefold()], set()).add(nombre)
            categorias = sorted(vistas.values(), key=lambda c: c.casefold())
            skills_por_categoria = {
                cat: sorted(nombres, key=lambda n: n.casefold()) for cat, nombres in skills_por_categoria.items()
            }
    except Exception:
        categorias, skills_por_categoria = [], {}

    perfiles, _ = _cargar_perfiles_puesto(api_request, token)
    niveles = _lista_de_nombres(api_request, token, "/recruiting/niveles-seniority", ordenar=False)
    return provincias, categorias, skills_por_categoria, perfiles, niveles


@recruiting_bp.route("/candidatos", methods=["GET"])
@require_permiso("recruiting.candidatos")
def candidatos():
    api_request = get_api_request_func()
    token = session.get("token")

    busqueda = request.args.get("busqueda") or request.args.get("search") or request.args.get("q") or ""
    estado = request.args.get("estado") or ""
    fuente = request.args.get("fuente") or ""
    seniority = request.args.get("seniority") or ""
    ubicacion = request.args.get("ubicacion") or ""
    puesto = (request.args.get("puesto") or "").strip()
    categorias_sel = []
    for c in request.args.getlist("categorias"):
        c = " ".join((c or "").split())
        if c and c.casefold() not in [x.casefold() for x in categorias_sel]:
            categorias_sel.append(c)
    categorias_sel = categorias_sel[:20]
    skill_sel = " ".join((request.args.get("skills") or "").split())

    try:
        pagina = max(1, int(request.args.get("page") or request.args.get("pagina") or 1))
    except ValueError, TypeError:
        pagina = 1
    try:
        limite = int(request.args.get("limit") or request.args.get("por_pagina") or 20)
    except ValueError, TypeError:
        limite = 20
    limite = 20 if limite <= 20 else 50 if limite <= 50 else 100

    provincias, categorias_skills, skills_por_categoria, perfiles_puesto, niveles_seniority = _opciones_de_filtros(
        api_request, token
    )

    # La skill específica solo aplica si hay una categoría elegida y la skill pertenece a ella
    if not (categorias_sel and skill_sel and skill_sel in skills_por_categoria.get(categorias_sel[0], [])):
        skill_sel = ""

    parametros = [("pagina", pagina), ("por_pagina", limite)]
    for clave, valor in (
        ("busqueda", busqueda),
        ("estado", estado),
        ("fuente", fuente),
        ("seniority", seniority),
        ("ubicacion", ubicacion),
        ("puesto", puesto),
    ):
        if valor:
            parametros.append((clave, valor))
    parametros += [("categorias", c) for c in categorias_sel]
    if skill_sel:
        parametros.append(("skills", skill_sel))

    data, status = api_request("GET", f"/recruiting/candidatos?{urlencode(parametros)}", token=token)

    candidatos_pagina, total_registros, total_paginas = [], 0, 1
    if status == 200 and isinstance(data, dict):
        candidatos_pagina = data.get("items", [])
        total_registros = data.get("total", len(candidatos_pagina))
        total_paginas = data.get("total_paginas", 1)
        pagina = data.get("pagina", pagina)
        limite = data.get("por_pagina", limite)

    if total_registros > 0:
        registro_inicio = (pagina - 1) * limite + 1
        registro_fin = min(pagina * limite, total_registros)
    else:
        registro_inicio = registro_fin = 0

    return render_template(
        "recruiting/candidatos.html",
        niveles_seniority=niveles_seniority,
        provincias=provincias,
        categorias_skills=categorias_skills,
        skills_por_categoria=skills_por_categoria,
        filtro_skill=skill_sel,
        perfiles_puesto=perfiles_puesto,
        filtro_puesto=puesto,
        filtro_categorias=categorias_sel,
        candidatos=candidatos_pagina,
        total_registros=total_registros,
        total_paginas=total_paginas,
        pagina_actual=pagina,
        limite_actual=limite,
        registro_inicio=registro_inicio,
        registro_fin=registro_fin,
        filtro_busqueda=busqueda,
        filtro_estado=estado,
        filtro_fuente=fuente,
        filtro_seniority=seniority,
        filtro_ubicacion=ubicacion,
        error_listado=None if status == 200 else _detalle_de_error(data, "No se pudo cargar el listado de candidatos."),
        **_permisos_candidatos(),
    )


@recruiting_bp.route("/candidatos/nuevo", methods=["GET"])
@require_permiso("recruiting.candidatos")
def nuevo_candidato():
    api_request = get_api_request_func()
    token = session.get("token")
    return render_template(
        "recruiting/candidato_form.html",
        niveles_seniority_catalogo=_lista_de_nombres(
            api_request, token, "/recruiting/niveles-seniority", ordenar=False
        ),
        **_contexto_de_formulario(api_request, token),
    )


def _lista_desde_texto(valor):
    """Skills y habilidades llegan como lista (fetch) o como texto separado por comas (formulario clásico)."""
    if isinstance(valor, str):
        return [s.strip() for s in valor.split(",") if s.strip()]
    return valor if isinstance(valor, list) else []


def _payload_de_candidato(body):
    """Cuerpo del alta en la forma de CandidatoCreate, desde el JSON del fetch o el formulario clásico."""
    if "apellido" in body and body.get("apellido") is not None:
        nombre = (body.get("nombre") or "").strip()
        apellido = (body.get("apellido") or "").strip()
    else:
        partes = (body.get("nombre") or "").strip().split(" ", 1)
        nombre = partes[0] if partes else ""
        apellido = partes[1] if len(partes) > 1 else ""

    pretension = None
    salario_raw = body.get("salario") or body.get("pretension_salarial")
    if salario_raw:
        limpio = re.sub(r"[^\d.]", "", str(salario_raw).replace(".", "").replace(",", "."))
        try:
            pretension = float(limpio) if limpio else None
        except ValueError:
            pretension = None

    return {
        "nombre": nombre,
        "apellido": apellido,
        "email": (body.get("email") or "").strip(),
        "telefono": (body.get("telefono") or "").strip() or None,
        "ubicacion": (body.get("ubicacion") or "").strip() or None,
        "provincia_id": _entero_o_none(body.get("provincia_id")),
        "ciudad_id": _entero_o_none(body.get("ciudad_id")),
        "dni": (body.get("dni") or "").strip() or None,
        "fecha_nacimiento": normalizar_fecha(body.get("fecha_nacimiento")),
        "linkedin_url": (body.get("linkedin") or body.get("linkedin_url") or "").strip() or None,
        "cv_url": (body.get("cv_url") or "").strip() or None,
        "headline": (body.get("puesto") or body.get("headline") or "").strip() or None,
        "seniority": (body.get("seniority") or "").strip() or None,
        "modalidad": (body.get("modalidad") or "").strip() or None,
        "skills": _lista_desde_texto(body.get("skills")),
        "habilidades": _lista_desde_texto(body.get("habilidades")),
        "pretension_salarial": pretension,
        "moneda_pretension": (body.get("moneda_pretension") or "ARS").strip().upper(),
        "estado": (body.get("estado") or "Activo").strip(),
        "fuente": (body.get("fuente") or "Portal Propio").strip(),
    }


@recruiting_bp.route("/candidatos", methods=["POST"])
@require_permiso("recruiting.candidatos")
def crear_candidato():
    """Reenvía el alta al backend; el backend valida y es dueño de las reglas."""
    api_request = get_api_request_func()
    token = session.get("token")
    body = (request.get_json(silent=True) or {}) if request.is_json else request.form.to_dict()

    data, status = api_request("POST", "/recruiting/candidatos", data=_payload_de_candidato(body), token=token)
    destino = _volver_valido(body.get("volver")) or url_for("recruiting.candidatos")

    if status in (200, 201):
        if request.is_json:
            return {"success": True, "candidato": data, "redirect": destino}, 201
        return redirect(destino)

    error_msg = _detalle_de_error(data, "Error al crear el candidato")
    if request.is_json:
        return {"success": False, "error": error_msg}, status

    # Envío clásico: se vuelve a mostrar el formulario con el error y lo que el usuario cargó
    return (
        render_template(
            "recruiting/candidato_form.html",
            error=error_msg,
            form=body,
            niveles_seniority_catalogo=_lista_de_nombres(
                api_request, token, "/recruiting/niveles-seniority", ordenar=False
            ),
            **_contexto_de_formulario(api_request, token),
        ),
        status,
    )


@recruiting_bp.route("/candidatos/<uuid:id>", methods=["GET"])
@require_permiso("recruiting.candidatos")
def candidato_detalle(id):
    api_request = get_api_request_func()
    token = session.get("token")
    data, status = api_request("GET", f"/recruiting/candidatos/{id}", token=token)
    if status != 200 or not isinstance(data, dict):
        msg = _detalle_de_error(data, "No se pudo encontrar el candidato solicitado o no tenés permisos para acceder.")
        flash(msg, "danger" if status == 403 else "warning")
        return redirect(url_for("recruiting.candidatos"))
    return render_template(
        "recruiting/candidato_detalle.html",
        candidato=data,
        volver_default=url_for("recruiting.candidatos"),
        **_contexto_de_formulario(api_request, token),
    )


@recruiting_bp.route("/candidatos/<uuid:id>", methods=["PUT"])
@require_permiso("recruiting.candidatos")
def candidato_actualizar(id):
    api_request = get_api_request_func()
    payload = request.get_json(silent=True) or {}
    if "fecha_nacimiento" in payload:
        payload["fecha_nacimiento"] = normalizar_fecha(payload.get("fecha_nacimiento"))
    data, status = api_request("PUT", f"/recruiting/candidatos/{id}", data=payload, token=session.get("token"))
    if status in (200, 201):
        return {"success": True, "candidato": data}, 200
    return {"success": False, "error": _detalle_de_error(data, "Error al actualizar el candidato")}, status


@recruiting_bp.route("/candidatos/<uuid:id>", methods=["DELETE"])
@require_permiso("recruiting.candidatos")
def candidato_eliminar(id):
    api_request = get_api_request_func()
    data, status = api_request("DELETE", f"/recruiting/candidatos/{id}", token=session.get("token"))
    if status in (200, 204):
        flash("Candidato eliminado correctamente.", "success")
        return {"success": True, "redirect": url_for("recruiting.candidatos")}, 200
    return {"success": False, "error": _detalle_de_error(data, "Error al eliminar el candidato")}, status


# --- Carga de CV: reenvío de archivos (multipart) al backend ---


def _reenviar_archivos(metodo, ruta, archivos=None, timeout=30.0):
    """Llama al backend con el token de la sesión (y archivos, si hay); devuelve (cuerpo JSON, código)."""
    try:
        with httpx.Client(timeout=timeout) as cliente:
            respuesta = cliente.request(
                metodo,
                f"{current_app.config['API_URL']}/api/v1/recruiting{ruta}",
                headers={"Authorization": f"Bearer {session.get('token')}"},
                files=archivos,
            )
        try:
            return respuesta.json(), respuesta.status_code
        except ValueError:
            return {"detail": "Respuesta no válida del backend"}, 502
    except Exception:
        logging.getLogger(__name__).error(f"Error al reenviar {metodo} {ruta} al backend", exc_info=True)
        return {"detail": MENSAJE_ERROR_GENERICO}, 500


def _archivo_de_cv(maximo_bytes):
    """El archivo del formulario ya validado (existe, extensión y tamaño) como (nombre, contenido, tipo), o un error."""
    archivo = request.files.get("archivo")
    if archivo is None:
        return None, ({"error": "No se envió ningún archivo de CV"}, 400)
    if not archivo.filename:
        return None, ({"error": "Nombre de archivo no válido"}, 400)
    if not archivo.filename.lower().endswith(EXTENSIONES_CV):
        return None, ({"error": "Solo se admiten archivos .pdf, .doc y .docx"}, 400)
    contenido = archivo.read()
    if len(contenido) > maximo_bytes:
        return None, (
            {"error": f"El archivo excede el tamaño máximo permitido de {maximo_bytes // (1024 * 1024)} MB."},
            400,
        )
    return (archivo.filename, contenido, archivo.content_type or "application/octet-stream"), None


@recruiting_bp.route("/candidatos/<uuid:id>/cv", methods=["POST"])
@require_permiso("recruiting.candidatos")
def candidato_subir_cv(id):
    """Sube el CV (PDF, DOC o DOCX, hasta 2 MB) al candidato."""
    archivo, error = _archivo_de_cv(MAX_CV_BYTES)
    if error:
        return jsonify(error[0]), error[1]
    data, status = _reenviar_archivos("POST", f"/candidatos/{id}/cv", {"archivo": archivo}, timeout=30.0)
    if status >= 400:
        return jsonify({"error": _detalle_de_error(data, MENSAJE_ERROR_GENERICO)}), status
    return jsonify(data), status


@recruiting_bp.route("/candidatos/cargar-cv", methods=["POST"], defaults={"accion": "cargar-cv"})
@recruiting_bp.route("/candidatos/actualizar-cv", methods=["POST"], defaults={"accion": "actualizar-cv"})
@require_permiso("recruiting.candidatos")
def candidato_cargar_individual_cv(accion):
    """Carga individual de un CV: extrae los datos y crea el candidato. Con email existente y CV distinto devuelve los
    datos de ambos CVs para compararlos; «actualizar-cv» confirma el reemplazo."""
    if not _permisos_candidatos()["puede_cargar_cv_general"]:
        return jsonify({"ok": False, "error": "No tenés permisos para cargar CV desde el listado de Candidatos."}), 403
    archivo, error = _archivo_de_cv(MAX_CV_CARGA_BYTES)
    if error:
        return jsonify(error[0]), error[1]

    data, status = _reenviar_archivos("POST", f"/candidatos/{accion}", {"archivo": archivo}, timeout=45.0)
    if status in (200, 201) and isinstance(data, dict) and data.get("ok", True) is not False:
        flash(
            "Candidato creado y CV procesado exitosamente."
            if accion == "cargar-cv"
            else "Candidato actualizado con el nuevo CV.",
            "success",
        )
        return (
            jsonify(
                {
                    "ok": True,
                    "success": True,
                    "candidato": data.get("candidato", data),
                    "redirect": url_for("recruiting.candidatos"),
                }
            ),
            201,
        )
    if status == 409 and isinstance(data, dict) and data.get("requiere_comparacion"):
        return (
            jsonify(
                {
                    "ok": False,
                    "requiere_comparacion": True,
                    "actual": data.get("actual", {}),
                    "nuevo": data.get("nuevo", {}),
                }
            ),
            409,
        )
    status = status if status >= 400 else 400
    mensaje = _detalle_de_error(data, "Error al procesar el archivo.")
    return jsonify({"ok": False, "error": MENSAJE_ERROR_GENERICO if status >= 500 else mensaje}), status


def _responder_lote(data, status):
    """Respuesta de las llamadas del lote masivo: los 5xx solo muestran el mensaje genérico."""
    if status < 400:
        return jsonify(data), 200
    detalle = _detalle_de_error(data, MENSAJE_ERROR_GENERICO)
    return jsonify({"ok": False, "error": MENSAJE_ERROR_GENERICO if status >= 500 else detalle}), status


@recruiting_bp.route("/candidatos/cargar-cv-masivo/iniciar", methods=["POST"])
@require_permiso("recruiting.candidatos")
def candidato_cargar_masivo_cv_iniciar():
    """Inicia la carga masiva en segundo plano (CV sueltos, .zip o .rar) y devuelve el lote para seguir su avance."""
    if not _permisos_candidatos()["puede_carga_masiva"]:
        return jsonify({"ok": False, "error": "No tenés permisos para realizar cargas masivas de CV."}), 403
    subidos = [a for a in request.files.getlist("archivos") if a and a.filename]
    if not subidos:
        return jsonify({"ok": False, "error": "No se envió ningún archivo"}), 400
    if any(not a.filename.lower().endswith(EXTENSIONES_CV + EXTENSIONES_COMPRIMIDOS) for a in subidos):
        return jsonify({"ok": False, "error": "Solo se admiten archivos .pdf, .doc, .docx, .zip y .rar"}), 400
    if sum(1 for a in subidos if a.filename.lower().endswith(EXTENSIONES_CV)) > MAX_CVS_INDIVIDUALES:
        return (
            jsonify(
                {"ok": False, "error": f"Se superó el límite de {MAX_CVS_INDIVIDUALES} CVs individuales por operación."}
            ),
            400,
        )
    envio, total_bytes = [], 0
    for a in subidos:
        contenido = a.read()
        total_bytes += len(contenido)
        envio.append(("archivos", (a.filename, contenido, a.content_type or "application/octet-stream")))
    if total_bytes > MAX_CARGA_MASIVA_BYTES:
        return jsonify({"ok": False, "error": "La carga supera el tamaño máximo permitido de 500 MB."}), 400
    data, status = _reenviar_archivos("POST", "/candidatos/cargar-cv-masivo/iniciar", envio, timeout=180.0)
    return _responder_lote(data, 200 if status == 202 else status)


@recruiting_bp.route("/candidatos/cargar-cv-masivo/<lote_id>/estado", methods=["GET"])
@require_permiso("recruiting.candidatos")
def candidato_cargar_masivo_cv_estado(lote_id):
    data, status = _reenviar_archivos("GET", f"/candidatos/cargar-cv-masivo/{quote(lote_id, safe='')}/estado")
    return _responder_lote(data, status)


@recruiting_bp.route("/candidatos/cargar-cv-masivo/<lote_id>/cancelar", methods=["POST"])
@require_permiso("recruiting.candidatos")
def candidato_cargar_masivo_cv_cancelar(lote_id):
    data, status = _reenviar_archivos("POST", f"/candidatos/cargar-cv-masivo/{quote(lote_id, safe='')}/cancelar")
    return _responder_lote(data, status)


# === BÚSQUEDAS (oportunidades) ===
# Todas las rutas exigen 'recruiting.oportunidades'; el backend valida el acceso de verdad en cada llamada y esta capa
# solo orienta la interfaz. El cambio de etapa, el kanban y «agregar candidato» desde el Pipeline se migran con
# Pipeline; la carga de CV desde una búsqueda asignada (EXTERNOS), con la revisión de CV duplicados.

ESTADOS_BUSQUEDA = ["Abierta", "Pre-ingreso", "Suspendida", "Ganada", "Cancelada"]
POR_PAGINA_BUSQUEDAS = (20, 50, 100)
ERROR_BUSQUEDAS = "No se pudo cargar el listado de búsquedas."

# Valores iniciales del formulario de una búsqueda nueva (los demás campos arrancan vacíos)
BUSQUEDA_NUEVA = {
    "id": "",
    "titulo": "",
    "puesto": "",
    "cliente": "",
    "vacantes": 1,
    "prioridad": "Alta",
    "tipo": "Efectiva",
    "seniority": "Senior",
    "modalidad": "Hibrido",
    "rango": "",
    "descripcion": "",
}


def _permisos_busquedas():
    """Acciones que el usuario ve en Búsquedas; restrictivo si no se puede consultar el backend."""
    permisos = {
        "puede_crear_busquedas": False,
        "puede_eliminar_busquedas": False,
        "puede_ver_lider_tipo_fecha_busqueda": False,
        "puede_ver_smart_matching": False,
        "puede_asignar_candidatos": False,
        "puede_asignar_reclutador": False,
        "puede_administrar_externos": False,
        "es_externo": False,
    }
    try:
        data, status = get_api_request_func()("GET", "/recruiting/oportunidades/permisos", token=session.get("token"))
        if status == 200 and isinstance(data, dict):
            for clave in permisos:
                permisos[clave] = bool(data.get(clave))
    except Exception:
        pass
    return permisos


def _externos_disponibles(api_request, token):
    """Usuarios del grupo Externos que se pueden asignar a una búsqueda (el backend valida el permiso)."""
    try:
        data, status = api_request("GET", "/recruiting/externos-disponibles", token=token)
        if status == 200 and isinstance(data, list):
            return [u for u in data if isinstance(u, dict) and u.get("id")]
    except Exception:
        pass
    return []


def _opciones_de_personas(api_request, token, ruta):
    """Nombres activos del catálogo de líderes o reclutadores, para los combos."""
    return _lista_de_nombres(api_request, token, f"/recruiting/{ruta}", ordenar=False)


# El formulario llama «hm» al líder y «reclutador» al reclutador
ALIAS_OPORTUNIDAD = {"lider_nombre": "hm", "recruiter_nombre": "reclutador"}
TEXTOS_OPORTUNIDAD = (
    "titulo",
    "cliente",
    "estado",
    "puesto",
    "area",
    "seniority",
    "modalidad",
    "rango",
    "prioridad",
    "tipo",
    "lider_nombre",
    "recruiter_nombre",
    "id_busqueda",
)


def _payload_de_oportunidad(body, solo_enviados=False):
    """Cuerpo de OportunidadCreate (alta) o de OportunidadUpdate (edición: solo viaja lo que vino) desde el JSON del
    formulario. Lo vacío no se manda: el backend aplica sus valores predeterminados (Abierta, Efectiva, Senior...)."""

    def valor(campo):
        return body[campo] if campo in body else body.get(ALIAS_OPORTUNIDAD.get(campo))

    def enviado(campo):
        return campo in body or ALIAS_OPORTUNIDAD.get(campo) in body

    payload = {}
    for campo in TEXTOS_OPORTUNIDAD:
        if solo_enviados and not enviado(campo):
            continue
        texto = valor(campo)
        texto = texto.strip() if isinstance(texto, str) else None
        if texto or solo_enviados or campo in ("lider_nombre", "recruiter_nombre"):
            payload[campo] = texto or None
    vacantes = _entero_o_none(body.get("vacantes"))
    if vacantes or not solo_enviados:
        payload["vacantes"] = vacantes or 1
    for campo in ("skills", "habilidades", "skills_deseadas"):
        if campo in body or not solo_enviados:
            payload[campo] = _lista_desde_texto(body.get(campo))
    if "descripcion" in body or not solo_enviados:
        descripcion = body.get("descripcion")
        payload["descripcion"] = (descripcion.strip() or None) if isinstance(descripcion, str) else None
    return payload


def _respuesta_de_busqueda(data, status, mensaje_ok, error_por_defecto, **extra):
    """Respuesta JSON de las acciones sobre una búsqueda: lo que espera la pantalla (success y ok, o error)."""
    if status in (200, 201) and isinstance(data, dict):
        return jsonify({"success": True, "ok": True, "oportunidad": data, "message": mensaje_ok, **extra}), 200
    return jsonify({"success": False, "ok": False, "error": _detalle_de_error(data, error_por_defecto)}), status or 400


@recruiting_bp.route("/oportunidades", methods=["GET"])
@require_permiso("recruiting.oportunidades")
def oportunidades():
    api_request = get_api_request_func()
    token = session.get("token")
    permisos = _permisos_busquedas()

    busqueda = (request.args.get("busqueda") or "").strip()
    estado = request.args.get("estado") or "Abierta"
    if estado != "todos" and estado not in ESTADOS_BUSQUEDA:
        estado = "Abierta"
    # El tipo solo se elige con permiso (el grupo EXTERNOS solo ve las efectivas)
    tipo = request.args.get("tipo") or "Efectiva"
    if tipo not in ("Efectiva", "Potencial", "Todas") or not permisos["puede_ver_lider_tipo_fecha_busqueda"]:
        tipo = "Efectiva"
    try:
        pagina = max(1, int(request.args.get("pagina") or 1))
    except ValueError, TypeError:
        pagina = 1
    try:
        limite = int(request.args.get("por_pagina") or POR_PAGINA_BUSQUEDAS[0])
    except ValueError, TypeError:
        limite = POR_PAGINA_BUSQUEDAS[0]
    limite = next((o for o in POR_PAGINA_BUSQUEDAS if limite <= o), POR_PAGINA_BUSQUEDAS[-1])

    parametros = [("pagina", pagina), ("por_pagina", limite), ("estado", estado), ("tipo", tipo)]
    if busqueda:
        parametros.append(("busqueda", busqueda))
    data, status = api_request("GET", f"/recruiting/oportunidades?{urlencode(parametros)}", token=token)

    items, total, total_paginas = [], 0, 1
    if status == 200 and isinstance(data, dict):
        items = data.get("items", [])
        total = data.get("total", len(items))
        total_paginas = data.get("total_paginas", 1)
        pagina = data.get("pagina", pagina)
        limite = data.get("por_pagina", limite)

    def url_pagina(numero):
        filtros = {"estado": estado, "tipo": tipo, "por_pagina": limite, "pagina": numero}
        if busqueda:
            filtros["busqueda"] = busqueda
        return url_for("recruiting.oportunidades", **filtros)

    return render_template(
        "recruiting/oportunidades.html",
        oportunidades=items,
        estados=ESTADOS_BUSQUEDA,
        filtro_busqueda=busqueda,
        filtro_estado=estado,
        filtro_tipo=tipo,
        total_registros=total,
        total_paginas=total_paginas,
        pagina_actual=pagina,
        limite_actual=limite,
        registro_inicio=(pagina - 1) * limite + 1 if total else 0,
        registro_fin=min(pagina * limite, total),
        url_pagina=url_pagina,
        error_listado=None if status == 200 else _detalle_de_error(data, ERROR_BUSQUEDAS),
        puede_administrar_externos=permisos["puede_administrar_externos"],
        externos_disponibles=_externos_disponibles(api_request, token)
        if permisos["puede_administrar_externos"]
        else [],
        puede_crear_busquedas=permisos["puede_crear_busquedas"],
        puede_eliminar_busquedas=permisos["puede_eliminar_busquedas"],
        puede_ver_lider_tipo_fecha=permisos["puede_ver_lider_tipo_fecha_busqueda"],
    )


@recruiting_bp.route("/oportunidades/nueva", methods=["GET"])
@require_permiso("recruiting.oportunidades")
def nueva_oportunidad():
    if not _permisos_busquedas()["puede_crear_busquedas"]:
        flash("No tenés permisos para crear búsquedas.", "error")
        return redirect(url_for("recruiting.oportunidades"))
    api_request = get_api_request_func()
    token = session.get("token")
    perfiles, perfiles_ok = _cargar_perfiles_puesto(api_request, token)
    return render_template(
        "recruiting/oportunidad_form.html",
        oportunidad=dict(BUSQUEDA_NUEVA),
        is_edit=False,
        perfiles_puesto_catalogo=perfiles,
        perfiles_puesto_ok=perfiles_ok,
        skills_catalogo=_lista_de_nombres(api_request, token, "/recruiting/skills"),
        habilidades_catalogo=_lista_de_nombres(api_request, token, "/recruiting/habilidades"),
        lideres_catalogo=_opciones_de_personas(api_request, token, "lideres"),
        reclutadores_catalogo=_opciones_de_personas(api_request, token, "reclutadores"),
    )


@recruiting_bp.route("/oportunidades", methods=["POST"])
@recruiting_bp.route("/oportunidades/nueva", methods=["POST"])
@require_permiso("recruiting.oportunidades")
def crear_oportunidad():
    """Reenvía el alta al backend; el backend valida y es dueño de las reglas."""
    body = request.get_json(silent=True) or {}
    data, status = get_api_request_func()(
        "POST", "/recruiting/oportunidades", data=_payload_de_oportunidad(body), token=session.get("token")
    )
    return _respuesta_de_busqueda(
        data,
        status,
        "Búsqueda creada exitosamente.",
        "Error al crear la búsqueda",
        redirect=url_for("recruiting.oportunidades"),
    )


@recruiting_bp.route("/oportunidades/<uuid:id>", methods=["GET"])
@require_permiso("recruiting.oportunidades")
def oportunidad_detalle(id):
    api_request = get_api_request_func()
    token = session.get("token")

    op, status = api_request("GET", f"/recruiting/oportunidades/{id}", token=token)
    if status != 200 or not isinstance(op, dict):
        flash(
            "No tenés acceso a esta búsqueda: no la tenés asignada."
            if status == 403
            else "La búsqueda solicitada no existe o no fue encontrada.",
            "error",
        )
        return redirect(url_for("recruiting.oportunidades"))

    permisos = _permisos_busquedas()
    # Búsqueda Ganada = cerrada: se muestra para consulta, sin acciones que modifiquen el proceso
    ganada = str(op.get("estado") or "").strip().lower() == "ganada"
    ve_smart_matching = permisos["puede_ver_smart_matching"] and not ganada
    puede_administrar_externos = permisos["puede_administrar_externos"] and not ganada

    candidatos, estado_candidatos = api_request("GET", f"/recruiting/oportunidades/{id}/candidatos", token=token)
    sugeridos, match_minimo = [], 50
    if ve_smart_matching:
        datos_sug, estado_sug = api_request(
            "GET", f"/recruiting/oportunidades/{id}/candidatos-compatibles", token=token
        )
        if estado_sug == 200 and isinstance(datos_sug, list):
            sugeridos = datos_sug
        config, estado_config = api_request("GET", "/recruiting/config", token=token)
        if estado_config == 200 and isinstance(config, dict):
            match_minimo = config.get("match_minimo_porcentaje", 50)

    perfiles, perfiles_ok = _cargar_perfiles_puesto(api_request, token)
    return render_template(
        "recruiting/oportunidad_detalle.html",
        op=op,
        oportunidad=op,
        busqueda_ganada=ganada,
        perfiles_puesto_catalogo=perfiles,
        perfiles_puesto_ok=perfiles_ok,
        candidatos_proceso=candidatos if estado_candidatos == 200 and isinstance(candidatos, list) else [],
        candidatos_sugeridos=sugeridos,
        match_minimo=match_minimo,
        skills_catalogo=_lista_de_nombres(api_request, token, "/recruiting/skills"),
        habilidades_catalogo=_lista_de_nombres(api_request, token, "/recruiting/habilidades"),
        puede_asignar_reclutador=permisos["puede_asignar_reclutador"] and not ganada,
        puede_ver_lider_tipo_fecha=permisos["puede_ver_lider_tipo_fecha_busqueda"],
        puede_ver_smart_matching=ve_smart_matching,
        puede_administrar_externos=puede_administrar_externos,
        es_usuario_externo=permisos["es_externo"],
        externos_disponibles=_externos_disponibles(api_request, token) if puede_administrar_externos else [],
        reclutadores_catalogo=_opciones_de_personas(api_request, token, "reclutadores"),
    )


@recruiting_bp.route("/oportunidades/<uuid:id>/editar", methods=["GET"])
@require_permiso("recruiting.oportunidades")
def editar_oportunidad(id):
    return redirect(url_for("recruiting.oportunidad_detalle", id=id, edit="true"))


@recruiting_bp.route("/oportunidades/<uuid:id>", methods=["PUT"])
@require_permiso("recruiting.oportunidades")
def actualizar_oportunidad(id):
    body = request.get_json(silent=True) or {}
    data, status = get_api_request_func()(
        "PUT",
        f"/recruiting/oportunidades/{id}",
        data=_payload_de_oportunidad(body, solo_enviados=True),
        token=session.get("token"),
    )
    return _respuesta_de_busqueda(
        data, status, "Búsqueda actualizada correctamente.", "Error al actualizar la búsqueda"
    )


@recruiting_bp.route("/oportunidades/<uuid:id>/asignar", methods=["POST"])
@require_permiso("recruiting.oportunidades")
def asignar_oportunidad(id):
    """El reclutador toma la búsqueda: queda como responsable con la fecha de asignación."""
    data, status = get_api_request_func()("POST", f"/recruiting/oportunidades/{id}/asignar", token=session.get("token"))
    return _respuesta_de_busqueda(
        data,
        status,
        "Búsqueda asignada correctamente.",
        "Error al asignar la búsqueda",
        fecha_asignacion=data.get("fecha_asignacion") if isinstance(data, dict) else None,
    )


@recruiting_bp.route("/oportunidades/<uuid:id>/desasignar", methods=["POST"])
@require_permiso("recruiting.oportunidades")
def desasignar_oportunidad(id):
    """Libera la búsqueda para que otro reclutador pueda tomarla."""
    data, status = get_api_request_func()(
        "POST", f"/recruiting/oportunidades/{id}/desasignar", token=session.get("token")
    )
    return _respuesta_de_busqueda(
        data,
        status,
        "Búsqueda desasignada correctamente. Queda libre para ser tomada.",
        "Error al desasignar la búsqueda",
        fecha_asignacion=None,
    )


@recruiting_bp.route("/oportunidades/<uuid:id>/reclutador", methods=["POST"])
@require_permiso("recruiting.oportunidades")
def asignar_reclutador_oportunidad(id):
    """Asigna o reasigna el reclutador responsable con una persona activa del catálogo de Reclutadores."""
    body = request.get_json(silent=True) or {}
    data, status = get_api_request_func()(
        "POST",
        f"/recruiting/oportunidades/{id}/reclutador",
        data={"recruiter_nombre": (body.get("recruiter_nombre") or "").strip()},
        token=session.get("token"),
    )
    return _respuesta_de_busqueda(data, status, "Reclutador asignado correctamente.", "Error al asignar el reclutador")


@recruiting_bp.route("/oportunidades/<uuid:id>/externo", methods=["POST"])
@require_permiso("recruiting.oportunidades")
def asignar_externo_oportunidad(id):
    """Asigna o cambia el usuario externo (grupo Externos) de la búsqueda."""
    body = request.get_json(silent=True) or {}
    data, status = get_api_request_func()(
        "PUT",
        f"/recruiting/oportunidades/{id}/externo",
        data={"externo_id": (body.get("externo_id") or "").strip()},
        token=session.get("token"),
    )
    return _respuesta_de_busqueda(
        data, status, "Usuario externo asignado correctamente.", "Error al asignar el usuario externo"
    )


@recruiting_bp.route("/oportunidades/<uuid:id>/externo", methods=["DELETE"])
@require_permiso("recruiting.oportunidades")
def quitar_externo_oportunidad(id):
    """Quita la asignación del usuario externo; la búsqueda y sus candidatos no se modifican."""
    data, status = get_api_request_func()(
        "DELETE", f"/recruiting/oportunidades/{id}/externo", token=session.get("token")
    )
    return _respuesta_de_busqueda(
        data, status, "Asignación del usuario externo quitada.", "Error al quitar la asignación del usuario externo"
    )


@recruiting_bp.route("/oportunidades/<uuid:id>/candidatos", methods=["POST"])
@require_permiso("recruiting.oportunidades")
def asignar_candidato_oportunidad(id):
    """Suma un candidato (Smart Matching) a la búsqueda."""
    body = request.get_json(silent=True) or {}
    data, status = get_api_request_func()(
        "POST", f"/recruiting/oportunidades/{id}/candidatos", data=body, token=session.get("token")
    )
    if status in (200, 201):
        return jsonify({"success": True, "data": data}), status
    return jsonify({"success": False, "error": _detalle_de_error(data, "Error al asignar el candidato")}), status or 400
