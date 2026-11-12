"""
Alertas de fallo por Webex (F19-P04, D-99).

Van al room configurado en Parámetros (`alertas_webex_room_id`): una por corrida
fallida (no una por mensaje) y una por tanda de envíos que agotaron los reintentos.
Salen directo por Webex, no por la cola: si la cola fallara, la alerta tiene que
poder salir igual. Un mismo error de una misma tarea no se repite dentro de la hora,
así una tarea continua que falla en cada vuelta no llena el room.
"""

import logging
from datetime import timedelta
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from backend.core import config
from backend.core.config import settings
from backend.core.utils import utc_now
from backend.core.webex import describir_error, webex_service
from backend.modules.tareas.models import Envio, TareaCorrida

logger = logging.getLogger(__name__)

CLAVE_ROOM = "alertas_webex_room_id"
RUTA_PANTALLA = "/tareas-programadas"
VENTANA_SIN_REPETIR = timedelta(hours=1)
MAX_ENVIOS_EN_ALERTA = 10


def room_de_alertas(db: Session) -> Optional[str]:
    valor = str(config.get_parameter(CLAVE_ROOM, "", db=db) or "").strip()
    return valor or None


def _tarjeta(titulo: str, subtitulo: str, cuerpo: List[Dict[str, Any]], pestana: str) -> Dict[str, Any]:
    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.3",
        "body": [
            {
                "type": "TextBlock",
                "text": titulo,
                "weight": "Bolder",
                "size": "Large",
                "color": "Attention",
                "wrap": True,
            },
            {"type": "TextBlock", "text": subtitulo, "spacing": "None", "isSubtle": True, "wrap": True},
            *cuerpo,
        ],
        "actions": [
            {
                "type": "Action.OpenUrl",
                "title": "Ver en Tareas programadas",
                "url": f"{settings.frontend_url.rstrip('/')}{RUTA_PANTALLA}?tab={pestana}",
            }
        ],
    }


def _enviar(db: Session, tarjeta: Dict[str, Any], texto: str) -> bool:
    room = room_de_alertas(db)
    if not room:
        logger.warning(f"⚠️ Alerta sin room configurado ({CLAVE_ROOM} en Parámetros): {texto}")
        return False
    try:
        resultado = webex_service.send_card(tarjeta, fallback_text=texto, room_id=room)
    except Exception as exc:  # noqa: BLE001 - la alerta nunca rompe al que alerta
        logger.error(f"❌ No salió la alerta por Webex: {exc}")
        return False
    if not resultado.get("success"):
        logger.error(f"❌ No salió la alerta por Webex: {describir_error(resultado)}")
        return False
    return True


def alertar_corrida(db: Session, corrida: TareaCorrida, nombre: str) -> bool:
    """Avisa que una corrida terminó en error. Devuelve si salió (o si ya se había avisado lo mismo)."""
    repetida = (
        db.query(TareaCorrida.id)
        .filter(
            TareaCorrida.tarea == corrida.tarea,
            TareaCorrida.id != corrida.id,
            TareaCorrida.estado == "error",
            TareaCorrida.alerta_enviada.is_(True),
            TareaCorrida.error == corrida.error,
            TareaCorrida.creada_at >= utc_now() - VENTANA_SIN_REPETIR,
        )
        .first()
    )
    if repetida:
        logger.info(f"🔕 Alerta de «{nombre}» omitida: el mismo error ya se avisó en la última hora")
        return False
    disparo = "a mano" if corrida.disparo == "manual" else "programada"
    tarjeta = _tarjeta(
        f"Falló: {nombre}",
        f"Corrida {disparo}" + (f" pedida por {corrida.solicitada_por}" if corrida.solicitada_por else ""),
        [
            {
                "type": "Container",
                "style": "attention",
                "spacing": "Medium",
                "items": [{"type": "TextBlock", "text": (corrida.error or "Error sin detalle")[:1500], "wrap": True}],
            }
        ],
        "historial",
    )
    enviada = _enviar(db, tarjeta, f"Falló la tarea «{nombre}»: {(corrida.error or '')[:200]}")
    corrida.alerta_enviada = enviada
    return enviada


def alertar_envios(db: Session, envios: Iterable[Envio]) -> bool:
    """Una alerta por tanda de envíos que agotaron los reintentos."""
    envios = list(envios)
    if not envios:
        return False
    filas = [
        {
            "type": "ColumnSet",
            "separator": True,
            "spacing": "Small",
            "columns": [
                {
                    "type": "Column",
                    "width": "stretch",
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": f"{e.origen} · {e.canal} → {e.destino}",
                            "weight": "Bolder",
                            "wrap": True,
                        },
                        {
                            "type": "TextBlock",
                            "text": (e.error or "")[:300],
                            "isSubtle": True,
                            "spacing": "None",
                            "wrap": True,
                        },
                    ],
                },
            ],
        }
        for e in envios[:MAX_ENVIOS_EN_ALERTA]
    ]
    extra = len(envios) - MAX_ENVIOS_EN_ALERTA
    if extra > 0:
        filas.append({"type": "TextBlock", "text": f"…y {extra} más", "isSubtle": True, "wrap": True})
    plural = "s" if len(envios) != 1 else ""
    tarjeta = _tarjeta(
        f"No salieron {len(envios)} envío{plural}", "Agotaron los reintentos de la cola de envíos", filas, "envios"
    )
    enviada = _enviar(db, tarjeta, f"No salieron {len(envios)} envío{plural} de la cola")
    for envio in envios:
        envio.alerta_enviada = enviada
    return enviada
