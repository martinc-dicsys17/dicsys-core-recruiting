"""
Seguimiento y avisos de la evaluación de proveedores (D-63, D-66, D-77).

- Seguimiento: avance por evaluador, sus pendientes y la vista previa del aviso.
- Envío manual: el admin elige a quién avisar; sale por los canales activos.
- Prueba de canales: el aviso de un evaluador, marcado [Prueba], por los canales
  como están en pantalla. No cuenta como aviso (queda solo en la auditoría).

Por email el aviso va en HTML con la marca de Dicsys Core; por Webex (personal
y canal), como Adaptive Card (D-95, D-96).
- Job diario: el motor de tareas (F19) lo corre cada minuto y, pasada la hora
  configurada (hora Argentina), encola los avisos que correspondan ese día
  (apertura, día anterior al cierre, recordatorio cada 1 o 2 días). La cola los
  despacha con reintentos. Con todos los checks apagados no manda nada.

Los mensajes se arman en el servidor con los pendientes del momento: nunca se
avisa a quien está al día. Los mails van solo al email corporativo
(@dicsys.com o @dicsys.ai). Cada envío queda en proveedores_avisos; el job no
repite el mismo aviso en el día.
"""

import logging
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from backend.core import email_layout as correo
from backend.core.config import settings
from backend.modules.administracion.evaluacion_proveedores_services import (
    ConfiguracionService,
    EvaluacionService,
    nombre_empleado,
)
from backend.modules.administracion.proveedores_auditoria import SISTEMA, Actor, registrar
from backend.modules.administracion.proveedores_comun import (
    ahora_argentina,
    estado_evaluacion,
    evaluacion_vigente,
    hoy_argentina,
)
from backend.modules.administracion.proveedores_models import (
    EvaluacionProveedores,
    ProveedoresAviso,
    ProveedoresConfiguracion,
)
from backend.modules.nomina.models import Empleado
from backend.modules.tareas import cola

logger = logging.getLogger(__name__)

RUTA_TABLERO = "/administracion/evaluaciones-proveedores"
ORIGEN = "avisos_evaluacion_proveedores"  # en la cola de envíos
EN_COLA = "En cola: lo despacha el motor de tareas"


def _dominios_corporativos() -> List[str]:
    return [d.strip().lower() for d in (settings.webex_sync_allowed_domains or "").split(",") if d.strip()]


def es_corporativo(email: Optional[str]) -> bool:
    return bool(email) and email.rsplit("@", 1)[-1].lower() in _dominios_corporativos()


def _canales(configuracion: Optional[ProveedoresConfiguracion]) -> List[str]:
    if configuracion is None:
        return []
    canales = []
    if configuracion.canal_email:
        canales.append("email")
    if configuracion.canal_webex_personal:
        canales.append("webex_personal")
    if configuracion.canal_webex_canal and configuracion.webex_room_id:
        canales.append("webex_canal")
    return canales


# ─── Seguimiento ────────────────────────────────────────────────────────────────


def mensaje(evaluacion: EvaluacionProveedores, empleado: Empleado, pendientes: List[str]) -> Dict[str, str]:
    """Asunto y cuerpo (texto) del aviso a un evaluador."""
    plural = "s" if len(pendientes) != 1 else ""
    lista = "\n".join(f"  - {p}" for p in pendientes)
    return {
        "asunto": f"Evaluación de proveedores {evaluacion.periodo}: {len(pendientes)} pendiente{plural}",
        "cuerpo": (
            f"Hola {empleado.nombre},\n\n"
            f"Tenés pendiente la evaluación de estos proveedores y herramientas "
            f"(cierra el {evaluacion.fecha_cierre:%d/%m/%Y}):\n\n{lista}\n\n"
            f"Completala en Dicsys Core → Administración → Proveedores → Evaluación de Proveedores:\n"
            f"{settings.frontend_url.rstrip('/')}{RUTA_TABLERO}\n\nGracias."
        ),
    }


def _por_evaluador(db: Session, evaluacion: EvaluacionProveedores) -> Dict[uuid.UUID, Dict[str, Any]]:
    grupos: Dict[uuid.UUID, Dict[str, Any]] = {}
    for item in EvaluacionService.items(db, evaluacion.id):
        if item.evaluador is None:
            continue
        grupo = grupos.setdefault(item.evaluador.id, {"empleado": item.evaluador, "total": 0, "pendientes": []})
        grupo["total"] += 1
        if item.evaluado_at is None:
            grupo["pendientes"].append(item.proveedor.nombre)
    for grupo in grupos.values():
        grupo["pendientes"].sort(key=str.lower)
    return grupos


def seguimiento(db: Session, empresa_id: uuid.UUID) -> Dict[str, Any]:
    evaluacion = evaluacion_vigente(db, empresa_id)
    configuracion = ConfiguracionService.obtener(db, empresa_id)
    if evaluacion is None:
        return {"evaluacion": None, "evaluadores": [], "sin_evaluador": [], "canales": _canales(configuracion)}
    filas = []
    for grupo in sorted(_por_evaluador(db, evaluacion).values(), key=lambda g: nombre_empleado(g["empleado"]).lower()):
        empleado = grupo["empleado"]
        filas.append(
            {
                "evaluador": {"id": str(empleado.id), "nombre": nombre_empleado(empleado)},
                "email": empleado.email_corporativo,
                "total": grupo["total"],
                "evaluados": grupo["total"] - len(grupo["pendientes"]),
                "pendientes": grupo["pendientes"],
                "mensaje": mensaje(evaluacion, empleado, grupo["pendientes"]) if grupo["pendientes"] else None,
            }
        )
    sin_evaluador = sorted(
        (i.proveedor.nombre for i in EvaluacionService.items(db, evaluacion.id) if i.evaluador_empleado_id is None),
        key=str.lower,
    )
    return {
        "evaluacion": EvaluacionService.resumen(db, evaluacion),
        "evaluadores": filas,
        "sin_evaluador": sin_evaluador,
        "canales": _canales(configuracion),
    }


# ─── Tarjetas de Webex (Adaptive Cards, D-95) ───────────────────────────────────


def _tarjeta(titulo: str, subtitulo: str, cuerpo: List[Dict[str, Any]], nota: Optional[str]) -> Dict[str, Any]:
    """Encabezado, la nota de prueba (si hay), el contenido y el botón al tablero."""
    bloques: List[Dict[str, Any]] = [
        {"type": "TextBlock", "text": titulo, "weight": "Bolder", "size": "Large", "color": "Accent", "wrap": True},
        {"type": "TextBlock", "text": subtitulo, "spacing": "None", "isSubtle": True, "wrap": True},
    ]
    if nota:
        bloques.append(
            {
                "type": "Container",
                "style": "warning",
                "spacing": "Medium",
                "items": [{"type": "TextBlock", "text": nota, "size": "Small", "wrap": True}],
            }
        )
    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.3",
        "body": bloques + cuerpo,
        "actions": [
            {
                "type": "Action.OpenUrl",
                "title": "Ir a Evaluación de Proveedores",
                "url": f"{settings.frontend_url.rstrip('/')}{RUTA_TABLERO}",
            }
        ],
    }


def tarjeta_evaluador(
    evaluacion: EvaluacionProveedores, empleado: Empleado, pendientes: List[str], nota: Optional[str] = None
) -> Dict[str, Any]:
    """El aviso a un evaluador, como Adaptive Card."""
    plural = "s" if len(pendientes) != 1 else ""
    lista = [{"type": "TextBlock", "text": f"• {p}", "spacing": "Small", "wrap": True} for p in pendientes] or [
        {"type": "TextBlock", "text": "Sin pendientes", "isSubtle": True, "wrap": True}
    ]
    return _tarjeta(
        f"Evaluación de proveedores {evaluacion.periodo}",
        f"Tenés {len(pendientes)} pendiente{plural} · cierra el {evaluacion.fecha_cierre:%d/%m/%Y}",
        [
            {
                "type": "TextBlock",
                "text": f"Hola {empleado.nombre}, tenés pendiente la evaluación de estos proveedores y herramientas:",
                "spacing": "Medium",
                "wrap": True,
            },
            {"type": "Container", "style": "emphasis", "spacing": "Small", "items": lista},
        ],
        nota,
    )


def _fila_canal(evaluador: str, pendientes: str, encabezado: bool = False) -> Dict[str, Any]:
    """Una fila de la tabla del room: el nombre ocupa todo el ancho y el número va a la derecha."""
    estilo = {"size": "Small", "weight": "Bolder", "isSubtle": True} if encabezado else {}
    return {
        "type": "ColumnSet",
        "separator": not encabezado,
        "spacing": "Small",
        "columns": [
            {
                "type": "Column",
                "width": "stretch",
                "verticalContentAlignment": "Center",
                "items": [{"type": "TextBlock", "text": evaluador, "wrap": True, **estilo}],
            },
            {
                "type": "Column",
                "width": "auto",
                "verticalContentAlignment": "Center",
                "items": [
                    {
                        "type": "TextBlock",
                        "text": pendientes,
                        "horizontalAlignment": "Right",
                        **(estilo or {"weight": "Bolder", "color": "Accent"}),
                    }
                ],
            },
        ],
    }


def tarjeta_canal(
    evaluacion: EvaluacionProveedores, avisados: List[tuple], nota: Optional[str] = None
) -> Dict[str, Any]:
    """El resumen de pendientes del room, como Adaptive Card: una tabla evaluador → pendientes a todo el ancho
    (un FactSet ocupa solo el ancho de su contenido)."""
    total = sum(n for _, n in avisados)
    tabla = [_fila_canal("Evaluador", "Pendientes", encabezado=True)] + [
        _fila_canal(nombre, str(n)) for nombre, n in sorted(avisados)
    ]
    return _tarjeta(
        f"Evaluación de proveedores {evaluacion.periodo}",
        f"Quedan {total} evaluaciones pendientes · cierra el {evaluacion.fecha_cierre:%d/%m/%Y}",
        [{"type": "Container", "spacing": "Medium", "items": tabla}]
        if avisados
        else [
            {"type": "TextBlock", "text": "No quedan pendientes", "isSubtle": True, "spacing": "Medium", "wrap": True}
        ],
        nota,
    )


# ─── Envío ──────────────────────────────────────────────────────────────────────


def html_evaluador(
    evaluacion: EvaluacionProveedores, empleado: Empleado, pendientes: List[str], nota: Optional[str] = None
) -> str:
    """El aviso a un evaluador como mail, con el layout de la marca (D-96, core/email_layout)."""
    url = f"{settings.frontend_url.rstrip('/')}{RUTA_TABLERO}"
    plural = "s" if len(pendientes) != 1 else ""
    cuerpo = (
        (correo.nota(nota, icono="🧪") if nota else "")
        + correo.parrafo(
            f"Hola <strong>{correo.e(empleado.nombre or '')}</strong>, tenés pendiente la evaluación "
            f"de estos proveedores y herramientas:"
        )
        + correo.lista(pendientes, vacia="Sin pendientes")
        + correo.boton(url, "Ir a Evaluación de Proveedores", icono="📝")
        + correo.enlace_alternativo(url)
    )
    return correo.pagina(
        titulo=f"Evaluación de proveedores {evaluacion.periodo}",
        icono="📋",
        subtitulo=f"Tenés {len(pendientes)} pendiente{plural} · cierra el {evaluacion.fecha_cierre:%d/%m/%Y}",
        seccion="Administración · Proveedores",
        cuerpo=cuerpo,
        pie="Administración → Proveedores → Evaluación de Proveedores. "
        "Este aviso se manda mientras tengas evaluaciones pendientes.",
    )


def _ya_enviado(
    db: Session, evaluacion_id: uuid.UUID, motivo: str, canal: str, empleado_id: Optional[uuid.UUID], dia: date
) -> bool:
    return (
        db.query(ProveedoresAviso.id)
        .filter(
            ProveedoresAviso.evaluacion_id == evaluacion_id,
            ProveedoresAviso.motivo == motivo,
            ProveedoresAviso.canal == canal,
            ProveedoresAviso.empleado_id.is_(None)
            if empleado_id is None
            else ProveedoresAviso.empleado_id == empleado_id,
            ProveedoresAviso.fecha_local == dia,
            ProveedoresAviso.enviado.is_(True),
        )
        .first()
        is not None
    )


def _contenido(
    canal: str,
    evaluacion: EvaluacionProveedores,
    empleado: Empleado,
    pendientes: List[str],
    cc: List[str],
    nota: Optional[str] = None,
) -> Tuple[str, Dict[str, Any]]:
    """Asunto y contenido del aviso a un evaluador: mail con la marca o tarjeta de Webex. `nota` marca las pruebas."""
    asunto = mensaje(evaluacion, empleado, pendientes)["asunto"]
    asunto = f"[Prueba] {asunto}" if nota else asunto
    if canal == "email":
        return asunto, {"html": html_evaluador(evaluacion, empleado, pendientes, nota), "cc": cc}
    return asunto, {"card": tarjeta_evaluador(evaluacion, empleado, pendientes, nota), "texto": asunto}


def _contenido_canal(
    evaluacion: EvaluacionProveedores, avisados: List[tuple], nota: Optional[str] = None
) -> Tuple[str, Dict[str, Any]]:
    """El resumen de pendientes para el room de Webex, como tarjeta."""
    asunto = f"Evaluación de proveedores {evaluacion.periodo}"
    asunto = f"[Prueba] {asunto}" if nota else asunto
    return asunto, {"card": tarjeta_canal(evaluacion, avisados, nota), "texto": asunto}


def _avisar(
    canal: str,
    destino: str,
    evaluacion: EvaluacionProveedores,
    empleado: Empleado,
    pendientes: List[str],
    cc: List[str],
    nota: Optional[str] = None,
    db: Optional[Session] = None,
) -> Optional[str]:
    """Manda ya el aviso a un evaluador. Devuelve None si salió o el motivo si no. Con `db`, el mensaje personal de
    Webex va a la cuenta de Webex de la persona (principal y si no secundario, F22)."""
    asunto, contenido = _contenido(canal, evaluacion, empleado, pendientes, cc, nota)
    return cola.mandar(canal, destino, asunto, contenido, db=db)


def _avisar_canal(
    room: str, evaluacion: EvaluacionProveedores, avisados: List[tuple], nota: Optional[str] = None
) -> Optional[str]:
    """Manda ya el resumen al room de Webex."""
    asunto, contenido = _contenido_canal(evaluacion, avisados, nota)
    return cola.mandar("webex_room", room, asunto, contenido)


def _clave(evaluacion: EvaluacionProveedores, motivo: str, canal: str, empleado_id, dia: date) -> str:
    return f"proveedores:{evaluacion.id}:{motivo}:{canal}:{empleado_id or 'room'}:{dia.isoformat()}"


def _resultado_de_la_cola(db: Session, aviso_id: str, envio) -> None:
    """La cola despachó (o agotó los reintentos de) un aviso del job: se actualiza su registro."""
    aviso = db.get(ProveedoresAviso, uuid.UUID(aviso_id))
    if aviso is not None:
        aviso.enviado, aviso.error = envio.estado == "enviado", envio.error


cola.registrar_manejador("proveedores_aviso", _resultado_de_la_cola)


def enviar(
    db: Session,
    empresa_id: uuid.UUID,
    empleado_ids: Optional[List[str]],
    motivo: str,
    actor: Actor,
    dia: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """
    Avisa a los evaluadores indicados (None = todos los que tienen pendientes)
    por los canales activos. El envío manual sale ya (se ve el resultado en el
    momento); el del job (motivo distinto de 'manual') se encola, sin repetir un
    aviso ya encolado ese día, y la cola lo despacha con reintentos.
    """
    dia = dia or hoy_argentina()
    evaluacion = evaluacion_vigente(db, empresa_id)
    configuracion = ConfiguracionService.obtener(db, empresa_id)
    canales = _canales(configuracion)
    if evaluacion is None or estado_evaluacion(evaluacion, dia) != "abierta":
        raise ValueError("La evaluación no está abierta: no hay a quién avisar")
    if not canales:
        raise ValueError("No hay canales de aviso activos en la configuración")
    cc = [m.strip() for m in (configuracion.email_cc or "").split(",") if m.strip()]
    en_cola = motivo != "manual"

    def registrar_aviso(canal, empleado_id, destino, pendientes, detalle, encolado=False) -> ProveedoresAviso:
        aviso = ProveedoresAviso(
            empresa_id=empresa_id,
            evaluacion_id=evaluacion.id,
            fecha_local=dia,
            motivo=motivo,
            canal=canal,
            empleado_id=empleado_id,
            destino=(destino or "(sin email)")[:255],
            cc=", ".join(cc) if canal == "email" and cc else None,
            pendientes=pendientes,
            enviado=detalle is None and not encolado,
            error=EN_COLA if encolado else detalle,
            enviado_por=actor.usuario_id,
        )
        db.add(aviso)
        db.flush()
        return aviso

    grupos = _por_evaluador(db, evaluacion)
    elegidos = None if empleado_ids is None else {str(i) for i in empleado_ids}
    resultados: List[Dict[str, Any]] = []
    avisados = []
    for empleado_id, grupo in grupos.items():
        if elegidos is not None and str(empleado_id) not in elegidos:
            continue
        empleado = grupo["empleado"]
        nombre = nombre_empleado(empleado)
        if not grupo["pendientes"]:
            if motivo == "manual":
                resultados.append(
                    {
                        "evaluador": nombre,
                        "canal": "-",
                        "destino": None,
                        "enviado": False,
                        "detalle": "No tiene pendientes",
                    }
                )
            continue
        for canal in (c for c in canales if c != "webex_canal"):
            destino = empleado.email_corporativo
            if motivo != "manual" and _ya_enviado(db, evaluacion.id, motivo, canal, empleado.id, dia):
                continue
            cantidad = len(grupo["pendientes"])
            if not es_corporativo(destino):
                detalle = "No tiene email corporativo (@dicsys.com o @dicsys.ai) en la nómina"
                registrar_aviso(canal, empleado.id, destino, cantidad, detalle)
            elif en_cola:
                aviso = registrar_aviso(canal, empleado.id, destino, cantidad, None, encolado=True)
                asunto, contenido = _contenido(
                    canal, evaluacion, empleado, grupo["pendientes"], cc if canal == "email" else []
                )
                cola.encolar(
                    db,
                    origen=ORIGEN,
                    canal=canal,
                    destino=destino,
                    asunto=asunto,
                    contenido=contenido,
                    clave=_clave(evaluacion, motivo, canal, empleado.id, dia),
                    referencia=f"proveedores_aviso:{aviso.id}",
                )
                resultados.append(
                    {
                        "evaluador": nombre,
                        "canal": canal,
                        "destino": destino,
                        "enviado": False,
                        "encolado": True,
                        "detalle": EN_COLA,
                    }
                )
                continue
            else:
                detalle = _avisar(
                    canal, destino, evaluacion, empleado, grupo["pendientes"], cc if canal == "email" else [], db=db
                )
                registrar_aviso(canal, empleado.id, destino, cantidad, detalle)
            resultados.append(
                {
                    "evaluador": nombre,
                    "canal": canal,
                    "destino": destino,
                    "enviado": detalle is None,
                    "detalle": detalle,
                }
            )
        avisados.append((nombre, len(grupo["pendientes"])))

    if (
        "webex_canal" in canales
        and avisados
        and not (motivo != "manual" and _ya_enviado(db, evaluacion.id, motivo, "webex_canal", None, dia))
    ):
        total = sum(n for _, n in avisados)
        room = configuracion.webex_room_id
        if en_cola:
            aviso = registrar_aviso("webex_canal", None, room, total, None, encolado=True)
            asunto, contenido = _contenido_canal(evaluacion, avisados)
            cola.encolar(
                db,
                origen=ORIGEN,
                canal="webex_room",
                destino=room,
                asunto=asunto,
                contenido=contenido,
                clave=_clave(evaluacion, motivo, "webex_canal", None, dia),
                referencia=f"proveedores_aviso:{aviso.id}",
            )
            resultados.append(
                {
                    "evaluador": "Canal de Webex",
                    "canal": "webex_canal",
                    "destino": room,
                    "enviado": False,
                    "encolado": True,
                    "detalle": EN_COLA,
                }
            )
        else:
            detalle = _avisar_canal(room, evaluacion, avisados)
            registrar_aviso("webex_canal", None, room, total, detalle)
            resultados.append(
                {
                    "evaluador": "Canal de Webex",
                    "canal": "webex_canal",
                    "destino": room,
                    "enviado": detalle is None,
                    "detalle": detalle,
                }
            )

    intentos = [r for r in resultados if r["canal"] != "-"]
    if intentos:
        registrar(
            db,
            empresa_id,
            actor,
            "aviso",
            evaluacion.id,
            "enviar_aviso",
            evaluacion_id=evaluacion.id,
            despues={
                "motivo": motivo,
                "enviados": sum(1 for r in intentos if r["enviado"]),
                "encolados": sum(1 for r in intentos if r.get("encolado")),
                "fallidos": sum(1 for r in intentos if not r["enviado"] and not r.get("encolado")),
            },
        )
    db.commit()
    return resultados


def probar(
    db: Session, empresa_id: uuid.UUID, evaluador_id: str, canales: Dict[str, Any], actor: Actor
) -> List[Dict[str, Any]]:
    """
    Prueba de canales: le manda de verdad al evaluador elegido el aviso que le
    corresponde hoy, marcado [Prueba], por los canales tildados en pantalla
    (aunque no estén guardados). Con «Webex en canal», publica en el room el
    resumen de pendientes, también marcado. Funciona con la evaluación vigente
    en cualquier estado. No cuenta como aviso: no queda en el historial de
    avisos ni frena los del job; queda en la auditoría.
    """
    if not (canales.get("canal_email") or canales.get("canal_webex_personal") or canales.get("canal_webex_canal")):
        raise ValueError("Tildá al menos un canal para probar")
    if canales.get("canal_webex_canal") and not canales.get("webex_room_id"):
        raise ValueError("Para probar el canal de Webex hay que indicar el ID del room")
    evaluacion = evaluacion_vigente(db, empresa_id)
    if evaluacion is None:
        raise ValueError("No hay una evaluación vigente: hace falta una para armar el aviso del evaluador")
    grupos = _por_evaluador(db, evaluacion)
    grupo = next((g for empleado_id, g in grupos.items() if str(empleado_id) == str(evaluador_id)), None)
    if grupo is None:
        raise ValueError("Ese empleado no evalúa ningún proveedor de la evaluación vigente")
    empleado = grupo["empleado"]
    nombre = nombre_empleado(empleado)

    nota = (
        f"[Prueba] Mensaje de prueba de los canales de aviso, enviado por {actor.email or 'el sistema'}. "
        f"No hay que hacer nada."
    )
    if not grupo["pendientes"]:
        nota += " Hoy no tiene pendientes: el aviso real no se le mandaría."

    resultados: List[Dict[str, Any]] = []

    def anotar(evaluador, canal, destino, detalle):
        resultados.append(
            {"evaluador": evaluador, "canal": canal, "destino": destino, "enviado": detalle is None, "detalle": detalle}
        )

    for canal, activo in (
        ("email", canales.get("canal_email")),
        ("webex_personal", canales.get("canal_webex_personal")),
    ):
        if not activo:
            continue
        destino = empleado.email_corporativo
        if not es_corporativo(destino):
            anotar(nombre, canal, destino, "No tiene email corporativo (@dicsys.com o @dicsys.ai) en la nómina")
            continue
        cc = list(canales.get("email_cc") or []) if canal == "email" else []
        anotar(
            nombre, canal, destino, _avisar(canal, destino, evaluacion, empleado, grupo["pendientes"], cc, nota, db=db)
        )
    if canales.get("canal_webex_canal"):
        room = canales.get("webex_room_id")
        avisados = [(nombre_empleado(g["empleado"]), len(g["pendientes"])) for g in grupos.values() if g["pendientes"]]
        nota_canal = f"[Prueba] Mensaje de prueba del canal de avisos, enviado por {actor.email or 'el sistema'}."
        anotar("Canal de Webex", "webex_canal", room, _avisar_canal(room, evaluacion, avisados, nota_canal))

    registrar(
        db,
        empresa_id,
        actor,
        "aviso",
        evaluacion.id,
        "probar_canales",
        evaluacion_id=evaluacion.id,
        despues={
            "evaluador": nombre,
            "canales": [r["canal"] for r in resultados],
            "enviados": sum(1 for r in resultados if r["enviado"]),
            "fallidos": sum(1 for r in resultados if not r["enviado"]),
        },
    )
    db.commit()
    return resultados


def historial(db: Session, empresa_id: uuid.UUID, limite: int = 100) -> List[ProveedoresAviso]:
    evaluacion = evaluacion_vigente(db, empresa_id)
    if evaluacion is None:
        return []
    return (
        db.query(ProveedoresAviso)
        .filter(ProveedoresAviso.evaluacion_id == evaluacion.id)
        .order_by(ProveedoresAviso.fecha_hora.desc())
        .limit(limite)
        .all()
    )


# ─── Job diario ─────────────────────────────────────────────────────────────────


def motivo_del_dia(
    configuracion: ProveedoresConfiguracion, evaluacion: EvaluacionProveedores, dia: date
) -> Optional[str]:
    """Qué aviso corresponde hoy (uno solo: apertura, después previo al cierre, después recordatorio)."""
    if estado_evaluacion(evaluacion, dia) != "abierta":
        return None
    if configuracion.aviso_apertura and dia == evaluacion.fecha_apertura:
        return "apertura"
    if configuracion.aviso_previo_cierre and dia == evaluacion.fecha_cierre - timedelta(days=1):
        return "previo_cierre"
    cada = configuracion.recordar_cada_dias
    dias = (dia - evaluacion.fecha_apertura).days
    if cada and dias > 0 and dias % cada == 0:
        return "recordatorio"
    return None


def procesar_avisos_del_dia(db: Session, ahora: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Recorre las empresas con configuración y encola lo que corresponda si ya pasó su
    hora. Lo corre el motor de tareas cada minuto (evaluacion_proveedores_tareas.py).
    """
    ahora = ahora or ahora_argentina()
    resumen: Dict[str, Any] = {"empresas": 0, "encolados": 0, "errores": []}
    for configuracion in db.query(ProveedoresConfiguracion).all():
        if ahora.time() < configuracion.hora_envio or not _canales(configuracion):
            continue
        evaluacion = evaluacion_vigente(db, configuracion.empresa_id)
        motivo = motivo_del_dia(configuracion, evaluacion, ahora.date()) if evaluacion else None
        if motivo is None:
            continue
        # Una tanda por día y motivo: los reintentos los hace la cola; lo que agota
        # los reintentos se alerta y se puede reintentar a mano desde Seguimiento.
        if (
            db.query(ProveedoresAviso.id)
            .filter(
                ProveedoresAviso.evaluacion_id == evaluacion.id,
                ProveedoresAviso.motivo == motivo,
                ProveedoresAviso.fecha_local == ahora.date(),
            )
            .first()
        ):
            continue
        try:
            resultados = enviar(db, configuracion.empresa_id, None, motivo, SISTEMA, dia=ahora.date())
        except Exception as exc:  # noqa: BLE001 - una empresa con error no frena al resto
            db.rollback()
            logger.error(
                f"Error en avisos de evaluación de proveedores ({configuracion.empresa_id}): {exc}", exc_info=True
            )
            resumen["errores"].append(f"Empresa {configuracion.empresa_id}: {exc}")
            continue
        resumen["empresas"] += 1
        resumen["encolados"] += sum(1 for r in resultados if r.get("encolado"))
    return resumen
