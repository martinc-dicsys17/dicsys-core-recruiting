"""
Servicios de la evaluación de proveedores: configuración global, campañas,
tablero y respuestas.

Reglas (decisiones de director): una sola evaluación vigente por empresa;
activa hasta su cierre o hasta que se cree la siguiente (D-74); se evalúa solo
entre apertura y cierre (D-65); solo el referente evalúa su proveedor (D-72);
un ítem cuenta como evaluado cuando tiene respondidas las dos preguntas
(incidentes y mal manejo; el checklist de seguridad salió de la evaluación), y
una respuesta «Si» lleva su evidencia.
"""

import calendar
import uuid
from datetime import date, time
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from backend.core.google_sheets import cuenta_de_servicio
from backend.core.utils import utc_now
from backend.modules.administracion.proveedores_auditoria import SISTEMA, Actor, diferencias, foto, registrar
from backend.modules.administracion.proveedores_comun import (
    ReferenciaInvalida,
    asegurar_item,
    es_activa,
    estado_evaluacion,
    evaluacion_activa,
    evaluacion_vigente,
    hoy_argentina,
    item_de,
    uuid_o_none,
)
from backend.modules.administracion.proveedores_models import (
    EVIDENCIA_DE,
    EVIDENCIAS,
    OPCIONES_INCIDENTES,
    OPCIONES_MAL_MANEJO,
    EvaluacionItem,
    EvaluacionProveedores,
    ImportacionProveedores,
    ProveedoresAuditoria,
    ProveedoresConfiguracion,
    RegistroProveedor,
)
from backend.modules.administracion.proveedores_services import (
    OperacionNoPermitida,
    ProveedorRegistroService,
    filtro_busqueda,
)
from backend.modules.nomina.models import Empleado
from backend.modules.usuarios.models import Usuario

OPCIONES = {
    "incidentes": list(OPCIONES_INCIDENTES),
    "mal_manejo": list(OPCIONES_MAL_MANEJO),
}
# Las dos son obligatorias para todos los proveedores
PREGUNTAS = ["incidentes", "mal_manejo"]
NOMBRES_PREGUNTA = {"incidentes": "incidentes", "mal_manejo": "mal manejo de información"}
CAMPOS_CONFIGURACION = (
    "sheet_url",
    "sheet_hoja",
    "recordar_cada_dias",
    "aviso_apertura",
    "aviso_previo_cierre",
    "hora_envio",
    "canal_email",
    "email_cc",
    "canal_webex_personal",
    "canal_webex_canal",
    "webex_room_id",
)
CAMPOS_RESPUESTA = (*PREGUNTAS, *EVIDENCIAS)


class EvaluacionCerrada(ValueError):
    """Fuera de la ventana apertura–cierre, o la evaluación ya fue reemplazada (409)."""


class NoEsEvaluador(PermissionError):
    """El proveedor no está asignado al usuario (403)."""


class EvaluacionInvalida(ValueError):
    """Respuestas incompletas o que no aplican (422)."""


class PeriodoDuplicado(ValueError):
    """Ya hay una evaluación con ese período (409)."""


def nombre_empleado(empleado: Optional[Empleado]) -> Optional[str]:
    return f"{empleado.apellido}, {empleado.nombre}" if empleado else None


def empleado_del_usuario(db: Session, empresa_id: uuid.UUID, usuario) -> Optional[Empleado]:
    """El empleado de la nómina vinculado al usuario por DNI (como el login)."""
    if not getattr(usuario, "dni", None):
        return None
    return (
        db.query(Empleado)
        .filter(
            Empleado.empresa_id == empresa_id,
            Empleado.dni == usuario.dni,
            Empleado.deleted_at.is_(None),
        )
        .first()
    )


def preguntas_de(tipo: str) -> List[str]:
    """Las preguntas a responder: las dos, sea cual sea el tipo."""
    return list(PREGUNTAS)


def puede_editar(item: EvaluacionItem, empleado: Optional[Empleado], es_admin: bool) -> bool:
    """Editan el referente asignado al ítem (D-72) y el admin del módulo (D-87)."""
    return es_admin or (empleado is not None and item.evaluador_empleado_id == empleado.id)


# ─── Configuración ──────────────────────────────────────────────────────────────


class ConfiguracionService:
    @staticmethod
    def obtener(db: Session, empresa_id: uuid.UUID) -> Optional[ProveedoresConfiguracion]:
        return db.query(ProveedoresConfiguracion).filter(ProveedoresConfiguracion.empresa_id == empresa_id).first()

    @staticmethod
    def como_dict(configuracion: Optional[ProveedoresConfiguracion]) -> Dict[str, Any]:
        """La configuración guardada o los valores por defecto (todo apagado)."""
        if configuracion is None:
            return {
                "sheet_url": None,
                "sheet_hoja": "Listado Proveedores",
                "recordar_cada_dias": None,
                "aviso_apertura": False,
                "aviso_previo_cierre": False,
                "hora_envio": time(9, 0),
                "canal_email": False,
                "email_cc": [],
                "canal_webex_personal": False,
                "canal_webex_canal": False,
                "webex_room_id": None,
                "actualizado_por": None,
                "actualizado_at": None,
                "cuenta_sheets": cuenta_de_servicio(),
            }
        datos = {campo: getattr(configuracion, campo) for campo in CAMPOS_CONFIGURACION}
        datos["email_cc"] = [m.strip() for m in (configuracion.email_cc or "").split(",") if m.strip()]
        datos["actualizado_por"] = configuracion.updated_by
        datos["actualizado_at"] = configuracion.updated_at
        datos["cuenta_sheets"] = cuenta_de_servicio()
        return datos

    @staticmethod
    def guardar(db: Session, empresa_id: uuid.UUID, datos: Dict[str, Any], actor: Actor) -> ProveedoresConfiguracion:
        configuracion = ConfiguracionService.obtener(db, empresa_id)
        nueva = configuracion is None
        if nueva:
            configuracion = ProveedoresConfiguracion(id=uuid.uuid4(), empresa_id=empresa_id, created_by=actor.email)
            db.add(configuracion)
        antes = ConfiguracionService.como_dict(None if nueva else configuracion)
        for campo in CAMPOS_CONFIGURACION:
            valor = datos.get(campo)
            if campo == "email_cc":
                valor = ", ".join(valor) if valor else None
            setattr(configuracion, campo, valor)
        configuracion.updated_by = actor.email
        despues = {campo: datos.get(campo) for campo in CAMPOS_CONFIGURACION}
        cambios_antes, cambios_despues = diferencias({k: antes[k] for k in CAMPOS_CONFIGURACION}, despues)
        if cambios_despues or nueva:
            registrar(
                db,
                empresa_id,
                actor,
                "configuracion",
                configuracion.id,
                "configurar",
                antes=cambios_antes,
                despues=cambios_despues,
            )
        db.commit()
        db.refresh(configuracion)
        return configuracion


# ─── Campañas ───────────────────────────────────────────────────────────────────


class EvaluacionService:
    @staticmethod
    def _de_la_empresa(db: Session, empresa_id: uuid.UUID, evaluacion_id) -> EvaluacionProveedores:
        evaluacion = (
            db.query(EvaluacionProveedores)
            .filter(
                EvaluacionProveedores.id == uuid_o_none(evaluacion_id),
                EvaluacionProveedores.empresa_id == empresa_id,
                EvaluacionProveedores.deleted_at.is_(None),
            )
            .first()
        )
        if evaluacion is None:
            raise ReferenciaInvalida("La evaluación no existe")
        return evaluacion

    @staticmethod
    def items(db: Session, evaluacion_id: uuid.UUID) -> List[EvaluacionItem]:
        return (
            db.query(EvaluacionItem)
            .options(
                joinedload(EvaluacionItem.proveedor),
                joinedload(EvaluacionItem.evaluador),
            )
            .filter(
                EvaluacionItem.evaluacion_id == evaluacion_id,
                EvaluacionItem.deleted_at.is_(None),
            )
            .all()
        )

    @staticmethod
    def metricas(items: List[EvaluacionItem]) -> Dict[str, int]:
        evaluados = sum(1 for i in items if i.evaluado_at is not None)
        return {
            "total": len(items),
            "evaluados": evaluados,
            "pendientes": len(items) - evaluados,
            "con_hallazgo": sum(1 for i in items if i.con_hallazgo),
            "sin_evaluador": sum(1 for i in items if i.evaluador_empleado_id is None),
        }

    @staticmethod
    def resumen(db: Session, evaluacion: EvaluacionProveedores, hoy: Optional[date] = None) -> Dict[str, Any]:
        return {
            "id": str(evaluacion.id),
            "periodo": evaluacion.periodo,
            "fecha_apertura": evaluacion.fecha_apertura,
            "fecha_cierre": evaluacion.fecha_cierre,
            "estado": estado_evaluacion(evaluacion, hoy),
            "activa": es_activa(evaluacion, hoy),
            "metricas": EvaluacionService.metricas(EvaluacionService.items(db, evaluacion.id)),
        }

    @staticmethod
    def listar(db: Session, empresa_id: uuid.UUID) -> List[EvaluacionProveedores]:
        return (
            db.query(EvaluacionProveedores)
            .filter(
                EvaluacionProveedores.empresa_id == empresa_id,
                EvaluacionProveedores.deleted_at.is_(None),
            )
            .order_by(EvaluacionProveedores.fecha_apertura.desc())
            .all()
        )

    @staticmethod
    def crear(
        db: Session,
        empresa_id: uuid.UUID,
        datos: Dict[str, Any],
        actor: Actor,
        con_proveedores_activos: bool = False,
        via: Optional[str] = None,
    ) -> EvaluacionProveedores:
        """
        Crea la campaña nueva y reemplaza a la vigente. Creada a mano arranca sin proveedores:
        entran por la importación del Sheet o con «Agregar proveedor» del tablero. La
        auto-generación la crea con todos los activos (`con_proveedores_activos`).
        """
        periodo = datos["periodo"]
        if (
            db.query(EvaluacionProveedores.id)
            .filter(
                EvaluacionProveedores.empresa_id == empresa_id,
                EvaluacionProveedores.periodo == periodo,
                EvaluacionProveedores.deleted_at.is_(None),
            )
            .first()
        ):
            raise PeriodoDuplicado(f"Ya existe la evaluación del período {periodo}")

        anterior = evaluacion_vigente(db, empresa_id)
        if anterior is not None:
            anterior.reemplazada_at = utc_now()
            anterior.updated_by = actor.email
            registrar(
                db,
                empresa_id,
                actor,
                "evaluacion",
                anterior.id,
                "reemplazar",
                evaluacion_id=anterior.id,
                despues={"reemplazada_por_periodo": periodo},
            )
            db.flush()

        evaluacion = EvaluacionProveedores(
            id=uuid.uuid4(),
            empresa_id=empresa_id,
            periodo=periodo,
            fecha_apertura=datos["fecha_apertura"],
            fecha_cierre=datos["fecha_cierre"],
            created_by=actor.email,
            updated_by=actor.email,
        )
        db.add(evaluacion)
        despues = foto(evaluacion, ("periodo", "fecha_apertura", "fecha_cierre"))
        registrar(
            db,
            empresa_id,
            actor,
            "evaluacion",
            evaluacion.id,
            "crear",
            evaluacion_id=evaluacion.id,
            despues={**despues, "via": via} if via else despues,
        )
        if con_proveedores_activos:
            db.flush()
            for proveedor in (
                db.query(RegistroProveedor)
                .filter(
                    RegistroProveedor.empresa_id == empresa_id,
                    RegistroProveedor.deleted_at.is_(None),
                    RegistroProveedor.activo.is_(True),
                )
                .order_by(func.lower(RegistroProveedor.nombre))
                .all()
            ):
                asegurar_item(db, evaluacion, proveedor, actor)
        db.commit()
        db.refresh(evaluacion)
        return evaluacion

    @staticmethod
    def cambiar_fechas(
        db: Session, empresa_id: uuid.UUID, evaluacion_id, datos: Dict[str, Any], actor: Actor
    ) -> EvaluacionProveedores:
        """Solo la vigente: ampliar el cierre la vuelve a abrir (D-65, D-74)."""
        evaluacion = EvaluacionService._de_la_empresa(db, empresa_id, evaluacion_id)
        if evaluacion.reemplazada_at is not None:
            raise EvaluacionCerrada("La evaluación ya fue reemplazada por otra: no se pueden cambiar sus fechas")
        antes = foto(evaluacion, ("fecha_apertura", "fecha_cierre"))
        evaluacion.fecha_apertura = datos["fecha_apertura"]
        evaluacion.fecha_cierre = datos["fecha_cierre"]
        evaluacion.updated_by = actor.email
        despues = foto(evaluacion, ("fecha_apertura", "fecha_cierre"))
        cambios_antes, cambios_despues = diferencias(antes, despues)
        if cambios_despues:
            accion = (
                "ampliar_cierre"
                if datos["fecha_cierre"] > date.fromisoformat(antes["fecha_cierre"])
                else "cambiar_fechas"
            )
            registrar(
                db,
                empresa_id,
                actor,
                "evaluacion",
                evaluacion.id,
                accion,
                evaluacion_id=evaluacion.id,
                antes=cambios_antes,
                despues=cambios_despues,
            )
        db.commit()
        db.refresh(evaluacion)
        return evaluacion

    @staticmethod
    def eliminar(db: Session, empresa_id: uuid.UUID, evaluacion_id, actor: Actor) -> None:
        """
        Baja lógica de la campaña y de sus ítems, aunque ya tenga evaluados (la pantalla
        pide confirmación con los números). Si era la vigente no queda ninguna: la anterior
        sigue finalizada. Una vista previa del Sheet pendiente para ella se descarta.
        """
        evaluacion = EvaluacionService._de_la_empresa(db, empresa_id, evaluacion_id)
        items = EvaluacionService.items(db, evaluacion.id)
        metricas = EvaluacionService.metricas(items)
        ahora = utc_now()
        for item in items:
            item.deleted_at = ahora
            item.updated_by = actor.email
        evaluacion.deleted_at = ahora
        evaluacion.updated_by = actor.email
        for vista_previa in (
            db.query(ImportacionProveedores).filter(ImportacionProveedores.evaluacion_id == evaluacion.id).all()
        ):
            db.delete(vista_previa)
        registrar(
            db,
            empresa_id,
            actor,
            "evaluacion",
            evaluacion.id,
            "eliminar",
            evaluacion_id=evaluacion.id,
            antes={
                **foto(evaluacion, ("periodo", "fecha_apertura", "fecha_cierre")),
                "proveedores": metricas["total"],
                "evaluados": metricas["evaluados"],
            },
        )
        db.commit()


# ─── Auto-generación anual ──────────────────────────────────────────────────────

CAMPOS_AUTOGENERACION = {
    "activa": "auto_generar",
    "inicio_dia": "auto_inicio_dia",
    "inicio_mes": "auto_inicio_mes",
    "fin_dia": "auto_fin_dia",
    "fin_mes": "auto_fin_mes",
}


def _fecha_del_anio(anio: int, mes: int, dia: int) -> date:
    """Ese día y mes en el año pedido; el 29/02 de un año no bisiesto cae el 28."""
    return date(anio, mes, min(dia, calendar.monthrange(anio, mes)[1]))


class AutogeneracionService:
    """
    Cada año, al llegar la fecha de inicio, crea la evaluación del año (período = el año) con
    todos los proveedores activos, cada uno con su referente como evaluador, y reemplaza a la
    vigente como la creación manual. Una sola vez por año: si ya hay una evaluación de ese
    período, o la creada se elimina, no crea otra. Si se activa con la ventana del año ya
    pasada, espera al año siguiente. Arranca apagada.
    """

    @staticmethod
    def configurada(configuracion: Optional[ProveedoresConfiguracion]) -> bool:
        return configuracion is not None and None not in (
            configuracion.auto_inicio_dia,
            configuracion.auto_inicio_mes,
            configuracion.auto_fin_dia,
            configuracion.auto_fin_mes,
        )

    @staticmethod
    def ventana(configuracion: ProveedoresConfiguracion, anio: int) -> Tuple[date, date]:
        """Apertura y cierre de ese año; si el fin cae antes del inicio, el cierre es al año siguiente."""
        apertura = _fecha_del_anio(anio, configuracion.auto_inicio_mes, configuracion.auto_inicio_dia)
        cierre = _fecha_del_anio(anio, configuracion.auto_fin_mes, configuracion.auto_fin_dia)
        if cierre < apertura:
            cierre = _fecha_del_anio(anio + 1, configuracion.auto_fin_mes, configuracion.auto_fin_dia)
        return apertura, cierre

    @staticmethod
    def _existe(db: Session, empresa_id: uuid.UUID, periodo: str) -> bool:
        return (
            db.query(EvaluacionProveedores.id)
            .filter(
                EvaluacionProveedores.empresa_id == empresa_id,
                EvaluacionProveedores.periodo == periodo,
                EvaluacionProveedores.deleted_at.is_(None),
            )
            .first()
            is not None
        )

    @staticmethod
    def como_dict(
        db: Session,
        empresa_id: uuid.UUID,
        configuracion: Optional[ProveedoresConfiguracion],
        hoy: Optional[date] = None,
    ) -> Dict[str, Any]:
        """La configuración y la próxima evaluación que va a crear la tarea (si está configurada)."""
        hoy = hoy or hoy_argentina()
        datos = {
            campo: getattr(configuracion, columna) if configuracion else None
            for campo, columna in CAMPOS_AUTOGENERACION.items()
        }
        datos["activa"] = bool(datos["activa"])
        datos["ultimo_periodo"] = configuracion.auto_ultimo_periodo if configuracion else None
        datos["proxima"] = None
        if AutogeneracionService.configurada(configuracion):
            anio = hoy.year
            apertura, cierre = AutogeneracionService.ventana(configuracion, anio)
            if configuracion.auto_ultimo_periodo == str(anio) or hoy > cierre:
                anio += 1
                apertura, cierre = AutogeneracionService.ventana(configuracion, anio)
            datos["proxima"] = {
                "periodo": str(anio),
                "fecha_apertura": apertura,
                "fecha_cierre": cierre,
                "ya_existe": AutogeneracionService._existe(db, empresa_id, str(anio)),
            }
        return datos

    @staticmethod
    def guardar(db: Session, empresa_id: uuid.UUID, datos: Dict[str, Any], actor: Actor) -> ProveedoresConfiguracion:
        configuracion = ConfiguracionService.obtener(db, empresa_id)
        if configuracion is None:
            configuracion = ProveedoresConfiguracion(id=uuid.uuid4(), empresa_id=empresa_id, created_by=actor.email)
            db.add(configuracion)
        antes = {campo: getattr(configuracion, columna) for campo, columna in CAMPOS_AUTOGENERACION.items()}
        for campo, columna in CAMPOS_AUTOGENERACION.items():
            setattr(configuracion, columna, datos.get(campo))
        configuracion.updated_by = actor.email
        cambios_antes, cambios_despues = diferencias(
            antes, {campo: datos.get(campo) for campo in CAMPOS_AUTOGENERACION}
        )
        if cambios_despues:
            registrar(
                db,
                empresa_id,
                actor,
                "configuracion",
                configuracion.id,
                "configurar_autogeneracion",
                antes=cambios_antes,
                despues=cambios_despues,
            )
        db.commit()
        db.refresh(configuracion)
        return configuracion

    @staticmethod
    def generar_si_corresponde(
        db: Session, configuracion: ProveedoresConfiguracion, hoy: Optional[date] = None
    ) -> Optional[EvaluacionProveedores]:
        """La evaluación del año, si llegó la fecha de inicio y este año todavía no se resolvió."""
        hoy = hoy or hoy_argentina()
        periodo = str(hoy.year)
        if (
            not configuracion.auto_generar
            or configuracion.auto_ultimo_periodo == periodo
            or not AutogeneracionService.configurada(configuracion)
        ):
            return None
        apertura, cierre = AutogeneracionService.ventana(configuracion, hoy.year)
        if hoy < apertura:
            return None  # todavía no llegó la fecha de inicio
        configuracion.auto_ultimo_periodo = periodo  # se resuelve una sola vez por año
        if hoy > cierre or AutogeneracionService._existe(db, configuracion.empresa_id, periodo):
            db.commit()  # activada con la ventana ya pasada, o la del año ya existe: no crea otra
            return None
        return EvaluacionService.crear(
            db,
            configuracion.empresa_id,
            {"periodo": periodo, "fecha_apertura": apertura, "fecha_cierre": cierre},
            SISTEMA,
            con_proveedores_activos=True,
            via="autogeneracion",
        )

    @staticmethod
    def procesar(db: Session, hoy: Optional[date] = None) -> Dict[str, List[str]]:
        """Lo que corre la tarea cada minuto, para todas las empresas con la auto-generación activa."""
        creadas: List[str] = []
        errores: List[str] = []
        for configuracion in (
            db.query(ProveedoresConfiguracion).filter(ProveedoresConfiguracion.auto_generar.is_(True)).all()
        ):
            empresa_id = configuracion.empresa_id
            try:
                evaluacion = AutogeneracionService.generar_si_corresponde(db, configuracion, hoy)
                if evaluacion is not None:
                    total = len(EvaluacionService.items(db, evaluacion.id))
                    creadas.append(f"{evaluacion.periodo} con {total} proveedor(es)")
            except Exception as exc:  # noqa: BLE001 - una empresa no frena a las demás; se reintenta
                db.rollback()
                errores.append(f"empresa {empresa_id}: {exc}")
        return {"creadas": creadas, "errores": errores}


# ─── Tablero y respuestas ───────────────────────────────────────────────────────


class TableroService:
    @staticmethod
    def armar(
        db: Session, empresa_id: uuid.UUID, usuario, es_admin: bool, evaluacion_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        El admin ve todos los ítems (y puede mirar una evaluación anterior); el
        resto, solo los asignados a su empleado (D-76). Editan, hasta el cierre,
        el referente de cada ítem y el admin (D-87).
        """
        hoy = hoy_argentina()
        if es_admin and evaluacion_id:
            evaluacion = EvaluacionService._de_la_empresa(db, empresa_id, evaluacion_id)
        else:
            evaluacion = evaluacion_vigente(db, empresa_id)
        empleado = empleado_del_usuario(db, empresa_id, usuario)
        respuesta = {
            "evaluacion": None,
            "es_admin": es_admin,
            "empleado_vinculado": empleado is not None,
            "puede_evaluar": False,
            "opciones": OPCIONES,
            "metricas": EvaluacionService.metricas([]),
            "items": [],
            "evaluadores": [],
            "evaluaciones": [],
        }
        if es_admin:
            respuesta["evaluaciones"] = [
                {"id": str(e.id), "nombre": e.periodo} for e in EvaluacionService.listar(db, empresa_id)
            ]
        if evaluacion is None:
            return respuesta

        abierta = estado_evaluacion(evaluacion, hoy) == "abierta"
        items = EvaluacionService.items(db, evaluacion.id)
        if not es_admin:
            items = [i for i in items if empleado is not None and i.evaluador_empleado_id == empleado.id]
        items.sort(key=lambda i: (i.proveedor.nombre or "").lower())

        evaluadores = {}
        filas = []
        for item in items:
            if item.evaluador is not None:
                evaluadores[str(item.evaluador.id)] = nombre_empleado(item.evaluador)
            filas.append(
                {
                    "id": str(item.id),
                    "proveedor": {"id": str(item.proveedor.id), "nombre": item.proveedor.nombre},
                    "tipo": item.proveedor.tipo,
                    "evaluador": (
                        {"id": str(item.evaluador.id), "nombre": nombre_empleado(item.evaluador)}
                        if item.evaluador
                        else None
                    ),
                    "preguntas": preguntas_de(item.proveedor.tipo),
                    "incidentes": item.incidentes,
                    "mal_manejo": item.mal_manejo,
                    "con_evidencia": any(getattr(item, campo) for campo in EVIDENCIAS),
                    "con_hallazgo": bool(item.con_hallazgo),
                    "evaluado": item.evaluado_at is not None,
                    "evaluado_at": item.evaluado_at,
                    "puede_editar": abierta and puede_editar(item, empleado, es_admin),
                }
            )
        respuesta.update(
            {
                "evaluacion": EvaluacionService.resumen(db, evaluacion, hoy),
                "puede_evaluar": abierta,
                "metricas": EvaluacionService.metricas(items),
                "items": filas,
                "evaluadores": [{"id": k, "nombre": v} for k, v in sorted(evaluadores.items(), key=lambda p: p[1])],
            }
        )
        return respuesta

    @staticmethod
    def _item(db: Session, empresa_id: uuid.UUID, item_id) -> EvaluacionItem:
        item = (
            db.query(EvaluacionItem)
            .options(
                joinedload(EvaluacionItem.proveedor),
                joinedload(EvaluacionItem.evaluador),
            )
            .filter(
                EvaluacionItem.id == uuid_o_none(item_id),
                EvaluacionItem.empresa_id == empresa_id,
                EvaluacionItem.deleted_at.is_(None),
            )
            .first()
        )
        if item is None:
            raise ReferenciaInvalida("El ítem no existe")
        return item

    @staticmethod
    def detalle(db: Session, empresa_id: uuid.UUID, item_id, usuario, es_admin: bool) -> Dict[str, Any]:
        """La evaluación completa de un proveedor, con su historial de cambios (D-67)."""
        item = TableroService._item(db, empresa_id, item_id)
        empleado = empleado_del_usuario(db, empresa_id, usuario)
        es_evaluador = empleado is not None and item.evaluador_empleado_id == empleado.id
        if not (es_admin or es_evaluador):
            raise NoEsEvaluador("Esa evaluación no está asignada a vos")
        evaluacion = db.get(EvaluacionProveedores, item.evaluacion_id)
        abierta = estado_evaluacion(evaluacion) == "abierta"
        evaluado_por = db.get(Usuario, item.evaluado_por) if item.evaluado_por else None
        eventos = (
            db.query(ProveedoresAuditoria)
            .filter(
                ProveedoresAuditoria.entidad == "item",
                ProveedoresAuditoria.entidad_id == item.id,
            )
            .order_by(ProveedoresAuditoria.fecha_hora.desc())
            .all()
        )
        return {
            "id": str(item.id),
            "proveedor": {
                "id": str(item.proveedor.id),
                "nombre": item.proveedor.nombre,
                "razon_social": item.proveedor.razon_social,
            },
            "tipo": item.proveedor.tipo,
            "evaluacion": EvaluacionService.resumen(db, evaluacion),
            "evaluador": (
                {"id": str(item.evaluador.id), "nombre": nombre_empleado(item.evaluador)} if item.evaluador else None
            ),
            "preguntas": preguntas_de(item.proveedor.tipo),
            "opciones": OPCIONES,
            "incidentes": item.incidentes,
            "mal_manejo": item.mal_manejo,
            **{campo: getattr(item, campo) for campo in EVIDENCIAS},
            "con_hallazgo": bool(item.con_hallazgo),
            "evaluado": item.evaluado_at is not None,
            "evaluado_at": item.evaluado_at,
            "evaluado_por": evaluado_por.email if evaluado_por else None,
            "puede_editar": abierta and puede_editar(item, empleado, es_admin),
            "es_admin": es_admin,
            "historial": [
                {
                    "fecha_hora": e.fecha_hora,
                    "usuario": e.usuario_email,
                    "accion": e.accion,
                    "antes": e.antes,
                    "despues": e.despues,
                }
                for e in eventos
            ],
        }

    @staticmethod
    def responder(
        db: Session,
        empresa_id: uuid.UUID,
        item_id,
        datos: Dict[str, Any],
        usuario,
        actor: Actor,
        es_admin: bool = False,
    ) -> EvaluacionItem:
        item = TableroService._item(db, empresa_id, item_id)
        evaluacion = db.get(EvaluacionProveedores, item.evaluacion_id)
        estado = estado_evaluacion(evaluacion)
        if estado != "abierta":
            mensajes = {
                "programada": f"La evaluación abre el {evaluacion.fecha_apertura:%d/%m/%Y}",
                "cerrada": "La evaluación está cerrada: para evaluar hay que ampliar la fecha de cierre",
                "reemplazada": "La evaluación ya fue reemplazada por otra",
            }
            raise EvaluacionCerrada(mensajes[estado])
        if not puede_editar(item, empleado_del_usuario(db, empresa_id, usuario), es_admin):
            raise NoEsEvaluador("Ese proveedor no está asignado a vos")

        preguntas = preguntas_de(item.proveedor.tipo)
        faltan = [p for p in preguntas if not datos.get(p)]
        if faltan:
            raise EvaluacionInvalida("Falta responder: " + ", ".join(NOMBRES_PREGUNTA[p] for p in faltan))
        sin_evidencia = [p for p in preguntas if datos.get(p) == "Si" and not datos.get(EVIDENCIA_DE[p])]
        if sin_evidencia:
            raise EvaluacionInvalida(
                "Con «Si» la evidencia es obligatoria: falta la de "
                + ", ".join(NOMBRES_PREGUNTA[p] for p in sin_evidencia)
            )

        antes = foto(item, CAMPOS_RESPUESTA)
        for campo in preguntas:
            setattr(item, campo, datos.get(campo))
            # La evidencia solo acompaña a un «Si»: con otra respuesta queda vacía
            setattr(item, EVIDENCIA_DE[campo], datos.get(EVIDENCIA_DE[campo]) if datos.get(campo) == "Si" else None)
        item.evaluado_at = utc_now()
        item.evaluado_por = actor.usuario_id
        item.updated_by = actor.email
        cambios_antes, cambios_despues = diferencias(antes, foto(item, CAMPOS_RESPUESTA))
        registrar(
            db,
            empresa_id,
            actor,
            "item",
            item.id,
            "evaluar",
            evaluacion_id=item.evaluacion_id,
            antes=cambios_antes,
            despues=cambios_despues or foto(item, CAMPOS_RESPUESTA),
        )
        db.commit()
        db.refresh(item)
        return item


# ─── Agregar proveedores a la evaluación activa (admin) ─────────────────────────


class AsignacionService:
    """
    Desde el tablero se suma un proveedor del registro a la evaluación activa (además de
    la importación del Sheet, es la única forma de que un proveedor entre a evaluarse).
    El admin del módulo busca en todo el registro; el evaluador, solo entre los activos
    que tiene asignados como usuario referente. Un inactivo aparece marcado pero no se
    puede agregar: primero se activa en Proveedores.
    """

    @staticmethod
    def _empleado_evaluador(empleado: Optional[Empleado]) -> Empleado:
        if empleado is None:
            raise NoEsEvaluador(
                "Tu usuario no está vinculado a un empleado de la nómina: no tenés proveedores asignados para agregar"
            )
        return empleado

    @staticmethod
    def _activa(db: Session, empresa_id: uuid.UUID) -> EvaluacionProveedores:
        evaluacion = evaluacion_activa(db, empresa_id)
        if evaluacion is None:
            raise EvaluacionCerrada("No hay una evaluación activa a la que agregar proveedores")
        return evaluacion

    @staticmethod
    def candidatos(
        db: Session,
        empresa_id: uuid.UUID,
        buscar: str = "",
        limite: int = 30,
        *,
        es_admin: bool = True,
        empleado: Optional[Empleado] = None,
    ) -> Dict[str, Any]:
        """
        Proveedores que coinciden con la búsqueda, todos: los que ya están en la evaluación
        activa vienen marcados (y al final), así la búsqueda encuentra a cualquiera. Al
        evaluador solo le aparecen los activos que tiene asignados.
        """
        evaluacion = AsignacionService._activa(db, empresa_id)
        ya_estan = db.query(EvaluacionItem.proveedor_id).filter(
            EvaluacionItem.evaluacion_id == evaluacion.id,
            EvaluacionItem.deleted_at.is_(None),
        )
        query = db.query(RegistroProveedor).filter(
            RegistroProveedor.empresa_id == empresa_id,
            RegistroProveedor.deleted_at.is_(None),
        )
        if not es_admin:
            query = query.filter(
                RegistroProveedor.referente_empleado_id == AsignacionService._empleado_evaluador(empleado).id,
                RegistroProveedor.activo.is_(True),
            )
        if buscar.strip():
            query = query.filter(filtro_busqueda(buscar))
        total = query.count()
        en_evaluacion = RegistroProveedor.id.in_(ya_estan)
        filas = (
            query.options(joinedload(RegistroProveedor.referente_rel))
            .add_columns(en_evaluacion)
            .order_by(en_evaluacion, func.lower(RegistroProveedor.nombre))
            .limit(max(1, min(limite, 50)))
            .all()
        )
        return {
            "total": total,
            "items": [
                {
                    "id": str(p.id),
                    "nombre": p.nombre,
                    "tipo": p.tipo,
                    "activo": p.activo,
                    "cuit": p.cuit,
                    "referente": nombre_empleado(p.referente_rel),
                    "en_evaluacion": bool(esta),
                }
                for p, esta in filas
            ],
        }

    @staticmethod
    def agregar(
        db: Session,
        empresa_id: uuid.UUID,
        proveedor_ids: List[str],
        actor: Actor,
        *,
        es_admin: bool = True,
        empleado: Optional[Empleado] = None,
    ) -> List[EvaluacionItem]:
        """
        Suma varios proveedores de una vez. Primero valida todos y recién después guarda: si
        uno no se puede agregar, no entra ninguno (y el mensaje dice cuál y por qué).
        """
        evaluacion = AsignacionService._activa(db, empresa_id)
        proveedores = [
            ProveedorRegistroService.obtener(db, empresa_id, pid) for pid in dict.fromkeys(proveedor_ids)
        ]  # sin repetidos, en el orden pedido
        evaluador = None if es_admin else AsignacionService._empleado_evaluador(empleado)
        for proveedor in proveedores:
            if evaluador is not None and proveedor.referente_empleado_id != evaluador.id:
                raise NoEsEvaluador(
                    f"«{proveedor.nombre}» no te está asignado: solo podés agregar los "
                    f"proveedores que tenés como usuario referente"
                )
            if not proveedor.activo:
                raise OperacionNoPermitida(
                    f"«{proveedor.nombre}» está inactivo: para evaluarlo, primero activalo en Proveedores"
                )
            if item_de(db, evaluacion.id, proveedor.id) is not None:
                raise OperacionNoPermitida(f"«{proveedor.nombre}» ya está en la evaluación {evaluacion.periodo}")

        items = [asegurar_item(db, evaluacion, proveedor, actor) for proveedor in proveedores]
        db.commit()
        return items
