"""
Cola de envíos (F19-P05, D-98).

Los módulos encolan (`encolar`) y el programador despacha (`despachar`) en orden de
llegada, uno por uno, con una pausa entre mensajes de Webex para no chocar contra
su límite de tasa. Si un envío falla se reintenta con espera creciente (1, 5 y 15
minutos); al tercer fallo queda en error y se alerta (una alerta por tanda).

Sin duplicados: un envío con `clave` no se encola dos veces con la misma clave.
Con `referencia` («tipo:id») el módulo se entera del resultado final: registra un
manejador con `registrar_manejador(tipo, funcion)`.

`mandar()` es el envío por canal que usa la cola; los módulos lo usan directo cuando
necesitan el resultado en el momento (un envío manual o una prueba de canales).
"""

import logging
import time as reloj
from datetime import timedelta
from typing import Any, Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.core.email import email_service
from backend.core.utils import utc_now
from backend.core.webex import describir_error, email_de_persona, webex_service
from backend.modules.tareas import alertas
from backend.modules.tareas.models import Envio

logger = logging.getLogger(__name__)

MAX_INTENTOS = 3
ESPERAS = (timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=15))
PAUSA_WEBEX_SEGUNDOS = 0.3  # entre mensajes de Webex
LOTE = 50  # envíos por vuelta del programador

Manejador = Callable[[Session, str, Envio], None]
_manejadores: Dict[str, Manejador] = {}


def registrar_manejador(tipo: str, funcion: Manejador) -> None:
    """`funcion(db, id, envio)` se llama cuando un envío con referencia «tipo:id» sale o queda en error."""
    _manejadores[tipo] = funcion


def encolar(
    db: Session,
    *,
    origen: str,
    canal: str,
    destino: str,
    contenido: Dict[str, Any],
    asunto: Optional[str] = None,
    clave: Optional[str] = None,
    referencia: Optional[str] = None,
) -> Optional[Envio]:
    """Agrega un envío a la cola (lo confirma el que llama). None si la clave ya estaba encolada."""
    if clave and db.query(Envio.id).filter(Envio.clave == clave).first():
        return None
    envio = Envio(
        origen=origen,
        canal=canal,
        destino=destino,
        asunto=(asunto or "")[:300] or None,
        contenido=contenido,
        clave=clave,
        referencia=referencia,
    )
    db.add(envio)
    db.flush()
    return envio


def _destino_webex_personal(destino: str, db: Optional[Session]) -> str:
    """Con la base, el mensaje personal va al email de la cuenta de Webex de la persona: su email corporativo
    principal de su cuenta si existe en Webex y si no el secundario (F22). Sin cuenta, al destino tal cual."""
    if db is None:
        return destino
    from backend.modules.usuarios.emails_corporativos import emails_de_la_persona

    return email_de_persona(emails_de_la_persona(db, destino)) or destino


def mandar(
    canal: str, destino: str, asunto: Optional[str], contenido: Dict[str, Any], db: Optional[Session] = None
) -> Optional[str]:
    """Manda un mensaje por su canal. Devuelve None si salió o el motivo legible si no."""
    try:
        if canal == "email":
            cc = list(contenido.get("cc") or [])
            email_service.send(to=[destino] + cc if cc else destino, subject=asunto or "", html=contenido["html"])
            return None
        if canal == "webex_personal":
            destino = _destino_webex_personal(destino, db)
        destinos = {"person_email": destino} if canal == "webex_personal" else {"room_id": destino}
        if contenido.get("card"):
            resultado = webex_service.send_card(
                contenido["card"], fallback_text=contenido.get("texto") or asunto or "", **destinos
            )
        else:
            resultado = webex_service.send_text(
                contenido.get("texto") or "", markdown=contenido.get("markdown"), **destinos
            )
        return None if resultado.get("success") else describir_error(resultado)
    except Exception as exc:  # noqa: BLE001 - un canal caído no corta el resto
        detalle = getattr(exc, "detail", None) or str(exc) or exc.__class__.__name__
        logger.warning(f"Envío no salió por {canal} a {destino}: {detalle}")
        return str(detalle)


def _avisar_al_modulo(db: Session, envio: Envio) -> None:
    if not envio.referencia or ":" not in envio.referencia:
        return
    tipo, ident = envio.referencia.split(":", 1)
    manejador = _manejadores.get(tipo)
    if manejador is None:
        return
    try:
        manejador(db, ident, envio)
    except Exception as exc:  # noqa: BLE001 - el registro del módulo no frena la cola
        logger.error(f"El manejador «{tipo}» falló con el envío {envio.id}: {exc}", exc_info=True)


def despachar(db: Session, pausar: bool = True) -> Dict[str, int]:
    """Despacha los envíos que tocan, en orden de llegada. Devuelve cuántos salieron, se reintentan o fallaron."""
    ahora = utc_now()
    pendientes = (
        db.query(Envio)
        .filter(
            Envio.estado == "pendiente",
            Envio.proximo_intento_at <= ahora,
        )
        .order_by(Envio.creada_at)
        .limit(LOTE)
        .all()
    )
    resumen = {"enviados": 0, "reintentos": 0, "fallidos": 0}
    fallidos: List[Envio] = []
    ultimo_webex = False
    for envio in pendientes:
        if pausar and ultimo_webex and envio.canal != "email":
            reloj.sleep(PAUSA_WEBEX_SEGUNDOS)
        detalle = mandar(envio.canal, envio.destino, envio.asunto, envio.contenido, db=db)
        ultimo_webex = envio.canal != "email"
        envio.intentos += 1
        if detalle is None:
            envio.estado, envio.enviado_at, envio.error = "enviado", utc_now(), None
            resumen["enviados"] += 1
            _avisar_al_modulo(db, envio)
        elif envio.intentos >= MAX_INTENTOS:
            envio.estado, envio.error = "error", detalle
            resumen["fallidos"] += 1
            fallidos.append(envio)
            _avisar_al_modulo(db, envio)
        else:
            envio.error = detalle
            envio.proximo_intento_at = utc_now() + ESPERAS[envio.intentos - 1]
            resumen["reintentos"] += 1
        db.commit()  # cada envío queda registrado aunque el siguiente falle
    if fallidos:
        alertas.alertar_envios(db, fallidos)
        db.commit()
    return resumen


def reintentar(db: Session, envio: Envio) -> Envio:
    """Vuelve a poner en la cola un envío que quedó en error (a mano, desde la pantalla)."""
    if envio.estado != "error":
        raise ValueError("Solo se reintenta un envío que quedó en error")
    envio.estado, envio.intentos, envio.proximo_intento_at = "pendiente", 0, utc_now()
    envio.alerta_enviada = False
    db.commit()
    return envio
