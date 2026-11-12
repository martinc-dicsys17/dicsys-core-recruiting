"""
Servicios para el módulo de Notificaciones.

Flujo de cumpleaños:
  1. Busca empleados activos que cumplen años hoy.
  2. Lee el canal de presentaciones de Webex y filtra los mensajes de esa
     persona con más de 50 caracteres (su presentación al equipo).
  3. Genera un saludo informal y alegre con Gemini usando ese contexto.
  4. Envía una Adaptive Card al room de cumpleaños.
  5. Registra cada paso en notificaciones_log (check + detalle de errores).
  6. Entre persona y persona espera un sleep aleatorio (hasta N minutos).

El proceso corre en un thread en background; un lock evita ejecuciones
concurrentes y el log con estado 'enviado' por empleado+fecha evita
duplicados si se vuelve a disparar el mismo día.
"""

import logging
import random
import threading
import time
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import extract, text
from sqlalchemy.orm import Session

from backend.core import config
from backend.core.utils import utc_now
from backend.core.webex import build_mention, describir_error, email_de_persona, webex_service
from backend.modules.nomina.models import Empleado
from backend.modules.notificaciones.models import NotificacionLog

logger = logging.getLogger(__name__)

TIPO_CUMPLEANOS = "cumpleanos"
MIN_CARACTERES_PRESENTACION = 50
MAX_MENSAJES_CONTEXTO = 3
MAX_PAGINAS_PRESENTACIONES = 10  # tope de páginas al buscar la presentación en el historial
SLEEP_MAX_MINUTOS_DEFAULT = 20

# Advisory lock de Postgres: evita que dos procesos manden los saludos a la vez.
# El envío automático lo dispara el motor de tareas (backend/modules/notificaciones/tareas.py).
PG_LOCK_CUMPLEANOS = 982451653  # arbitrario pero estable

# Lock del proceso de envío dentro de este worker.
_proceso_lock = threading.Lock()


class NotificacionService:
    """Lógica de negocio de notificaciones de cumpleaños."""

    # ─── Consultas ───────────────────────────────────────────────────────────

    @staticmethod
    def buscar_cumpleaneros(db: Session, fecha: Optional[date] = None) -> List[Empleado]:
        """Empleados activos que cumplen años en la fecha indicada (hoy por defecto)."""
        fecha = fecha or date.today()
        return (
            db.query(Empleado)
            .filter(
                Empleado.deleted_at.is_(None),
                Empleado.activo.is_(True),
                Empleado.fecha_baja.is_(None),
                Empleado.fecha_nacimiento.isnot(None),
                extract("month", Empleado.fecha_nacimiento) == fecha.month,
                extract("day", Empleado.fecha_nacimiento) == fecha.day,
            )
            .order_by(Empleado.apellido, Empleado.nombre)
            .all()
        )

    @staticmethod
    def listar_logs(
        db: Session,
        estado: Optional[str] = None,
        fecha: Optional[date] = None,
        limit: int = 100,
    ) -> List[NotificacionLog]:
        """Listado de logs de notificaciones, más recientes primero."""
        query = db.query(NotificacionLog).filter(NotificacionLog.deleted_at.is_(None))
        if estado:
            query = query.filter(NotificacionLog.estado == estado)
        if fecha:
            query = query.filter(NotificacionLog.fecha_evento == fecha)
        return query.order_by(NotificacionLog.created_at.desc()).limit(limit).all()

    @staticmethod
    def ya_enviado(db: Session, empleado_id, fecha: date) -> bool:
        """Indica si ya hay una notificación enviada para el empleado en esa fecha."""
        return (
            db.query(NotificacionLog)
            .filter(
                NotificacionLog.deleted_at.is_(None),
                NotificacionLog.tipo == TIPO_CUMPLEANOS,
                NotificacionLog.empleado_id == empleado_id,
                NotificacionLog.fecha_evento == fecha,
                NotificacionLog.estado == "enviado",
            )
            .first()
            is not None
        )

    # ─── Helpers puros (testeables sin DB ni red) ───────────────────────────

    @staticmethod
    def filtrar_mensajes_presentacion(
        items: List[Dict[str, Any]],
        email: str,
        min_caracteres: int = MIN_CARACTERES_PRESENTACION,
        max_mensajes: int = MAX_MENSAJES_CONTEXTO,
    ) -> List[str]:
        """
        Filtra los mensajes del canal de presentaciones: solo los de la persona
        (por email) y con más de `min_caracteres` caracteres.
        """
        if not email:
            return []
        email = email.strip().lower()
        encontrados = []
        for item in items:
            texto = (item.get("text") or "").strip()
            autor = (item.get("personEmail") or "").strip().lower()
            if autor == email and len(texto) > min_caracteres:
                encontrados.append(texto)
            if len(encontrados) >= max_mensajes:
                break
        return encontrados

    @staticmethod
    def obtener_mensajes_presentacion(
        room_id: str,
        email: str,
        token: Optional[str] = None,
        max_paginas: int = MAX_PAGINAS_PRESENTACIONES,
    ) -> List[str]:
        """
        Busca los mensajes de presentación de la persona paginando hacia atrás
        en el historial del room (la presentación puede ser antigua).
        """
        encontrados: List[str] = []
        url = None
        for _ in range(max_paginas):
            resultado = webex_service.list_messages(room_id=room_id, token=token, url=url)
            if not resultado.get("success"):
                logger.warning(f"⚠️ No se pudo leer el canal de presentaciones: {resultado.get('error')}")
                break
            encontrados += NotificacionService.filtrar_mensajes_presentacion(
                resultado["items"],
                email,
                max_mensajes=MAX_MENSAJES_CONTEXTO - len(encontrados),
            )
            url = resultado.get("next_url")
            if len(encontrados) >= MAX_MENSAJES_CONTEXTO or not url:
                break
        return encontrados

    @staticmethod
    def armar_prompt(nombre: str, fecha: date, contexto: Optional[str]) -> str:
        """Arma el prompt para Gemini: saludo breve, alegre y en voz del equipo."""
        fecha_str = fecha.strftime("%d/%m/%Y")
        prompt = (
            f"Hoy es {fecha_str} y es el cumpleaños de {nombre}.\n"
            "Escribí UN solo mensaje de cumpleaños, breve, para publicar en el canal de Webex del equipo.\n"
            "Tono: informal, alegre y cercano, en español rioplatense. Máximo 50 palabras. "
            "Podés usar algunos emojis.\n"
            "Escribí en nombre del equipo: usá 'nosotros' o un tono neutral, nunca la primera persona del singular ('yo').\n"
            "No menciones la edad ni la cantidad de años que cumple.\n"
        )
        if contexto:
            prompt += (
                "\nTomá UN solo dato puntual de su presentación al equipo y mencionalo muy al pasar "
                "(una referencia breve y simpática); no resumas ni repitas el contexto:\n"
                f"---\n{contexto}\n---\n"
            )
        prompt += "\nDevolvé únicamente el texto del mensaje, sin títulos, opciones ni explicaciones."
        return prompt

    @staticmethod
    def build_birthday_card(nombre: str, mensaje: str, fecha: date) -> Dict[str, Any]:
        """Construye la Adaptive Card de cumpleaños."""
        icono_torta = "https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/1f382.png"
        return {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.3",
            "body": [
                {
                    "type": "ColumnSet",
                    "columns": [
                        {
                            "type": "Column",
                            "width": "auto",
                            "verticalContentAlignment": "Center",
                            "items": [
                                {
                                    "type": "Image",
                                    "url": icono_torta,
                                    "size": "Medium",
                                    "altText": "🎂",
                                }
                            ],
                        },
                        {
                            "type": "Column",
                            "width": "stretch",
                            "verticalContentAlignment": "Center",
                            "items": [
                                {
                                    "type": "TextBlock",
                                    "text": "¡Feliz cumpleaños!",
                                    "weight": "Bolder",
                                    "size": "ExtraLarge",
                                    "color": "Attention",
                                    "wrap": True,
                                },
                                {
                                    "type": "TextBlock",
                                    "text": nombre,
                                    "weight": "Bolder",
                                    "size": "Large",
                                    "color": "Accent",
                                    "spacing": "None",
                                    "wrap": True,
                                },
                            ],
                        },
                    ],
                },
                {
                    "type": "Container",
                    "style": "emphasis",
                    "spacing": "Medium",
                    "items": [
                        {
                            "type": "TextBlock",
                            "text": mensaje,
                            "size": "Medium",
                            "wrap": True,
                        }
                    ],
                },
                {
                    "type": "ColumnSet",
                    "spacing": "Medium",
                    "columns": [
                        {
                            "type": "Column",
                            "width": "stretch",
                            "items": [
                                {
                                    "type": "TextBlock",
                                    "text": "🎉 De parte de todo el equipo",
                                    "size": "Small",
                                    "isSubtle": True,
                                    "wrap": True,
                                }
                            ],
                        },
                        {
                            "type": "Column",
                            "width": "auto",
                            "items": [
                                {
                                    "type": "TextBlock",
                                    "text": fecha.strftime("%d/%m/%Y"),
                                    "size": "Small",
                                    "isSubtle": True,
                                }
                            ],
                        },
                    ],
                },
            ],
        }

    # ─── Proceso en background ──────────────────────────────────────────────

    @staticmethod
    def proceso_en_ejecucion() -> bool:
        """Indica si hay un proceso de envío corriendo."""
        return _proceso_lock.locked()

    @staticmethod
    def iniciar_proceso_cumpleanos(usuario: str) -> bool:
        """
        Lanza el proceso de envío en un thread en background.
        Devuelve False si ya hay una ejecución en curso.
        """
        if not _proceso_lock.acquire(blocking=False):
            return False
        thread = threading.Thread(
            target=NotificacionService._procesar_cumpleanos,
            args=(usuario,),
            daemon=True,
            name="notificaciones-cumpleanos",
        )
        thread.start()
        return True

    @staticmethod
    def _procesar_cumpleanos(usuario: str):
        """Cuerpo del thread: procesa los cumpleañeros del día uno por uno."""
        from backend.database import SessionLocal

        hoy = date.today()
        # Advisory lock de Postgres (sesión dedicada que se mantiene abierta
        # durante toda la corrida): si otro worker ya está procesando, salir.
        lock_db = SessionLocal()
        lock_tomado = False
        try:
            lock_tomado = bool(
                lock_db.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": PG_LOCK_CUMPLEANOS}).scalar()
            )
            lock_db.commit()
            if not lock_tomado:
                logger.info("🎂 Otro worker ya está procesando cumpleaños, se omite")
                return

            NotificacionService._procesar_cumpleanos_con_lock(hoy, usuario)
        except Exception as e:
            logger.error(f"❌ Error inesperado en el proceso de cumpleaños: {e}", exc_info=True)
        finally:
            if lock_tomado:
                try:
                    lock_db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": PG_LOCK_CUMPLEANOS})
                    lock_db.commit()
                except Exception:
                    pass
            lock_db.close()
            _proceso_lock.release()

    @staticmethod
    def _procesar_cumpleanos_con_lock(hoy: date, usuario: str):
        """Corrida del proceso (ya con el advisory lock tomado)."""
        from backend.database import SessionLocal

        # 1. Crear logs pendientes para los cumpleañeros aún no notificados
        db = SessionLocal()
        try:
            NotificacionService._marcar_abandonados(db)

            cumpleaneros = NotificacionService.buscar_cumpleaneros(db, hoy)
            log_ids = []
            for emp in cumpleaneros:
                if NotificacionService.ya_enviado(db, emp.id, hoy):
                    logger.info(f"🎂 {emp.empleado_nombre_completo}: ya notificado hoy, se omite")
                    continue
                log = NotificacionLog(
                    empresa_id=emp.empresa_id,
                    tipo=TIPO_CUMPLEANOS,
                    fecha_evento=hoy,
                    empleado_id=emp.id,
                    empleado_nombre=f"{emp.nombre} {emp.apellido}",
                    empleado_email=emp.email_corporativo,
                    estado="pendiente",
                    updated_by=usuario,
                )
                db.add(log)
                db.flush()
                log_ids.append(log.id)
            db.commit()

            sleep_max_seg = NotificacionService._sleep_max_segundos(db)
        finally:
            db.close()

        if not log_ids:
            logger.info("🎂 Sin cumpleañeros pendientes de notificar hoy")
            return

        # 2. Procesar de a uno, con espera aleatoria entre personas.
        #    Sesión nueva por persona: el sleep puede durar varios minutos
        #    y no conviene retener una conexión del pool durante la espera.
        for i, log_id in enumerate(log_ids):
            if i > 0:
                espera = random.randint(1, sleep_max_seg)
                logger.info(f"⏳ Esperando {espera // 60}m {espera % 60}s antes del próximo cumpleañero")
                time.sleep(espera)

            db = SessionLocal()
            try:
                NotificacionService._procesar_log(db, log_id, hoy, usuario)
            finally:
                db.close()

    @staticmethod
    def _marcar_abandonados(db: Session):
        """
        Logs colgados en pendiente/procesando hace más de 2 horas (proceso
        interrumpido por un reinicio) pasan a error para que el detalle quede
        visible y el próximo run los reintente.
        """
        limite = utc_now() - timedelta(hours=2)
        colgados = (
            db.query(NotificacionLog)
            .filter(
                NotificacionLog.deleted_at.is_(None),
                NotificacionLog.estado.in_(["pendiente", "procesando"]),
                NotificacionLog.updated_at < limite,
            )
            .all()
        )
        for log in colgados:
            log.estado = "error"
            log.error_detalle = "Proceso interrumpido (marcado por la limpieza automática)"
        if colgados:
            db.commit()
            logger.info(f"🧹 {len(colgados)} notificación(es) colgadas marcadas como error")

    @staticmethod
    def _sleep_max_segundos(db: Session) -> int:
        """Tope de la espera aleatoria entre envíos (parametrizable, default 20 min)."""
        valor = config.get_parameter("notificaciones_sleep_max_minutos", SLEEP_MAX_MINUTOS_DEFAULT, db=db)
        try:
            minutos = max(1, int(valor))
        except TypeError, ValueError:
            minutos = SLEEP_MAX_MINUTOS_DEFAULT
        return minutos * 60

    @staticmethod
    def _procesar_log(db: Session, log_id, hoy: date, usuario: str):
        """Procesa una notificación individual: contexto → Gemini → card → log."""
        from backend.core.llm.client import LLMError, generate

        log = db.query(NotificacionLog).filter(NotificacionLog.id == log_id).first()
        if not log or log.estado == "enviado":
            return

        log.estado = "procesando"
        log.updated_by = usuario
        db.commit()

        try:
            room_destino = config.get_parameter("webex_room_birthdate_id", db=db)
            if not room_destino:
                raise ValueError(
                    "Parámetro 'webex_room_birthdate_id' sin configurar (Configuración → Parámetros → Notificaciones)"
                )

            # 2. Contexto: mensajes de la persona en el canal de presentaciones.
            #    Se lee con el token de la cuenta lectora OAuth (los bots no ven
            #    el historial de salas grupales); sin cuenta conectada se sigue
            #    sin contexto.
            from backend.core import webex_oauth

            # La cuenta de Webex de la persona: su email corporativo principal si existe en Webex y si no el
            # secundario (F22).
            from backend.modules.usuarios.emails_corporativos import emails_de_la_persona

            email_webex = email_de_persona(emails_de_la_persona(db, log.empleado_email)) if log.empleado_email else None

            contexto = None
            room_presentaciones = config.get_parameter("webex_room_presentaciones_id", db=db)
            if room_presentaciones and email_webex:
                token_lector = webex_oauth.get_reader_access_token(db)
                if not token_lector:
                    logger.warning("⚠️ Sin cuenta lectora de Webex conectada: se genera el saludo sin contexto")
                mensajes = NotificacionService.obtener_mensajes_presentacion(
                    room_presentaciones, email_webex, token=token_lector
                )
                contexto = "\n\n".join(mensajes) if mensajes else None
            log.contexto_presentacion = contexto
            db.commit()

            # 3. Generar el saludo con Gemini
            prompt = NotificacionService.armar_prompt(log.empleado_nombre, hoy, contexto)
            resultado_llm = generate(
                modulo="notificaciones",
                contents=prompt,
                db=db,
                usuario=usuario,
            )
            mensaje = (resultado_llm.text or "").strip()
            if not mensaje:
                raise LLMError("La LLM devolvió un mensaje vacío")
            log.llm_request_id = resultado_llm.id
            log.mensaje_generado = mensaje
            db.commit()

            # 4a. Saludo con @mención antes de la card: agrega a la persona a la
            #     sala si no estaba (para que pueda ver el mensaje) y la taggea.
            #     Si este paso falla, la card sale igual.
            email_mencion = email_webex
            if email_mencion:
                invitacion = webex_service.ensure_membership(room_id=room_destino, person_email=email_mencion)
                if not invitacion.get("success"):
                    logger.warning(f"⚠️ No se pudo agregar a {email_mencion} a la sala: {describir_error(invitacion)}")
                saludo = webex_service.send_text(
                    text=f"Hola {log.empleado_nombre}! 🎉",
                    markdown=f"Hola {build_mention(email_mencion, log.empleado_nombre)}! 🎉",
                    room_id=room_destino,
                )
                if not saludo.get("success"):
                    logger.warning(f"⚠️ No se pudo enviar el saludo con mención: {describir_error(saludo)}")
            else:
                logger.warning(f"⚠️ {log.empleado_nombre} sin email corporativo: card sin mención previa")

            # 4b. Enviar la card a Webex
            card = NotificacionService.build_birthday_card(log.empleado_nombre, mensaje, hoy)
            envio = webex_service.send_card(
                card=card,
                fallback_text=f"🎂 ¡Feliz cumpleaños {log.empleado_nombre}! {mensaje}",
                room_id=room_destino,
            )
            if not envio.get("success"):
                raise RuntimeError(f"Error al enviar a Webex: {describir_error(envio)}")

            # 5/6. Registrar el envío
            log.webex_message_id = envio.get("message_id")
            log.estado = "enviado"
            log.enviado_at = utc_now()
            log.error_detalle = None
            db.commit()
            logger.info(f"✅ Cumpleaños notificado: {log.empleado_nombre}")

        except Exception as e:
            db.rollback()
            log.estado = "error"
            log.error_detalle = str(e)
            log.updated_by = usuario
            db.commit()
            logger.error(f"❌ Error notificando a {log.empleado_nombre}: {e}", exc_info=True)
