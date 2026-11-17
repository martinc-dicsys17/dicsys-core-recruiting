"""
Host de la nueva interfaz Vue 3 de Dicsys Core (implementacion piloto).

La SPA vive en /frontend-vue y se compila dentro de frontend/static/vue. Este modulo solo:
  - sirve el index.html compilado bajo /v2/... con la sesion actual de Flask (sin plantillas Jinja),
  - le entrega a la SPA los datos de sesion (usuario, empresa, menu) dentro del HTML,
  - publica en el menu lateral actual los accesos a las pantallas Vue (PANTALLAS_VUE).

No modifica la autenticacion: usa el mismo login_required y la misma sesion que el resto del frontend.
"""
import os

from flask import Blueprint, Response, current_app, session, url_for
from jinja2.utils import htmlsafe_json_dumps
from werkzeug.routing import BuildError

from modulos.auth_helpers import get_api_request_func, login_required, require_permiso

vue_app_bp = Blueprint('vue_app', __name__, url_prefix='/v2')

# Marcador que deja Vite en el index.html compilado (ver frontend-vue/index.html).
MARCADOR_BOOTSTRAP = '<script id="dicsys-bootstrap" type="application/json">null</script>'

# Pantallas de la nueva interfaz, por codigo de menu. Cada una aparece en el menu lateral
# con el estandar visual de pantallas Vue (fondo verde suave + etiqueta "VUE").
# 'ruta' es la ruta del router de Vue (frontend-vue/src/router/index.ts).
PANTALLAS_VUE = {
    'recruiting': [
        {'nombre': 'Blacklist', 'icono': 'user-x', 'ruta': 'recruiting/blacklist'},
    ],
}

# Items del menu de siempre cuya pantalla ya es Vue: se muestran con el mismo verde que las pantallas Vue.
# Se identifican por el endpoint de Flask del item (la url que arma el menu).
ENDPOINTS_MIGRADOS_A_VUE = {'recruiting.candidatos', 'recruiting.oportunidades'}

HTML_SIN_COMPILAR = (
    '<!doctype html><html lang="es"><meta charset="utf-8"><title>Dicsys Core</title>'
    '<body style="font-family:system-ui;padding:3rem;color:#334155">'
    '<h1 style="font-size:1.25rem">La nueva interfaz todavia no esta compilada</h1>'
    '<p>Ejecutar <code>npm install</code> y <code>npm run build</code> dentro de <code>frontend-vue/</code>.</p>'
    '</body></html>'
)


def _pantallas_vue(codigo_menu):
    return [
        {'nombre': p['nombre'], 'icono': p['icono'], 'url': url_for('vue_app.spa', ruta=p['ruta'])}
        for p in PANTALLAS_VUE.get(codigo_menu, [])
    ]


@vue_app_bp.app_context_processor
def _inyectar_pantallas_vue():
    """Deja disponibles las pantallas Vue para el menu lateral de core/base.html."""
    return {
        'pantallas_vue': {codigo: _pantallas_vue(codigo) for codigo in PANTALLAS_VUE},
        'endpoints_migrados_a_vue': ENDPOINTS_MIGRADOS_A_VUE,
    }


def _leer_indice():
    ruta = os.path.join(current_app.static_folder, 'vue', 'index.html')
    try:
        with open(ruta, encoding='utf-8') as archivo:
            return archivo.read()
    except OSError:
        return None


def _url_storage(key):
    if not key:
        return None
    return key if key.startswith('/') else f'/storage/{key}'


def _url_menu(endpoint):
    if not endpoint:
        return None
    try:
        return url_for(endpoint)
    except BuildError:
        return None


def _cargar_menus():
    """Menu del usuario con las URLs ya resueltas, mas las pantallas Vue de cada modulo."""
    try:
        data, status = get_api_request_func()('GET', '/menus', token=session.get('token'))
    except Exception:
        return []
    if status != 200 or not isinstance(data, dict):
        return []

    menus = []
    for menu in data.get('items') or []:
        codigo = menu.get('codigo') or ''
        items = [
            {'nombre': item.get('nombre'), 'icono': item.get('icono'), 'url': _url_menu(item.get('ruta')), 'vue': False}
            for item in menu.get('items') or []
        ]
        items += [{**pantalla, 'vue': True} for pantalla in _pantallas_vue(codigo)]
        menus.append({'codigo': codigo, 'nombre': menu.get('nombre'), 'icono': menu.get('icono'), 'items': items})
    return menus


def _armar_bootstrap():
    user = session.get('user') or {}
    rol = user.get('empleado_perfil_nombre') or ('Administrador' if user.get('rol') == 'admin' else 'Usuario')
    avatar = user.get('avatar_url') or _url_storage(user.get('empleado_foto_thumbnail') or user.get('empleado_foto'))
    return {
        'origen': 'servidor',
        'usuario': {
            'nombre': user.get('nombre') or '',
            'email': user.get('email') or '',
            'rol': rol,
            'avatarUrl': avatar,
        },
        'empresa': {
            'nombre': session.get('empresa_nombre') or '',
            'logoUrl': session.get('empresa_logo') or None,
        },
        'enlaces': {
            'inicio': url_for('core.dashboard'),
            'perfil': url_for('core.profile'),
            'cerrarSesion': url_for('core.logout'),
        },
        'menus': _cargar_menus(),
    }


def _servir_spa():
    indice = _leer_indice()
    if indice is None or MARCADOR_BOOTSTRAP not in indice:
        return Response(HTML_SIN_COMPILAR, status=503, mimetype='text/html')

    bloque = f'<script id="dicsys-bootstrap" type="application/json">{htmlsafe_json_dumps(_armar_bootstrap())}</script>'
    respuesta = Response(indice.replace(MARCADOR_BOOTSTRAP, bloque, 1), mimetype='text/html')
    respuesta.headers['Cache-Control'] = 'no-store'
    return respuesta


@vue_app_bp.route('/', defaults={'ruta': ''})
@vue_app_bp.route('/<path:ruta>')
@login_required
def spa(ruta):
    """Punto de entrada unico de la SPA: cualquier ruta bajo /v2 la resuelve Vue Router."""
    return _servir_spa()


@vue_app_bp.route('/recruiting/candidatos')
@vue_app_bp.route('/recruiting/candidatos/nuevo')
@vue_app_bp.route('/recruiting/candidatos/<uuid:id>')
@require_permiso('recruiting.candidatos')
def spa_nuevo_candidato(id=None):
    """Candidatos y Nuevo Candidato exigen el mismo item de menu que sus URL originales (/recruiting/candidatos...).

    Ruta especifica: Flask la prefiere a la generica de arriba, que no cambia para el resto de las pantallas.
    """
    return _servir_spa()


@vue_app_bp.route('/recruiting/oportunidades')
@vue_app_bp.route('/recruiting/oportunidades/nueva')
@vue_app_bp.route('/recruiting/oportunidades/<uuid:id>')
@require_permiso('recruiting.oportunidades')
def spa_busquedas(id=None):
    """Busquedas exige el mismo item de menu que sus URL originales (/recruiting/oportunidades...)."""
    return _servir_spa()
