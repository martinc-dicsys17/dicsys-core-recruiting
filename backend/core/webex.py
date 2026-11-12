"""
Módulo genérico de comunicación con Webex Teams.
Permite enviar mensajes de texto y Adaptive Cards a rooms o personas.
Todas las variables se reciben por parámetro para ser reutilizable desde cualquier módulo.
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional

import httpx
from pydantic import BaseModel

from backend.core.adapter_proxy import AdapterProxy
from backend.core.config import settings

logger = logging.getLogger(__name__)

WEBEX_API_URL = "https://webexapis.com/v1/messages"
WEBEX_MEMBERSHIPS_URL = "https://webexapis.com/v1/memberships"
WEBEX_ROOMS_URL = "https://webexapis.com/v1/rooms"
WEBEX_TEAM_MEMBERSHIPS_URL = "https://webexapis.com/v1/team/memberships"
WEBEX_PEOPLE_URL = "https://webexapis.com/v1/people"

# Cuánto se recuerda si un email tiene cuenta de Webex (F22)
PERSONAS_TTL_SEGUNDOS = 3600

# Reintentos ante 429 (rate limit) de la API de Webex.
WEBEX_MAX_RETRIES_429 = 4


class WebexMessage(BaseModel):
    """Esquema para envío de mensajes a Webex."""

    room_id: Optional[str] = None
    person_email: Optional[str] = None
    person_id: Optional[str] = None
    text: str
    markdown: Optional[str] = None
    adaptive_card: Optional[Dict[str, Any]] = None


class WebexService:
    """
    Servicio genérico para envío de mensajes a Webex Teams.

    Uso:
        # Configurar al inicio de la app
        webex_service.configure(bot_token="xoxb-...")

        # Enviar mensaje de texto a un room
        webex_service.send_text(room_id="Y2lz...", text="Hola mundo")

        # Enviar Adaptive Card
        webex_service.send_card(room_id="Y2lz...", card={...}, fallback_text="Card")

        # Enviar a una persona por email
        webex_service.send_text(person_email="user@example.com", text="Hola")
    """

    def __init__(self):
        self._bot_token: Optional[str] = None
        self._default_room_id: Optional[str] = None
        self._personas: Dict[str, tuple] = {}  # email -> (tiene cuenta, hasta cuándo vale)

    def configure(self, bot_token: str, default_room_id: Optional[str] = None):
        """
        Configura el servicio de Webex.

        Args:
            bot_token: Token del bot de Webex.
            default_room_id: Room ID por defecto (opcional).
        """
        self._bot_token = bot_token
        self._default_room_id = default_room_id

    @property
    def is_configured(self) -> bool:
        """Indica si el servicio está configurado."""
        return bool(self._bot_token)

    def _get_headers(self) -> Dict[str, str]:
        """Retorna los headers para la API de Webex."""
        return {"Content-Type": "application/json", "Authorization": f"Bearer {self._bot_token}"}

    def _resolve_destination(
        self, room_id: Optional[str] = None, person_email: Optional[str] = None, person_id: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Resuelve el destino del mensaje.
        Prioridad: room_id > person_email > person_id > default_room_id.
        """
        if room_id:
            return {"roomId": room_id}
        if person_email:
            return {"toPersonEmail": person_email}
        if person_id:
            return {"toPersonId": person_id}
        if self._default_room_id:
            return {"roomId": self._default_room_id}
        raise ValueError("Debe especificar room_id, person_email, person_id o configurar un default_room_id")

    def existe_persona(self, email: str, timeout: float = 10.0) -> Optional[bool]:
        """
        Si hay una cuenta de Webex con ese email: GET /v1/people?email=. None si
        no se pudo saber (sin configurar, error o timeout).
        """
        clave = (email or "").strip().lower()
        if not self.is_configured or not clave:
            return None
        guardado = self._personas.get(clave)
        if guardado and guardado[1] > time.monotonic():
            return guardado[0]
        try:
            with httpx.Client(timeout=timeout) as client:
                response = self._get_con_reintento(client, WEBEX_PEOPLE_URL, {"email": clave})
            if not response.is_success:
                logger.warning(f"⚠️ Webex: error {response.status_code} al buscar a {clave} - {response.text}")
                return None
            existe = bool(response.json().get("items"))
        except Exception as e:
            logger.warning(f"⚠️ Webex: no se pudo buscar a {clave} - {str(e)}")
            return None
        self._personas[clave] = (existe, time.monotonic() + PERSONAS_TTL_SEGUNDOS)
        return existe

    def send_text(
        self,
        text: str,
        room_id: Optional[str] = None,
        person_email: Optional[str] = None,
        person_id: Optional[str] = None,
        markdown: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Envía un mensaje de texto (o markdown) a Webex.

        Args:
            text: Texto plano del mensaje (fallback).
            room_id: ID del room destino.
            person_email: Email de la persona destino.
            person_id: ID de la persona destino.
            markdown: Contenido en markdown (opcional).

        Returns:
            dict con id del mensaje y status.
        """
        if not self.is_configured:
            logger.warning("⚠️ Webex service no configurado - mensaje no enviado")
            return {"success": False, "error": "Webex service no configurado"}

        destination = self._resolve_destination(room_id, person_email, person_id)
        payload = {**destination, "text": text}
        if markdown:
            payload["markdown"] = markdown

        return self._send(payload)

    def send_card(
        self,
        card: Dict[str, Any],
        fallback_text: str = "Mensaje con tarjeta adaptiva",
        room_id: Optional[str] = None,
        person_email: Optional[str] = None,
        person_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Envía una Adaptive Card a Webex.

        Args:
            card: Diccionario con la estructura de la Adaptive Card.
            fallback_text: Texto plano para clientes que no soportan cards.
            room_id: ID del room destino.
            person_email: Email de la persona destino.
            person_id: ID de la persona destino.

        Returns:
            dict con id del mensaje y status.
        """
        if not self.is_configured:
            logger.warning("⚠️ Webex service no configurado - card no enviada")
            return {"success": False, "error": "Webex service no configurado"}

        destination = self._resolve_destination(room_id, person_email, person_id)
        payload = {
            **destination,
            "text": fallback_text,
            "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive", "content": card}],
        }

        return self._send(payload)

    def list_messages(
        self,
        room_id: Optional[str] = None,
        max_results: int = 100,
        token: Optional[str] = None,
        url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Lista los mensajes de un room de Webex (más recientes primero).

        IMPORTANTE: los bots solo ven los mensajes de salas grupales donde
        fueron @mencionados. Para leer el historial completo pasar `token`
        con el access token de una cuenta de usuario miembro del room
        (ver backend.core.webex_oauth).

        Args:
            room_id: ID del room a leer (ignorado si se pasa `url`).
            max_results: Cantidad de mensajes por página.
            token: Access token alternativo; por defecto usa el del bot.
            url: URL de la página siguiente (next_url de una llamada anterior).

        Returns:
            dict con success, items (mensajes con personEmail, text, created)
            y next_url para paginar hacia atrás en el historial (None si no hay más).
        """
        auth_token = token or self._bot_token
        if not auth_token:
            logger.warning("⚠️ Webex: sin token disponible - no se pueden leer mensajes")
            return {"success": False, "error": "Webex service no configurado", "items": [], "next_url": None}

        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {auth_token}"}

        try:
            with httpx.Client(timeout=15.0) as client:
                if url:
                    response = client.get(url, headers=headers)
                else:
                    logger.info(f"📥 Webex: leyendo mensajes del room {room_id}")
                    response = client.get(
                        WEBEX_API_URL, headers=headers, params={"roomId": room_id, "max": max_results}
                    )

            if response.is_success:
                items = response.json().get("items", [])
                logger.info(f"✅ Webex: {len(items)} mensajes leídos")
                return {
                    "success": True,
                    "items": items,
                    "next_url": parse_next_link(response.headers.get("Link")),
                    "status_code": response.status_code,
                }

            logger.error(f"❌ Webex: error {response.status_code} al leer mensajes - {response.text}")
            return {
                "success": False,
                "status_code": response.status_code,
                "error": response.text,
                "items": [],
                "next_url": None,
            }

        except httpx.TimeoutException:
            logger.error("❌ Webex: timeout al leer mensajes")
            return {"success": False, "error": "Timeout al conectar con Webex API", "items": [], "next_url": None}
        except Exception as e:
            logger.error(f"❌ Webex: error inesperado al leer mensajes - {str(e)}")
            return {"success": False, "error": str(e), "items": [], "next_url": None}

    def _post_membership(self, url: str, payload: Dict[str, Any], descripcion: str = "") -> Dict[str, Any]:
        """
        POST de membresía (team o room) con manejo de 429 (rate limit) vía
        Retry-After. 409 = ya era miembro.

        Returns:
            dict con success y added (True si se la agregó, False si ya estaba).
        """
        if not self.is_configured:
            logger.warning("⚠️ Webex service no configurado - no se puede agregar la membresía")
            return {"success": False, "error": "Webex service no configurado", "added": False}

        try:
            with httpx.Client(timeout=15.0) as client:
                response = client.post(url, headers=self._get_headers(), json=payload)
                intento = 0
                while response.status_code == 429 and intento < WEBEX_MAX_RETRIES_429:
                    intento += 1
                    espera = _espera_retry_after(response, intento)
                    logger.warning(
                        f"⚠️ Webex 429 al agregar {descripcion}; espero {espera}s ({intento}/{WEBEX_MAX_RETRIES_429})"
                    )
                    time.sleep(espera)
                    response = client.post(url, headers=self._get_headers(), json=payload)

            if response.is_success:
                return {"success": True, "added": True}

            if response.status_code == 409:  # ya es miembro
                return {"success": True, "added": False}

            logger.error(f"❌ Webex: error {response.status_code} al agregar {descripcion} - {response.text}")
            return {"success": False, "status_code": response.status_code, "error": response.text, "added": False}

        except httpx.TimeoutException:
            logger.error(f"❌ Webex: timeout al agregar {descripcion}")
            return {"success": False, "error": "Timeout al conectar con Webex API", "added": False}
        except Exception as e:
            logger.error(f"❌ Webex: error inesperado al agregar {descripcion} - {str(e)}")
            return {"success": False, "error": str(e), "added": False}

    def ensure_membership(self, room_id: str, person_email: str) -> Dict[str, Any]:
        """
        Agrega a la persona al room si todavía no es miembro (la "invita").

        Returns:
            dict con success y added (True si se la agregó, False si ya estaba).
        """
        return self._post_membership(
            WEBEX_MEMBERSHIPS_URL,
            {"roomId": room_id, "personEmail": person_email},
            descripcion=f"{person_email} al room",
        )

    def _get_con_reintento(self, client: "httpx.Client", url: str, params: Optional[Dict[str, Any]] = None):
        """GET con reintento ante 429 (rate limit), respetando Retry-After."""
        response = client.get(url, headers=self._get_headers(), params=params)
        intento = 0
        while response.status_code == 429 and intento < WEBEX_MAX_RETRIES_429:
            intento += 1
            espera = _espera_retry_after(response, intento)
            logger.warning(f"⚠️ Webex 429 (GET); espero {espera}s y reintento ({intento}/{WEBEX_MAX_RETRIES_429})")
            time.sleep(espera)
            response = client.get(url, headers=self._get_headers(), params=params)
        return response

    def _paginated_get(self, url: str, params: Dict[str, Any], timeout: float = 15.0) -> Dict[str, Any]:
        """
        GET paginado de la API de Webex: junta todos los items siguiendo el
        header Link rel="next". Maneja 429 (rate limit) con reintento. Devuelve
        dict con success e items (parciales si hubo error/timeout a mitad de camino).
        """
        items: List[Dict[str, Any]] = []
        try:
            with httpx.Client(timeout=timeout) as client:
                response = self._get_con_reintento(client, url, params)
                while True:
                    if not response.is_success:
                        logger.error(f"❌ Webex: error {response.status_code} en {url} - {response.text}")
                        return {
                            "success": False,
                            "status_code": response.status_code,
                            "error": response.text,
                            "items": items,
                        }
                    items.extend(response.json().get("items", []))
                    next_url = parse_next_link(response.headers.get("Link"))
                    if not next_url:
                        break
                    response = self._get_con_reintento(client, next_url)
            return {"success": True, "items": items}
        except httpx.TimeoutException:
            logger.warning(f"⚠️ Webex: timeout al consultar {url}")
            return {"success": False, "error": "Timeout al conectar con Webex API", "timeout": True, "items": items}
        except Exception as e:
            logger.error(f"❌ Webex: error inesperado al consultar {url} - {str(e)}")
            return {"success": False, "error": str(e), "items": items}

    def list_rooms_by_team(self, team_id: str, timeout: float = 15.0) -> Dict[str, Any]:
        """
        Lista los espacios (rooms) de un team de Webex: GET /v1/rooms?teamId=.

        Returns:
            dict con success, rooms ([{id, nombre}]) y error/timeout si falló.
        """
        if not self.is_configured:
            return {"success": False, "error": "Webex service no configurado", "rooms": []}

        result = self._paginated_get(WEBEX_ROOMS_URL, {"teamId": team_id, "max": 100}, timeout=timeout)
        if not result["success"]:
            logger.warning(f"⚠️ Webex: no se pudieron listar los rooms del team {team_id}")
            return {
                "success": False,
                "error": result.get("error"),
                "timeout": result.get("timeout", False),
                "rooms": [],
            }

        rooms = [{"id": r.get("id"), "nombre": r.get("title")} for r in result["items"] if r.get("id")]
        return {"success": True, "rooms": rooms}

    def list_room_member_emails(self, room_id: str, timeout: float = 15.0) -> Dict[str, Any]:
        """
        Emails (en minúscula) de los miembros de un espacio:
        GET /v1/memberships?roomId=. Sirve para hacer diff antes de invitar.
        """
        if not self.is_configured:
            return {"success": False, "error": "Webex service no configurado", "emails": set()}

        result = self._paginated_get(WEBEX_MEMBERSHIPS_URL, {"roomId": room_id, "max": 100}, timeout=timeout)
        if not result["success"]:
            return {"success": False, "error": result.get("error"), "emails": set()}

        emails = {m["personEmail"].strip().lower() for m in result["items"] if m.get("personEmail")}
        return {"success": True, "emails": emails}

    def list_team_member_emails(self, team_id: str, timeout: float = 15.0) -> Dict[str, Any]:
        """
        Emails (en minúscula) de los miembros de un team:
        GET /v1/team/memberships?teamId=. Sirve para hacer diff antes de invitar.
        """
        if not self.is_configured:
            return {"success": False, "error": "Webex service no configurado", "emails": set()}

        result = self._paginated_get(WEBEX_TEAM_MEMBERSHIPS_URL, {"teamId": team_id, "max": 100}, timeout=timeout)
        if not result["success"]:
            return {"success": False, "error": result.get("error"), "emails": set()}

        emails = {m["personEmail"].strip().lower() for m in result["items"] if m.get("personEmail")}
        return {"success": True, "emails": emails}

    def ensure_team_membership(self, team_id: str, person_email: str) -> Dict[str, Any]:
        """
        Agrega a la persona al team si todavía no es miembro: la "invita" al
        team (y por ende al espacio General). POST /v1/team/memberships.

        Returns:
            dict con success y added (True si se la agregó, False si ya estaba).
        """
        return self._post_membership(
            WEBEX_TEAM_MEMBERSHIPS_URL,
            {"teamId": team_id, "personEmail": person_email},
            descripcion=f"{person_email} al team",
        )

    def remove_membership(self, room_id: str, person_email: str) -> Dict[str, Any]:
        """
        Quita a la persona de un espacio (room) si es miembro:
        GET /v1/memberships?roomId=&personEmail= para ubicar el membershipId y
        DELETE /v1/memberships/{id}. Maneja 429 (rate limit).

        Returns:
            dict con success y removed (True si se la quitó, False si no era miembro).
        """
        if not self.is_configured:
            return {"success": False, "error": "Webex service no configurado", "removed": False}

        try:
            with httpx.Client(timeout=15.0) as client:
                resp = self._get_con_reintento(
                    client, WEBEX_MEMBERSHIPS_URL, {"roomId": room_id, "personEmail": person_email}
                )
                if not resp.is_success:
                    return {"success": False, "status_code": resp.status_code, "error": resp.text, "removed": False}

                items = resp.json().get("items", [])
                if not items:
                    return {"success": True, "removed": False}  # no era miembro

                membership_id = items[0].get("id")
                del_resp = client.delete(f"{WEBEX_MEMBERSHIPS_URL}/{membership_id}", headers=self._get_headers())
                intento = 0
                while del_resp.status_code == 429 and intento < WEBEX_MAX_RETRIES_429:
                    intento += 1
                    espera = _espera_retry_after(del_resp, intento)
                    logger.warning(
                        f"⚠️ Webex 429 al quitar {person_email}; espero {espera}s ({intento}/{WEBEX_MAX_RETRIES_429})"
                    )
                    time.sleep(espera)
                    del_resp = client.delete(f"{WEBEX_MEMBERSHIPS_URL}/{membership_id}", headers=self._get_headers())

            if del_resp.is_success:
                return {"success": True, "removed": True}
            return {"success": False, "status_code": del_resp.status_code, "error": del_resp.text, "removed": False}

        except httpx.TimeoutException:
            logger.error(f"❌ Webex: timeout al quitar {person_email}")
            return {"success": False, "error": "Timeout al conectar con Webex API", "removed": False}
        except Exception as e:
            logger.error(f"❌ Webex: error inesperado al quitar {person_email} - {str(e)}")
            return {"success": False, "error": str(e), "removed": False}

    def send_message(self, message: WebexMessage) -> Dict[str, Any]:
        """
        Envía un mensaje usando el esquema WebexMessage.

        Args:
            message: Esquema con los datos del mensaje.

        Returns:
            dict con resultado del envío.
        """
        if message.adaptive_card:
            return self.send_card(
                card=message.adaptive_card,
                fallback_text=message.text,
                room_id=message.room_id,
                person_email=message.person_email,
                person_id=message.person_id,
            )
        return self.send_text(
            text=message.text,
            room_id=message.room_id,
            person_email=message.person_email,
            person_id=message.person_id,
            markdown=message.markdown,
        )

    def _send(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Ejecuta el envío HTTP a la API de Webex.

        Args:
            payload: Body del request.

        Returns:
            dict con success, message_id y status_code.
        """
        try:
            logger.info(
                f"📨 Webex: enviando mensaje a {payload.get('roomId') or payload.get('toPersonEmail') or payload.get('toPersonId')}"
            )

            with httpx.Client(timeout=15.0) as client:
                response = client.post(WEBEX_API_URL, headers=self._get_headers(), json=payload)

            if response.is_success:
                data = response.json()
                logger.info(f"✅ Webex: mensaje enviado. ID: {data.get('id', 'N/A')}")
                return {"success": True, "message_id": data.get("id"), "status_code": response.status_code}
            else:
                logger.error(f"❌ Webex: error {response.status_code} - {response.text}")
                return {"success": False, "status_code": response.status_code, "error": response.text}

        except httpx.TimeoutException:
            logger.error("❌ Webex: timeout al enviar mensaje")
            return {"success": False, "error": "Timeout al conectar con Webex API"}
        except Exception as e:
            logger.error(f"❌ Webex: error inesperado - {str(e)}")
            return {"success": False, "error": str(e)}


def _espera_retry_after(response, intento: int, tope: float = 30.0) -> float:
    """
    Segundos a esperar ante un 429: usa el header Retry-After si está presente,
    si no, backoff exponencial (2^intento) acotado a `tope` segundos.
    """
    retry_after = response.headers.get("Retry-After")
    try:
        espera = float(retry_after) if retry_after else 2.0**intento
    except TypeError, ValueError:
        espera = 2.0**intento
    return min(max(espera, 0.0), tope)


def build_mention(person_email: str, display_name: Optional[str] = None) -> str:
    """
    Markdown de mención de Webex: <@personEmail:email|Nombre>.
    La persona mencionada recibe la notificación de @mención en el room.
    """
    if display_name:
        return f"<@personEmail:{person_email}|{display_name}>"
    return f"<@personEmail:{person_email}>"


def parse_next_link(link_header: Optional[str]) -> Optional[str]:
    """
    Extrae la URL rel="next" de un header Link (paginación de Webex).
    Ej: '<https://webexapis.com/v1/messages?roomId=X&beforeMessage=Y>; rel="next"'
    """
    if not link_header:
        return None
    for parte in link_header.split(","):
        secciones = parte.split(";")
        if len(secciones) >= 2 and 'rel="next"' in secciones[1]:
            return secciones[0].strip().strip("<>")
    return None


# === Helpers para construir Adaptive Cards ===


def build_notification_card(
    title: str,
    facts: List[Dict[str, str]],
    icon_url: Optional[str] = None,
    actions: Optional[List[Dict[str, Any]]] = None,
    accent_color: str = "Accent",
) -> Dict[str, Any]:
    """
    Construye una Adaptive Card genérica de notificación.

    Args:
        title: Título principal de la card.
        facts: Lista de dicts con 'title' y 'value'.
        icon_url: URL de un ícono/imagen (opcional).
        actions: Lista de acciones (botones) para la card.
        accent_color: Color del título (Accent, Good, Warning, Attention).

    Returns:
        dict con la estructura de la Adaptive Card.
    """
    body: List[Dict[str, Any]] = [
        {"type": "TextBlock", "text": title, "weight": "Bolder", "size": "Medium", "color": accent_color, "wrap": True}
    ]

    columns: List[Dict[str, Any]] = []

    if icon_url:
        columns.append(
            {
                "type": "Column",
                "width": "auto",
                "items": [{"type": "Image", "url": icon_url, "size": "Small", "style": "Person"}],
            }
        )

    columns.append(
        {
            "type": "Column",
            "width": "stretch",
            "items": [{"type": "FactSet", "facts": [{"title": f["title"], "value": f["value"]} for f in facts]}],
        }
    )

    body.append({"type": "ColumnSet", "columns": columns})

    card: Dict[str, Any] = {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.3",
        "body": body,
    }

    if actions:
        card["actions"] = actions

    return card


# Fachada estable: los callers conservan la referencia y tests cambian el adaptador.
webex_service = AdapterProxy(WebexService())


def email_de_persona(candidatos: List[Optional[str]]) -> Optional[str]:
    """
    De los emails corporativos de una persona (el principal primero), el de su
    cuenta de Webex: el principal si existe en Webex y si no el secundario
    (F22). Si ninguno existe o no se puede saber, el principal, como antes.
    Con un solo email no se consulta a Webex.
    """
    emails = []
    for email in candidatos:
        email = (email or "").strip().lower()
        if email and email not in emails:
            emails.append(email)
    if len(emails) <= 1:
        return emails[0] if emails else None
    for email in emails:
        if webex_service.existe_persona(email):
            return email
    return emails[0]


def init_webex_service():
    """
    Inicializa el servicio de Webex con la configuración de la aplicación.
    Llamar esta función al iniciar la aplicación.
    """
    bot_token = getattr(settings, "webex_bot_token", None)
    default_room = getattr(settings, "webex_default_room_id", None)

    if bot_token:
        webex_service.configure(bot_token=bot_token, default_room_id=default_room)
        logger.info(f"✅ Webex service configurado. Default room: {default_room or 'ninguno'}")
    else:
        logger.warning("⚠️ WEBEX_BOT_TOKEN no configurada - Webex deshabilitado")


# ─── Errores legibles ────────────────────────────────────────────────────────

# Errores de Webex que se traducen a algo accionable; el resto se muestra con su `message`
_ERRORES_CONOCIDOS = (
    ("must join the team", "El bot de Webex no es miembro del equipo (team) de ese room: hay que invitarlo al equipo"),
    ("could not find a room", "No se encontró el room de Webex: revisá el ID o invitá al bot al room"),
)


def describir_error(resultado: Optional[Dict[str, Any]]) -> str:
    """
    Por qué no salió un mensaje de Webex, en castellano y legible. `send_text` y
    `send_card` devuelven el cuerpo crudo de la API (un JSON) en `error`: de ahí
    se toma su `message`, y los errores conocidos se traducen a qué hacer.
    """
    resultado = resultado or {}
    texto = str(resultado.get("error") or "").strip()
    try:
        texto = json.loads(texto).get("message") or texto
    except ValueError, AttributeError:
        pass
    for clave, mensaje in _ERRORES_CONOCIDOS:
        if clave in texto.lower():
            return mensaje
    if resultado.get("status_code") == 401:
        return "El token del bot de Webex no es válido o venció"
    return texto or "Webex no confirmó el envío"
