"""
Servicios para el módulo de Innovación.
"""

import math
import uuid
from datetime import date
from typing import Any, Dict, List, Optional

from sqlalchemy import String, case, desc, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.core.utils import utc_now
from backend.modules.innovacion.models import (
    CAMPOS_PROGRESO,
    TAG_ASISTENCIA_RESUMEN,
    TIPOS_CERTIFICACION,
    Certificacion,
    Evento,
    evento_asistencia,
)
from backend.modules.nomina.models import Empleado

_MESES = [
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
]


def _url_para_accion(valor: Optional[str]) -> Optional[str]:
    """Prepara una URL para un Action.OpenUrl de Adaptive Card.

    Webex valida cada botón y, si una URL es inválida, rechaza la card entera
    con HTTP 400 ("Invalid URL provided for Action.OpenUrl"): se pierde el aviso
    completo por un botón. El caso típico son los repos de casos de uso, cuya
    ruta lleva el nombre del equipo con espacios (".../AGD - BI/...").

    Devuelve None si no hay una URL usable, para poder omitir ese botón en lugar
    de perder la notificación.
    """
    from urllib.parse import quote

    url = (valor or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        return None
    # '%' va en safe para no volver a codificar lo que ya venga escapado.
    return quote(url, safe=":/?#[]@!$&'()*+,;=~%")


def limpiar_datos(datos: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitiza todos los campos string: trim, colapsar espacios, None si vacío."""
    limpio = {}
    for campo, valor in datos.items():
        if isinstance(valor, str):
            valor = valor.strip()
            valor = " ".join(valor.split())
            valor = valor if valor else None
        limpio[campo] = valor
    return limpio


class CertificacionService:
    """Servicio para operaciones de Certificaciones."""

    @staticmethod
    def crear(db: Session, empresa_id: uuid.UUID, datos: Dict[str, Any], usuario: str = None) -> Certificacion:
        datos = limpiar_datos(datos)
        if usuario:
            datos["updated_by"] = usuario

        # Validar tipo
        tipo = datos.get("tipo_certificacion")
        if tipo not in TIPOS_CERTIFICACION:
            raise ValueError(f"Tipo de certificación inválido: '{tipo}'")

        # Validar que no tenga una certificación activa
        if datos.get("empleado_id"):
            existente = (
                db.query(Certificacion)
                .filter(
                    Certificacion.empleado_id == uuid.UUID(datos["empleado_id"]),
                    Certificacion.empresa_id == empresa_id,
                    Certificacion.deleted_at.is_(None),
                )
                .first()
            )
            if existente:
                raise ValueError("Ya tenés una certificación en curso")

        try:
            cert = Certificacion(empresa_id=empresa_id, **datos)
            cert.calcular_progreso()
            db.add(cert)
            db.commit()
            db.refresh(cert)
            return cert
        except IntegrityError:
            db.rollback()
            raise ValueError("Error al crear la certificación")

    @staticmethod
    def obtener(db: Session, empresa_id: uuid.UUID, id: str) -> Optional[Certificacion]:
        return (
            db.query(Certificacion)
            .filter(
                Certificacion.id == uuid.UUID(id),
                Certificacion.empresa_id == empresa_id,
                Certificacion.deleted_at.is_(None),
            )
            .first()
        )

    @staticmethod
    def obtener_publico(db: Session, id: str) -> Optional[Certificacion]:
        """Obtiene una certificación por ID sin filtrar por empresa (uso público)."""
        return (
            db.query(Certificacion)
            .filter(Certificacion.id == uuid.UUID(id), Certificacion.deleted_at.is_(None))
            .first()
        )

    @staticmethod
    def obtener_por_empleado(db: Session, empresa_id: uuid.UUID, empleado_id: str) -> Optional[Certificacion]:
        """Obtiene la certificación activa de un empleado (si existe)."""
        return (
            db.query(Certificacion)
            .filter(
                Certificacion.empleado_id == uuid.UUID(empleado_id),
                Certificacion.empresa_id == empresa_id,
                Certificacion.deleted_at.is_(None),
            )
            .first()
        )

    @staticmethod
    def listar(db: Session, empresa_id: uuid.UUID, pagina: int = 1, por_pagina: int = 20, filtros: Dict = None) -> Dict:
        # Solo certificaciones de personal activo (no-activo queda fuera de todo el
        # módulo, consistente con obtener_resumen). Una persona inactiva como
        # empleado no es resultado, aunque su cuenta de usuario siga activa.
        query = (
            db.query(Certificacion)
            .join(Empleado, Empleado.id == Certificacion.empleado_id)
            .filter(
                Certificacion.deleted_at.is_(None),
                Certificacion.empresa_id == empresa_id,
                Empleado.deleted_at.is_(None),
                Empleado.activo == True,
            )
        )
        if filtros:
            if filtros.get("buscar"):
                buscar = f"%{filtros['buscar']}%"
                query = query.filter(
                    or_(
                        Certificacion.titulo.ilike(buscar),
                        Certificacion.descripcion.ilike(buscar),
                        Empleado.nombre.ilike(buscar),
                        Empleado.apellido.ilike(buscar),
                        Empleado.email_corporativo.ilike(buscar),
                        func.cast(Empleado.dni, String).ilike(buscar),
                    )
                )
            if filtros.get("estado"):
                # Soporta uno o varios estados separados por coma (ej: "en_progreso,en_revision")
                estados = [e for e in str(filtros["estado"]).split(",") if e]
                if len(estados) > 1:
                    query = query.filter(Certificacion.estado.in_(estados))
                elif estados:
                    query = query.filter(Certificacion.estado == estados[0])
            if filtros.get("tipo_certificacion"):
                query = query.filter(Certificacion.tipo_certificacion == filtros["tipo_certificacion"])
            if filtros.get("equipo_id"):
                from backend.modules.operaciones.models import Equipo, equipo_integrantes

                # Validar que el equipo pertenezca a la empresa activa
                equipo_empleados = (
                    db.query(equipo_integrantes.c.empleado_id)
                    .join(Equipo, Equipo.id == equipo_integrantes.c.equipo_id)
                    .filter(
                        equipo_integrantes.c.equipo_id == uuid.UUID(filtros["equipo_id"]),
                        Equipo.empresa_id == empresa_id,
                        Equipo.deleted_at.is_(None),
                    )
                )
                query = query.filter(Certificacion.empleado_id.in_(equipo_empleados))
            elif filtros.get("sin_equipo"):
                from backend.modules.operaciones.models import Equipo, equipo_integrantes

                # Solo empleados de equipos activos de esta empresa
                con_equipo = (
                    db.query(equipo_integrantes.c.empleado_id)
                    .join(Equipo, Equipo.id == equipo_integrantes.c.equipo_id)
                    .filter(Equipo.empresa_id == empresa_id, Equipo.deleted_at.is_(None))
                    .distinct()
                )
                query = query.filter(~Certificacion.empleado_id.in_(con_equipo))
        total = query.count()
        items = (
            query.order_by(Certificacion.created_at.desc()).offset((pagina - 1) * por_pagina).limit(por_pagina).all()
        )
        return {
            "items": items,
            "total": total,
            "pagina": pagina,
            "por_pagina": por_pagina,
            "total_paginas": math.ceil(total / por_pagina) or 1,
        }

    @staticmethod
    def actualizar(
        db: Session, empresa_id: uuid.UUID, id: str, datos: Dict[str, Any], usuario: str = None, finalizar: bool = False
    ) -> Optional[Certificacion]:
        datos = limpiar_datos(datos)
        # Flag del form de admin (default True). No es columna del modelo.
        enviar_notif = datos.pop("enviar_notificacion_webex", True)
        cert = (
            db.query(Certificacion)
            .filter(
                Certificacion.id == uuid.UUID(id),
                Certificacion.empresa_id == empresa_id,
                Certificacion.deleted_at.is_(None),
            )
            .first()
        )
        if not cert:
            return None
        estado_anterior = cert.estado
        # Estado explícito del admin (el form de admin siempre lo manda).
        estado_forzado = datos.pop("estado", None)
        for campo, valor in datos.items():
            if hasattr(cert, campo) and campo not in ("id", "empleado_id", "empresa_id", "tipo_certificacion"):
                setattr(cert, campo, valor)
        cert.updated_at = utc_now()
        if usuario:
            cert.updated_by = usuario
        cert.calcular_progreso()  # solo % + iniciado/en_progreso
        if estado_forzado:
            # Admin: controla el estado (incl. 'completada'). Al aprobar estampa
            # la fecha de aprobación si falta (hito "Approved").
            cert.estado = estado_forzado
            if estado_forzado == "completada" and not cert.fecha_aprobacion:
                cert.fecha_aprobacion = date.today()
        elif finalizar and cert.porcentaje_avance == "100":
            # Empleado: Finalizar manda a revisión y estampa el hito "Submitted".
            cert.estado = "en_revision"
            if not cert.fecha_en_presentacion:
                cert.fecha_en_presentacion = utc_now()
        db.commit()
        db.refresh(cert)
        # Aviso a Webex (#Innovación) SOLO cuando el admin aprueba (estado forzado
        # a 'completada' desde un estado previo distinto). Nunca desde my-path.
        # Se lanza en un hilo aparte para no bloquear la respuesta del guardado
        # (Gemini + Webex pueden tardar varios segundos).
        if enviar_notif and estado_forzado == "completada" and estado_anterior != "completada":
            CertificacionService._notificar_completada_async(cert.id)
        return cert

    @staticmethod
    def _notificar_completada_async(cert_id) -> None:
        """Dispara el aviso de certificación completada en un hilo daemon, con su
        propia sesión de DB, para no bloquear la respuesta del guardado.

        Fire-and-forget (F06-P02): no queda registro ni hay reintento. Si el aviso
        falla, solo queda el error en el log; si el backend se reinicia mientras
        corre (Gemini + Webex tardan unos segundos), se pierde. Es aceptable para
        un aviso de cortesía; si hiciera falta garantizarlo, el camino es la cola
        de envíos del motor de tareas (backend/modules/tareas/cola.py, F19)."""
        import threading

        def _run(cid):
            import logging

            from backend.database import SessionLocal

            _db = SessionLocal()
            try:
                cert = _db.query(Certificacion).filter(Certificacion.id == cid).first()
                if cert:
                    CertificacionService._notificar_completada(_db, cert)
            except Exception as e:  # noqa: BLE001
                logging.getLogger(__name__).error(
                    "Hilo de aviso de certificación completada falló (cert %s): %s", cid, e
                )
            finally:
                _db.close()

        threading.Thread(target=_run, args=(cert_id,), daemon=True, name="innovacion-cert-completada").start()

    @staticmethod
    def _notificar_completada(db: Session, cert: Certificacion) -> None:
        """Avisa al canal #Innovación de Webex cuando una certificación se completa.

        Defensivo: cualquier fallo se loguea y NO interrumpe la operación principal.
        El room se resuelve por el parámetro 'webex_room_innovacion_id' y cae al
        room por defecto de Webex si no está configurado.
        """
        import logging

        logger = logging.getLogger(__name__)
        try:
            from urllib.parse import quote

            from backend.core import config
            from backend.core.config import settings
            from backend.core.webex import describir_error, webex_service

            if not webex_service.is_configured:
                logger.info("Webex no configurado; se omite aviso de certificación completada (cert %s).", cert.id)
                return

            room_id = config.get_parameter("webex_room_innovacion_id", settings.webex_default_room_id, db=db)
            if not room_id:
                logger.warning("Sin room de Webex para Innovación; se omite aviso (cert %s).", cert.id)
                return

            empleado = getattr(cert, "empleado_rel", None)
            nombre = (getattr(empleado, "nombre", "") or "").strip()
            apellido = (getattr(empleado, "apellido", "") or "").strip()
            display_name = (
                f"{nombre} {apellido}".strip().title()
                or getattr(empleado, "empleado_nombre_completo", None)
                or "Un colaborador"
            )
            primer_nombre = nombre.split()[0].title() if nombre else display_name

            if cert.fecha_aprobacion:
                f = cert.fecha_aprobacion
                fecha_txt = f"{f.day} de {_MESES[f.month - 1].capitalize()} de {f.year}"
            else:
                fecha_txt = "—"

            base = (settings.frontend_url or "https://core.dicsys.ai").rstrip("/")
            cert_url = f"{base}/certificates/{cert.id}"
            # PNG (no SVG: Webex Adaptive Cards no renderiza SVG).
            banner_url = f"{base}/static/certificates/ai_professional.png"
            avatar_url = (
                "https://ui-avatars.com/api/?name="
                + quote(display_name)
                + "&background=3b82f6&color=fff&size=80&bold=true&format=png"
            )

            # Mensaje de felicitación generado por Gemini, con fallback fijo si el
            # LLM falla o está deshabilitado (no debe romper el aviso).
            mensaje = (
                f"🎉 {primer_nombre}, tu dedicación y esfuerzo dieron frutos. "
                "Sos parte del grupo de profesionales certificados en AI de Dicsys. "
                "¡A seguir creciendo! 💪"
            )
            try:
                from backend.core.llm import generate as llm_generate

                prompt = (
                    f"Escribí un mensaje breve (1 a 2 oraciones) felicitando a {primer_nombre}, "
                    "que acaba de completar la certificación AI Professional de DICSYS. "
                    "Tono cálido, motivador y profesional, en español rioplatense (voseo). "
                    "Incluí el nombre, 1 o 2 emojis y una frase de aliento al final. "
                    "No uses markdown, comillas ni saltos de línea. Devolvé solo el mensaje."
                )
                res = llm_generate(modulo="innovacion", contents=prompt, db=db)
                texto = (res.text or "").strip().strip('"').strip()
                if texto:
                    mensaje = texto
            except Exception as e:
                logger.info("LLM no disponible para el mensaje de felicitación; uso fallback (%s).", e)

            # El título solo se muestra en los tipos con entregable propio: caso de
            # uso (iniciativa) y challenge (finalista). En formación (training) no
            # aplica. Además es texto libre y opcional, así que puede venir vacío.
            tipo = cert.tipo_certificacion
            facts = [{"title": "📋 Certificación", "value": "AI Professional Certificate"}]
            titulo_txt = (cert.titulo or "").strip()
            label_titulo = {"iniciativa": "📝 Caso de Uso", "finalista": "📝 Challenge"}.get(tipo)
            if titulo_txt and label_titulo:
                facts.append({"title": label_titulo, "value": titulo_txt})
            facts += [
                {"title": "🏢 Organización", "value": "DICSYS S.A."},
                {"title": "📅 Fecha", "value": fecha_txt},
                {"title": "✅ Estado", "value": "Aprobado"},
            ]

            actions = [{"type": "Action.OpenUrl", "title": "🔗 Ver Certificado", "url": cert_url}]
            if tipo in ("iniciativa", "finalista") and cert.repo_presentacion:
                # finalista (challenge) -> presentación · iniciativa (caso de uso) -> descripción
                titulo = "📄 Ver Presentación" if tipo == "finalista" else "📄 Ver Descripción"
                repo_url = _url_para_accion(cert.repo_presentacion)
                if repo_url:
                    actions.append({"type": "Action.OpenUrl", "title": titulo, "url": repo_url})
                else:
                    logger.warning(
                        "repo_presentacion no es una URL usable (cert %s); "
                        "se omite el botón '%s' para no perder el aviso.",
                        cert.id,
                        titulo,
                    )
            elif tipo == "training":
                # Formación: link al perfil de certificación del empleado.
                actions.append(
                    {"type": "Action.OpenUrl", "title": "👤 Ver Perfil", "url": f"{base}/innovacion/profile/{cert.id}"}
                )

            card = {
                "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                "type": "AdaptiveCard",
                "version": "1.3",
                "body": [
                    {"type": "Image", "url": banner_url, "size": "Large", "horizontalAlignment": "Center"},
                    {
                        "type": "Container",
                        "style": "emphasis",
                        "items": [
                            {
                                "type": "TextBlock",
                                "text": "🏆 ¡Felicitaciones por tu Certificación!",
                                "weight": "Bolder",
                                "size": "ExtraLarge",
                                "color": "Accent",
                                "wrap": True,
                            },
                        ],
                    },
                    {
                        "type": "ColumnSet",
                        "columns": [
                            {
                                "type": "Column",
                                "width": "auto",
                                "items": [
                                    {"type": "Image", "url": avatar_url, "size": "Medium", "style": "Person"},
                                ],
                            },
                            {
                                "type": "Column",
                                "width": "stretch",
                                "verticalContentAlignment": "Center",
                                "items": [
                                    {"type": "TextBlock", "text": display_name, "weight": "Bolder", "size": "Large"},
                                    {
                                        "type": "TextBlock",
                                        "text": "Ha completado exitosamente el programa",
                                        "size": "Default",
                                        "isSubtle": True,
                                        "spacing": "None",
                                    },
                                ],
                            },
                        ],
                    },
                    {"type": "FactSet", "facts": facts},
                    {
                        "type": "Container",
                        "style": "accent",
                        "items": [
                            {"type": "TextBlock", "text": mensaje, "wrap": True, "size": "Default"},
                        ],
                    },
                ],
                "actions": actions,
            }
            resultado = (
                webex_service.send_card(
                    card,
                    fallback_text=f"🏆 Felicitaciones {display_name} por obtener la certificación AI Professional!",
                    room_id=room_id,
                )
                or {}
            )
            # send_card nunca lanza: ante un fallo devuelve success=False. Si no
            # se mira el resultado, el log da por enviado un aviso que se cayó.
            if resultado.get("success"):
                logger.info(
                    "Aviso de certificación completada enviado a Webex (cert %s, msg %s).",
                    cert.id,
                    resultado.get("message_id"),
                )
            else:
                logger.error(
                    "Webex rechazó el aviso de certificación completada (cert %s): HTTP %s - %s",
                    cert.id,
                    resultado.get("status_code") or "sin respuesta",
                    describir_error(resultado),
                )
        except Exception as e:
            logger.error("Falló el aviso Webex de certificación completada (cert %s): %s", getattr(cert, "id", "?"), e)

    @staticmethod
    def actualizar_sin_finalizar(
        db: Session, empresa_id: uuid.UUID, id: str, datos: Dict[str, Any], usuario: str = None
    ) -> Optional[Certificacion]:
        """Guardado de borrador del wizard: persiste los campos sin finalizar.

        Como `actualizar` solo manda a 'en_revision' cuando se le pasa
        `finalizar=True`, un borrador nunca pasa de 'en_progreso'.
        """
        return CertificacionService.actualizar(db, empresa_id, id, datos, usuario=usuario)

    @staticmethod
    def volver_a_edicion(db: Session, empresa_id: uuid.UUID, id: str, usuario: str = None) -> Optional[Certificacion]:
        """Devuelve una certificación 'en_revision' a estado editable ('en_progreso').

        Se fuerza el estado directamente (sin recalcular progreso) para que el
        empleado retome la edición hasta volver a presionar Finalizar.
        """
        cert = (
            db.query(Certificacion)
            .filter(
                Certificacion.id == uuid.UUID(id),
                Certificacion.empresa_id == empresa_id,
                Certificacion.deleted_at.is_(None),
            )
            .first()
        )
        if not cert:
            return None
        if cert.estado != "en_revision":
            raise ValueError("Solo se puede volver a edición desde el estado En Revisión")
        cert.estado = "en_progreso"
        cert.updated_at = utc_now()
        if usuario:
            cert.updated_by = usuario
        db.commit()
        db.refresh(cert)
        return cert

    @staticmethod
    def eliminar(db: Session, empresa_id: uuid.UUID, id: str) -> bool:
        cert = (
            db.query(Certificacion)
            .filter(
                Certificacion.id == uuid.UUID(id),
                Certificacion.empresa_id == empresa_id,
                Certificacion.deleted_at.is_(None),
            )
            .first()
        )
        if not cert:
            return False
        cert.deleted_at = utc_now()
        db.commit()
        return True

    @staticmethod
    def obtener_perfil_logros(db: Session, empresa_id: uuid.UUID, cert_id: str) -> Optional[Dict]:
        """Perfil de logros a partir de una CERTIFICACIÓN (compat: links del admin)."""
        cert = CertificacionService.obtener(db, empresa_id, cert_id)
        if not cert:
            return None
        emp = cert.empleado_rel
        if not emp:
            return None
        return CertificacionService._armar_perfil_logros(db, empresa_id, emp, cert)

    @staticmethod
    def obtener_perfil_logros_por_empleado(db: Session, empresa_id: uuid.UUID, empleado_id: str) -> Optional[Dict]:
        """Perfil de logros a partir de un EMPLEADO. Funciona aunque no tenga
        certificación (en ese caso `cert` queda vacío). Se usa para linkear el
        perfil desde el listado de asistentes a eventos."""
        try:
            emp_uuid = uuid.UUID(empleado_id)
        except ValueError, TypeError:
            return None
        emp = (
            db.query(Empleado)
            .filter(Empleado.id == emp_uuid, Empleado.empresa_id == empresa_id, Empleado.deleted_at.is_(None))
            .first()
        )
        if not emp:
            return None
        cert = CertificacionService.obtener_por_empleado(db, empresa_id, str(emp.id))
        return CertificacionService._armar_perfil_logros(db, empresa_id, emp, cert)

    @staticmethod
    def _armar_perfil_logros(db: Session, empresa_id: uuid.UUID, emp, cert) -> Dict:
        """Arma el payload del perfil (empleado + equipos + certificación + eventos).
        `cert` puede ser None: en ese caso `cert` y `campos_requeridos` van vacíos."""
        # Datos del empleado
        empleado_data = {
            "id": str(emp.id),
            "nombre": emp.nombre,
            "apellido": emp.apellido,
            "nombre_completo": emp.empleado_nombre_completo,
            "foto": emp.foto,
            "foto_thumbnail": emp.foto.replace("/fotos/nomina/", "/fotos/nomina/thumbnails/") if emp.foto else None,
            "email_corporativo": emp.email_corporativo,
            "departamento": emp.departamento_rel.nombre if emp.departamento_rel else None,
            "perfil": emp.perfil_rel.nombre if emp.perfil_rel else None,
            "seniority": emp.seniority,
            "puesto": emp.puesto,
            "fecha_alta": emp.fecha_alta.strftime("%d/%m/%Y") if emp.fecha_alta else None,
            "antiguedad": emp.antiguedad,
            "localidad": emp.dir_laboral_localidad,
            "provincia": emp.dir_laboral_provincia,
        }

        # Equipos del empleado
        equipos = []
        if hasattr(emp, "equipos_como_integrante"):
            for eq in emp.equipos_como_integrante:
                if eq.deleted_at is None and eq.activo:
                    equipos.append(
                        {
                            "id": str(eq.id),
                            "nombre": eq.nombre,
                            "es_lider": eq.lider_id == emp.id if eq.lider_id else False,
                        }
                    )

        # Certificación (puede no existir: el empleado puede no tener certificación)
        if cert:
            tipo_info = TIPOS_CERTIFICACION.get(cert.tipo_certificacion, {})
            cert_data = {
                "id": str(cert.id),
                "tipo_certificacion": cert.tipo_certificacion,
                "tipo_nombre": tipo_info.get("nombre", cert.tipo_certificacion),
                "tipo_icono": tipo_info.get("icono", "award"),
                "estado": cert.estado,
                "progreso_completados": cert.progreso_completados,
                "porcentaje_avance": cert.porcentaje_avance,
                "titulo": cert.titulo,
                "descripcion": cert.descripcion,
                "repo_presentacion": cert.repo_presentacion,
                "repo_demo": cert.repo_demo,
                "tematica": cert.tematica,
                "tecnologias": cert.tecnologias or [],
                "fecha_presentacion": cert.fecha_presentacion.isoformat() if cert.fecha_presentacion else None,
                "fecha_aprobacion": cert.fecha_aprobacion.isoformat() if cert.fecha_aprobacion else None,
                "fecha_registro": cert.fecha_registro.isoformat() if cert.fecha_registro else None,
                "fecha_en_progreso": cert.fecha_en_progreso.isoformat() if cert.fecha_en_progreso else None,
                "fecha_en_presentacion": cert.fecha_en_presentacion.isoformat() if cert.fecha_en_presentacion else None,
                # Training
                "cert_noncode_origen": cert.cert_noncode_origen,
                "cert_noncode_imagen": cert.cert_noncode_imagen,
                "cert_noncode_fecha": cert.cert_noncode_fecha.isoformat() if cert.cert_noncode_fecha else None,
                "cert_noncode_plan": cert.cert_noncode_plan,
                "cert_n8n_origen": cert.cert_n8n_origen,
                "cert_n8n_imagen": cert.cert_n8n_imagen,
                "cert_n8n_fecha": cert.cert_n8n_fecha.isoformat() if cert.cert_n8n_fecha else None,
                "cert_n8n_plan": cert.cert_n8n_plan,
                "cert_ruta1_imagen": cert.cert_ruta1_imagen,
                "cert_ruta1_fecha": cert.cert_ruta1_fecha.isoformat() if cert.cert_ruta1_fecha else None,
                "cert_ruta2_imagen": cert.cert_ruta2_imagen,
                "cert_ruta2_fecha": cert.cert_ruta2_fecha.isoformat() if cert.cert_ruta2_fecha else None,
                "cert_ruta3_imagen": cert.cert_ruta3_imagen,
                "cert_ruta3_fecha": cert.cert_ruta3_fecha.isoformat() if cert.cert_ruta3_fecha else None,
                "empleado_nombre": emp.empleado_nombre_completo,
            }
            # Campos requeridos para el checklist de progreso (sin fecha_aprobacion, es solo admin)
            campos_req = [c for c in CAMPOS_PROGRESO.get(cert.tipo_certificacion, []) if c != "fecha_aprobacion"]
            if cert.tipo_certificacion == "training":
                if getattr(cert, "cert_noncode_origen", None) == "externa":
                    campos_req.append("cert_noncode_plan")
                if getattr(cert, "cert_n8n_origen", None) == "externa":
                    campos_req.append("cert_n8n_plan")
        else:
            cert_data = {}
            campos_req = []

        # Eventos del empleado (medallas: nombre + fecha + tags como caption)
        eventos_raw = EventoService.obtener_eventos_empleado(db, empresa_id, str(emp.id))
        eventos = [
            {
                "id": str(e.id),
                "nombre": e.nombre,
                "fecha": e.fecha.isoformat() if e.fecha else None,
                "fecha_display": e.fecha.strftime("%d/%m/%Y") if e.fecha else None,
                "tags": e.tags or [],
            }
            for e in eventos_raw
        ]

        return {
            "empleado": empleado_data,
            "equipos": equipos,
            "cert": cert_data,
            "campos_requeridos": campos_req,
            "eventos": eventos,
        }

    @staticmethod
    def obtener_resumen(db: Session, empresa_id: uuid.UUID) -> Dict:
        """Obtiene métricas para el dashboard de resumen."""

        # Solo certificaciones de personal activo (no-activo queda fuera de todo el módulo)
        base = (
            db.query(Certificacion)
            .join(Empleado, Empleado.id == Certificacion.empleado_id)
            .filter(
                Certificacion.deleted_at.is_(None),
                Certificacion.empresa_id == empresa_id,
                Empleado.deleted_at.is_(None),
                Empleado.activo == True,
            )
        )
        total_certificaciones = base.count()
        # "En Progreso" agrupa en_progreso + en_revision (no hay card propia de En Revisión)
        en_progreso = base.filter(Certificacion.estado.in_(["en_progreso", "en_revision"])).count()
        completadas = base.filter(Certificacion.estado == "completada").count()

        # Total de personal activo
        total_personal = (
            db.query(Empleado)
            .filter(Empleado.deleted_at.is_(None), Empleado.activo == True, Empleado.empresa_id == empresa_id)
            .count()
        )

        # Por tipo con participantes y aprobados
        por_tipo_raw = (
            db.query(
                Certificacion.tipo_certificacion,
                func.count(Certificacion.id),
                func.sum(case((Certificacion.estado == "completada", 1), else_=0)),
            )
            .join(Empleado, Empleado.id == Certificacion.empleado_id)
            .filter(
                Certificacion.deleted_at.is_(None),
                Certificacion.empresa_id == empresa_id,
                Empleado.deleted_at.is_(None),
                Empleado.activo == True,
            )
            .group_by(Certificacion.tipo_certificacion)
            .all()
        )

        por_tipo = []
        for tipo_key, cantidad, aprobados in por_tipo_raw:
            info = TIPOS_CERTIFICACION.get(tipo_key, {})
            aprobados_int = int(aprobados or 0)
            pct = round((aprobados_int / total_personal * 100), 1) if total_personal else 0
            por_tipo.append(
                {
                    "codigo": tipo_key,
                    "nombre": info.get("nombre", tipo_key),
                    "icono": info.get("icono", "award"),
                    "participantes": cantidad,
                    "aprobados": aprobados_int,
                    "porcentaje": pct,
                }
            )

        # Por equipo (operaciones): métricas + integrantes para avatares
        from backend.modules.operaciones.models import Equipo, equipo_integrantes

        # Traer equipos activos con sus integrantes
        equipos = (
            db.query(Equipo)
            .filter(Equipo.deleted_at.is_(None), Equipo.activo == True, Equipo.empresa_id == empresa_id)
            .order_by(Equipo.nombre)
            .all()
        )

        por_equipo = []
        for eq in equipos:
            # Integrantes activos del equipo
            integrantes = [e for e in eq.integrantes if e.deleted_at is None and e.activo]
            total_emp = len(integrantes)
            ids_integrantes = [e.id for e in integrantes]

            # Contar certificaciones de los integrantes (filtrado por empresa)
            if ids_integrantes:
                participantes = (
                    db.query(func.count(func.distinct(Certificacion.empleado_id)))
                    .filter(
                        Certificacion.empleado_id.in_(ids_integrantes),
                        Certificacion.empresa_id == empresa_id,
                        Certificacion.deleted_at.is_(None),
                    )
                    .scalar()
                    or 0
                )
                aprobados = (
                    db.query(func.count(func.distinct(Certificacion.empleado_id)))
                    .filter(
                        Certificacion.empleado_id.in_(ids_integrantes),
                        Certificacion.empresa_id == empresa_id,
                        Certificacion.deleted_at.is_(None),
                        Certificacion.estado == "completada",
                    )
                    .scalar()
                    or 0
                )
            else:
                participantes = 0
                aprobados = 0

            pct = round((aprobados / total_emp * 100), 1) if total_emp else 0

            # Preview de integrantes (primeros 5 para avatares)
            miembros_preview = []
            for e in integrantes[:5]:
                miembros_preview.append(
                    {
                        "nombre": e.nombre or "",
                        "apellido": e.apellido or "",
                        "foto": e.foto,
                    }
                )

            por_equipo.append(
                {
                    "id": str(eq.id),
                    "nombre": eq.nombre,
                    "total_empleados": total_emp,
                    "participantes": participantes,
                    "aprobados": aprobados,
                    "porcentaje": pct,
                    "miembros_preview": miembros_preview,
                    "total_miembros": total_emp,
                }
            )

        # Empleados sin equipo (solo de equipos activos de esta empresa)
        empleados_con_equipo = (
            db.query(equipo_integrantes.c.empleado_id)
            .join(Equipo, Equipo.id == equipo_integrantes.c.equipo_id)
            .filter(Equipo.empresa_id == empresa_id, Equipo.deleted_at.is_(None))
            .distinct()
        )
        sin_equipo = (
            db.query(Empleado)
            .filter(
                Empleado.deleted_at.is_(None),
                Empleado.activo == True,
                Empleado.empresa_id == empresa_id,
                ~Empleado.id.in_(empleados_con_equipo),
            )
            .all()
        )
        if sin_equipo:
            ids_sin = [e.id for e in sin_equipo]
            part_sin = (
                db.query(func.count(func.distinct(Certificacion.empleado_id)))
                .filter(
                    Certificacion.empleado_id.in_(ids_sin),
                    Certificacion.empresa_id == empresa_id,
                    Certificacion.deleted_at.is_(None),
                )
                .scalar()
                or 0
            )
            aprob_sin = (
                db.query(func.count(func.distinct(Certificacion.empleado_id)))
                .filter(
                    Certificacion.empleado_id.in_(ids_sin),
                    Certificacion.empresa_id == empresa_id,
                    Certificacion.deleted_at.is_(None),
                    Certificacion.estado == "completada",
                )
                .scalar()
                or 0
            )
            pct_sin = round((aprob_sin / len(sin_equipo) * 100), 1) if sin_equipo else 0
            por_equipo.append(
                {
                    "id": None,
                    "nombre": "Sin Equipo",
                    "total_empleados": len(sin_equipo),
                    "participantes": part_sin,
                    "aprobados": aprob_sin,
                    "porcentaje": pct_sin,
                    "miembros_preview": [],
                    "total_miembros": len(sin_equipo),
                }
            )

        # Ordenar equipos por porcentaje descendente
        por_equipo.sort(key=lambda x: x["porcentaje"], reverse=True)

        # Métrica de participación en eventos: se excluye a las personas de
        # equipos cuyo nombre contiene "dicsys" (no cuentan ni en el numerador
        # ni en el denominador). Solo afecta esta métrica.
        dicsys_emp_ids = (
            db.query(equipo_integrantes.c.empleado_id)
            .join(Equipo, Equipo.id == equipo_integrantes.c.equipo_id)
            .filter(Equipo.empresa_id == empresa_id, Equipo.deleted_at.is_(None), Equipo.nombre.ilike("%dicsys%"))
            .distinct()
        )

        # Denominador: personal activo elegible (excluye equipos Dicsys).
        total_personal_eventos = (
            db.query(Empleado)
            .filter(
                Empleado.deleted_at.is_(None),
                Empleado.activo == True,
                Empleado.empresa_id == empresa_id,
                ~Empleado.id.in_(dicsys_emp_ids),
            )
            .count()
        )

        # Numerador: asistentes únicos a eventos con tag Track#1, personal activo
        # elegible (excluye equipos Dicsys), coherente con total_personal_eventos.
        total_asistentes_eventos = (
            db.query(func.count(func.distinct(evento_asistencia.c.empleado_id)))
            .join(Evento, Evento.id == evento_asistencia.c.evento_id)
            .join(Empleado, Empleado.id == evento_asistencia.c.empleado_id)
            .filter(
                Evento.empresa_id == empresa_id,
                Evento.deleted_at.is_(None),
                Evento.tags.any(TAG_ASISTENCIA_RESUMEN),
                Empleado.deleted_at.is_(None),
                Empleado.activo == True,
                ~evento_asistencia.c.empleado_id.in_(dicsys_emp_ids),
            )
            .scalar()
            or 0
        )

        return {
            "total": total_personal,
            "total_certificaciones": total_certificaciones,
            "en_progreso": en_progreso,
            "completadas": completadas,
            "total_asistentes_eventos": total_asistentes_eventos,
            "total_personal_eventos": total_personal_eventos,
            "por_path": por_tipo,
            "por_equipo": por_equipo,
        }


class EventoService:
    """Servicio para operaciones de Eventos de Innovación."""

    @staticmethod
    def tags_disponibles(db: Session, empresa_id: uuid.UUID) -> List[str]:
        """Lista ordenada de tags únicos usados en los eventos de la empresa."""
        rows = (
            db.query(Evento.tags)
            .filter(
                Evento.empresa_id == empresa_id,
                Evento.deleted_at.is_(None),
            )
            .all()
        )
        tags = set()
        for (arr,) in rows:
            if arr:
                tags.update(t for t in arr if t)
        return sorted(tags, key=lambda s: s.lower())

    @staticmethod
    def ranking_asistentes(
        db: Session,
        empresa_id: uuid.UUID,
        pagina: int = 1,
        por_pagina: int = 50,
        buscar: str = None,
        equipo_id: str = None,
        sin_participacion: bool = False,
        evento_id: str = None,
        tag: str = None,
    ) -> Dict:
        """Lista asistentes ordenados por mayor participación en eventos."""
        from backend.modules.operaciones.models import Equipo, equipo_integrantes

        asistencias_query = (
            db.query(
                evento_asistencia.c.empleado_id.label("empleado_id"),
                func.count(evento_asistencia.c.evento_id).label("cantidad_eventos"),
            )
            .join(Evento, Evento.id == evento_asistencia.c.evento_id)
            .filter(Evento.empresa_id == empresa_id, Evento.deleted_at.is_(None))
        )
        if tag:
            asistencias_query = asistencias_query.filter(Evento.tags.any(tag))
        asistencias = asistencias_query.group_by(evento_asistencia.c.empleado_id).subquery()

        cantidad_eventos = func.coalesce(asistencias.c.cantidad_eventos, 0)

        query = (
            db.query(Empleado, cantidad_eventos.label("cantidad_eventos"))
            .outerjoin(asistencias, asistencias.c.empleado_id == Empleado.id)
            .filter(Empleado.empresa_id == empresa_id, Empleado.deleted_at.is_(None), Empleado.activo == True)
        )

        if equipo_id == "__sin_equipo__":
            empleados_con_equipo = (
                db.query(equipo_integrantes.c.empleado_id)
                .join(Equipo, Equipo.id == equipo_integrantes.c.equipo_id)
                .filter(Equipo.empresa_id == empresa_id, Equipo.deleted_at.is_(None), Equipo.activo == True)
            )
            query = query.filter(Empleado.id.notin_(empleados_con_equipo))
        elif equipo_id:
            query = (
                query.join(equipo_integrantes, equipo_integrantes.c.empleado_id == Empleado.id)
                .join(Equipo, Equipo.id == equipo_integrantes.c.equipo_id)
                .filter(
                    equipo_integrantes.c.equipo_id == uuid.UUID(equipo_id),
                    Equipo.empresa_id == empresa_id,
                    Equipo.deleted_at.is_(None),
                    Equipo.activo == True,
                )
            )

        if buscar:
            buscar_like = f"%{buscar}%"
            query = query.filter(
                or_(
                    Empleado.nombre.ilike(buscar_like),
                    Empleado.apellido.ilike(buscar_like),
                    Empleado.email_corporativo.ilike(buscar_like),
                    func.cast(Empleado.dni, String).ilike(buscar_like),
                )
            )

        if sin_participacion:
            query = query.filter(cantidad_eventos == 0)
        else:
            query = query.filter(cantidad_eventos > 0)

        if evento_id and not sin_participacion:
            evento_uuid = uuid.UUID(evento_id)
            asistentes_evento = (
                db.query(evento_asistencia.c.empleado_id)
                .join(Evento, Evento.id == evento_asistencia.c.evento_id)
                .filter(
                    evento_asistencia.c.evento_id == evento_uuid,
                    Evento.empresa_id == empresa_id,
                    Evento.deleted_at.is_(None),
                )
            )
            query = query.filter(Empleado.id.in_(asistentes_evento))

        total = query.count()
        rows = (
            query.order_by(desc(cantidad_eventos), Empleado.apellido, Empleado.nombre)
            .offset((pagina - 1) * por_pagina)
            .limit(por_pagina)
            .all()
        )

        items = []
        for empleado, cantidad_eventos in rows:
            eventos_query = (
                db.query(Evento)
                .join(evento_asistencia, Evento.id == evento_asistencia.c.evento_id)
                .filter(
                    evento_asistencia.c.empleado_id == empleado.id,
                    Evento.empresa_id == empresa_id,
                    Evento.deleted_at.is_(None),
                )
            )
            if tag:
                eventos_query = eventos_query.filter(Evento.tags.any(tag))
            eventos = eventos_query.order_by(Evento.fecha.desc(), Evento.nombre).all()

            foto = empleado.foto
            if foto:
                foto = foto.replace("/fotos/nomina/", "/fotos/nomina/thumbnails/")

            equipos = []
            if hasattr(empleado, "equipos_como_integrante"):
                equipos = [
                    {"id": str(eq.id), "nombre": eq.nombre}
                    for eq in empleado.equipos_como_integrante
                    if eq.empresa_id == empresa_id and eq.deleted_at is None and eq.activo
                ]

            items.append(
                {
                    "id": str(empleado.id),
                    "nombre": empleado.nombre,
                    "apellido": empleado.apellido,
                    "display": empleado.empleado_nombre_completo,
                    "dni": empleado.dni,
                    "email_corporativo": empleado.email_corporativo,
                    "foto": foto,
                    "departamento": empleado.departamento_rel.nombre if empleado.departamento_rel else None,
                    "puesto": empleado.puesto,
                    "perfil": empleado.perfil_rel.nombre if empleado.perfil_rel else None,
                    "cantidad_eventos": int(cantidad_eventos or 0),
                    "equipos": equipos,
                    "eventos": [
                        {
                            "id": str(evento.id),
                            "nombre": evento.nombre,
                            "fecha": evento.fecha.isoformat(),
                        }
                        for evento in eventos
                    ],
                }
            )

        return {
            "items": items,
            "total": total,
            "pagina": pagina,
            "por_pagina": por_pagina,
            "total_paginas": math.ceil(total / por_pagina) or 1,
        }

    @staticmethod
    def resumen_asistentes_por_equipo(
        db: Session,
        empresa_id: uuid.UUID,
        equipo_id: str = None,
        evento_id: str = None,
        tag: str = None,
        buscar: str = None,
    ) -> Dict:
        """Agrupa participación en eventos por equipo.

        Si se indica ``buscar``, solo se devuelven los equipos que contienen a la
        persona buscada (por nombre, apellido, email corporativo o DNI), y la
        lista de integrantes de esos equipos se limita a las coincidencias.
        """
        from backend.modules.operaciones.models import Equipo, equipo_integrantes

        termino_buscar = (buscar or "").strip().lower()

        def _coincide(empleado) -> bool:
            if not termino_buscar:
                return True
            campos = [
                empleado.nombre or "",
                empleado.apellido or "",
                empleado.empleado_nombre_completo or "",
                empleado.email_corporativo or "",
                str(empleado.dni or ""),
            ]
            return any(termino_buscar in c.lower() for c in campos)

        equipos_query = db.query(Equipo).filter(
            Equipo.empresa_id == empresa_id, Equipo.deleted_at.is_(None), Equipo.activo == True
        )
        if equipo_id and equipo_id != "__sin_equipo__":
            equipos_query = equipos_query.filter(Equipo.id == uuid.UUID(equipo_id))
        equipos = [] if equipo_id == "__sin_equipo__" else equipos_query.order_by(Equipo.nombre).all()

        evento_filters = [Evento.empresa_id == empresa_id, Evento.deleted_at.is_(None)]
        if evento_id:
            evento_filters.append(Evento.id == uuid.UUID(evento_id))
        if tag:
            evento_filters.append(Evento.tags.any(tag))

        grupos = []
        resumen = {
            "total_equipos": 0,
            "total_miembros": 0,
            "total_asistentes": 0,
            "total_sin_participacion": 0,
            "total_participaciones": 0,
        }

        def agregar_grupo(grupo_id: str, nombre: str, integrantes: list):
            integrante_ids = [e.id for e in integrantes]

            conteos = {}
            if integrante_ids:
                rows = (
                    db.query(evento_asistencia.c.empleado_id, func.count(evento_asistencia.c.evento_id))
                    .join(Evento, Evento.id == evento_asistencia.c.evento_id)
                    .filter(evento_asistencia.c.empleado_id.in_(integrante_ids), *evento_filters)
                    .group_by(evento_asistencia.c.empleado_id)
                    .all()
                )
                conteos = {empleado_id: int(cantidad or 0) for empleado_id, cantidad in rows}

            total_miembros = len(integrantes)
            asistentes = len([cantidad for cantidad in conteos.values() if cantidad > 0])
            participaciones = sum(conteos.values())
            sin_participacion = total_miembros - asistentes
            porcentaje = round((asistentes / total_miembros) * 100, 1) if total_miembros else 0

            # Si hay búsqueda, el equipo solo se incluye cuando contiene a la
            # persona buscada, y se listan únicamente las coincidencias.
            visibles = [e for e in integrantes if _coincide(e)]
            if termino_buscar and not visibles:
                return

            # Integrantes a listar, ordenados por mayor participación
            # (los de 0 eventos quedan al final). Sin recorte: la UI maneja el scroll.
            integrantes_a_listar = visibles if termino_buscar else integrantes
            integrantes_detalle = []
            for empleado in sorted(
                integrantes_a_listar, key=lambda e: (-conteos.get(e.id, 0), e.apellido or "", e.nombre or "")
            ):
                cantidad = conteos.get(empleado.id, 0)
                integrantes_detalle.append(
                    {
                        "id": str(empleado.id),
                        "display": empleado.empleado_nombre_completo,
                        "cantidad_eventos": cantidad,
                        "foto": empleado.foto.replace("/fotos/nomina/", "/fotos/nomina/thumbnails/")
                        if empleado.foto
                        else None,
                    }
                )

            grupos.append(
                {
                    "id": grupo_id,
                    "nombre": nombre,
                    "total_miembros": total_miembros,
                    "asistentes": asistentes,
                    "sin_participacion": sin_participacion,
                    "participaciones": participaciones,
                    "porcentaje": porcentaje,
                    "integrantes": integrantes_detalle,
                }
            )

            resumen["total_equipos"] += 1
            resumen["total_miembros"] += total_miembros
            resumen["total_asistentes"] += asistentes
            resumen["total_sin_participacion"] += sin_participacion
            resumen["total_participaciones"] += participaciones

        for equipo in equipos:
            integrantes = [
                e for e in equipo.integrantes if e.deleted_at is None and e.activo and e.empresa_id == empresa_id
            ]
            agregar_grupo(str(equipo.id), equipo.nombre, integrantes)

        if not equipo_id or equipo_id == "__sin_equipo__":
            empleados_con_equipo = (
                db.query(equipo_integrantes.c.empleado_id)
                .join(Equipo, Equipo.id == equipo_integrantes.c.equipo_id)
                .filter(Equipo.empresa_id == empresa_id, Equipo.deleted_at.is_(None), Equipo.activo == True)
            )
            integrantes_sin_equipo = (
                db.query(Empleado)
                .filter(
                    Empleado.empresa_id == empresa_id,
                    Empleado.deleted_at.is_(None),
                    Empleado.activo == True,
                    Empleado.id.notin_(empleados_con_equipo),
                )
                .order_by(Empleado.apellido, Empleado.nombre)
                .all()
            )
            if integrantes_sin_equipo:
                agregar_grupo("__sin_equipo__", "Sin Equipo", integrantes_sin_equipo)

        grupos.sort(key=lambda x: (x["porcentaje"], x["participaciones"]), reverse=True)
        resumen["porcentaje_participacion"] = (
            round((resumen["total_asistentes"] / resumen["total_miembros"]) * 100, 1)
            if resumen["total_miembros"]
            else 0
        )

        return {
            "resumen": resumen,
            "grupos": grupos,
        }

    @staticmethod
    def crear(db: Session, empresa_id: uuid.UUID, datos: Dict[str, Any], usuario: str = None) -> Evento:
        datos = limpiar_datos(datos)
        if usuario:
            datos["updated_by"] = usuario

        # Validar unicidad nombre + fecha
        existente = (
            db.query(Evento)
            .filter(
                Evento.nombre == datos.get("nombre"),
                Evento.fecha == datos.get("fecha"),
                Evento.empresa_id == empresa_id,
                Evento.deleted_at.is_(None),
            )
            .first()
        )
        if existente:
            raise ValueError(f"Ya existe un evento '{datos.get('nombre')}' en esa fecha")

        try:
            evento = Evento(empresa_id=empresa_id, **datos)
            db.add(evento)
            db.commit()
            db.refresh(evento)
            return evento
        except IntegrityError:
            db.rollback()
            raise ValueError("Error al crear el evento")

    @staticmethod
    def obtener(db: Session, empresa_id: uuid.UUID, id: str) -> Optional[Evento]:
        return (
            db.query(Evento)
            .filter(Evento.id == uuid.UUID(id), Evento.empresa_id == empresa_id, Evento.deleted_at.is_(None))
            .first()
        )

    @staticmethod
    def listar(db: Session, empresa_id: uuid.UUID, pagina: int = 1, por_pagina: int = 20, filtros: Dict = None) -> Dict:
        query = db.query(Evento).filter(Evento.deleted_at.is_(None), Evento.empresa_id == empresa_id)
        if filtros and filtros.get("buscar"):
            buscar = f"%{filtros['buscar']}%"
            query = query.filter(Evento.nombre.ilike(buscar))
        total = query.count()
        items = query.order_by(Evento.fecha.desc()).offset((pagina - 1) * por_pagina).limit(por_pagina).all()
        return {
            "items": items,
            "total": total,
            "pagina": pagina,
            "por_pagina": por_pagina,
            "total_paginas": math.ceil(total / por_pagina) or 1,
        }

    @staticmethod
    def actualizar(
        db: Session, empresa_id: uuid.UUID, id: str, datos: Dict[str, Any], usuario: str = None
    ) -> Optional[Evento]:
        datos = limpiar_datos(datos)
        evento = (
            db.query(Evento)
            .filter(Evento.id == uuid.UUID(id), Evento.empresa_id == empresa_id, Evento.deleted_at.is_(None))
            .first()
        )
        if not evento:
            return None
        for campo, valor in datos.items():
            if hasattr(evento, campo) and campo not in ("id", "empresa_id"):
                setattr(evento, campo, valor)
        evento.updated_at = utc_now()
        if usuario:
            evento.updated_by = usuario
        db.commit()
        db.refresh(evento)
        return evento

    @staticmethod
    def eliminar(db: Session, empresa_id: uuid.UUID, id: str) -> bool:
        evento = (
            db.query(Evento)
            .filter(Evento.id == uuid.UUID(id), Evento.empresa_id == empresa_id, Evento.deleted_at.is_(None))
            .first()
        )
        if not evento:
            return False
        evento.deleted_at = utc_now()
        db.commit()
        return True

    @staticmethod
    def asignar_asistentes(db: Session, empresa_id: uuid.UUID, evento_id: str, empleado_ids: list) -> Evento:
        """Asigna una lista de empleados como asistentes al evento (reemplaza los existentes)."""
        evento = (
            db.query(Evento)
            .filter(Evento.id == uuid.UUID(evento_id), Evento.empresa_id == empresa_id, Evento.deleted_at.is_(None))
            .first()
        )
        if not evento:
            raise ValueError("Evento no encontrado")

        # Obtener empleados válidos filtrando por empresa (solo activos)
        empleados = (
            db.query(Empleado)
            .filter(
                Empleado.id.in_([uuid.UUID(eid) for eid in empleado_ids]),
                Empleado.empresa_id == empresa_id,
                Empleado.deleted_at.is_(None),
                Empleado.activo == True,
            )
            .all()
        )
        if not empleados:
            raise ValueError("No se encontraron empleados válidos")

        evento.asistentes = empleados
        db.commit()
        db.refresh(evento)
        return evento

    @staticmethod
    def obtener_eventos_empleado(db: Session, empresa_id: uuid.UUID, empleado_id: str) -> list:
        """Obtiene todos los eventos a los que asistió un empleado, filtrado por empresa."""
        return (
            db.query(Evento)
            .join(evento_asistencia, Evento.id == evento_asistencia.c.evento_id)
            .filter(
                evento_asistencia.c.empleado_id == uuid.UUID(empleado_id),
                Evento.empresa_id == empresa_id,
                Evento.deleted_at.is_(None),
            )
            .order_by(Evento.fecha.desc())
            .all()
        )

    @staticmethod
    def listar_empleados(db: Session, empresa_id: uuid.UUID, buscar: str = None) -> list:
        """Lista empleados activos para el selector de asistentes."""
        query = db.query(Empleado).filter(
            Empleado.deleted_at.is_(None), Empleado.activo == True, Empleado.empresa_id == empresa_id
        )
        if buscar:
            buscar_like = f"%{buscar}%"
            from sqlalchemy import or_

            query = query.filter(
                or_(
                    Empleado.nombre.ilike(buscar_like),
                    Empleado.apellido.ilike(buscar_like),
                    Empleado.email_corporativo.ilike(buscar_like),
                )
            )
        return query.order_by(Empleado.apellido, Empleado.nombre).limit(200).all()
