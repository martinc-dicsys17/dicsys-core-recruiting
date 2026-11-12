"""
Importación del Google Sheet a la evaluación activa (D-71, D-73, D-79).

Dos pasos:
  1. Vista previa: lee la hoja «Listado Proveedores» (columnas por el texto del
     encabezado, no por la letra), cruza cada fila con el registro y cada
     «Referente Interno» con la nómina. Queda guardada en tablas temporales.
  2. Confirmar: da de alta los proveedores nuevos, actualiza el referente solo
     en las filas que el admin dejó marcadas y agrega a la evaluación activa todos
     los proveedores del Sheet que todavía no están (los dados de baja, no). Es la
     forma de cargar la evaluación, que arranca vacía. Después la vista previa se borra.

Un alta tiene que traer los mismos datos obligatorios que el form (referente que
esté en la nómina, servicio, tipo de información, acuerdo Sí/No y, con No, la
política/NDA): si le falta alguno, la fila queda rechazada con el motivo y no entra
ni al registro ni a la evaluación. Con acuerdo Sí entra igual, pero el Sheet no
trae el archivo: el form del proveedor lo pide antes de dejar guardar.

La vista previa dice, por fila, qué pasa en el registro (alta, sin cambios, cambio de
referente, rechazada) y en la evaluación (se agrega, ya está, de baja, no entra).

Si la lectura o el encabezado fallan, no se escribe nada. Las evaluaciones
anteriores nunca se tocan (D-68).
"""

import uuid
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from backend.core import google_sheets
from backend.modules.administracion.proveedores_auditoria import Actor, registrar
from backend.modules.administracion.proveedores_comun import (
    ReferenciaInvalida,
    asegurar_item,
    datos_faltantes,
    evaluacion_activa,
    item_de,
    uuid_o_none,
)
from backend.modules.administracion.proveedores_models import (
    OPCIONES_ACUERDO,
    EvaluacionItem,
    EvaluacionProveedores,
    ImportacionFila,
    ImportacionProveedores,
    ProveedoresConfiguracion,
    RegistroProveedor,
)
from backend.modules.innovacion.licencias_utils import normalizar_nombre
from backend.modules.nomina.models import Empleado

# Dato → inicio del encabezado en la hoja (comparando sin acentos ni mayúsculas)
COLUMNAS = {
    "nombre": "razon social",
    "referente": "referente",
    "servicio_provisto": "servicio",
    "tipo_informacion": "tipo de informacion",
    "acuerdo_servicio": "hay un acuerdo",
    "politica_nda": "tiene politica",
}
OBLIGATORIAS = ("nombre", "referente")
FILAS_DE_ENCABEZADO = 10


class ErrorImportacion(ValueError):
    """No se puede importar (mensaje apto para UI, 422)."""


def _celda(fila: List[str], indice: Optional[int]) -> Optional[str]:
    if indice is None or indice >= len(fila):
        return None
    valor = (fila[indice] or "").strip()
    return valor or None


def ubicar_columnas(filas: List[List[str]]) -> Tuple[int, Dict[str, int]]:
    """(índice de la fila de encabezados, índice de cada columna) buscando en las primeras filas."""
    for numero, fila in enumerate(filas[:FILAS_DE_ENCABEZADO]):
        columnas: Dict[str, int] = {}
        for indice, celda in enumerate(fila):
            texto = normalizar_nombre(celda)
            for clave, prefijo in COLUMNAS.items():
                if clave not in columnas and texto.startswith(prefijo):
                    columnas[clave] = indice
        if "nombre" in columnas:
            faltan = [c for c in OBLIGATORIAS if c not in columnas]
            if faltan:
                raise ErrorImportacion("La hoja no tiene las columnas esperadas (falta: «Referente Interno»).")
            return numero, columnas
    raise ErrorImportacion("No se encontró la fila de encabezados («Razón Social…» y «Referente Interno»).")


class BuscadorNomina:
    """Cruza el «Referente Interno» del Sheet («Apellido Nombre») con la nómina."""

    def __init__(self, db: Session, empresa_id: uuid.UUID):
        self.empleados = [
            (e, set(normalizar_nombre(f"{e.apellido} {e.nombre}").split()))
            for e in db.query(Empleado)
            .filter(
                Empleado.empresa_id == empresa_id,
                Empleado.deleted_at.is_(None),
                Empleado.activo.is_(True),
            )
            .all()
        ]

    def buscar(self, texto: Optional[str]) -> Optional[Empleado]:
        """El único empleado cuyo nombre completo contiene todas las palabras; si hay 0 o 2+, None."""
        palabras = set(normalizar_nombre(texto).split())
        if not palabras:
            return None
        candidatos = [e for e, nombre in self.empleados if palabras <= nombre]
        return candidatos[0] if len(candidatos) == 1 else None


def _limpiar_vistas_previas(db: Session, empresa_id: uuid.UUID) -> None:
    """Las vistas previas abandonadas se borran al empezar otra."""
    for vieja in db.query(ImportacionProveedores).filter(ImportacionProveedores.empresa_id == empresa_id).all():
        db.delete(vieja)
    db.flush()


def generar_vista_previa(db: Session, empresa_id: uuid.UUID, usuario_id: Optional[uuid.UUID]) -> ImportacionProveedores:
    evaluacion = evaluacion_activa(db, empresa_id)
    if evaluacion is None:
        raise ErrorImportacion("No hay una evaluación activa: creá una antes de importar el Sheet.")
    configuracion = db.query(ProveedoresConfiguracion).filter(ProveedoresConfiguracion.empresa_id == empresa_id).first()
    if configuracion is None or not configuracion.sheet_url:
        raise ErrorImportacion("Falta configurar el link del Google Sheet en la configuración de evaluaciones.")

    try:
        filas = google_sheets.leer_hoja(configuracion.sheet_url, configuracion.sheet_hoja)
    except google_sheets.ErrorSheets as exc:
        raise ErrorImportacion(str(exc)) from exc
    encabezado, columnas = ubicar_columnas(filas)

    registro = {
        normalizar_nombre(p.nombre): p
        for p in db.query(RegistroProveedor)
        .filter(
            RegistroProveedor.empresa_id == empresa_id,
            RegistroProveedor.deleted_at.is_(None),
        )
        .all()
    }
    nomina = BuscadorNomina(db, empresa_id)

    _limpiar_vistas_previas(db, empresa_id)
    importacion = ImportacionProveedores(
        id=uuid.uuid4(), empresa_id=empresa_id, evaluacion_id=evaluacion.id, creada_por=usuario_id
    )
    db.add(importacion)
    vistos = set()
    for numero, fila in enumerate(filas[encabezado + 1 :], start=encabezado + 2):
        nombre = _celda(fila, columnas["nombre"])
        normalizado = normalizar_nombre(nombre)
        if not normalizado or normalizado in vistos:
            continue  # filas vacías y repetidas dentro del Sheet
        vistos.add(normalizado)
        referente_sheet = _celda(fila, columnas["referente"])
        referente = nomina.buscar(referente_sheet)
        existente = registro.get(normalizado)
        acuerdo = _celda(fila, columnas.get("acuerdo_servicio"))
        acuerdo = next((o for o in OPCIONES_ACUERDO if normalizar_nombre(o) == normalizar_nombre(acuerdo)), None)

        fila_importada = ImportacionFila(
            id=uuid.uuid4(),
            importacion_id=importacion.id,
            fila_sheet=numero,
            nombre=nombre[:200],
            referente_sheet=(referente_sheet or "")[:200] or None,
            referente_nuevo_id=referente.id if referente else None,
        )
        if existente is None:
            fila_importada.servicio_provisto = _celda(fila, columnas.get("servicio_provisto"))
            fila_importada.tipo_informacion = _celda(fila, columnas.get("tipo_informacion"))
            fila_importada.acuerdo_servicio = acuerdo
            fila_importada.politica_nda = _celda(fila, columnas.get("politica_nda"))
            faltan = _faltan_en_el_alta(fila_importada, referente_sheet)
            fila_importada.accion = "rechazada" if faltan else "alta"
            fila_importada.motivo = f"Falta: {', '.join(faltan)}" if faltan else None
        else:
            fila_importada.proveedor_id = existente.id
            fila_importada.referente_anterior_id = existente.referente_empleado_id
            # Un referente sin coincidencia en la nómina no borra al que ya tiene el registro
            cambia = referente is not None and referente.id != existente.referente_empleado_id
            fila_importada.accion = "cambio_referente" if cambia else "sin_cambios"
        db.add(fila_importada)
    db.commit()
    db.refresh(importacion)
    return importacion


def _faltan_en_el_alta(fila: ImportacionFila, referente_sheet: Optional[str]) -> List[str]:
    """Los datos obligatorios que no trae la fila; el referente, con el nombre que no se encontró."""
    faltan = datos_faltantes(
        referente=fila.referente_nuevo_id,
        servicio_provisto=fila.servicio_provisto,
        tipo_informacion=fila.tipo_informacion,
        acuerdo_servicio=fila.acuerdo_servicio,
        politica_nda=fila.politica_nda,
    )
    if fila.referente_nuevo_id is None and referente_sheet:
        faltan[0] = f"usuario referente («{referente_sheet}» no está en la nómina)"
    return faltan


def _de_la_empresa(db: Session, empresa_id: uuid.UUID, importacion_id) -> ImportacionProveedores:
    importacion = (
        db.query(ImportacionProveedores)
        .filter(
            ImportacionProveedores.id == uuid_o_none(importacion_id),
            ImportacionProveedores.empresa_id == empresa_id,
        )
        .first()
    )
    if importacion is None:
        raise ReferenciaInvalida("La vista previa ya no existe: volvé a importar el Sheet")
    return importacion


def obtener(db: Session, empresa_id: uuid.UUID, importacion_id) -> ImportacionProveedores:
    return _de_la_empresa(db, empresa_id, importacion_id)


def _en_la_evaluacion(db: Session, importacion: ImportacionProveedores) -> Dict[uuid.UUID, str]:
    """Qué pasa con cada proveedor ya registrado al confirmar: 'ya_esta', 'de_baja' o 'se_agrega'."""
    ids = [f.proveedor_id for f in importacion.filas if f.proveedor_id]
    if not ids:
        return {}
    ya_estan = {
        pid
        for (pid,) in db.query(EvaluacionItem.proveedor_id).filter(
            EvaluacionItem.evaluacion_id == importacion.evaluacion_id,
            EvaluacionItem.proveedor_id.in_(ids),
            EvaluacionItem.deleted_at.is_(None),
        )
    }
    de_baja = {
        pid
        for (pid,) in db.query(RegistroProveedor.id).filter(
            RegistroProveedor.id.in_(ids), RegistroProveedor.activo.is_(False)
        )
    }
    return {pid: "ya_esta" if pid in ya_estan else "de_baja" if pid in de_baja else "se_agrega" for pid in ids}


def _falta_adjunto(fila: ImportacionFila) -> bool:
    """Alta con acuerdo firmado: el Sheet no trae el archivo, se sube después desde el form."""
    return fila.accion == "alta" and fila.acuerdo_servicio == "Si"


def resumen(db: Session, importacion: ImportacionProveedores) -> Dict[str, Any]:
    ids = {f.referente_nuevo_id for f in importacion.filas} | {f.referente_anterior_id for f in importacion.filas}
    ids.discard(None)
    nombres = (
        {e.id: f"{e.apellido}, {e.nombre}" for e in db.query(Empleado).filter(Empleado.id.in_(ids)).all()}
        if ids
        else {}
    )
    evaluacion = db.get(EvaluacionProveedores, importacion.evaluacion_id)
    filas = importacion.filas
    estado = _en_la_evaluacion(db, importacion)
    # Las altas se agregan; las rechazadas no entran
    en_evaluacion = [estado.get(f.proveedor_id, "no_entra" if f.accion == "rechazada" else "se_agrega") for f in filas]
    return {
        "id": str(importacion.id),
        "evaluacion": evaluacion.periodo if evaluacion else "",
        "filas_leidas": len(filas),
        "se_agregan": en_evaluacion.count("se_agrega"),
        "ya_estan": en_evaluacion.count("ya_esta"),
        "de_baja": en_evaluacion.count("de_baja"),
        "altas": sum(1 for f in filas if f.accion == "alta"),
        "sin_cambios": sum(1 for f in filas if f.accion == "sin_cambios"),
        "cambios_referente": sum(1 for f in filas if f.accion == "cambio_referente"),
        "rechazadas": sum(1 for f in filas if f.accion == "rechazada"),
        "sin_definir": sum(1 for f in filas if f.referente_nuevo_id is None and f.accion != "rechazada"),
        "faltan_adjunto": sum(1 for f in filas if _falta_adjunto(f)),
        "filas": [
            {
                "id": str(f.id),
                "fila_sheet": f.fila_sheet,
                "nombre": f.nombre,
                "referente_sheet": f.referente_sheet,
                "accion": f.accion,
                "evaluacion": en_la_eval,
                "proveedor_id": str(f.proveedor_id) if f.proveedor_id else None,
                "referente_anterior": nombres.get(f.referente_anterior_id),
                "referente_nuevo": nombres.get(f.referente_nuevo_id),
                "confirmar": f.confirmar,
                "motivo": f.motivo,
                "falta_adjunto": _falta_adjunto(f),
            }
            for f, en_la_eval in zip(filas, en_evaluacion)
        ],
    }


def confirmar(
    db: Session, empresa_id: uuid.UUID, importacion_id, cambios_confirmados: List[str], actor: Actor
) -> Dict[str, int]:
    importacion = _de_la_empresa(db, empresa_id, importacion_id)
    evaluacion = evaluacion_activa(db, empresa_id)
    if evaluacion is None or evaluacion.id != importacion.evaluacion_id:
        raise ErrorImportacion("La evaluación de esta vista previa ya no está activa: volvé a importar el Sheet.")
    confirmados = {uuid_o_none(i) for i in cambios_confirmados}

    altas = cambios = rechazadas = 0
    proveedores: List[RegistroProveedor] = []
    for fila in importacion.filas:
        if fila.accion == "rechazada":
            rechazadas += 1
            continue
        if fila.accion == "alta":
            proveedor, creado = _alta(db, empresa_id, fila, actor)
            altas += creado
            rechazadas += proveedor is None
        else:
            proveedor = (
                db.query(RegistroProveedor)
                .filter(
                    RegistroProveedor.id == fila.proveedor_id,
                    RegistroProveedor.empresa_id == empresa_id,
                    RegistroProveedor.deleted_at.is_(None),
                )
                .first()
            )
            if proveedor is not None and fila.accion == "cambio_referente" and fila.id in confirmados:
                _cambiar_referente(db, evaluacion, proveedor, fila.referente_nuevo_id, actor)
                cambios += 1
        if proveedor is not None and proveedor.activo:
            proveedores.append(proveedor)

    db.flush()
    asignados = ya_estaban = 0
    for proveedor in proveedores:
        if item_de(db, evaluacion.id, proveedor.id) is None:
            asegurar_item(db, evaluacion, proveedor, actor)
            asignados += 1
        else:
            ya_estaban += 1

    resultado = {
        "altas": altas,
        "cambios_referente": cambios,
        "asignados": asignados,
        "ya_estaban": ya_estaban,
        "rechazadas": rechazadas,
    }
    registrar(
        db,
        empresa_id,
        actor,
        "evaluacion",
        evaluacion.id,
        "confirmar_importacion",
        evaluacion_id=evaluacion.id,
        despues={**resultado, "filas_leidas": len(importacion.filas)},
    )
    db.delete(importacion)
    db.commit()
    return resultado


def _alta(
    db: Session, empresa_id: uuid.UUID, fila: ImportacionFila, actor: Actor
) -> Tuple[Optional[RegistroProveedor], bool]:
    """
    (proveedor, si se creó). Si mientras tanto alguien lo dio de alta, usa ese. Si el
    referente dejó la nómina desde la vista previa, no lo crea: (None, False).
    """
    normalizado = normalizar_nombre(fila.nombre)
    for existente in (
        db.query(RegistroProveedor)
        .filter(
            RegistroProveedor.empresa_id == empresa_id,
            RegistroProveedor.deleted_at.is_(None),
        )
        .all()
    ):
        if normalizar_nombre(existente.nombre) == normalizado:
            return existente, False
    referente = (
        db.query(Empleado.id)
        .filter(
            Empleado.id == fila.referente_nuevo_id,
            Empleado.deleted_at.is_(None),
            Empleado.activo.is_(True),
        )
        .first()
        if fila.referente_nuevo_id
        else None
    )
    if referente is None:
        return None, False
    proveedor = RegistroProveedor(
        id=uuid.uuid4(),
        empresa_id=empresa_id,
        nombre=fila.nombre,
        tipo="sin_clasificar",
        referente_empleado_id=referente.id,
        servicio_provisto=fila.servicio_provisto,
        tipo_informacion=fila.tipo_informacion,
        acuerdo_servicio=fila.acuerdo_servicio,
        politica_nda=fila.politica_nda,
        activo=True,
        created_by=actor.email,
        updated_by=actor.email,
    )
    db.add(proveedor)
    db.flush()
    registrar(
        db,
        empresa_id,
        actor,
        "proveedor",
        proveedor.id,
        "crear",
        despues={
            "nombre": proveedor.nombre,
            "referente_empleado_id": proveedor.referente_empleado_id,
            "via": "importacion_sheet",
            "fila_sheet": fila.fila_sheet,
        },
    )
    return proveedor, True


def _cambiar_referente(db: Session, evaluacion, proveedor: RegistroProveedor, nuevo_id, actor: Actor) -> None:
    registrar(
        db,
        proveedor.empresa_id,
        actor,
        "proveedor",
        proveedor.id,
        "cambiar_referente",
        antes={"referente_empleado_id": proveedor.referente_empleado_id},
        despues={"referente_empleado_id": nuevo_id, "via": "importacion_sheet"},
    )
    proveedor.referente_empleado_id = nuevo_id
    proveedor.updated_by = actor.email
    item = item_de(db, evaluacion.id, proveedor.id)
    if item is not None and item.evaluador_empleado_id != nuevo_id:
        registrar(
            db,
            proveedor.empresa_id,
            actor,
            "item",
            item.id,
            "cambiar_evaluador",
            evaluacion_id=evaluacion.id,
            antes={"evaluador_empleado_id": item.evaluador_empleado_id},
            despues={"evaluador_empleado_id": nuevo_id},
        )
        item.evaluador_empleado_id = nuevo_id
        item.updated_by = actor.email


def cancelar(db: Session, empresa_id: uuid.UUID, importacion_id) -> None:
    db.delete(_de_la_empresa(db, empresa_id, importacion_id))
    db.commit()
