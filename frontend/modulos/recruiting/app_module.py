"""
Módulo Recruiting: Dashboard, Manager Dashboard, Candidatos, Búsquedas, Pipeline y Parámetros.
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
    Response,
    session,
    stream_with_context,
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


def _ve_pipeline():
    """Si el usuario tiene el ítem Pipeline: el Dashboard solo enlaza a las pantallas a las que puede entrar."""
    if _es_admin():
        return True
    permisos = _obtener_permisos_usuario()
    return bool(permisos.get("recruiting") and permisos.get("recruiting.gestion_busquedas"))


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

    return render_template(
        "recruiting/dashboard.html",
        dashboard=data,
        error=None,
        tiene_candidatos=_ve_candidatos(),
        tiene_pipeline=_ve_pipeline(),
        # Los casos de CV duplicado los revisa el personal interno: el grupo EXTERNOS no los ve
        puede_ver_duplicados=_permisos_pipeline()["puede_cargar_cv_general"],
    )


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
    permisos = {
        "puede_eliminar_candidatos": False,
        "puede_cargar_cv_general": False,
        "puede_carga_masiva": False,
        "puede_asignar_candidatos": False,
    }
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


# Parámetros del listado que se conservan al pasar a la pantalla Vue (filtros, página y la apertura de la carga de CV).
PARAMETROS_LISTADO = (
    "busqueda", "search", "q", "estado", "fuente", "seniority", "ubicacion", "puesto", "categorias", "skills",
    "page", "pagina", "limit", "por_pagina", "accion", "volver",
)


@recruiting_bp.route("/candidatos", methods=["GET"])
@require_permiso("recruiting.candidatos")
def candidatos():
    """El listado de candidatos es una pantalla Vue (/v2/recruiting/candidatos); acá se conserva la URL con todos los
    parámetros que usan los enlaces de las demás pantallas. Los datos, los filtros y los permisos de las acciones
    los pide la pantalla a la API; el permiso se valida acá y el backend lo valida de nuevo en cada llamada."""
    parametros = {k: v for k, v in request.args.lists() if k in PARAMETROS_LISTADO and any(v)}
    return redirect(url_for("vue_app.spa", ruta="recruiting/candidatos", **parametros))


@recruiting_bp.route("/candidatos/nuevo", methods=["GET"])
@require_permiso("recruiting.candidatos")
def nuevo_candidato():
    """El alta de candidatos es una pantalla Vue (/v2/recruiting/candidatos/nuevo); acá se conservan la URL y los
    parámetros (busqueda_id, volver) que usan los enlaces de las demás pantallas. El permiso se valida acá y el
    backend lo valida de nuevo en cada llamada."""
    parametros = {k: request.args[k] for k in ("busqueda_id", "volver") if request.args.get(k)}
    return redirect(url_for("vue_app.spa", ruta="recruiting/candidatos/nuevo", **parametros))


def _busqueda_id_valido(valor):
    """El id de la búsqueda desde la que se da de alta un candidato (texto UUID), o '' si no es válido."""
    texto = str(valor or "").strip()
    return texto if re.fullmatch(r"[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", texto) else ""


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

    # Alta desde el detalle de una búsqueda: el backend valida que sea EXTERNOS y que la búsqueda esté asignada al usuario
    busqueda_id = _busqueda_id_valido(body.get("busqueda_id"))
    if busqueda_id:
        data, status = api_request(
            "POST", f"/recruiting/oportunidades/{busqueda_id}/candidatos/nuevo", data=_payload_de_candidato(body), token=token
        )
        destino = _volver_valido(body.get("volver")) or url_for("recruiting.oportunidad_detalle", id=busqueda_id)
    else:
        data, status = api_request("POST", "/recruiting/candidatos", data=_payload_de_candidato(body), token=token)
        destino = _volver_valido(body.get("volver")) or url_for("recruiting.candidatos")

    if status in (200, 201):
        if request.is_json:
            candidato = data.get("candidato") if busqueda_id and isinstance(data, dict) else data
            return {"success": True, "candidato": candidato, "redirect": destino}, 201
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
            busqueda_id=busqueda_id,
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
        # El aviso de éxito lo muestra la pantalla Vue; un mensaje flash quedaría pendiente para la próxima página.
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
        puede_cargar_cv_en_busqueda=permisos["es_externo"] and not ganada,
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


# === PIPELINE (ítem «gestion_busquedas») ===
# La vista global, el Pipeline de una búsqueda (tabla, mover de etapa, descartar, adjuntos), la ficha del pipeline de un
# candidato y «Agregar candidato». Las pantallas compartidas con Candidatos y Búsquedas exigen solo el módulo: el backend
# valida el permiso del ítem en cada llamada y esta capa solo orienta la interfaz.

ERROR_PIPELINE = "No se pudo cargar el Pipeline. Probá de nuevo en unos minutos."
EXTENSIONES_ADJUNTO_ETAPA = (".pdf", ".doc", ".docx", ".png", ".jpg", ".jpeg", ".xlsx", ".xls", ".txt", ".zip", ".rar")
MAX_ADJUNTO_ETAPA_BYTES = 10 * 1024 * 1024


def _permisos_pipeline():
    """Acciones que el usuario ve en el Pipeline; restrictivo si no se puede consultar el backend."""
    permisos = {
        "puede_mover_descartar": False,
        "puede_eliminar_candidatos": False,
        "puede_asignar_candidatos": False,
        "puede_crear_busquedas": False,
        "puede_eliminar_busquedas": False,
        "puede_ver_lider_tipo_fecha_busqueda": False,
        "puede_ver_smart_matching": False,
        "puede_cargar_cv_general": False,
        "puede_cargar_cv_en_busqueda": False,
    }
    try:
        data, status = get_api_request_func()("GET", "/recruiting/pipeline-permisos", token=session.get("token"))
        if status == 200 and isinstance(data, dict):
            for clave in permisos:
                permisos[clave] = bool(data.get(clave))
    except Exception:
        pass
    return permisos


def _busqueda_ganada(op):
    """True si la búsqueda está Ganada (se cierra sola al confirmar el Ingreso de un candidato)."""
    return isinstance(op, dict) and str(op.get("estado") or "").strip().lower() == "ganada"


def _filtro_alcance_candidatos():
    """Filtro de candidatos del Pipeline desde la query string: '' (todos) | 'propios'."""
    return "propios" if request.args.get("alcance_candidatos", "").strip().lower() == "propios" else ""


def _parametro_alcance(prefijo="?"):
    alcance = _filtro_alcance_candidatos()
    return prefijo + urlencode({"alcance_candidatos": alcance}) if alcance else ""


@recruiting_bp.route("/gestion-busquedas", methods=["GET"])
@recruiting_bp.route("/asignar-candidato", methods=["GET"])
@require_permiso("recruiting.gestion_busquedas")
def gestion_busquedas():
    """Pipeline: vista global (todas las búsquedas con sus candidatos por columna) o individual (elegir una búsqueda)."""
    api_request = get_api_request_func()
    token = session.get("token")
    vista = request.args.get("vista", "global")
    if vista not in ("global", "individual"):
        vista = "global"

    resumen = {"columnas": [], "items": []}
    oportunidades_abiertas = []
    error = None
    if vista == "global":
        data, status = api_request(
            "GET",
            "/recruiting/pipeline-resumen?"
            + urlencode({"estado": "Abierta", "alcance_candidatos": _filtro_alcance_candidatos()}),
            token=token,
        )
        if status == 200 and isinstance(data, dict):
            resumen = {"columnas": data.get("columnas") or [], "items": data.get("items") or []}
        else:
            error = _detalle_de_error(data, ERROR_PIPELINE)
    else:
        data, status = api_request("GET", "/recruiting/oportunidades?estado=Abierta&por_pagina=100", token=token)
        if status == 200 and isinstance(data, dict):
            oportunidades_abiertas = [
                op for op in (data.get("items") or []) if str(op.get("estado", "")).strip().lower() == "abierta"
            ]
        else:
            error = _detalle_de_error(data, ERROR_PIPELINE)

    return render_template(
        "recruiting/asignar_candidato_hub.html",
        puede_crear_busquedas=_permisos_pipeline()["puede_crear_busquedas"],
        vista=vista,
        resumen=resumen,
        oportunidades=oportunidades_abiertas,
        filtro_alcance_candidatos=_filtro_alcance_candidatos(),
        error_pipeline=error,
    )


@recruiting_bp.route("/pipeline", methods=["GET"])
@recruiting_bp.route("/oportunidades/pipeline", methods=["GET"])
@require_permiso("recruiting.gestion_busquedas")
def oportunidades_pipeline_hub():
    """Lleva al Pipeline de la primera búsqueda Abierta (o de la más reciente); sin búsquedas, a la vista global."""
    data, status = get_api_request_func()("GET", "/recruiting/oportunidades?por_pagina=20", token=session.get("token"))
    if status == 200 and isinstance(data, dict):
        items = data.get("items") or []
        abierta = next((op for op in items if str(op.get("estado", "")).strip().lower() == "abierta"), None)
        elegida = abierta or (items[0] if items else None)
        if elegida and elegida.get("id"):
            return redirect(url_for("recruiting.pipeline", id=elegida["id"]))
    return redirect(url_for("recruiting.gestion_busquedas"))


@recruiting_bp.route("/oportunidades/<uuid:id>/pipeline", methods=["GET"])
@require_permiso("recruiting.gestion_busquedas")
def pipeline(id):
    """Pipeline de una búsqueda: sus candidatos por etapa, con mover de etapa y descartar."""
    api_request = get_api_request_func()
    token = session.get("token")
    consulta = _parametro_alcance()

    op, status_op = api_request("GET", f"/recruiting/oportunidades/{id}", token=token)
    if status_op != 200 or not isinstance(op, dict):
        flash(
            "No tenés acceso a esta búsqueda: no la tenés asignada."
            if status_op == 403
            else "La búsqueda solicitada no existe o no fue encontrada.",
            "error",
        )
        return redirect(url_for("recruiting.gestion_busquedas"))

    candidatos, status_cand = api_request("GET", f"/recruiting/oportunidades/{id}/pipeline-candidatos{consulta}", token=token)
    contadores, status_cont = api_request("GET", f"/recruiting/oportunidades/{id}/pipeline-contadores{consulta}", token=token)
    permisos = _permisos_pipeline()
    ganada = _busqueda_ganada(op)

    return render_template(
        "recruiting/pipeline.html",
        op=op,
        oportunidad=op,
        candidatos=candidatos if status_cand == 200 and isinstance(candidatos, list) else [],
        contadores=contadores if status_cont == 200 and isinstance(contadores, dict) else {"total": 0, "por_etapa": {}},
        error_pipeline=None if status_cand == 200 else _detalle_de_error(candidatos, ERROR_PIPELINE),
        busqueda_ganada=ganada,
        # Búsqueda Ganada = cerrada: solo consulta (el backend también rechaza cualquier cambio con 409)
        puede_mover_descartar=permisos["puede_mover_descartar"] and not ganada,
        puede_asignar_candidatos=permisos["puede_asignar_candidatos"] and not ganada,
        filtro_etapas=[e.strip() for e in request.args.get("etapas", "").split(",") if e.strip()],
        filtro_columna=request.args.get("columna", "").strip(),
        filtro_alcance_candidatos=_filtro_alcance_candidatos(),
    )


@recruiting_bp.route("/oportunidades/<uuid:id>/pipeline-columna/<string:columna>", methods=["GET"])
@require_permiso("recruiting.gestion_busquedas")
def pipeline_columna_candidatos(id, columna):
    """Candidatos de una búsqueda en una columna de la vista global (detalle al pasar el mouse sobre la cifra)."""
    data, status = get_api_request_func()(
        "GET",
        f"/recruiting/oportunidades/{id}/pipeline-columna/{quote(columna, safe='')}{_parametro_alcance()}",
        token=session.get("token"),
    )
    if status == 200 and isinstance(data, list):
        return jsonify(data), 200
    return jsonify({"error": _detalle_de_error(data, "Error al obtener los candidatos")}), status or 500


@recruiting_bp.route("/motivos-descarte", methods=["GET"])
@require_permiso("recruiting.gestion_busquedas")
def motivos_descarte():
    """Motivos de descarte de la etapa indicada."""
    etapa = request.args.get("etapa", "")
    data, status = get_api_request_func()(
        "GET", f"/recruiting/motivos-descarte?etapa={quote(etapa)}", token=session.get("token")
    )
    if status == 200 and isinstance(data, list):
        return jsonify(data), 200
    return jsonify({"error": _detalle_de_error(data, "Error al obtener los motivos de descarte")}), status or 500


@recruiting_bp.route("/oportunidades/<uuid:id>/candidatos/<uuid:candidato_id>/etapa", methods=["PUT", "POST"])
@require_permiso("recruiting.gestion_busquedas")
def actualizar_etapa_pipeline(id, candidato_id):
    """Mueve de etapa, descarta o reingresa al candidato; si el formulario trae un archivo, lo adjunta a la etapa."""
    api_request = get_api_request_func()
    token = session.get("token")
    archivo = request.files.get("archivo") if request.files else None
    payload = (request.get_json(silent=True) or {}) if request.is_json else request.form.to_dict()

    contenido = None
    if archivo and archivo.filename:
        extension = archivo.filename.lower().rsplit(".", 1)[-1] if "." in archivo.filename else ""
        if f".{extension}" not in EXTENSIONES_ADJUNTO_ETAPA:
            return jsonify({"success": False, "error": f"Tipo de archivo no permitido (.{extension})."}), 400
        contenido = archivo.read()
        if len(contenido) > MAX_ADJUNTO_ETAPA_BYTES:
            return jsonify({"success": False, "error": "El archivo excede el tamaño máximo permitido de 10 MB."}), 400

    # La observación vacía limpia la anterior; el backend acepta la pretensión como texto y la vacía como ausente
    payload = {k: v for k, v in payload.items() if v is not None}
    res, status = api_request(
        "PUT", f"/recruiting/oportunidades/{id}/candidatos/{candidato_id}/etapa", data=payload, token=token
    )
    if status not in (200, 201) or not isinstance(res, dict):
        return jsonify({"success": False, "error": _detalle_de_error(res, "Error al actualizar la etapa")}), status or 400

    if contenido is not None:
        parametros = {"etapa_id": str(payload.get("etapa_actual") or res.get("etapa_actual") or "Candidato").strip()}
        estado = payload.get("estado") or res.get("estado")
        if estado:
            parametros["estado"] = str(estado).strip()
        try:
            with httpx.Client(timeout=30.0) as cliente:
                respuesta = cliente.post(
                    f"{current_app.config['API_URL']}/api/v1/recruiting/oportunidades/{id}/candidatos/{candidato_id}/archivos-etapa",
                    params=parametros,
                    headers={"Authorization": f"Bearer {token}"},
                    files={"archivo": (archivo.filename, contenido, archivo.content_type or "application/octet-stream")},
                )
            if respuesta.status_code in (200, 201):
                res["archivo"] = respuesta.json()
            else:
                try:
                    detalle = _detalle_de_error(respuesta.json(), "Error al guardar el archivo adjunto")
                except ValueError:
                    detalle = "Error al guardar el archivo adjunto"
                return jsonify({"success": False, "error": detalle}), respuesta.status_code
        except Exception:
            logging.getLogger(__name__).error("Error al adjuntar el archivo de la etapa", exc_info=True)
            return jsonify({"success": False, "error": MENSAJE_ERROR_GENERICO}), 500

    return jsonify(res), 200


@recruiting_bp.route("/oportunidades/<uuid:id>/agregar-candidato", methods=["GET"])
@require_permiso("recruiting.gestion_busquedas")
def oportunidad_agregar_candidato(id):
    """Pantalla para buscar candidatos del Banco de Talentos y sumarlos a una búsqueda."""
    if not _permisos_pipeline()["puede_asignar_candidatos"]:
        flash("No tenés permisos para asignar candidatos a búsquedas.", "error")
        return redirect(url_for("recruiting.oportunidades"))
    api_request = get_api_request_func()
    token = session.get("token")

    op, status = api_request("GET", f"/recruiting/oportunidades/{id}", token=token)
    if status != 200 or not isinstance(op, dict):
        flash("La búsqueda solicitada no existe o no fue encontrada.", "error")
        return redirect(url_for("recruiting.oportunidades"))
    if _busqueda_ganada(op):
        flash("La búsqueda está Ganada y cerrada: no se pueden agregar nuevos candidatos.", "error")
        return redirect(url_for("recruiting.oportunidad_detalle", id=id))

    asignados, status_asig = api_request("GET", f"/recruiting/oportunidades/{id}/candidatos", token=token)
    disponibles, status_disp = api_request("GET", "/recruiting/candidatos?pagina=1&por_pagina=100", token=token)
    return render_template(
        "recruiting/oportunidad_agregar_candidato.html",
        op=op,
        oportunidad=op,
        candidatos_asignados=asignados if status_asig == 200 and isinstance(asignados, list) else [],
        candidatos_disponibles=(disponibles.get("items") or []) if status_disp == 200 and isinstance(disponibles, dict) else [],
    )


@recruiting_bp.route("/oportunidades/<uuid:id>/candidatos/<uuid:candidato_id>", methods=["DELETE"])
@require_permiso("recruiting.oportunidades")
def desvincular_candidato_oportunidad(id, candidato_id):
    """Quita al candidato de la búsqueda sin eliminarlo del Banco de Talentos."""
    data, status = get_api_request_func()(
        "DELETE", f"/recruiting/oportunidades/{id}/candidatos/{candidato_id}", token=session.get("token")
    )
    if status in (200, 204):
        return jsonify(data if isinstance(data, dict) else {"success": True}), 200
    return jsonify({"success": False, "error": _detalle_de_error(data, "Error al desvincular el candidato")}), status or 400


@recruiting_bp.route("/oportunidades/<uuid:op_id>/candidatos/<uuid:candidato_id>/detalle", methods=["GET"])
@require_permiso("recruiting")
def candidato_pipeline_detalle(op_id, candidato_id):
    """Ficha del pipeline de un candidato: sus pipelines (el de la URL primero) con historial y adjuntos de cada uno."""
    api_request = get_api_request_func()
    token = session.get("token")

    oportunidad, status_op = api_request("GET", f"/recruiting/oportunidades/{op_id}", token=token)
    oportunidad = oportunidad if status_op == 200 and isinstance(oportunidad, dict) else {}

    candidato, status_cand = api_request("GET", f"/recruiting/candidatos/{candidato_id}", token=token)
    if status_cand != 200 or not isinstance(candidato, dict):
        flash(
            _detalle_de_error(candidato, "No tenés permiso para acceder a este candidato.")
            if status_cand == 403
            else "El candidato solicitado no fue encontrado.",
            "danger" if status_cand == 403 else "warning",
        )
        return redirect(url_for("recruiting.oportunidad_detalle", id=op_id))

    # Siempre se traen todos los pipelines visibles del candidato: el de la URL va primero y el resto en «Otros Pipelines»
    pipelines, status_pipes = api_request("GET", f"/recruiting/candidatos/{candidato_id}/pipelines", token=token)
    pipelines = (
        sorted(pipelines, key=lambda p: str(p.get("oportunidad_id")) != str(op_id))
        if status_pipes == 200 and isinstance(pipelines, list)
        else []
    )
    if oportunidad and not pipelines:
        pipelines.insert(
            0, {"oportunidad_id": str(op_id), "titulo": oportunidad.get("titulo"), "cliente": oportunidad.get("cliente")}
        )

    # Historial y adjuntos de cada pipeline, sin mezclar búsquedas
    for p in pipelines:
        historial, status_hist = api_request(
            "GET", f"/recruiting/oportunidades/{p['oportunidad_id']}/candidatos/{candidato_id}/historial", token=token
        )
        archivos, status_arch = api_request(
            "GET", f"/recruiting/oportunidades/{p['oportunidad_id']}/candidatos/{candidato_id}/archivos-etapa", token=token
        )
        p["historial"] = historial if status_hist == 200 and isinstance(historial, list) else []
        p["archivos_etapa"] = archivos if status_arch == 200 and isinstance(archivos, list) else []

    return render_template(
        "recruiting/candidato_pipeline_detalle.html",
        oportunidad=oportunidad,
        candidato=candidato,
        pipelines=pipelines,
        op_id=str(op_id),
    )


@recruiting_bp.route("/candidatos/<uuid:id>/pipelines", methods=["GET"])
@require_permiso("recruiting")
def candidato_pipelines(id):
    """Pipelines del candidato (el listado de Candidatos abre el primero)."""
    data, status = get_api_request_func()("GET", f"/recruiting/candidatos/{id}/pipelines", token=session.get("token"))
    return jsonify(data if status == 200 and isinstance(data, list) else []), 200


@recruiting_bp.route("/candidatos/<uuid:id>/busquedas-elegibles", methods=["GET"])
@require_permiso("recruiting.candidatos")
def candidato_busquedas_elegibles(id):
    """Búsquedas Abiertas compatibles con el candidato (para «Asignar a búsqueda» del listado)."""
    data, status = get_api_request_func()(
        "GET", f"/recruiting/candidatos/{id}/busquedas-elegibles", token=session.get("token")
    )
    return jsonify(data if status == 200 and isinstance(data, list) else []), 200


@recruiting_bp.route("/archivos-etapa/<uuid:archivo_id>/descargar", methods=["GET"])
@require_permiso("recruiting")
def descargar_archivo_etapa_proxy(archivo_id):
    """Descarga un adjunto de etapa a través del backend."""
    try:
        with httpx.Client(timeout=60.0) as cliente:
            respuesta = cliente.get(
                f"{current_app.config['API_URL']}/api/v1/recruiting/archivos-etapa/{archivo_id}/descargar",
                headers={"Authorization": f"Bearer {session.get('token')}"},
            )
    except Exception:
        logging.getLogger(__name__).error("Error al descargar un adjunto de etapa", exc_info=True)
        return jsonify({"error": MENSAJE_ERROR_GENERICO}), 500
    if respuesta.status_code != 200:
        return jsonify({"error": "Archivo no encontrado"}), respuesta.status_code
    salida = Response(respuesta.content, status=200, content_type=respuesta.headers.get("content-type", "application/octet-stream"))
    if "Content-Disposition" in respuesta.headers:
        salida.headers["Content-Disposition"] = respuesta.headers["Content-Disposition"]
    return salida


# === ALTA DESDE UNA BÃšSQUEDA ASIGNADA (grupo EXTERNOS) Y CV DUPLICADOS ===


@recruiting_bp.route("/oportunidades/<uuid:id>/cargar-cv", methods=["POST"], defaults={"accion": "cargar-cv"})
@recruiting_bp.route("/oportunidades/<uuid:id>/actualizar-cv", methods=["POST"], defaults={"accion": "actualizar-cv"})
@require_permiso("recruiting.oportunidades")
def oportunidad_cargar_cv(id, accion):
    """Carga un CV desde una bÃºsqueda asignada: crea el candidato y lo asocia a la bÃºsqueda. Con el email de uno
    existente asocia la ficha (CV idÃ©ntico) o deriva el caso a Recruiting (CV distinto, respuesta 202)."""
    archivo, error = _archivo_de_cv(MAX_CV_CARGA_BYTES)
    if error:
        return jsonify({"ok": False, **error[0]}), error[1]
    data, status = _reenviar_archivos("POST", f"/oportunidades/{id}/candidatos/{accion}", {"archivo": archivo}, timeout=45.0)
    if status in (200, 201, 202) and isinstance(data, dict) and data.get("ok", True) is not False:
        # 200 (CV idÃ©ntico ya registrado) se reenvÃ­a como 201; 202 (caso derivado a Recruiting) se mantiene
        return (
            jsonify(
                {
                    "ok": True,
                    "candidato": data.get("candidato", {}),
                    "asignacion_id": data.get("asignacion_id"),
                    "mensaje": data.get("mensaje"),
                }
            ),
            202 if status == 202 else 201,
        )
    mensaje = _detalle_de_error(data, MENSAJE_ERROR_GENERICO) if status < 500 else MENSAJE_ERROR_GENERICO
    return jsonify({"ok": False, "error": mensaje}), status if status >= 400 else 400


@recruiting_bp.route("/candidatos-duplicados", methods=["GET"])
@recruiting_bp.route("/candidatos-duplicados/<uuid:caso_id>", methods=["GET"])
@recruiting_bp.route("/candidatos-duplicados/<uuid:caso_id>/resolver", methods=["POST"], defaults={"resolver": True})
@require_permiso("recruiting.dashboard")
def candidatos_duplicados_proxy(caso_id=None, resolver=False):
    """Casos de CV duplicado pendientes: listado, detalle para comparar y resoluciÃ³n (conservar o actualizar)."""
    api_request = get_api_request_func()
    endpoint = "/recruiting/candidatos-duplicados" + (f"/{caso_id}" if caso_id else "")
    if resolver:
        cuerpo = {"accion": (request.get_json(silent=True) or {}).get("accion")}
        data, status = api_request("POST", endpoint + "/resolver", data=cuerpo, token=session.get("token"))
    else:
        data, status = api_request("GET", endpoint, token=session.get("token"))
    if status and status < 400:
        return jsonify(data), status
    return jsonify({"ok": False, "error": _detalle_de_error(data, MENSAJE_ERROR_GENERICO)}), status or 500


# === PARÁMETROS (ítem «parametros») ===
# Configuración de Smart Matching, catálogos (skills, habilidades, provincias, ciudades, líderes, reclutadores, perfiles
# profesionales y motivos de Blacklist), Archivos de CV e Historial de cargas de CV. Cada pantalla exige
# 'recruiting.parametros'; el backend valida el permiso y las restricciones (EXTERNOS fuera de todo Parámetros;
# administradores para limpiar, respaldar, importar y el historial) en cada llamada: esta capa solo orienta la interfaz.

BASE_PARAMETROS = "/recruiting/parametros"


@recruiting_bp.context_processor
def _utilidades_parametros():
    """La pestaña «Historial de cargas de CV» solo se ofrece a los administradores."""
    return {"puede_ver_historial_cargas_cv": _es_admin()}


def _proxy_parametros(metodo, endpoint, clave_respuesta, mensaje_error, payload=None):
    """Reenvía una operación de Parámetros al backend y devuelve JSON {success, <clave>} o {success: false, error}."""
    try:
        data, status = get_api_request_func()(
            metodo, f"{BASE_PARAMETROS}{endpoint}", data=payload, token=session.get("token")
        )
    except Exception:
        return jsonify({"success": False, "error": "Error de conexión con el servidor."}), 500
    if status in (200, 201, 202):
        return jsonify({"success": True, clave_respuesta: data}), status
    return jsonify({"success": False, "error": _detalle_de_error(data, mensaje_error)}), status or 400


@recruiting_bp.route("/parametros", methods=["GET"])
@require_permiso("recruiting.parametros")
def parametros():
    data, status = get_api_request_func()("GET", f"{BASE_PARAMETROS}/config", token=session.get("token"))
    match_minimo = data.get("match_minimo_porcentaje", 50) if status == 200 and isinstance(data, dict) else 50
    return render_template("recruiting/parametros.html", match_minimo=match_minimo)


@recruiting_bp.route("/parametros/config", methods=["PUT"])
@require_permiso("recruiting.parametros")
def parametros_actualizar_config():
    return _proxy_parametros("PUT", "/config", "data", "Error al guardar", request.get_json(silent=True) or {})


def _registrar_abm_parametros(
    ruta, ruta_backend, plantilla, clave_lista, clave_item, singular, convertidor="uuid", alias_listado=None
):
    """Vista y proxies de un ABM con baja lógica (listar con inactivos, crear, editar y desactivar). Los nombres de
    endpoint (`parametros_<ruta>_vista`...) los usan las pestañas de las plantillas."""
    id_ruta = f"<{convertidor}:registro_id>"
    nombre = ruta.replace("-", "_")
    permiso = require_permiso("recruiting.parametros")

    def vista():
        return render_template(f"recruiting/{plantilla}.html")

    def listar():
        q = (request.args.get("q") or "").strip()
        sufijo = "?activo_only=false" + (f"&q={quote(q)}" if q else "")
        return _proxy_parametros("GET", f"/{ruta_backend}{sufijo}", clave_lista, f"Error al cargar {clave_lista}.")

    def crear():
        return _proxy_parametros(
            "POST", f"/{ruta_backend}", clave_item, f"Error al crear {singular}.", request.get_json(silent=True) or {}
        )

    def actualizar(registro_id):
        return _proxy_parametros(
            "PUT",
            f"/{ruta_backend}/{registro_id}",
            clave_item,
            f"Error al actualizar {singular}.",
            request.get_json(silent=True) or {},
        )

    def desactivar(registro_id):
        return _proxy_parametros("DELETE", f"/{ruta_backend}/{registro_id}", clave_item, f"Error al desactivar {singular}.")

    recruiting_bp.add_url_rule(f"/parametros/{ruta}", f"parametros_{nombre}_vista", permiso(vista), methods=["GET"])
    recruiting_bp.add_url_rule(f"/parametros/{ruta}/api", f"parametros_listar_{nombre}", permiso(listar), methods=["GET"])
    if alias_listado:
        recruiting_bp.add_url_rule(
            f"/parametros/{ruta}/{alias_listado}", f"parametros_listar_{nombre}_alias", permiso(listar), methods=["GET"]
        )
    recruiting_bp.add_url_rule(f"/parametros/{ruta}/api", f"parametros_crear_{nombre}", permiso(crear), methods=["POST"])
    recruiting_bp.add_url_rule(
        f"/parametros/{ruta}/api/{id_ruta}", f"parametros_actualizar_{nombre}", permiso(actualizar), methods=["PUT"]
    )
    recruiting_bp.add_url_rule(
        f"/parametros/{ruta}/api/{id_ruta}", f"parametros_desactivar_{nombre}", permiso(desactivar), methods=["DELETE"]
    )


_registrar_abm_parametros("skills", "skills", "skills", "skills", "skill", "la skill", alias_listado="list")
_registrar_abm_parametros(
    "habilidades", "habilidades", "habilidades", "habilidades", "habilidad", "la habilidad", alias_listado="list"
)
_registrar_abm_parametros("lideres", "lideres", "lideres", "lideres", "persona", "el líder")
_registrar_abm_parametros("reclutadores", "reclutadores", "reclutadores", "reclutadores", "persona", "el reclutador")
_registrar_abm_parametros(
    "perfiles-profesionales",
    "perfiles-puesto",
    "perfiles_profesionales",
    "perfiles",
    "perfil",
    "el perfil profesional",
    convertidor="int",
)


def _registrar_abm_ubicacion(ruta, clave_lista, clave_item, singular):
    """Provincias, ciudades y motivos de Blacklist: no hay baja lógica, el DELETE elimina."""
    nombre = ruta.replace("-", "_")  # plantilla y endpoints: `parametros_<nombre>_vista`...
    permiso = require_permiso("recruiting.parametros")

    def vista():
        return render_template(f"recruiting/{nombre}.html")

    def listar():
        provincia_id = request.args.get("provincia_id", type=int)
        sufijo = f"?provincia_id={provincia_id}" if ruta == "ciudades" and provincia_id else ""
        return _proxy_parametros("GET", f"/{ruta}{sufijo}", clave_lista, f"Error al cargar {clave_lista}.")

    def crear():
        return _proxy_parametros(
            "POST", f"/{ruta}", clave_item, f"Error al crear {singular}.", request.get_json(silent=True) or {}
        )

    def actualizar(registro_id):
        return _proxy_parametros(
            "PUT", f"/{ruta}/{registro_id}", clave_item, f"Error al actualizar {singular}.", request.get_json(silent=True) or {}
        )

    def eliminar(registro_id):
        return _proxy_parametros("DELETE", f"/{ruta}/{registro_id}", "resultado", f"Error al eliminar {singular}.")

    recruiting_bp.add_url_rule(f"/parametros/{ruta}", f"parametros_{nombre}_vista", permiso(vista), methods=["GET"])
    recruiting_bp.add_url_rule(f"/parametros/{ruta}/api", f"parametros_listar_{nombre}", permiso(listar), methods=["GET"])
    recruiting_bp.add_url_rule(f"/parametros/{ruta}/api", f"parametros_crear_{nombre}", permiso(crear), methods=["POST"])
    recruiting_bp.add_url_rule(
        f"/parametros/{ruta}/api/<int:registro_id>", f"parametros_actualizar_{nombre}", permiso(actualizar), methods=["PUT"]
    )
    recruiting_bp.add_url_rule(
        f"/parametros/{ruta}/api/<int:registro_id>", f"parametros_eliminar_{nombre}", permiso(eliminar), methods=["DELETE"]
    )


_registrar_abm_ubicacion("provincias", "provincias", "provincia", "la provincia")
_registrar_abm_ubicacion("ciudades", "ciudades", "ciudad", "la ciudad")
_registrar_abm_ubicacion("motivos-blacklist", "motivos", "motivo", "el motivo")


# ---- Archivos de CV ----------------------------------------------------------------------------------------------------


@recruiting_bp.route("/parametros/archivos-cv", methods=["GET"])
@require_permiso("recruiting.parametros")
def parametros_archivos_cv_vista():
    """Consulta y descarga de los CV archivados (cv_procesados_ok, cv_duplicados y cv_errores). Limpiar, respaldar e
    importar son de administradores."""
    return render_template("recruiting/archivos_cv.html", puede_limpiar_bd=_es_admin())


@recruiting_bp.route("/parametros/archivos-cv/api", methods=["GET"])
@require_permiso("recruiting.parametros")
def parametros_archivos_cv_resumen():
    return _proxy_parametros("GET", "/archivos-cv", "carpetas", "Error al consultar las carpetas de CV.")


@recruiting_bp.route("/parametros/archivos-cv/api/<carpeta>", methods=["GET"])
@require_permiso("recruiting.parametros")
def parametros_archivos_cv_detalle(carpeta):
    consulta = {k: request.args[k] for k in ("pagina", "por_pagina", "buscar") if request.args.get(k)}
    sufijo = f"?{urlencode(consulta)}" if consulta else ""
    return _proxy_parametros(
        "GET", f"/archivos-cv/{quote(carpeta, safe='')}{sufijo}", "carpeta", "Error al consultar la carpeta de CV."
    )


def _solo_administrador(mensaje):
    """Respuesta 403 si el usuario no es administrador (el backend lo vuelve a validar); None si lo es."""
    if not _es_admin():
        return jsonify({"success": False, "error": mensaje}), 403
    return None


@recruiting_bp.route("/parametros/archivos-cv/limpiar-bd", methods=["POST"])
@require_permiso("recruiting.parametros")
def parametros_archivos_cv_limpiar_bd():
    """Limpiar BD: solo administradores."""
    return _solo_administrador("No tenés permiso para limpiar los datos de Recruiting") or _proxy_parametros(
        "POST", "/archivos-cv/limpiar-bd", "resumen", "Error al limpiar los datos de Recruiting.", {"confirmar": True}
    )


@recruiting_bp.route("/parametros/archivos-cv/backup/iniciar", methods=["POST"])
@require_permiso("recruiting.parametros")
def parametros_archivos_cv_backup_iniciar():
    return _solo_administrador("No tenés permiso para generar backups de Recruiting") or _proxy_parametros(
        "POST", "/archivos-cv/backup/iniciar", "backup", "No se pudo iniciar el backup."
    )


@recruiting_bp.route("/parametros/archivos-cv/backup/<backup_id>/estado", methods=["GET"])
@require_permiso("recruiting.parametros")
def parametros_archivos_cv_backup_estado(backup_id):
    return _solo_administrador("No tenés permiso para consultar backups de Recruiting") or _proxy_parametros(
        "GET", f"/archivos-cv/backup/{quote(backup_id, safe='')}/estado", "backup", "No se pudo consultar el backup."
    )


@recruiting_bp.route("/parametros/archivos-cv/backup/<backup_id>/descargar", methods=["GET"])
@require_permiso("recruiting.parametros")
def parametros_archivos_cv_backup_descargar(backup_id):
    return _solo_administrador("No tenés permiso para descargar backups de Recruiting") or _proxy_descarga_archivos_cv(
        f"/recruiting/parametros/archivos-cv/backup/{quote(backup_id, safe='')}/descargar"
    )


@recruiting_bp.route("/parametros/archivos-cv/importar/subir", methods=["POST"])
@require_permiso("recruiting.parametros")
def parametros_archivos_cv_importar_subir():
    """Reenvía el ZIP del backup al backend por bloques, sin cargarlo en memoria. Solo administradores."""
    error = _solo_administrador("No tenés permiso para importar backups de Recruiting")
    if error:
        return error
    archivo = request.files.get("archivo")
    if not archivo or not archivo.filename:
        return jsonify({"success": False, "error": "Seleccioná un backup .zip."}), 400
    try:
        with httpx.Client(timeout=httpx.Timeout(3600.0, connect=10.0)) as cliente:
            respuesta = cliente.post(
                f"{current_app.config['API_URL']}/api/v1/recruiting/parametros/archivos-cv/importar/subir",
                headers={"Authorization": f"Bearer {session.get('token')}"},
                files={"archivo": (archivo.filename, archivo.stream, "application/zip")},
            )
        data = respuesta.json()
    except Exception:
        return jsonify({"success": False, "error": "Error de conexión con el servidor."}), 502
    if respuesta.status_code in (200, 201, 202):
        return jsonify({"success": True, "importacion": data}), 202
    return jsonify({"success": False, "error": _detalle_de_error(data, "No se pudo importar el backup.")}), respuesta.status_code


@recruiting_bp.route("/parametros/archivos-cv/importar/<importacion_id>/estado", methods=["GET"])
@require_permiso("recruiting.parametros")
def parametros_archivos_cv_importar_estado(importacion_id):
    return _solo_administrador("No tenés permiso para consultar importaciones de Recruiting") or _proxy_parametros(
        "GET",
        f"/archivos-cv/importar/{quote(importacion_id, safe='')}/estado",
        "importacion",
        "No se pudo consultar la importación.",
    )


@recruiting_bp.route("/parametros/archivos-cv/importar/<importacion_id>/confirmar", methods=["POST"])
@require_permiso("recruiting.parametros")
def parametros_archivos_cv_importar_confirmar(importacion_id):
    return _solo_administrador("No tenés permiso para importar backups de Recruiting") or _proxy_parametros(
        "POST",
        f"/archivos-cv/importar/{quote(importacion_id, safe='')}/confirmar",
        "importacion",
        "No se pudo iniciar la restauración.",
        request.get_json(silent=True) or {},
    )


@recruiting_bp.route("/parametros/archivos-cv/importar/<importacion_id>", methods=["DELETE"])
@require_permiso("recruiting.parametros")
def parametros_archivos_cv_importar_descartar(importacion_id):
    return _solo_administrador("No tenés permiso para importar backups de Recruiting") or _proxy_parametros(
        "DELETE", f"/archivos-cv/importar/{quote(importacion_id, safe='')}", "resultado", "No se pudo descartar el backup."
    )


@recruiting_bp.route("/parametros/archivos-cv/<carpeta>/descargar", methods=["GET"])
@require_permiso("recruiting.parametros")
def parametros_archivos_cv_descargar(carpeta):
    """Descarga de un CV original: el backend valida carpeta y nombre; acá solo se reenvía el archivo por bloques."""
    return _proxy_descarga_archivos_cv(
        f"/recruiting/parametros/archivos-cv/{quote(carpeta, safe='')}/descargar", {"nombre": request.args.get("nombre", "")}
    )


@recruiting_bp.route("/parametros/archivos-cv/<carpeta>/descargar-todos", methods=["GET"])
@require_permiso("recruiting.parametros")
def parametros_archivos_cv_descargar_todos(carpeta):
    """Descarga en un ZIP de todos los CV de la carpeta."""
    return _proxy_descarga_archivos_cv(f"/recruiting/parametros/archivos-cv/{quote(carpeta, safe='')}/descargar-todos")


def _proxy_descarga_archivos_cv(endpoint, params=None):
    """Reenvía una descarga al backend y la entrega por bloques, sin cargar el archivo completo en memoria."""
    token = session.get("token")
    cliente = httpx.Client(timeout=httpx.Timeout(300.0, connect=10.0))
    try:
        peticion = cliente.build_request(
            "GET",
            f"{current_app.config['API_URL']}/api/v1{endpoint}",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
        respuesta = cliente.send(peticion, stream=True)
    except Exception:
        cliente.close()
        return jsonify({"success": False, "error": "Error de conexión con el servidor."}), 502

    if respuesta.status_code != 200:
        detalle = None
        try:
            respuesta.read()
            detalle = respuesta.json().get("detail")
        except Exception:
            pass
        finally:
            respuesta.close()
            cliente.close()
        error = detalle if isinstance(detalle, str) and detalle else "No se pudo completar la descarga."
        return jsonify({"success": False, "error": error}), respuesta.status_code

    def bloques():
        try:
            yield from respuesta.iter_bytes(64 * 1024)
        finally:
            respuesta.close()
            cliente.close()

    cabeceras = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
    reenviadas = ("Content-Disposition", "X-Cantidad-Archivos")
    if "content-encoding" not in respuesta.headers:
        reenviadas += ("Content-Length",)
    for nombre in reenviadas:
        if nombre in respuesta.headers:
            cabeceras[nombre] = respuesta.headers[nombre]
    return Response(
        stream_with_context(bloques()),
        status=200,
        content_type=respuesta.headers.get("content-type", "application/octet-stream"),
        headers=cabeceras,
    )


# ---- Historial de cargas de CV (administradores) ----------------------------------------------------------------------


@recruiting_bp.route("/parametros/historial-cargas-cv", methods=["GET"])
@require_permiso("recruiting.parametros")
def parametros_historial_cargas_cv_vista():
    if not _es_admin():
        return render_template("core/403.html", modulo="recruiting.parametros"), 403
    return render_template("recruiting/historial_cargas_cv.html")


@recruiting_bp.route("/parametros/historial-cargas-cv/api", methods=["GET"])
@require_permiso("recruiting.parametros")
def parametros_historial_cargas_cv_listado():
    consulta = request.query_string.decode("utf-8")
    return _proxy_parametros(
        "GET",
        "/historial-cargas-cv" + (f"?{consulta}" if consulta else ""),
        "historial",
        "Error al consultar el historial de cargas de CV.",
    )


@recruiting_bp.route("/parametros/historial-cargas-cv/api/<uuid:historial_id>", methods=["GET"])
@require_permiso("recruiting.parametros")
def parametros_historial_cargas_cv_detalle(historial_id):
    return _proxy_parametros(
        "GET", f"/historial-cargas-cv/{historial_id}", "detalle", "Error al consultar el detalle de la carga."
    )
