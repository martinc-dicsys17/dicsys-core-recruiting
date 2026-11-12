"""
Servicios para el módulo de Recibos de Sueldo.

- LoteReciboService: CRUD de lotes con soft delete en cascada, reprocesamiento
- ReciboService: Listado por lote/empleado, obtener, firmar duplicado
"""

import logging
import math
import uuid
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from backend.core.storage import cloud_storage
from backend.core.utils import utc_now
from backend.modules.recibos.models import LoteRecibo, Recibo, ReciboLog
from backend.modules.recibos.pdf_service import PDFService, slug_tipo_liquidacion

logger = logging.getLogger(__name__)


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


# ─── LoteReciboService ────────────────────────────────────────────────────────


class LoteReciboService:
    """Servicio para operaciones CRUD de Lotes de Recibos."""

    @staticmethod
    def crear(
        db: Session,
        empresa_id: uuid.UUID,
        datos: Dict[str, Any],
        archivo_original_path: str,
        archivo_nombre: str,
        usuario: str = None,
    ) -> LoteRecibo:
        """Crea un nuevo lote de recibos con estado 'pendiente'."""
        datos = limpiar_datos(datos)

        lote = LoteRecibo(
            empresa_id=empresa_id,
            periodo=datos["periodo"],
            tipo_liquidacion=datos["tipo_liquidacion"],
            estado="pendiente",
            archivo_original=archivo_original_path,
            archivo_nombre=archivo_nombre,
            updated_by=usuario,
        )
        db.add(lote)
        db.commit()
        db.refresh(lote)
        return lote

    @staticmethod
    def buscar_activo(
        db: Session,
        empresa_id: uuid.UUID,
        periodo: str,
        tipo_liquidacion: str,
    ) -> Optional[LoteRecibo]:
        """Busca un lote activo de la misma empresa, período y tipo.

        Compara por slug y no por string crudo: 'SAC' y 'Sac ' son valores
        distintos pero comparten carpeta de storage, así que colisionarían
        igual. La regla de duplicado tiene que coincidir con la de colisión.
        """
        slug_buscado = slug_tipo_liquidacion(tipo_liquidacion)
        lotes = (
            db.query(LoteRecibo)
            .filter(
                LoteRecibo.empresa_id == empresa_id,
                LoteRecibo.periodo == periodo,
                LoteRecibo.deleted_at.is_(None),
            )
            .all()
        )
        for lote in lotes:
            if slug_tipo_liquidacion(lote.tipo_liquidacion) == slug_buscado:
                return lote
        return None

    @staticmethod
    def listar(db: Session, empresa_id: uuid.UUID, pagina: int = 1, por_pagina: int = 20, filtros: Dict = None) -> Dict:
        """Lista lotes paginados, filtrable por periodo, estado, tipo_liquidacion."""
        query = db.query(LoteRecibo).filter(LoteRecibo.deleted_at.is_(None), LoteRecibo.empresa_id == empresa_id)

        if filtros:
            if filtros.get("periodo"):
                query = query.filter(LoteRecibo.periodo == filtros["periodo"])
            if filtros.get("estado"):
                query = query.filter(LoteRecibo.estado == filtros["estado"])
            if filtros.get("tipo_liquidacion"):
                query = query.filter(LoteRecibo.tipo_liquidacion == filtros["tipo_liquidacion"])

        total = query.count()
        items = query.order_by(LoteRecibo.created_at.desc()).offset((pagina - 1) * por_pagina).limit(por_pagina).all()

        return {
            "items": items,
            "total": total,
            "pagina": pagina,
            "por_pagina": por_pagina,
            "total_paginas": math.ceil(total / por_pagina) or 1,
        }

    @staticmethod
    def obtener(db: Session, empresa_id: uuid.UUID, id: str) -> Optional[LoteRecibo]:
        """Obtiene un lote por ID, filtrado por empresa_id y deleted_at IS NULL."""
        try:
            return (
                db.query(LoteRecibo)
                .filter(
                    LoteRecibo.id == uuid.UUID(id), LoteRecibo.deleted_at.is_(None), LoteRecibo.empresa_id == empresa_id
                )
                .first()
            )
        except ValueError:
            return None

    @staticmethod
    def eliminar(db: Session, empresa_id: uuid.UUID, id: str) -> bool:
        """Soft delete de un lote y todos sus recibos (cascada)."""
        lote = LoteReciboService.obtener(db, empresa_id, id)
        if not lote:
            return False

        ahora = utc_now()
        lote.deleted_at = ahora

        # Soft delete en cascada de todos los recibos del lote
        db.query(Recibo).filter(Recibo.lote_id == lote.id, Recibo.deleted_at.is_(None)).update({"deleted_at": ahora})

        db.commit()
        return True

    @staticmethod
    def reprocesar(db: Session, empresa_id: uuid.UUID, id: str, pdf_bytes: bytes, empresa_cuit: str) -> LoteRecibo:
        """Reprocesa un lote: elimina recibos existentes y re-ejecuta el parsing."""
        lote = LoteReciboService.obtener(db, empresa_id, id)
        if not lote:
            raise ValueError("Lote no encontrado")

        # Soft delete de los recibos existentes del lote (preserva logs/auditoría)
        ahora = utc_now()
        db.query(Recibo).filter(Recibo.lote_id == lote.id, Recibo.deleted_at.is_(None)).update({"deleted_at": ahora})
        db.flush()

        # Re-ejecutar procesamiento
        resultado = PDFService.procesar_pdf_masivo(
            pdf_bytes=pdf_bytes,
            empresa_id=str(empresa_id),
            empresa_cuit=empresa_cuit,
            periodo=lote.periodo,
            tipo_liquidacion=lote.tipo_liquidacion,
            lote_id=str(lote.id),
            db=db,
        )

        # Actualizar lote con resultados
        LoteReciboService.actualizar_estado(db, lote, resultado)

        return lote

    @staticmethod
    def actualizar_recibos(
        db: Session,
        empresa_id: uuid.UUID,
        id: str,
        pdf_bytes: bytes,
        empresa_cuit: str,
    ) -> Dict[str, Any]:
        """
        Actualiza recibos específicos de un lote a partir de un PDF parcial.

        El PDF debe contener solo los recibos a actualizar, con la misma estructura
        que el lote: si el lote trae pares duplicado→original, el parche también;
        si trae una hoja por empleado, el parche también. Para cada CUIL detectado:
          1) Se eliminan en forma definitiva (hard delete) los recibos existentes
             del lote con ese CUIL, junto con sus logs de actividad.
          2) Se crean los nuevos recibos a partir del PDF parcial.

        Recalcula totales del lote y agrega los nuevos warnings al detalle de errores.
        """
        from io import BytesIO

        from pypdf import PdfReader

        lote = LoteReciboService.obtener(db, empresa_id, id)
        if not lote:
            raise ValueError("Lote no encontrado")

        # 1) Pre-parsear CUILs del PDF nuevo para saber qué reemplazar
        try:
            reader = PdfReader(BytesIO(pdf_bytes))
        except Exception:
            raise ValueError("El archivo no es un PDF válido")

        cuils_por_pagina = [PDFService.extraer_cuil_de_texto(page.extract_text() or "") for page in reader.pages]
        cuils_en_pdf = {cuil for cuil in cuils_por_pagina if cuil}

        if not cuils_en_pdf:
            raise ValueError("No se detectaron CUILs válidos en el PDF a actualizar")

        # 2) El parche tiene que traer la misma estructura que el lote: si el lote
        #    tiene duplicados y el parche no (o al revés), el paso siguiente borra
        #    recibos reales y los recrea mal. Se compara contra lo que hay guardado.
        lote_con_duplicados = (
            db.query(Recibo.id)
            .filter(
                Recibo.lote_id == lote.id,
                Recibo.empresa_id == empresa_id,
                Recibo.archivo_duplicado.isnot(None),
            )
            .first()
            is not None
        )

        if lote_con_duplicados != PDFService.lote_tiene_duplicados(cuils_por_pagina):
            con, sin = ("el lote", "el PDF") if lote_con_duplicados else ("el PDF", "el lote")
            raise ValueError(
                f"El PDF a actualizar no tiene la misma estructura que el lote: {con} trae duplicados y {sin} no"
            )

        # 3) Hard delete de recibos existentes (y sus logs) con esos CUILs en el lote
        recibos_a_borrar = (
            db.query(Recibo)
            .filter(
                Recibo.lote_id == lote.id,
                Recibo.empresa_id == empresa_id,
                Recibo.cuil_extraido.in_(cuils_en_pdf),
            )
            .all()
        )

        cuils_borrados = set()
        archivos_borrados = []
        for r in recibos_a_borrar:
            cuils_borrados.add(r.cuil_extraido)
            # Eliminar archivos del storage (best-effort)
            for key in (r.archivo_original, r.archivo_duplicado, r.archivo_firmado):
                if not key:
                    continue
                try:
                    cloud_storage.delete(key)
                    archivos_borrados.append(key)
                except Exception as e:
                    logger.warning(f"No se pudo eliminar archivo {key}: {e}")
            # Eliminar logs
            db.query(ReciboLog).filter(ReciboLog.recibo_id == r.id).delete(synchronize_session=False)
            db.delete(r)
        db.flush()

        # 4) Limpiar de errores_detalle los warnings/errores asociados a esos CUILs
        errores_actuales = list(lote.errores_detalle or [])
        errores_filtrados = [
            e for e in errores_actuales if str(e.get("cuil") or "") not in {str(c) for c in cuils_en_pdf}
        ]

        # 5) Procesar PDF nuevo (crea nuevos Recibo + logs de creación)
        resultado = PDFService.procesar_pdf_masivo(
            pdf_bytes=pdf_bytes,
            empresa_id=str(empresa_id),
            empresa_cuit=empresa_cuit,
            periodo=lote.periodo,
            tipo_liquidacion=lote.tipo_liquidacion,
            lote_id=str(lote.id),
            db=db,
        )

        # 6) Recalcular totales reales del lote desde DB
        total_recibos = (
            db.query(Recibo)
            .filter(
                Recibo.lote_id == lote.id,
                Recibo.deleted_at.is_(None),
            )
            .count()
        )

        nuevos_errores = resultado.get("errores", []) or []
        errores_combinados = errores_filtrados + nuevos_errores
        errores_reales = [e for e in errores_combinados if not str(e.get("tipo", "")).startswith("warning_")]

        lote.total_recibos = total_recibos
        lote.total_errores = len(errores_reales)
        lote.errores_detalle = errores_combinados
        lote.estado = "procesado_con_errores" if errores_reales else "procesado"
        lote.updated_at = utc_now()
        db.commit()
        db.refresh(lote)

        return {
            "lote": lote,
            "cuils_actualizados": sorted(cuils_borrados),
            "recibos_creados": resultado.get("recibos_creados", []),
            "recibos_eliminados": len(recibos_a_borrar),
        }

    @staticmethod
    def avisos_vigentes(db: Session, empresa_id: uuid.UUID, lote: LoteRecibo) -> list:
        """Filtra de `errores_detalle` los avisos que ya no aplican.

        `errores_detalle` es la foto del momento del procesamiento. Los errores
        del PDF (páginas sin CUIL, pares rotos) son hechos inmutables, pero
        'no se encontró empleado en nómina' es una condición que se verifica
        contra la nómina de hoy: si el empleado se dio de alta después de cargar
        el lote, el aviso dejó de ser cierto y no tiene sentido mostrarlo.

        Se resuelve en lectura y no se reescribe la columna: el JSON queda como
        registro de lo que pasó al procesar, y lo que se muestra es lo que sigue
        pendiente.
        """
        avisos = list(lote.errores_detalle or [])
        if not avisos:
            return []

        cuils_sin_empleado = {
            str(a.get("cuil")) for a in avisos if a.get("tipo") == "warning_sin_empleado" and a.get("cuil")
        }
        if not cuils_sin_empleado:
            return avisos

        from backend.modules.nomina.models import Empleado

        resueltos = {
            str(cuil)
            for (cuil,) in db.query(Empleado.cuil)
            .filter(
                Empleado.cuil.in_([int(c) for c in cuils_sin_empleado if c.isdigit()]),
                Empleado.empresa_id == empresa_id,
                Empleado.deleted_at.is_(None),
            )
            .all()
        }
        if not resueltos:
            return avisos

        return [a for a in avisos if not (a.get("tipo") == "warning_sin_empleado" and str(a.get("cuil")) in resueltos)]

    @staticmethod
    def actualizar_estado(db: Session, lote: LoteRecibo, resultado: Dict[str, Any]) -> None:
        """Actualiza el lote con los resultados del procesamiento."""
        lote.total_paginas = resultado.get("total_paginas")
        lote.total_recibos = resultado.get("total_recibos")

        errores = resultado.get("errores", [])
        # Separar errores reales de warnings
        errores_reales = [e for e in errores if not e.get("tipo", "").startswith("warning_")]

        lote.total_errores = len(errores_reales)
        lote.errores_detalle = errores  # Guardar todos (errores + warnings)

        if len(errores_reales) > 0:
            lote.estado = "procesado_con_errores"
        else:
            lote.estado = "procesado"

        lote.updated_at = utc_now()
        db.commit()
        db.refresh(lote)


# ─── ReciboService ─────────────────────────────────────────────────────────────


class ReciboService:
    """Servicio para operaciones de Recibos individuales."""

    @staticmethod
    def listar_por_lote(
        db: Session,
        empresa_id: uuid.UUID,
        lote_id: str,
        pagina: int = 1,
        por_pagina: int = 20,
        buscar: str = None,
        estado: str = None,
    ) -> Dict:
        """Lista recibos paginados de un lote con búsqueda por nombre o CUIL."""
        from sqlalchemy import String, cast, or_

        from backend.modules.nomina.models import Empleado

        try:
            lote_uuid = uuid.UUID(lote_id)
        except ValueError:
            return {
                "items": [],
                "total": 0,
                "pagina": pagina,
                "por_pagina": por_pagina,
                "total_paginas": 1,
            }

        query = db.query(Recibo).filter(
            Recibo.deleted_at.is_(None), Recibo.empresa_id == empresa_id, Recibo.lote_id == lote_uuid
        )

        if estado and estado.strip():
            query = query.filter(Recibo.estado == estado.strip())

        # Si hay búsqueda, hacer join con empleados
        if buscar and buscar.strip():
            termino = f"%{buscar.strip()}%"
            query = query.outerjoin(
                Empleado,
                (Recibo.cuil_extraido == Empleado.cuil)
                & (Empleado.empresa_id == empresa_id)
                & (Empleado.deleted_at.is_(None)),
            ).filter(
                or_(
                    cast(Recibo.cuil_extraido, String).ilike(termino),
                    Empleado.nombre.ilike(termino),
                    Empleado.apellido.ilike(termino),
                )
            )

        total = query.count()
        recibos = query.order_by(Recibo.created_at.desc()).offset((pagina - 1) * por_pagina).limit(por_pagina).all()

        # Obtener nombres de empleados por CUIL en una sola query
        cuils = list(set(r.cuil_extraido for r in recibos if r.cuil_extraido))
        nombres_map = {}
        if cuils:
            empleados = (
                db.query(Empleado.cuil, Empleado.apellido, Empleado.nombre)
                .filter(Empleado.cuil.in_(cuils), Empleado.empresa_id == empresa_id, Empleado.deleted_at.is_(None))
                .all()
            )
            for emp in empleados:
                nombres_map[emp.cuil] = f"{emp.apellido}, {emp.nombre}" if emp.apellido else emp.nombre

        items = [{"recibo": r, "empleado_nombre": nombres_map.get(r.cuil_extraido)} for r in recibos]

        return {
            "items": items,
            "total": total,
            "pagina": pagina,
            "por_pagina": por_pagina,
            "total_paginas": math.ceil(total / por_pagina) or 1,
        }

    @staticmethod
    def listar_por_empleado(
        db: Session, empresa_id: uuid.UUID, empleado_id: str, pagina: int = 1, por_pagina: int = 20
    ) -> Dict:
        """Lista recibos paginados de un empleado (por CUIL), ordenados por periodo DESC."""
        from backend.modules.nomina.models import Empleado

        try:
            empleado_uuid = uuid.UUID(empleado_id)
        except ValueError:
            return {
                "items": [],
                "total": 0,
                "pagina": pagina,
                "por_pagina": por_pagina,
                "total_paginas": 1,
            }

        # Obtener CUIL del empleado
        empleado = (
            db.query(Empleado)
            .filter(Empleado.id == empleado_uuid, Empleado.empresa_id == empresa_id, Empleado.deleted_at.is_(None))
            .first()
        )

        if not empleado or not empleado.cuil:
            return {
                "items": [],
                "total": 0,
                "pagina": pagina,
                "por_pagina": por_pagina,
                "total_paginas": 1,
            }

        # Buscar recibos por CUIL
        query = (
            db.query(Recibo)
            .join(LoteRecibo, Recibo.lote_id == LoteRecibo.id)
            .filter(
                Recibo.deleted_at.is_(None),
                Recibo.empresa_id == empresa_id,
                Recibo.cuil_extraido == empleado.cuil,
                LoteRecibo.deleted_at.is_(None),
            )
        )

        total = query.count()
        recibos = (
            query.order_by(LoteRecibo.periodo.desc(), Recibo.created_at.desc())
            .offset((pagina - 1) * por_pagina)
            .limit(por_pagina)
            .all()
        )

        nombre = f"{empleado.apellido}, {empleado.nombre}" if empleado.apellido else empleado.nombre
        items = [{"recibo": r, "empleado_nombre": nombre} for r in recibos]

        return {
            "items": items,
            "total": total,
            "pagina": pagina,
            "por_pagina": por_pagina,
            "total_paginas": math.ceil(total / por_pagina) or 1,
        }

    @staticmethod
    def obtener(db: Session, empresa_id: uuid.UUID, id: str) -> Optional[Recibo]:
        """Obtiene un recibo por ID, filtrado por empresa_id y deleted_at IS NULL."""
        try:
            return (
                db.query(Recibo)
                .filter(Recibo.id == uuid.UUID(id), Recibo.deleted_at.is_(None), Recibo.empresa_id == empresa_id)
                .first()
            )
        except ValueError:
            return None

    @staticmethod
    def firmar(
        db: Session,
        empresa_id: uuid.UUID,
        recibo_id: str,
        archivo_firmado_path: str,
        usuario: str = None,
        ip_firma: str = None,
    ) -> Optional[Recibo]:
        """Firma un recibo: actualiza estado a 'firmado', guarda ruta del archivo firmado."""
        recibo = ReciboService.obtener(db, empresa_id, recibo_id)
        if not recibo:
            return None

        recibo.archivo_firmado = archivo_firmado_path
        recibo.estado = "firmado"
        recibo.fecha_firma = utc_now()
        recibo.ip_firma = ip_firma
        recibo.updated_at = utc_now()
        if usuario:
            recibo.updated_by = usuario

        db.commit()
        db.refresh(recibo)
        return recibo

    @staticmethod
    def revertir_firma(
        db: Session,
        empresa_id: uuid.UUID,
        recibo_id: str,
        usuario: str = None,
    ) -> Optional[Recibo]:
        """Revierte la firma de un recibo: vuelve a 'asignado' y borra el archivo firmado del storage.

        Idempotente respecto al borrado en storage: si el blob ya no existe,
        se continúa con la actualización del estado.
        """
        recibo = ReciboService.obtener(db, empresa_id, recibo_id)
        if not recibo:
            return None

        if recibo.archivo_firmado:
            try:
                cloud_storage.delete(recibo.archivo_firmado)
            except Exception:
                pass  # idempotente: si el blob ya no está, seguimos

        recibo.archivo_firmado = None
        recibo.estado = "asignado"
        recibo.fecha_firma = None
        recibo.ip_firma = None
        recibo.updated_at = utc_now()
        if usuario:
            recibo.updated_by = usuario

        db.commit()
        db.refresh(recibo)
        return recibo


# ─── ReciboLogService ──────────────────────────────────────────────────────────


class ReciboLogService:
    """Servicio para registrar y consultar logs de actividad de recibos."""

    @staticmethod
    def registrar(
        db: Session,
        recibo_id,
        empresa_id,
        accion: str,
        usuario_email: str = None,
        usuario_nombre: str = None,
        ip: str = None,
        detalle: str = None,
    ):
        """Registra un evento de actividad en el log del recibo."""
        from backend.modules.recibos.models import ReciboLog

        log = ReciboLog(
            recibo_id=recibo_id,
            empresa_id=empresa_id,
            accion=accion,
            usuario_email=usuario_email,
            usuario_nombre=usuario_nombre,
            ip=ip,
            detalle=detalle,
        )
        db.add(log)
        db.flush()

    @staticmethod
    def listar(db: Session, empresa_id: uuid.UUID, recibo_id: str):
        """Lista los logs de un recibo, orden desc por fecha. Filtrado por empresa."""
        from backend.modules.recibos.models import ReciboLog

        try:
            rid = uuid.UUID(recibo_id)
        except ValueError, TypeError:
            return []
        return (
            db.query(ReciboLog)
            .filter(
                ReciboLog.recibo_id == rid,
                ReciboLog.empresa_id == empresa_id,
            )
            .order_by(ReciboLog.created_at.desc())
            .all()
        )
