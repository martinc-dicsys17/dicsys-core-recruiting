"""
Seed de parámetros iniciales del sistema.
Idempotente por key: cuando se agrega un parámetro nuevo a PARAMETROS_SEED,
aparece solo en el próximo reinicio sin tocar los valores ya cargados.
"""

from sqlalchemy.orm import Session

from backend.modules.parametros.models import Parametro

PARAMETROS_SEED = [
    {
        "categoria": "Notificaciones",
        "subcategoria": "Webex",
        "nombre": "Sala de Notificación de Cumpleaños",
        "key": "webex_room_birthdate_id",
        "descripcion": "Room ID de Webex donde se publican las notificaciones de cumpleaños.",
        "valor_default": None,
        "valor": None,
    },
    {
        "categoria": "Notificaciones",
        "subcategoria": "Webex",
        "nombre": "Sala de Notificación de Innovacion",
        "key": "webex_room_innovacion_id",
        "descripcion": "Room ID de Webex donde se publican las notificaciones de Innovación.",
        "valor_default": None,
        "valor": None,
    },
    {
        "categoria": "Notificaciones",
        "subcategoria": "Webex",
        "nombre": "Sala de Notificación de Canjes de Star Miles",
        "key": "webex_room_starmiles_canjes_id",
        "descripcion": (
            "Room ID de Webex donde se avisa cada canje nuevo de Star Miles, para que quienes "
            "aprueban se enteren. Vacío: no se avisa. El bot tiene que estar en el room."
        ),
        "valor_default": None,
        "valor": None,
    },
    {
        "categoria": "Notificaciones",
        "subcategoria": "Webex",
        "nombre": "Sala de Presentaciones",
        "key": "webex_room_presentaciones_id",
        "descripcion": "Room ID de Webex del canal de presentaciones; se usa como contexto para los saludos de cumpleaños.",
        "valor_default": None,
        "valor": None,
    },
    {
        "categoria": "Notificaciones",
        "subcategoria": "Cumpleaños",
        "nombre": "Espera máxima entre envíos (minutos)",
        "key": "notificaciones_sleep_max_minutos",
        "descripcion": "Tope en minutos de la espera aleatoria entre saludos de cumpleaños consecutivos.",
        "valor_default": "20",
        "valor": None,
    },
    {
        "categoria": "Sincronización",
        "subcategoria": "Webex",
        "nombre": "Team ID de Webex (Dicsys)",
        "key": "webex_team_dicsys_id",
        "descripcion": "Team ID del equipo Dicsys en Webex. Se usa para descubrir los espacios (GET /v1/rooms?teamId=) e invitar a los empleados activos al team y a cada espacio.",
        "valor_default": None,
        "valor": None,
    },
    {
        "categoria": "Sincronización",
        "subcategoria": "Webex",
        "nombre": "Espacio General de Webex (lista maestra)",
        "key": "webex_general_room_id",
        "descripcion": "Room ID del espacio General del team (Dicsys.AI). Es la lista maestra del offboarding: los usuarios @dicsys que NO estén en General se quitan de todos los espacios del team. Si está vacío, el offboarding se omite.",
        "valor_default": None,
        "valor": None,
    },
    {
        "categoria": "Sincronización",
        "subcategoria": "Webex",
        "nombre": "Espacios de Webex a sincronizar",
        "key": "webex_sync_espacios",
        "descripcion": "Espacios del team donde se asegura la membresía de los empleados activos. Se editan con el selector «Editar» (trae la lista de la API y muestra los nombres); internamente se guarda el ID de cada espacio.",
        "valor_default": "[]",
        "valor": None,
    },
    {
        "categoria": "Sincronización",
        "subcategoria": "Webex",
        "nombre": "Pausa entre altas de Webex (segundos)",
        "key": "webex_sync_sleep_segundos",
        "descripcion": "Pausa entre cada alta de membresía en Webex, para no exceder los rate limits de la API. Sube este valor si sincronizás muchos espacios/personas. Default 0.3.",
        "valor_default": "0.3",
        "valor": None,
    },
    {
        "categoria": "Seguridad",
        "subcategoria": "OpenID Connect",
        "nombre": "Dominios de email verificados",
        "key": "oidc_dominios_verificados",
        "descripcion": (
            "Dominios (separados por coma) cuyos emails Dicsys Core informa como verificados "
            "(email_verified) a las apps que entran con Core, como razorback. Una cuenta activa con un "
            "email de otro dominio sale como no verificada y la app la rechaza."
        ),
        "valor_default": "dicsys.com,dicsys.ai",
        "valor": None,
    },
    {
        "categoria": "Seguridad",
        "subcategoria": "Ingreso con Google",
        "nombre": "Pedir el 2FA de Core al entrar con Google",
        "key": "google_login_requiere_2fa",
        "descripcion": (
            "true: quien entra con Google y tiene el segundo factor de Core activado (o exigido) también "
            "tiene que ingresar el código. false: la cuenta de Google alcanza."
        ),
        "valor_default": "false",
        "valor": None,
    },
    {
        "categoria": "Seguridad",
        "subcategoria": "Ingreso con Google",
        "nombre": "Dominio de las cuentas de Google",
        "key": "google_login_dominio",
        "descripcion": (
            "Solo se entra con cuentas de Google de este dominio (lo firma Google en el id_token). En el "
            "primer ingreso de nombre@<dominio>, quien solo tiene nombre@<otro dominio de su empresa> en "
            "la ficha pasa a tener el de Google como principal y el anterior como secundario."
        ),
        "valor_default": "dicsys.ai",
        "valor": None,
    },
]


def ejecutar_seed_parametros(db: Session) -> bool:
    """
    Crea los parámetros del seed que no existan.
    El chequeo por key es sin filtrar deleted_at: si un admin eliminó un
    parámetro seedeado, no se recrea en cada reinicio.
    """
    hubo_cambios = False

    for param in PARAMETROS_SEED:
        existe = db.query(Parametro).filter(Parametro.key == param["key"]).first()
        if not existe:
            db.add(Parametro(**param, updated_by="sistema@dicsys.com"))
            print(f"⚙️ Parámetro creado: {param['key']}")
            hubo_cambios = True

    if hubo_cambios:
        db.commit()

    return hubo_cambios
