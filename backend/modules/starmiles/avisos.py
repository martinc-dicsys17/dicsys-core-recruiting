"""
Aviso de canje nuevo por Webex (F20).

Cuando un empleado registra un canje, sale una card al room de Webex del parámetro
`webex_room_starmiles_canjes_id` (Configuración → Parámetros → Notificaciones → Webex),
para que quienes aprueban se enteren sin tener que entrar a mirar.

Sale por la cola de envíos del motor de tareas (F19): se encola en la misma transacción
que el canje, el programador la despacha, se reintenta si Webex falla y, si no sale,
llega la alerta de fallo. Sin room configurado no se avisa (queda en el log). Un error al
armar el aviso nunca impide registrar el canje.
"""

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.core import config
from backend.core.config import settings
from backend.modules.nomina.models import Empleado
from backend.modules.starmiles.models import Canje, ItemCanje
from backend.modules.tareas import cola
from backend.modules.tareas.models import Envio
from backend.modules.tareas.registro import a_argentina

logger = logging.getLogger(__name__)

CLAVE_ROOM = "webex_room_starmiles_canjes_id"
ORIGEN = "starmiles_canjes"
RUTA_APROBAR = "/starmiles/aprobador/canjes"


def _nombre(empleado: Optional[Empleado]) -> str:
    if empleado is None:
        return "Un colaborador"
    nombre = f"{(empleado.nombre or '').strip()} {(empleado.apellido or '').strip()}".strip()
    return nombre.title() or "Un colaborador"


def _millas(valor: int) -> str:
    return f"{valor:,}".replace(",", ".")  # 1.250


def _pesos(valor: Decimal) -> str:
    return "$ " + f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")  # $ 1.234,50


def _fila(etiqueta: str, valor: str) -> Dict[str, Any]:
    """Etiqueta a la izquierda y valor a lo ancho (un FactSet ocupa solo el ancho de su contenido)."""
    return {
        "type": "ColumnSet",
        "spacing": "Small",
        "columns": [
            {
                "type": "Column",
                "width": "110px",
                "items": [{"type": "TextBlock", "text": etiqueta, "isSubtle": True, "wrap": True}],
            },
            {
                "type": "Column",
                "width": "stretch",
                "items": [{"type": "TextBlock", "text": valor, "weight": "Bolder", "wrap": True}],
            },
        ],
    }


def tarjeta_canje(canje: Canje, empleado: Optional[Empleado], item: ItemCanje) -> Dict[str, Any]:
    """El aviso al room, como Adaptive Card."""
    filas: List[Dict[str, Any]] = [
        _fila("Premio", item.nombre),
        _fila("Cantidad", str(canje.cantidad)),
        _fila("Star Miles", _millas(canje.star_miles_total)),
    ]
    if canje.mercadolibre_precio is not None:
        filas.append(_fila("Precio", _pesos(Decimal(canje.mercadolibre_precio))))
    if (canje.comentario or "").strip():
        filas.append(_fila("Comentario", canje.comentario.strip()))
    fecha = a_argentina(canje.fecha_solicitud)
    if fecha is not None:
        filas.append(_fila("Pedido el", f"{fecha:%d/%m/%Y %H:%M}"))

    acciones = [
        {
            "type": "Action.OpenUrl",
            "title": "Revisar canjes pendientes",
            "url": f"{settings.frontend_url.rstrip('/')}{RUTA_APROBAR}",
        }
    ]
    if canje.mercadolibre_url:
        acciones.append({"type": "Action.OpenUrl", "title": "Ver en MercadoLibre", "url": canje.mercadolibre_url})
    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.3",
        "body": [
            {
                "type": "TextBlock",
                "text": "🎁 Nuevo canje de Star Miles",
                "weight": "Bolder",
                "size": "Large",
                "color": "Accent",
                "wrap": True,
            },
            {
                "type": "TextBlock",
                "text": f"{_nombre(empleado)} pidió un canje y está pendiente de aprobación.",
                "spacing": "None",
                "isSubtle": True,
                "wrap": True,
            },
            {"type": "Container", "style": "emphasis", "spacing": "Medium", "items": filas},
        ],
        "actions": acciones,
    }


def texto_canje(canje: Canje, empleado: Optional[Empleado], item: ItemCanje) -> str:
    """Lo que muestra Webex si no puede dibujar la card (y la vista previa de la notificación)."""
    return (
        f"Nuevo canje de Star Miles: {_nombre(empleado)} pidió «{item.nombre}» "
        f"({_millas(canje.star_miles_total)} Star Miles)."
    )


def encolar_aviso_canje(db: Session, canje: Canje, empleado: Optional[Empleado], item: ItemCanje) -> Optional[Envio]:
    """Encola el aviso al room (lo confirma el que llama). None si no hay room configurado."""
    room = (config.get_parameter(CLAVE_ROOM, db=db) or "").strip()
    if not room:
        logger.info("Sin room de Webex para canjes de Star Miles (%s): no se avisa el canje %s", CLAVE_ROOM, canje.id)
        return None
    return cola.encolar(
        db,
        origen=ORIGEN,
        canal="webex_room",
        destino=room,
        asunto=f"Nuevo canje de Star Miles: {_nombre(empleado)}",
        contenido={"card": tarjeta_canje(canje, empleado, item), "texto": texto_canje(canje, empleado, item)},
        clave=f"starmiles_canje:{canje.id}",
    )
