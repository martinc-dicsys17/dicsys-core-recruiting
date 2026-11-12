"""
Servicios del registro de proveedores: alta, edición, estado (activo/inactivo),
oficinas, contactos, documentos y el adjunto de política/NDA (obligatorio con acuerdo
firmado: el alta lo trae y no se puede quitar). Cada cambio queda en la auditoría
(D-67). En la evaluación activa, el cambio de referente cambia el evaluador y pasar a
inactivo saca al proveedor si estaba pendiente (D-72); el alta no lo suma (entra por el
Sheet o con «Agregar proveedor»).

Inactivo: se sigue viendo y conserva su historial (evaluaciones, documentos), pero no
entra en evaluaciones nuevas; tampoco se podrá usar en facturas o pedidos cuando esos
módulos existan.
"""

import math
import uuid
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from backend.core.utils import utc_now
from backend.modules.administracion.proveedores_auditoria import Actor, diferencias, foto, registrar
from backend.modules.administracion.proveedores_comun import (
    ReferenciaInvalida,
    evaluacion_activa,
    item_de,
    uuid_o_none,
)
from backend.modules.administracion.proveedores_models import (
    EVIDENCIAS,
    EvaluacionItem,
    EvaluacionProveedores,
    ProveedorContacto,
    ProveedorDocumento,
    ProveedorOficina,
    RegistroProveedor,
)
from backend.modules.innovacion.licencias_utils import normalizar_nombre
from backend.modules.nomina.models import Empleado

CAMPOS_PROVEEDOR = (
    "nombre",
    "razon_social",
    "cuit",
    "responsabilidad_afip",
    "nro_ingresos_brutos",
    "tipo",
    "referente_empleado_id",
    "servicio_provisto",
    "tipo_informacion",
    "email",
    "telefono_whatsapp",
    "pagina_web",
    "acuerdo_servicio",
    "politica_nda",
    "observaciones",
    "activo",
)
CAMPOS_OFICINA = (
    "nombre_oficina",
    "calle",
    "numero",
    "piso",
    "departamento",
    "localidad",
    "provincia",
    "pais",
    "codigo_postal",
    "es_legal",
)
CAMPOS_CONTACTO = ("nombre", "apellido", "cargo", "telefono", "email", "es_principal", "notas", "oficina_id")


class ProveedorDuplicado(ValueError):
    """Ya hay un proveedor vigente con ese nombre (409)."""


class OperacionNoPermitida(ValueError):
    """La acción no se puede hacer en el estado actual (409)."""


class DatosIncompletos(ValueError):
    """Falta un dato obligatorio que no se valida en el schema: el adjunto del acuerdo (422)."""


SIN_ADJUNTO = "Con acuerdo de servicio firmado hay que adjuntar el archivo del acuerdo / NDA"


def empleado_de_la_empresa(db: Session, empresa_id: uuid.UUID, empleado_id) -> Optional[Empleado]:
    """Empleado activo de la nómina de la empresa, o ReferenciaInvalida. None si no se eligió."""
    if empleado_id in (None, ""):
        return None
    empleado = (
        db.query(Empleado)
        .filter(
            Empleado.id == uuid_o_none(empleado_id),
            Empleado.empresa_id == empresa_id,
            Empleado.deleted_at.is_(None),
            Empleado.activo.is_(True),
        )
        .first()
    )
    if empleado is None:
        raise ReferenciaInvalida("El usuario referente no existe en la nómina")
    return empleado


# Búsqueda en el registro: lo que normalizar_nombre hace en Python, del lado de la base
_CON_ACENTO, _SIN_ACENTO = "áàäâéèëêíìïîóòöôúùüûñç", "aaaaeeeeiiiioooouuuunc"


def filtro_busqueda(buscar: str):
    """
    Nombre o razón social sin importar mayúsculas ni acentos («galicia» encuentra «Galicía»),
    o CUIT con o sin guiones. Lo usan el listado del registro y «Agregar» de la evaluación.
    """
    patron = f"%{normalizar_nombre(buscar)}%"

    def plegado(columna):
        return func.translate(func.lower(columna), _CON_ACENTO, _SIN_ACENTO)

    return or_(
        plegado(RegistroProveedor.nombre).like(patron),
        plegado(RegistroProveedor.razon_social).like(patron),
        func.replace(RegistroProveedor.cuit, "-", "").like(patron.replace("-", "")),
    )


class ProveedorRegistroService:
    # ─── Consultas ──────────────────────────────────────────────────────────────

    @staticmethod
    def _de_la_empresa(db: Session, empresa_id: uuid.UUID, proveedor_id) -> RegistroProveedor:
        proveedor = (
            db.query(RegistroProveedor)
            .filter(
                RegistroProveedor.id == uuid_o_none(proveedor_id),
                RegistroProveedor.empresa_id == empresa_id,
                RegistroProveedor.deleted_at.is_(None),
            )
            .first()
        )
        if proveedor is None:
            raise ReferenciaInvalida("El proveedor no existe")
        return proveedor

    @staticmethod
    def listar(
        db: Session,
        empresa_id: uuid.UUID,
        *,
        buscar: str = "",
        tipo: str = "",
        referente_id: str = "",
        sin_referente: bool = False,
        estado: str = "activos",
        pagina: int = 1,
        por_pagina: int = 20,
    ) -> Dict[str, Any]:
        base = db.query(RegistroProveedor).filter(
            RegistroProveedor.empresa_id == empresa_id,
            RegistroProveedor.deleted_at.is_(None),
        )
        metricas = {
            "activos": base.filter(RegistroProveedor.activo.is_(True)).count(),
            "sin_referente": base.filter(
                RegistroProveedor.activo.is_(True), RegistroProveedor.referente_empleado_id.is_(None)
            ).count(),
            "de_baja": base.filter(RegistroProveedor.activo.is_(False)).count(),
        }

        query = base.options(joinedload(RegistroProveedor.referente_rel))
        if estado == "activos":
            query = query.filter(RegistroProveedor.activo.is_(True))
        elif estado == "baja":
            query = query.filter(RegistroProveedor.activo.is_(False))
        if buscar.strip():
            query = query.filter(filtro_busqueda(buscar))
        if tipo:
            query = query.filter(RegistroProveedor.tipo == tipo)
        if sin_referente:
            query = query.filter(RegistroProveedor.referente_empleado_id.is_(None))
        elif referente_id:
            query = query.filter(RegistroProveedor.referente_empleado_id == uuid_o_none(referente_id))

        total = query.count()
        por_pagina = max(1, min(por_pagina, 100))
        items = (
            query.order_by(func.lower(RegistroProveedor.nombre))
            .offset((max(pagina, 1) - 1) * por_pagina)
            .limit(por_pagina)
            .all()
        )
        return {
            "items": items,
            "total": total,
            "pagina": max(pagina, 1),
            "por_pagina": por_pagina,
            "total_paginas": max(1, math.ceil(total / por_pagina)),
            "metricas": metricas,
        }

    @staticmethod
    def obtener(db: Session, empresa_id: uuid.UUID, proveedor_id) -> RegistroProveedor:
        return ProveedorRegistroService._de_la_empresa(db, empresa_id, proveedor_id)

    @staticmethod
    def historial(db: Session, proveedor: RegistroProveedor) -> List[Dict[str, Any]]:
        """Resultado del proveedor en cada campaña, de la más nueva a la más vieja."""
        filas = (
            db.query(EvaluacionItem, EvaluacionProveedores)
            .join(
                EvaluacionProveedores,
                EvaluacionProveedores.id == EvaluacionItem.evaluacion_id,
            )
            .options(joinedload(EvaluacionItem.evaluador))
            .filter(
                EvaluacionItem.proveedor_id == proveedor.id,
                EvaluacionItem.deleted_at.is_(None),
                EvaluacionProveedores.deleted_at.is_(None),
            )
            .order_by(EvaluacionProveedores.fecha_apertura.desc())
            .all()
        )
        return [
            {
                "evaluacion_id": str(evaluacion.id),
                "periodo": evaluacion.periodo,
                "evaluador": (f"{item.evaluador.apellido}, {item.evaluador.nombre}" if item.evaluador else None),
                "incidentes": item.incidentes,
                "mal_manejo": item.mal_manejo,
                **{campo: getattr(item, campo) for campo in EVIDENCIAS},
                "con_hallazgo": bool(item.con_hallazgo),
                "evaluado_at": item.evaluado_at,
            }
            for item, evaluacion in filas
        ]

    @staticmethod
    def buscar_empleados(db: Session, empresa_id: uuid.UUID, buscar: str = "", limite: int = 20) -> List[Empleado]:
        """Empleados activos de la nómina para elegir el usuario referente."""
        query = db.query(Empleado).filter(
            Empleado.empresa_id == empresa_id,
            Empleado.deleted_at.is_(None),
            Empleado.activo.is_(True),
        )
        for palabra in buscar.split():
            patron = f"%{palabra}%"
            query = query.filter(or_(Empleado.nombre.ilike(patron), Empleado.apellido.ilike(patron)))
        return query.order_by(Empleado.apellido, Empleado.nombre).limit(max(1, min(limite, 50))).all()

    # ─── Alta y edición ─────────────────────────────────────────────────────────

    @staticmethod
    def _validar_nombre(
        db: Session, empresa_id: uuid.UUID, nombre: str, excluir_id: Optional[uuid.UUID] = None
    ) -> None:
        """Rechaza un nombre que ya usa otro proveedor vigente, comparando sin acentos."""
        normalizado = normalizar_nombre(nombre)
        query = db.query(RegistroProveedor.id, RegistroProveedor.nombre).filter(
            RegistroProveedor.empresa_id == empresa_id,
            RegistroProveedor.deleted_at.is_(None),
        )
        if excluir_id is not None:
            query = query.filter(RegistroProveedor.id != excluir_id)
        for _, existente in query.all():
            if normalizar_nombre(existente) == normalizado:
                raise ProveedorDuplicado(f"Ya existe el proveedor «{existente}»")

    @staticmethod
    def _confirmar(db: Session) -> None:
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise ProveedorDuplicado("Ya existe un proveedor con ese nombre") from exc

    @staticmethod
    def crear(
        db: Session,
        empresa_id: uuid.UUID,
        datos: Dict[str, Any],
        actor: Actor,
        adjunto: Optional[Tuple[str, str]] = None,
    ) -> RegistroProveedor:
        """`adjunto` = (clave en el storage, nombre del archivo): obligatorio con acuerdo firmado."""
        if datos.get("acuerdo_servicio") == "Si" and adjunto is None:
            raise DatosIncompletos(SIN_ADJUNTO)
        ProveedorRegistroService._validar_nombre(db, empresa_id, datos["nombre"])
        referente = empleado_de_la_empresa(db, empresa_id, datos.get("referente_empleado_id"))
        proveedor = RegistroProveedor(
            id=uuid.uuid4(), empresa_id=empresa_id, created_by=actor.email, updated_by=actor.email, activo=True
        )
        for campo in CAMPOS_PROVEEDOR:
            if campo in ("referente_empleado_id", "activo"):
                continue
            setattr(proveedor, campo, datos.get(campo))
        proveedor.tipo = datos.get("tipo") or "sin_clasificar"
        proveedor.referente_empleado_id = referente.id if referente else None
        if adjunto is not None:
            proveedor.politica_nda_archivo, proveedor.politica_nda_archivo_nombre = adjunto
        db.add(proveedor)
        despues = foto(proveedor, CAMPOS_PROVEEDOR)
        if adjunto is not None:
            despues["politica_nda_archivo_nombre"] = proveedor.politica_nda_archivo_nombre
        registrar(db, empresa_id, actor, "proveedor", proveedor.id, "crear", despues=despues)
        # No entra solo a la evaluación activa: se suma con «Agregar proveedor» o desde el Sheet
        ProveedorRegistroService._confirmar(db)
        db.refresh(proveedor)
        return proveedor

    @staticmethod
    def actualizar(
        db: Session, empresa_id: uuid.UUID, proveedor_id, datos: Dict[str, Any], actor: Actor
    ) -> RegistroProveedor:
        proveedor = ProveedorRegistroService._de_la_empresa(db, empresa_id, proveedor_id)
        # El adjunto se sube antes de guardar, desde la misma pantalla
        if datos.get("acuerdo_servicio") == "Si" and not proveedor.politica_nda_archivo:
            raise DatosIncompletos(SIN_ADJUNTO)
        ProveedorRegistroService._validar_nombre(db, empresa_id, datos["nombre"], excluir_id=proveedor.id)
        referente = empleado_de_la_empresa(db, empresa_id, datos.get("referente_empleado_id"))
        antes = foto(proveedor, CAMPOS_PROVEEDOR)

        for campo in CAMPOS_PROVEEDOR:
            if campo in ("referente_empleado_id", "activo"):
                continue
            setattr(proveedor, campo, datos.get(campo))
        proveedor.tipo = datos.get("tipo") or "sin_clasificar"
        proveedor.referente_empleado_id = referente.id if referente else None
        proveedor.updated_by = actor.email
        ProveedorRegistroService._propagar_referente(db, proveedor, actor)

        cambios_antes, cambios_despues = diferencias(antes, foto(proveedor, CAMPOS_PROVEEDOR))
        if cambios_despues:
            registrar(
                db, empresa_id, actor, "proveedor", proveedor.id, "editar", antes=cambios_antes, despues=cambios_despues
            )
        # Estado elegido en la edición (None = no se tocó): queda como baja o reactivación
        if datos.get("activo") is not None and datos["activo"] != proveedor.activo:
            ProveedorRegistroService._cambiar_estado(db, proveedor, datos["activo"], actor)
        ProveedorRegistroService._confirmar(db)
        db.refresh(proveedor)
        return proveedor

    @staticmethod
    def _propagar_referente(db: Session, proveedor: RegistroProveedor, actor: Actor) -> None:
        """El cambio de referente alcanza a la evaluación activa; las anteriores no se tocan."""
        evaluacion = evaluacion_activa(db, proveedor.empresa_id)
        if evaluacion is None:
            return
        item = item_de(db, evaluacion.id, proveedor.id)
        if item is None or item.evaluador_empleado_id == proveedor.referente_empleado_id:
            return
        registrar(
            db,
            proveedor.empresa_id,
            actor,
            "item",
            item.id,
            "cambiar_evaluador",
            evaluacion_id=evaluacion.id,
            antes={"evaluador_empleado_id": item.evaluador_empleado_id},
            despues={"evaluador_empleado_id": proveedor.referente_empleado_id},
        )
        item.evaluador_empleado_id = proveedor.referente_empleado_id
        item.updated_by = actor.email

    # ─── Baja, reactivación y eliminación ───────────────────────────────────────

    @staticmethod
    def _cambiar_estado(db: Session, proveedor: RegistroProveedor, activo: bool, actor: Actor) -> None:
        """
        Inactivo: sale de las próximas evaluaciones y de la activa solo si estaba pendiente
        (lo ya evaluado se conserva). Activo: vuelve a poder usarse para todo.
        """
        proveedor.activo = activo
        proveedor.updated_by = actor.email
        registrar(
            db,
            proveedor.empresa_id,
            actor,
            "proveedor",
            proveedor.id,
            "reactivar" if activo else "baja",
            antes={"activo": not activo},
            despues={"activo": activo},
        )
        if not activo:
            ProveedorRegistroService._quitar_de_la_activa_si_pendiente(db, proveedor, actor)

    @staticmethod
    def dar_de_baja(db: Session, empresa_id: uuid.UUID, proveedor_id, actor: Actor) -> RegistroProveedor:
        """Pasa a inactivo (desde el listado)."""
        proveedor = ProveedorRegistroService._de_la_empresa(db, empresa_id, proveedor_id)
        if proveedor.activo:
            ProveedorRegistroService._cambiar_estado(db, proveedor, False, actor)
            db.commit()
            db.refresh(proveedor)
        return proveedor

    @staticmethod
    def reactivar(db: Session, empresa_id: uuid.UUID, proveedor_id, actor: Actor) -> RegistroProveedor:
        """Pasa a activo (desde el listado)."""
        proveedor = ProveedorRegistroService._de_la_empresa(db, empresa_id, proveedor_id)
        if not proveedor.activo:
            ProveedorRegistroService._cambiar_estado(db, proveedor, True, actor)
            db.commit()
            db.refresh(proveedor)
        return proveedor

    @staticmethod
    def eliminar(db: Session, empresa_id: uuid.UUID, proveedor_id, actor: Actor) -> None:
        """Baja lógica definitiva: solo si nunca fue evaluado (si no, queda la baja)."""
        proveedor = ProveedorRegistroService._de_la_empresa(db, empresa_id, proveedor_id)
        evaluado = (
            db.query(EvaluacionItem.id)
            .filter(
                EvaluacionItem.proveedor_id == proveedor.id,
                EvaluacionItem.deleted_at.is_(None),
                EvaluacionItem.evaluado_at.isnot(None),
            )
            .first()
        )
        if evaluado:
            raise OperacionNoPermitida(
                "El proveedor ya tiene evaluaciones: no se puede eliminar, pero se puede pasar a Inactivo"
            )
        ahora = utc_now()
        ProveedorRegistroService._quitar_de_la_activa_si_pendiente(db, proveedor, actor)
        for hijo in list(proveedor.oficinas) + list(proveedor.contactos) + list(proveedor.documentos):
            hijo.deleted_at = ahora
            hijo.updated_by = actor.email
        proveedor.deleted_at = ahora
        proveedor.updated_by = actor.email
        registrar(db, empresa_id, actor, "proveedor", proveedor.id, "eliminar", antes=foto(proveedor, CAMPOS_PROVEEDOR))
        db.commit()

    @staticmethod
    def _quitar_de_la_activa_si_pendiente(db: Session, proveedor: RegistroProveedor, actor: Actor) -> None:
        evaluacion = evaluacion_activa(db, proveedor.empresa_id)
        if evaluacion is None:
            return
        item = item_de(db, evaluacion.id, proveedor.id)
        if item is None or item.evaluado_at is not None:
            return
        item.deleted_at = utc_now()
        item.updated_by = actor.email
        registrar(
            db,
            proveedor.empresa_id,
            actor,
            "item",
            item.id,
            "quitar",
            evaluacion_id=evaluacion.id,
            antes={"proveedor_id": proveedor.id},
        )

    # ─── Adjunto de política/NDA (D-84) ─────────────────────────────────────────

    @staticmethod
    def guardar_nda(db: Session, empresa_id: uuid.UUID, proveedor_id, clave: str, nombre: str, actor: Actor) -> tuple:
        """Asocia el adjunto y devuelve (proveedor, clave anterior para borrar del storage)."""
        proveedor = ProveedorRegistroService._de_la_empresa(db, empresa_id, proveedor_id)
        anterior = proveedor.politica_nda_archivo
        registrar(
            db,
            empresa_id,
            actor,
            "proveedor",
            proveedor.id,
            "adjuntar_nda",
            antes={"politica_nda_archivo_nombre": proveedor.politica_nda_archivo_nombre},
            despues={"politica_nda_archivo_nombre": nombre},
        )
        proveedor.politica_nda_archivo = clave
        proveedor.politica_nda_archivo_nombre = nombre
        proveedor.updated_by = actor.email
        db.commit()
        db.refresh(proveedor)
        return proveedor, anterior

    @staticmethod
    def quitar_nda(db: Session, empresa_id: uuid.UUID, proveedor_id, actor: Actor) -> Optional[str]:
        proveedor = ProveedorRegistroService._de_la_empresa(db, empresa_id, proveedor_id)
        anterior = proveedor.politica_nda_archivo
        if anterior is None:
            return None
        if proveedor.acuerdo_servicio == "Si":
            raise OperacionNoPermitida(
                "Con acuerdo de servicio firmado el adjunto es obligatorio: reemplazalo "
                "por otro, o guardá primero el acuerdo en «No» con la política/NDA"
            )
        registrar(
            db,
            empresa_id,
            actor,
            "proveedor",
            proveedor.id,
            "quitar_nda",
            antes={"politica_nda_archivo_nombre": proveedor.politica_nda_archivo_nombre},
        )
        proveedor.politica_nda_archivo = None
        proveedor.politica_nda_archivo_nombre = None
        proveedor.updated_by = actor.email
        db.commit()
        return anterior


class DocumentoService:
    """
    Documentos de la pestaña Documentos. El router sube el archivo y su miniatura al
    storage; acá se registran (todos o ninguno) y se dan de baja. Se pueden subir y
    borrar también con el proveedor inactivo: no cambian su estado ni su historial.
    """

    @staticmethod
    def _de_proveedor(db: Session, empresa_id: uuid.UUID, proveedor_id, documento_id) -> ProveedorDocumento:
        documento = (
            db.query(ProveedorDocumento)
            .filter(
                ProveedorDocumento.id == uuid_o_none(documento_id),
                ProveedorDocumento.proveedor_id == uuid_o_none(proveedor_id),
                ProveedorDocumento.empresa_id == empresa_id,
                ProveedorDocumento.deleted_at.is_(None),
            )
            .first()
        )
        if documento is None:
            raise ReferenciaInvalida("El documento no existe")
        return documento

    @staticmethod
    def obtener(db: Session, empresa_id: uuid.UUID, proveedor_id, documento_id) -> ProveedorDocumento:
        return DocumentoService._de_proveedor(db, empresa_id, proveedor_id, documento_id)

    @staticmethod
    def registrar_subidos(
        db: Session, empresa_id: uuid.UUID, proveedor: RegistroProveedor, subidos: List[Dict[str, Any]], actor: Actor
    ) -> List[ProveedorDocumento]:
        """`subidos`: id, nombre, clave, tipo_mime, tamano y miniatura_clave de cada archivo ya en el storage."""
        documentos = []
        for datos in subidos:
            documento = ProveedorDocumento(
                empresa_id=empresa_id,
                proveedor_id=proveedor.id,
                created_by=actor.email,
                updated_by=actor.email,
                **datos,
            )
            db.add(documento)
            registrar(
                db,
                empresa_id,
                actor,
                "documento",
                documento.id,
                "subir",
                despues={"proveedor_id": proveedor.id, "nombre": documento.nombre, "tamano": documento.tamano},
            )
            documentos.append(documento)
        db.commit()
        for documento in documentos:
            db.refresh(documento)
        return documentos

    @staticmethod
    def eliminar(db: Session, empresa_id: uuid.UUID, proveedor_id, documento_id, actor: Actor) -> List[str]:
        """Baja lógica; devuelve las claves (documento y miniatura) para borrar del storage."""
        documento = DocumentoService._de_proveedor(db, empresa_id, proveedor_id, documento_id)
        documento.deleted_at = utc_now()
        documento.updated_by = actor.email
        registrar(
            db,
            empresa_id,
            actor,
            "documento",
            documento.id,
            "eliminar",
            antes={"proveedor_id": documento.proveedor_id, "nombre": documento.nombre},
        )
        db.commit()
        return [clave for clave in (documento.clave, documento.miniatura_clave) if clave]


class OficinaService:
    @staticmethod
    def _de_la_empresa(db: Session, empresa_id: uuid.UUID, proveedor_id, oficina_id) -> ProveedorOficina:
        oficina = (
            db.query(ProveedorOficina)
            .filter(
                ProveedorOficina.id == uuid_o_none(oficina_id),
                ProveedorOficina.proveedor_id == uuid_o_none(proveedor_id),
                ProveedorOficina.empresa_id == empresa_id,
                ProveedorOficina.deleted_at.is_(None),
            )
            .first()
        )
        if oficina is None:
            raise ReferenciaInvalida("La oficina no existe")
        return oficina

    @staticmethod
    def _unico_legal(db: Session, oficina: ProveedorOficina, es_legal: bool, actor: Actor) -> None:
        """Marca o desmarca la oficina como domicilio legal; si la marca, las demás dejan de serlo (uno por proveedor).

        Las demás se desmarcan y se escriben antes de marcar esta: el índice único parcial se chequea fila por fila y
        SQLAlchemy ordena los UPDATE por clave primaria, así que marcar primero fallaba según el orden de los ids.
        """
        if es_legal:
            otras = (
                db.query(ProveedorOficina)
                .filter(
                    ProveedorOficina.proveedor_id == oficina.proveedor_id,
                    ProveedorOficina.id != oficina.id,
                    ProveedorOficina.es_legal.is_(True),
                    ProveedorOficina.deleted_at.is_(None),
                )
                .all()
            )
            for otra in otras:
                otra.es_legal = False
                otra.updated_by = actor.email
            if otras:
                db.flush()
        oficina.es_legal = es_legal

    @staticmethod
    def crear(
        db: Session, empresa_id: uuid.UUID, proveedor_id, datos: Dict[str, Any], actor: Actor
    ) -> ProveedorOficina:
        proveedor = ProveedorRegistroService._de_la_empresa(db, empresa_id, proveedor_id)
        oficina = ProveedorOficina(
            id=uuid.uuid4(),
            empresa_id=empresa_id,
            proveedor_id=proveedor.id,
            created_by=actor.email,
            updated_by=actor.email,
            **{c: datos.get(c) for c in CAMPOS_OFICINA},
        )
        OficinaService._unico_legal(db, oficina, bool(datos.get("es_legal")), actor)
        db.add(oficina)
        registrar(db, empresa_id, actor, "oficina", oficina.id, "crear", despues=foto(oficina, CAMPOS_OFICINA))
        db.commit()
        db.refresh(oficina)
        return oficina

    @staticmethod
    def actualizar(
        db: Session, empresa_id: uuid.UUID, proveedor_id, oficina_id, datos: Dict[str, Any], actor: Actor
    ) -> ProveedorOficina:
        oficina = OficinaService._de_la_empresa(db, empresa_id, proveedor_id, oficina_id)
        antes = foto(oficina, CAMPOS_OFICINA)
        for campo in CAMPOS_OFICINA:
            if campo != "es_legal":  # la marca la pone _unico_legal, después de desmarcar las demás
                setattr(oficina, campo, datos.get(campo))
        oficina.updated_by = actor.email
        OficinaService._unico_legal(db, oficina, bool(datos.get("es_legal")), actor)
        cambios_antes, cambios_despues = diferencias(antes, foto(oficina, CAMPOS_OFICINA))
        if cambios_despues:
            registrar(
                db, empresa_id, actor, "oficina", oficina.id, "editar", antes=cambios_antes, despues=cambios_despues
            )
        db.commit()
        db.refresh(oficina)
        return oficina

    @staticmethod
    def eliminar(db: Session, empresa_id: uuid.UUID, proveedor_id, oficina_id, actor: Actor) -> None:
        oficina = OficinaService._de_la_empresa(db, empresa_id, proveedor_id, oficina_id)
        oficina.deleted_at = utc_now()
        oficina.updated_by = actor.email
        # Los contactos que trabajaban ahí quedan sin oficina
        db.query(ProveedorContacto).filter(ProveedorContacto.oficina_id == oficina.id).update(
            {ProveedorContacto.oficina_id: None}, synchronize_session=False
        )
        registrar(db, empresa_id, actor, "oficina", oficina.id, "eliminar", antes=foto(oficina, CAMPOS_OFICINA))
        db.commit()


class ContactoService:
    @staticmethod
    def _de_la_empresa(db: Session, empresa_id: uuid.UUID, proveedor_id, contacto_id) -> ProveedorContacto:
        contacto = (
            db.query(ProveedorContacto)
            .filter(
                ProveedorContacto.id == uuid_o_none(contacto_id),
                ProveedorContacto.proveedor_id == uuid_o_none(proveedor_id),
                ProveedorContacto.empresa_id == empresa_id,
                ProveedorContacto.deleted_at.is_(None),
            )
            .first()
        )
        if contacto is None:
            raise ReferenciaInvalida("El contacto no existe")
        return contacto

    @staticmethod
    def _aplicar(
        db: Session, empresa_id: uuid.UUID, contacto: ProveedorContacto, datos: Dict[str, Any], actor: Actor
    ) -> None:
        oficina_id = datos.get("oficina_id")
        if oficina_id:
            oficina_id = OficinaService._de_la_empresa(db, empresa_id, contacto.proveedor_id, oficina_id).id
        for campo in CAMPOS_CONTACTO:
            if campo not in ("oficina_id", "es_principal"):  # la marca va al final, después de desmarcar los otros
                setattr(contacto, campo, datos.get(campo))
        contacto.oficina_id = oficina_id or None
        es_principal = bool(datos.get("es_principal"))
        if es_principal:
            # Uno solo principal por proveedor. Los otros se desmarcan y se escriben antes de marcar este: el índice
            # único parcial se chequea fila por fila y los UPDATE salen en orden de clave primaria (ver _unico_legal).
            otros = (
                db.query(ProveedorContacto)
                .filter(
                    ProveedorContacto.proveedor_id == contacto.proveedor_id,
                    ProveedorContacto.id != contacto.id,
                    ProveedorContacto.es_principal.is_(True),
                    ProveedorContacto.deleted_at.is_(None),
                )
                .all()
            )
            for otro in otros:
                otro.es_principal = False
                otro.updated_by = actor.email
            if otros:
                db.flush()
        contacto.es_principal = es_principal

    @staticmethod
    def crear(
        db: Session, empresa_id: uuid.UUID, proveedor_id, datos: Dict[str, Any], actor: Actor
    ) -> ProveedorContacto:
        proveedor = ProveedorRegistroService._de_la_empresa(db, empresa_id, proveedor_id)
        contacto = ProveedorContacto(
            id=uuid.uuid4(),
            empresa_id=empresa_id,
            proveedor_id=proveedor.id,
            created_by=actor.email,
            updated_by=actor.email,
        )
        ContactoService._aplicar(db, empresa_id, contacto, datos, actor)
        db.add(contacto)
        registrar(db, empresa_id, actor, "contacto", contacto.id, "crear", despues=foto(contacto, CAMPOS_CONTACTO))
        db.commit()
        db.refresh(contacto)
        return contacto

    @staticmethod
    def actualizar(
        db: Session, empresa_id: uuid.UUID, proveedor_id, contacto_id, datos: Dict[str, Any], actor: Actor
    ) -> ProveedorContacto:
        contacto = ContactoService._de_la_empresa(db, empresa_id, proveedor_id, contacto_id)
        antes = foto(contacto, CAMPOS_CONTACTO)
        ContactoService._aplicar(db, empresa_id, contacto, datos, actor)
        contacto.updated_by = actor.email
        cambios_antes, cambios_despues = diferencias(antes, foto(contacto, CAMPOS_CONTACTO))
        if cambios_despues:
            registrar(
                db, empresa_id, actor, "contacto", contacto.id, "editar", antes=cambios_antes, despues=cambios_despues
            )
        db.commit()
        db.refresh(contacto)
        return contacto

    @staticmethod
    def eliminar(db: Session, empresa_id: uuid.UUID, proveedor_id, contacto_id, actor: Actor) -> None:
        contacto = ContactoService._de_la_empresa(db, empresa_id, proveedor_id, contacto_id)
        contacto.deleted_at = utc_now()
        contacto.updated_by = actor.email
        registrar(db, empresa_id, actor, "contacto", contacto.id, "eliminar", antes=foto(contacto, CAMPOS_CONTACTO))
        db.commit()
