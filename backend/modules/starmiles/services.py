"""
Servicios para Star Miles - Lógica de negocio.
"""

import hashlib
import logging
import math
import uuid
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, UploadFile
from PIL import Image
from sqlalchemy import String, and_, cast, func, or_
from sqlalchemy.orm import Session

from backend.core.utils import utc_now
from backend.modules.nomina.models import Empleado
from backend.modules.starmiles.models import (
    Canje,
    CategoriaDesafio,
    ContenidoCMS,
    Desafio,
    EmpleadoStarMiles,
    InscripcionDesafio,
    ItemCanje,
)


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


class CategoriaDesafioService:
    """Servicio para categorías de desafíos."""

    @staticmethod
    def crear(db: Session, empresa_id: uuid.UUID, datos: Dict[str, Any]) -> CategoriaDesafio:
        datos = limpiar_datos(datos)
        categoria = CategoriaDesafio(empresa_id=empresa_id, **datos)
        db.add(categoria)
        db.commit()
        db.refresh(categoria)
        return categoria

    @staticmethod
    def obtener(db: Session, empresa_id: uuid.UUID, id: str) -> Optional[CategoriaDesafio]:
        return (
            db.query(CategoriaDesafio)
            .filter(
                CategoriaDesafio.id == uuid.UUID(id),
                CategoriaDesafio.empresa_id == empresa_id,
                CategoriaDesafio.deleted_at.is_(None),
            )
            .first()
        )

    @staticmethod
    def listar(db: Session, empresa_id: uuid.UUID) -> List[CategoriaDesafio]:
        return (
            db.query(CategoriaDesafio)
            .filter(CategoriaDesafio.empresa_id == empresa_id, CategoriaDesafio.deleted_at.is_(None))
            .order_by(CategoriaDesafio.nombre)
            .all()
        )

    @staticmethod
    def actualizar(db: Session, empresa_id: uuid.UUID, id: str, datos: Dict) -> Optional[CategoriaDesafio]:
        datos = limpiar_datos(datos)
        categoria = (
            db.query(CategoriaDesafio)
            .filter(
                CategoriaDesafio.id == uuid.UUID(id),
                CategoriaDesafio.empresa_id == empresa_id,
                CategoriaDesafio.deleted_at.is_(None),
            )
            .first()
        )
        if not categoria:
            return None
        for campo, valor in datos.items():
            if hasattr(categoria, campo) and campo not in ("id", "empresa_id"):
                setattr(categoria, campo, valor)
        categoria.updated_at = utc_now()
        db.commit()
        db.refresh(categoria)
        return categoria

    @staticmethod
    def eliminar(db: Session, empresa_id: uuid.UUID, id: str) -> bool:
        categoria = (
            db.query(CategoriaDesafio)
            .filter(
                CategoriaDesafio.id == uuid.UUID(id),
                CategoriaDesafio.empresa_id == empresa_id,
                CategoriaDesafio.deleted_at.is_(None),
            )
            .first()
        )
        if not categoria:
            return False
        categoria.deleted_at = utc_now()
        db.commit()
        return True


class DesafioService:
    """Servicio para desafíos."""

    @staticmethod
    def crear(db: Session, empresa_id: uuid.UUID, datos: Dict[str, Any], usuario: str = None) -> Desafio:
        datos = limpiar_datos(datos)
        if "categoria_id" in datos and datos["categoria_id"]:
            datos["categoria_id"] = uuid.UUID(datos["categoria_id"])
        if usuario:
            datos["updated_by"] = usuario
        desafio = Desafio(empresa_id=empresa_id, **datos)
        db.add(desafio)
        db.commit()
        db.refresh(desafio)
        return desafio

    @staticmethod
    def obtener(db: Session, empresa_id: uuid.UUID, id: str) -> Optional[Desafio]:
        return (
            db.query(Desafio)
            .filter(Desafio.id == uuid.UUID(id), Desafio.empresa_id == empresa_id, Desafio.deleted_at.is_(None))
            .first()
        )

    @staticmethod
    def listar(
        db: Session,
        empresa_id: uuid.UUID,
        pagina: int = 1,
        por_pagina: int = 20,
        filtros: Dict = None,
        solo_vigentes: bool = False,
        ordenar_por: str = None,
        ordenar_dir: str = "asc",
    ) -> Dict:
        from sqlalchemy.orm import subqueryload

        query = (
            db.query(Desafio)
            .options(subqueryload(Desafio.inscripciones), subqueryload(Desafio.categoria))
            .filter(Desafio.deleted_at.is_(None), Desafio.empresa_id == empresa_id)
        )

        if filtros:
            if "buscar" in filtros and filtros["buscar"]:
                buscar = f"%{filtros['buscar']}%"
                query = query.filter(or_(Desafio.nombre.ilike(buscar), Desafio.descripcion.ilike(buscar)))
            if "categoria_id" in filtros and filtros["categoria_id"]:
                query = query.filter(Desafio.categoria_id == uuid.UUID(filtros["categoria_id"]))
            if "activo" in filtros:
                query = query.filter(Desafio.activo == filtros["activo"])
            if "alcance" in filtros and filtros["alcance"]:
                query = query.filter(Desafio.alcance == filtros["alcance"])

        if solo_vigentes:
            hoy = date.today()
            query = query.filter(
                Desafio.activo == True,
                or_(Desafio.fecha_inicio.is_(None), Desafio.fecha_inicio <= hoy),
                or_(Desafio.fecha_vencimiento.is_(None), Desafio.fecha_vencimiento >= hoy),
            )

        total = query.count()

        # Ordenamiento
        campos_orden = {
            "nombre": Desafio.nombre,
            "star_miles": Desafio.star_miles,
            "fecha_vencimiento": Desafio.fecha_vencimiento,
            "created_at": Desafio.created_at,
        }
        columna = campos_orden.get(ordenar_por)
        if columna is not None:
            if ordenar_dir == "desc":
                query = query.order_by(columna.desc())
            else:
                query = query.order_by(columna.asc())
        else:
            query = query.order_by(Desafio.created_at.desc())

        items = query.offset((pagina - 1) * por_pagina).limit(por_pagina).all()

        return {
            "items": items,
            "total": total,
            "pagina": pagina,
            "por_pagina": por_pagina,
            "total_paginas": math.ceil(total / por_pagina) or 1,
        }

    @staticmethod
    def actualizar(db: Session, empresa_id: uuid.UUID, id: str, datos: Dict, usuario: str = None) -> Optional[Desafio]:
        datos = limpiar_datos(datos)
        desafio = (
            db.query(Desafio)
            .filter(Desafio.id == uuid.UUID(id), Desafio.empresa_id == empresa_id, Desafio.deleted_at.is_(None))
            .first()
        )
        if not desafio:
            return None
        if datos.get("inscripcion_unica_por_empleado") and not desafio.inscripcion_unica_por_empleado:
            duplicados = (
                db.query(InscripcionDesafio.empleado_id)
                .filter(
                    InscripcionDesafio.empresa_id == empresa_id,
                    InscripcionDesafio.desafio_id == desafio.id,
                    InscripcionDesafio.deleted_at.is_(None),
                    InscripcionDesafio.estado.in_(["pendiente", "aprobada", "completada"]),
                )
                .group_by(InscripcionDesafio.empleado_id)
                .having(func.count(InscripcionDesafio.id) > 1)
                .count()
            )
            if duplicados:
                raise ValueError(
                    "No se puede activar la inscripcion unica: existen empleados con inscripciones activas o completadas duplicadas"
                )
        if "categoria_id" in datos and datos["categoria_id"]:
            datos["categoria_id"] = uuid.UUID(datos["categoria_id"])
        for campo, valor in datos.items():
            if hasattr(desafio, campo) and campo not in ("id", "empresa_id"):
                setattr(desafio, campo, valor)
        desafio.updated_at = utc_now()
        if usuario:
            desafio.updated_by = usuario
        db.commit()
        db.refresh(desafio)
        return desafio

    @staticmethod
    def eliminar(db: Session, empresa_id: uuid.UUID, id: str) -> bool:
        desafio = (
            db.query(Desafio)
            .filter(Desafio.id == uuid.UUID(id), Desafio.empresa_id == empresa_id, Desafio.deleted_at.is_(None))
            .first()
        )
        if not desafio:
            return False
        ahora = utc_now()
        # Cancelar inscripciones pendientes o aprobadas antes de eliminar el desafío
        db.query(InscripcionDesafio).filter(
            InscripcionDesafio.desafio_id == desafio.id,
            InscripcionDesafio.empresa_id == empresa_id,
            InscripcionDesafio.deleted_at.is_(None),
            InscripcionDesafio.estado.in_(["pendiente", "aprobada"]),
        ).update(
            {
                "estado": "rechazada",
                "fecha_rechazo": ahora,
                "comentario_aprobador": "Desafío eliminado por el administrador",
                "updated_at": ahora,
            },
            synchronize_session=False,
        )
        desafio.deleted_at = ahora
        db.commit()
        return True

    @staticmethod
    def esta_vigente(desafio: Desafio) -> bool:
        if not desafio.activo:
            return False
        hoy = date.today()
        if desafio.fecha_inicio and desafio.fecha_inicio > hoy:
            return False
        if desafio.fecha_vencimiento and desafio.fecha_vencimiento < hoy:
            return False
        return True

    @staticmethod
    def obtener_alcances(db: Session, empresa_id: uuid.UUID) -> List[str]:
        """Obtiene los valores únicos de alcance para los desafíos activos."""
        resultados = (
            db.query(Desafio.alcance)
            .filter(
                Desafio.deleted_at.is_(None),
                Desafio.empresa_id == empresa_id,
                Desafio.alcance.isnot(None),
                Desafio.alcance != "",
            )
            .distinct()
            .order_by(Desafio.alcance)
            .all()
        )
        return [r[0] for r in resultados]


class EmpleadoStarMilesService:
    """Servicio para cuentas de Star Miles de empleados."""

    @staticmethod
    def obtener_o_crear(db: Session, empresa_id: uuid.UUID, empleado_id: str) -> EmpleadoStarMiles:
        """Obtiene la cuenta de millas o la crea si no existe."""
        cuenta = (
            db.query(EmpleadoStarMiles)
            .filter(
                EmpleadoStarMiles.empleado_id == uuid.UUID(empleado_id),
                EmpleadoStarMiles.empresa_id == empresa_id,
                EmpleadoStarMiles.deleted_at.is_(None),
            )
            .first()
        )

        if not cuenta:
            cuenta = EmpleadoStarMiles(
                empresa_id=empresa_id, empleado_id=uuid.UUID(empleado_id), millas_historicas=0, millas_disponibles=0
            )
            db.add(cuenta)
            db.commit()
            db.refresh(cuenta)

        return cuenta

    @staticmethod
    def acreditar_millas(db: Session, empresa_id: uuid.UUID, empleado_id: str, cantidad: int) -> EmpleadoStarMiles:
        """Acredita millas a un empleado."""
        cuenta = EmpleadoStarMilesService.obtener_o_crear(db, empresa_id, empleado_id)
        cuenta.millas_historicas += cantidad
        cuenta.millas_disponibles += cantidad
        cuenta.updated_at = utc_now()
        db.commit()
        db.refresh(cuenta)
        return cuenta

    @staticmethod
    def debitar_millas(db: Session, empresa_id: uuid.UUID, empleado_id: str, cantidad: int) -> EmpleadoStarMiles:
        """Debita millas de un empleado (para canjes)."""
        cuenta = EmpleadoStarMilesService.obtener_o_crear(db, empresa_id, empleado_id)
        if cuenta.millas_disponibles < cantidad:
            raise ValueError("Millas insuficientes")
        cuenta.millas_disponibles -= cantidad
        cuenta.updated_at = utc_now()
        db.commit()
        db.refresh(cuenta)
        return cuenta

    @staticmethod
    def devolver_millas(db: Session, empresa_id: uuid.UUID, empleado_id: str, cantidad: int) -> EmpleadoStarMiles:
        """Devuelve millas (cuando se rechaza un canje)."""
        cuenta = EmpleadoStarMilesService.obtener_o_crear(db, empresa_id, empleado_id)
        cuenta.millas_disponibles += cantidad
        cuenta.updated_at = utc_now()
        db.commit()
        db.refresh(cuenta)
        return cuenta

    @staticmethod
    def obtener_por_empleado(db: Session, empresa_id: uuid.UUID, empleado_id: str) -> Optional[EmpleadoStarMiles]:
        return (
            db.query(EmpleadoStarMiles)
            .filter(
                EmpleadoStarMiles.empleado_id == uuid.UUID(empleado_id),
                EmpleadoStarMiles.empresa_id == empresa_id,
                EmpleadoStarMiles.deleted_at.is_(None),
            )
            .first()
        )


class InscripcionDesafioService:
    """Servicio para inscripciones a desafíos."""

    @staticmethod
    def crear(db: Session, empresa_id: uuid.UUID, empleado_id: str, datos: Dict[str, Any]) -> InscripcionDesafio:
        # Verificar que el desafío existe y está vigente
        desafio = DesafioService.obtener(db, empresa_id, datos["desafio_id"])
        if not desafio:
            raise ValueError("Desafío no encontrado")
        if not DesafioService.esta_vigente(desafio):
            raise ValueError("El desafío no está vigente")

        # Verificar que no esté ya inscripto
        existente = (
            db.query(InscripcionDesafio)
            .filter(
                InscripcionDesafio.desafio_id == uuid.UUID(datos["desafio_id"]),
                InscripcionDesafio.empleado_id == uuid.UUID(empleado_id),
                InscripcionDesafio.deleted_at.is_(None),
                InscripcionDesafio.estado.in_(
                    ["pendiente", "aprobada", "completada"]
                    if desafio.inscripcion_unica_por_empleado
                    else ["pendiente", "aprobada"]
                ),
            )
            .first()
        )
        if existente:
            raise ValueError("Ya estás inscripto en este desafío")

        inscripcion = InscripcionDesafio(
            empresa_id=empresa_id,
            desafio_id=uuid.UUID(datos["desafio_id"]),
            empleado_id=uuid.UUID(empleado_id),
            comentario_solicitud=datos.get("comentario_solicitud"),
            estado="pendiente",
            fecha_solicitud=utc_now(),
        )
        db.add(inscripcion)
        db.commit()
        db.refresh(inscripcion)
        return inscripcion

    @staticmethod
    def aprobar(
        db: Session, empresa_id: uuid.UUID, id: str, aprobador_id: str, comentario: str = None
    ) -> InscripcionDesafio:
        inscripcion = (
            db.query(InscripcionDesafio)
            .filter(
                InscripcionDesafio.id == uuid.UUID(id),
                InscripcionDesafio.empresa_id == empresa_id,
                InscripcionDesafio.deleted_at.is_(None),
            )
            .first()
        )
        if not inscripcion:
            raise ValueError("Inscripción no encontrada")
        if inscripcion.estado != "pendiente":
            raise ValueError("La inscripción no está pendiente")

        inscripcion.estado = "aprobada"
        inscripcion.aprobador_id = uuid.UUID(aprobador_id)
        inscripcion.fecha_aprobacion = utc_now()
        inscripcion.comentario_aprobador = comentario
        inscripcion.updated_at = utc_now()
        db.commit()
        db.refresh(inscripcion)
        return inscripcion

    @staticmethod
    def rechazar(db: Session, empresa_id: uuid.UUID, id: str, aprobador_id: str, comentario: str) -> InscripcionDesafio:
        inscripcion = (
            db.query(InscripcionDesafio)
            .filter(
                InscripcionDesafio.id == uuid.UUID(id),
                InscripcionDesafio.empresa_id == empresa_id,
                InscripcionDesafio.deleted_at.is_(None),
            )
            .first()
        )
        if not inscripcion:
            raise ValueError("Inscripción no encontrada")
        if inscripcion.estado != "pendiente":
            raise ValueError("La inscripción no está pendiente")

        inscripcion.estado = "rechazada"
        inscripcion.aprobador_id = uuid.UUID(aprobador_id)
        inscripcion.fecha_rechazo = utc_now()
        inscripcion.comentario_aprobador = comentario
        inscripcion.updated_at = utc_now()
        db.commit()
        db.refresh(inscripcion)
        return inscripcion

    @staticmethod
    def finalizar(
        db: Session, empresa_id: uuid.UUID, id: str, aprobador_id: str, comentario: str = None
    ) -> InscripcionDesafio:
        """Finaliza un desafío y acredita las millas."""
        inscripcion = (
            db.query(InscripcionDesafio)
            .filter(
                InscripcionDesafio.id == uuid.UUID(id),
                InscripcionDesafio.empresa_id == empresa_id,
                InscripcionDesafio.deleted_at.is_(None),
            )
            .first()
        )
        if not inscripcion:
            raise ValueError("Inscripción no encontrada")
        if inscripcion.estado != "aprobada":
            raise ValueError("La inscripción debe estar aprobada para finalizar")

        # Acreditar millas
        EmpleadoStarMilesService.acreditar_millas(
            db, empresa_id, str(inscripcion.empleado_id), inscripcion.desafio.star_miles
        )

        inscripcion.estado = "completada"
        inscripcion.fecha_finalizacion = utc_now()
        if comentario:
            inscripcion.comentario_aprobador = comentario
        inscripcion.updated_at = utc_now()
        db.commit()
        db.refresh(inscripcion)
        return inscripcion

    @staticmethod
    def cancelar(db: Session, empresa_id: uuid.UUID, id: str, aprobador_id: str, comentario: str) -> InscripcionDesafio:
        inscripcion = InscripcionDesafioService.obtener(db, empresa_id, id)
        if not inscripcion:
            raise ValueError("Inscripcion no encontrada")
        if inscripcion.estado != "aprobada":
            raise ValueError("La inscripcion debe estar aprobada para cancelarla")

        inscripcion.estado = "rechazada"
        inscripcion.aprobador_id = uuid.UUID(aprobador_id)
        inscripcion.fecha_rechazo = utc_now()
        inscripcion.comentario_aprobador = comentario
        inscripcion.updated_at = utc_now()
        db.commit()
        db.refresh(inscripcion)
        return inscripcion

    @staticmethod
    def marcar_incompleta(
        db: Session, empresa_id: uuid.UUID, id: str, aprobador_id: str, comentario: str
    ) -> InscripcionDesafio:
        """Marca un desafío como incompleto (no acredita millas)."""
        inscripcion = (
            db.query(InscripcionDesafio)
            .filter(
                InscripcionDesafio.id == uuid.UUID(id),
                InscripcionDesafio.empresa_id == empresa_id,
                InscripcionDesafio.deleted_at.is_(None),
            )
            .first()
        )
        if not inscripcion:
            raise ValueError("Inscripción no encontrada")
        if inscripcion.estado != "aprobada":
            raise ValueError("La inscripción debe estar aprobada para marcar como incompleta")

        inscripcion.estado = "incompleta"
        inscripcion.aprobador_id = uuid.UUID(aprobador_id)
        inscripcion.fecha_finalizacion = utc_now()
        inscripcion.comentario_aprobador = comentario
        inscripcion.updated_at = utc_now()
        db.commit()
        db.refresh(inscripcion)
        return inscripcion

    @staticmethod
    def revocar(db: Session, empresa_id: uuid.UUID, id: str, aprobador_id: str, comentario: str) -> InscripcionDesafio:
        inscripcion = InscripcionDesafioService.obtener(db, empresa_id, id)
        if not inscripcion:
            raise ValueError("Inscripcion no encontrada")
        if inscripcion.estado != "completada":
            raise ValueError("La inscripcion debe estar completada para revocarla")

        millas = inscripcion.desafio.star_miles
        cuenta = EmpleadoStarMilesService.obtener_por_empleado(db, empresa_id, str(inscripcion.empleado_id))
        if not cuenta or cuenta.millas_historicas < millas:
            raise ValueError("No se pueden revocar las millas de esta inscripcion")
        if cuenta.millas_disponibles < millas:
            raise ValueError(
                "No se puede revocar porque el empleado no tiene millas disponibles. "
                "Primero rechaza y reintegra sus canjes aprobados."
            )

        cuenta.millas_historicas -= millas
        cuenta.millas_disponibles -= millas
        cuenta.updated_at = utc_now()
        inscripcion.estado = "rechazada"
        inscripcion.aprobador_id = uuid.UUID(aprobador_id)
        inscripcion.fecha_rechazo = utc_now()
        inscripcion.comentario_aprobador = comentario
        inscripcion.updated_at = utc_now()
        db.commit()
        db.refresh(inscripcion)
        return inscripcion

    @staticmethod
    def listar(db: Session, empresa_id: uuid.UUID, pagina: int = 1, por_pagina: int = 20, filtros: Dict = None) -> Dict:
        query = db.query(InscripcionDesafio).filter(
            InscripcionDesafio.deleted_at.is_(None), InscripcionDesafio.empresa_id == empresa_id
        )

        if filtros:
            if "empleado_id" in filtros and filtros["empleado_id"]:
                query = query.filter(InscripcionDesafio.empleado_id == uuid.UUID(filtros["empleado_id"]))
            if "estado" in filtros and filtros["estado"]:
                query = query.filter(InscripcionDesafio.estado == filtros["estado"])
            if "desafio_id" in filtros and filtros["desafio_id"]:
                query = query.filter(InscripcionDesafio.desafio_id == uuid.UUID(filtros["desafio_id"]))
            if "buscar" in filtros and filtros["buscar"]:
                buscar = f"%{filtros['buscar']}%"
                query = query.join(Empleado, InscripcionDesafio.empleado_id == Empleado.id).filter(
                    or_(
                        Empleado.nombre.ilike(buscar),
                        Empleado.apellido.ilike(buscar),
                        Empleado.email_corporativo.ilike(buscar),
                        cast(Empleado.dni, String).ilike(buscar),
                        cast(Empleado.cuil, String).ilike(buscar),
                    )
                )
            if "fecha_desde" in filtros and filtros["fecha_desde"]:
                fecha_desde = date.fromisoformat(filtros["fecha_desde"])
                query = query.filter(
                    InscripcionDesafio.fecha_solicitud >= datetime.combine(fecha_desde, datetime.min.time())
                )
            if "fecha_hasta" in filtros and filtros["fecha_hasta"]:
                fecha_hasta = date.fromisoformat(filtros["fecha_hasta"])
                query = query.filter(
                    InscripcionDesafio.fecha_solicitud <= datetime.combine(fecha_hasta, datetime.max.time())
                )

        total = query.count()
        items = (
            query.order_by(InscripcionDesafio.fecha_solicitud.desc())
            .offset((pagina - 1) * por_pagina)
            .limit(por_pagina)
            .all()
        )

        return {
            "items": items,
            "total": total,
            "pagina": pagina,
            "por_pagina": por_pagina,
            "total_paginas": math.ceil(total / por_pagina) or 1,
        }

    @staticmethod
    def obtener(db: Session, empresa_id: uuid.UUID, id: str) -> Optional[InscripcionDesafio]:
        return (
            db.query(InscripcionDesafio)
            .filter(
                InscripcionDesafio.id == uuid.UUID(id),
                InscripcionDesafio.empresa_id == empresa_id,
                InscripcionDesafio.deleted_at.is_(None),
            )
            .first()
        )


# Tasa de conversión: 10 Star Miles = 1 USD
STAR_MILES_POR_USD = 10


class CotizacionService:
    """Servicio para obtener cotización del dólar desde BCRA."""

    _cache_cotizacion: Optional[float] = None
    _cache_timestamp: Optional[datetime] = None
    _cache_duration = timedelta(hours=1)  # Cache por 1 hora

    @staticmethod
    async def obtener_cotizacion_usd() -> float:
        """Obtiene la cotización del dólar oficial desde el BCRA."""
        import httpx

        # Verificar cache
        ahora = utc_now()
        if (
            CotizacionService._cache_cotizacion
            and CotizacionService._cache_timestamp
            and ahora - CotizacionService._cache_timestamp < CotizacionService._cache_duration
        ):
            return CotizacionService._cache_cotizacion

        try:
            # API del BCRA - Dólar oficial
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "https://api.bcra.gob.ar/estadisticascambiarias/v1.0/Cotizaciones",
                    headers={"Accept": "application/json"},
                )

                if response.status_code == 200:
                    data = response.json()
                    # Buscar USD en la respuesta
                    for cotizacion in data.get("results", []):
                        if cotizacion.get("codigoMoneda") == "USD":
                            # Usar tipo vendedor
                            valor = cotizacion.get("tipoCotizacion", [{}])[0].get("tipoCambio", 1000)
                            CotizacionService._cache_cotizacion = float(valor)
                            CotizacionService._cache_timestamp = ahora
                            return CotizacionService._cache_cotizacion
        except Exception:
            pass

        # Fallback: API alternativa (dolarapi.com)
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get("https://dolarapi.com/v1/dolares/oficial")
                if response.status_code == 200:
                    data = response.json()
                    valor = data.get("venta", 1000)
                    CotizacionService._cache_cotizacion = float(valor)
                    CotizacionService._cache_timestamp = ahora
                    return CotizacionService._cache_cotizacion
        except Exception:
            pass

        # Si todo falla, usar valor por defecto
        return CotizacionService._cache_cotizacion or 1000.0


class MercadoLibreService:
    """Servicio para consultar precios de MercadoLibre mediante scraping."""

    @staticmethod
    def extraer_item_id(url: str) -> Optional[str]:
        """Extrae el ID del item de una URL de MercadoLibre."""
        import re

        patterns = [
            r"/p/(MLA\d+)",  # Formato /p/MLA123456
            r"MLA-(\d+)",  # Formato MLA-123456 (con guión)
            r"(MLA\d+)",  # Formato MLA123456 (sin guión)
        ]
        for pattern in patterns:
            match = re.search(pattern, url, re.IGNORECASE)
            if match:
                item_id = match.group(1)
                if not item_id.upper().startswith("MLA"):
                    item_id = f"MLA{item_id}"
                return item_id.upper().replace("-", "")
        return None

    @staticmethod
    async def obtener_precio(url: str) -> Dict[str, Any]:
        """Obtiene el precio de un producto de MercadoLibre mediante scraping."""
        import re

        import httpx

        item_id = MercadoLibreService.extraer_item_id(url)
        if not item_id:
            raise ValueError("No se pudo extraer el ID del producto de la URL")

        # Headers para simular navegador
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
        }

        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)

            if response.status_code != 200:
                raise ValueError(f"Error al acceder a MercadoLibre: {response.status_code}")

            html = response.text

            # Extraer precio del HTML
            precio = None
            titulo = None

            # Buscar precio en meta tags o JSON-LD
            # Patrón para precio en JSON-LD
            json_ld_match = re.search(r'"price"\s*:\s*"?(\d+(?:\.\d+)?)"?', html)
            if json_ld_match:
                precio = float(json_ld_match.group(1))

            # Patrón alternativo para precio en el HTML
            if not precio:
                # Buscar en el formato de precio de ML
                precio_match = re.search(r'price-tag-fraction["\s>]+(\d+(?:[.,]\d+)*)', html)
                if precio_match:
                    precio_str = precio_match.group(1).replace(".", "").replace(",", ".")
                    precio = float(precio_str)

            # Otro patrón común
            if not precio:
                precio_match = re.search(r'"amount"\s*:\s*(\d+(?:\.\d+)?)', html)
                if precio_match:
                    precio = float(precio_match.group(1))

            if not precio:
                raise ValueError("No se pudo extraer el precio del producto")

            # Extraer título
            titulo_match = re.search(r"<title>([^<]+)</title>", html)
            if titulo_match:
                titulo = titulo_match.group(1).split(" | ")[0].strip()
            else:
                titulo_match = re.search(r'"name"\s*:\s*"([^"]+)"', html)
                if titulo_match:
                    titulo = titulo_match.group(1)

            # Obtener cotización del dólar
            cotizacion_usd = await CotizacionService.obtener_cotizacion_usd()

            # Calcular Star Miles: precio_ars / cotizacion_usd * 10
            precio_usd = precio / cotizacion_usd
            star_miles = int(precio_usd * STAR_MILES_POR_USD)

            return {
                "item_id": item_id,
                "titulo": titulo or "Producto de MercadoLibre",
                "precio": precio,
                "moneda": "ARS",
                "cotizacion_usd": cotizacion_usd,
                "precio_usd": round(precio_usd, 2),
                "star_miles": star_miles,
                "url": url,
            }


class ItemCanjeService:
    """Servicio para items de canje."""

    @staticmethod
    def crear(db: Session, empresa_id: uuid.UUID, datos: Dict[str, Any], usuario: str = None) -> ItemCanje:
        datos = limpiar_datos(datos)
        if usuario:
            datos["updated_by"] = usuario
        item = ItemCanje(empresa_id=empresa_id, **datos)
        db.add(item)
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def obtener(db: Session, empresa_id: uuid.UUID, id: str) -> Optional[ItemCanje]:
        return (
            db.query(ItemCanje)
            .filter(ItemCanje.id == uuid.UUID(id), ItemCanje.empresa_id == empresa_id, ItemCanje.deleted_at.is_(None))
            .first()
        )

    @staticmethod
    def listar(
        db: Session,
        empresa_id: uuid.UUID,
        pagina: int = 1,
        por_pagina: int = 20,
        filtros: Dict = None,
        solo_activos: bool = False,
    ) -> Dict:
        query = db.query(ItemCanje).filter(ItemCanje.deleted_at.is_(None), ItemCanje.empresa_id == empresa_id)

        if filtros:
            if "buscar" in filtros and filtros["buscar"]:
                buscar = f"%{filtros['buscar']}%"
                query = query.filter(or_(ItemCanje.nombre.ilike(buscar), ItemCanje.descripcion.ilike(buscar)))

        if solo_activos:
            query = query.filter(ItemCanje.activo == True)

        total = query.count()
        items = query.order_by(ItemCanje.nombre.asc()).offset((pagina - 1) * por_pagina).limit(por_pagina).all()

        return {
            "items": items,
            "total": total,
            "pagina": pagina,
            "por_pagina": por_pagina,
            "total_paginas": math.ceil(total / por_pagina) or 1,
        }

    @staticmethod
    def actualizar(
        db: Session, empresa_id: uuid.UUID, id: str, datos: Dict, usuario: str = None
    ) -> Optional[ItemCanje]:
        datos = limpiar_datos(datos)
        item = (
            db.query(ItemCanje)
            .filter(ItemCanje.id == uuid.UUID(id), ItemCanje.empresa_id == empresa_id, ItemCanje.deleted_at.is_(None))
            .first()
        )
        if not item:
            return None
        for campo, valor in datos.items():
            if hasattr(item, campo) and campo not in ("id", "empresa_id"):
                setattr(item, campo, valor)
        item.updated_at = utc_now()
        if usuario:
            item.updated_by = usuario
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def eliminar(db: Session, empresa_id: uuid.UUID, id: str) -> bool:
        item = (
            db.query(ItemCanje)
            .filter(ItemCanje.id == uuid.UUID(id), ItemCanje.empresa_id == empresa_id, ItemCanje.deleted_at.is_(None))
            .first()
        )
        if not item:
            return False
        ahora = utc_now()
        # Cancelar canjes pendientes o aprobados antes de eliminar el item
        canjes_activos = (
            db.query(Canje)
            .filter(
                Canje.item_id == item.id,
                Canje.empresa_id == empresa_id,
                Canje.deleted_at.is_(None),
                Canje.estado == "pendiente",
            )
            .all()
        )
        for canje in canjes_activos:
            canje.estado = "rechazado"
            canje.fecha_rechazo = ahora
            canje.comentario = "Item de canje eliminado por el administrador"
            canje.updated_at = ahora
        item.deleted_at = ahora
        db.commit()
        return True


class CanjeService:
    """Servicio para canjes."""

    @staticmethod
    def crear(db: Session, empresa_id: uuid.UUID, empleado_id: str, datos: Dict[str, Any]) -> Canje:
        # Verificar que no tenga un canje pendiente
        canje_pendiente = (
            db.query(Canje)
            .filter(
                Canje.empleado_id == uuid.UUID(empleado_id),
                Canje.empresa_id == empresa_id,
                Canje.estado == "pendiente",
                Canje.deleted_at.is_(None),
            )
            .first()
        )
        if canje_pendiente:
            raise ValueError(
                "Ya tenés un canje pendiente de aprobación. Esperá a que se procese antes de solicitar otro."
            )

        # Verificar item
        item = ItemCanjeService.obtener(db, empresa_id, datos["item_id"])
        if not item:
            raise ValueError("Item no encontrado")
        if not item.activo:
            raise ValueError("Item no disponible")

        cantidad = datos.get("cantidad", 1)

        # Determinar costo según tipo de item
        if item.tipo == "mercadolibre":
            # Para MercadoLibre, el costo viene del precio ingresado manualmente (1 peso = 1 milla)
            if not datos.get("star_miles_calculado"):
                raise ValueError("Debe calcular las Star Miles ingresando el precio")
            if not datos.get("mercadolibre_url"):
                raise ValueError("Debe proporcionar la URL de MercadoLibre")
            if not datos.get("mercadolibre_precio"):
                raise ValueError("Debe proporcionar el precio del producto")
            costo_total = datos["star_miles_calculado"] * cantidad
        else:
            # Para producto normal, usar el costo fijo
            if not item.star_miles_costo:
                raise ValueError("El item no tiene costo definido")
            costo_total = item.star_miles_costo * cantidad

        # Verificar stock
        if item.stock is not None and item.stock < cantidad:
            raise ValueError("Stock insuficiente")

        # Verificar millas disponibles
        cuenta = EmpleadoStarMilesService.obtener_o_crear(db, empresa_id, empleado_id)
        if cuenta.millas_disponibles < costo_total:
            raise ValueError(f"Millas insuficientes. Necesitás {costo_total}, tenés {cuenta.millas_disponibles}")

        # Crear canje
        canje = Canje(
            empresa_id=empresa_id,
            item_id=uuid.UUID(datos["item_id"]),
            empleado_id=uuid.UUID(empleado_id),
            cantidad=cantidad,
            star_miles_total=costo_total,
            mercadolibre_url=datos.get("mercadolibre_url"),
            mercadolibre_precio=datos.get("mercadolibre_precio"),
            estado="pendiente",
            fecha_solicitud=utc_now(),
            comentario=datos.get("comentario"),
        )
        db.add(canje)
        db.flush()
        CanjeService._avisar_canje_nuevo(db, canje, item)
        db.commit()
        db.refresh(canje)
        return canje

    @staticmethod
    def _avisar_canje_nuevo(db: Session, canje: Canje, item: ItemCanje) -> None:
        """
        Encola el aviso al room de Webex de quienes aprueban (F20), en la misma transacción
        que el canje. En un savepoint: si armar el aviso falla, se descarta solo el aviso.
        """
        from backend.modules.starmiles.avisos import encolar_aviso_canje

        try:
            with db.begin_nested():
                encolar_aviso_canje(db, canje, db.get(Empleado, canje.empleado_id), item)
        except Exception as exc:  # noqa: BLE001 - el canje se registra igual
            logging.getLogger(__name__).warning("No se pudo encolar el aviso del canje %s: %s", canje.id, exc)

    @staticmethod
    def aprobar(db: Session, empresa_id: uuid.UUID, id: str, aprobador_id: str, comentario: str = None) -> Canje:
        canje = (
            db.query(Canje)
            .filter(Canje.id == uuid.UUID(id), Canje.empresa_id == empresa_id, Canje.deleted_at.is_(None))
            .first()
        )
        if not canje:
            raise ValueError("Canje no encontrado")
        if canje.estado != "pendiente":
            raise ValueError("El canje no está pendiente")

        # Debitar millas
        EmpleadoStarMilesService.debitar_millas(db, empresa_id, str(canje.empleado_id), canje.star_miles_total)

        # Descontar stock si aplica
        if canje.item.stock is not None:
            canje.item.stock -= canje.cantidad

        canje.estado = "aprobado"
        canje.aprobador_id = uuid.UUID(aprobador_id)
        canje.fecha_aprobacion = utc_now()
        if comentario:
            canje.comentario = comentario
        canje.updated_at = utc_now()
        db.commit()
        db.refresh(canje)
        return canje

    @staticmethod
    def rechazar(db: Session, empresa_id: uuid.UUID, id: str, aprobador_id: str, comentario: str) -> Canje:
        canje = (
            db.query(Canje)
            .filter(Canje.id == uuid.UUID(id), Canje.empresa_id == empresa_id, Canje.deleted_at.is_(None))
            .first()
        )
        if not canje:
            raise ValueError("Canje no encontrado")
        if canje.estado != "pendiente":
            raise ValueError("El canje no está pendiente")

        canje.estado = "rechazado"
        canje.aprobador_id = uuid.UUID(aprobador_id)
        canje.fecha_rechazo = utc_now()
        canje.comentario = comentario
        canje.updated_at = utc_now()
        db.commit()
        db.refresh(canje)
        return canje

    @staticmethod
    def entregar(db: Session, empresa_id: uuid.UUID, id: str, aprobador_id: str, comentario: str = None) -> Canje:
        canje = (
            db.query(Canje)
            .filter(Canje.id == uuid.UUID(id), Canje.empresa_id == empresa_id, Canje.deleted_at.is_(None))
            .first()
        )
        if not canje:
            raise ValueError("Canje no encontrado")
        if canje.estado != "aprobado":
            raise ValueError("El canje debe estar aprobado para entregar")

        canje.estado = "entregado"
        canje.fecha_entrega = utc_now()
        if comentario:
            canje.comentario = comentario
        canje.updated_at = utc_now()
        db.commit()
        db.refresh(canje)
        return canje

    @staticmethod
    def rechazar_y_reintegrar(db: Session, empresa_id: uuid.UUID, id: str, aprobador_id: str, comentario: str) -> Canje:
        canje = CanjeService.obtener(db, empresa_id, id)
        if not canje:
            raise ValueError("Canje no encontrado")
        if canje.estado != "aprobado":
            raise ValueError("El canje debe estar aprobado para rechazarlo y reintegrar las millas")

        EmpleadoStarMilesService.devolver_millas(db, empresa_id, str(canje.empleado_id), canje.star_miles_total)
        if canje.item.stock is not None:
            canje.item.stock += canje.cantidad
        canje.estado = "rechazado"
        canje.aprobador_id = uuid.UUID(aprobador_id)
        canje.fecha_rechazo = utc_now()
        canje.comentario = comentario
        canje.updated_at = utc_now()
        db.commit()
        db.refresh(canje)
        return canje

    @staticmethod
    def listar(db: Session, empresa_id: uuid.UUID, pagina: int = 1, por_pagina: int = 20, filtros: Dict = None) -> Dict:
        query = db.query(Canje).filter(Canje.deleted_at.is_(None), Canje.empresa_id == empresa_id)

        if filtros:
            if "empleado_id" in filtros and filtros["empleado_id"]:
                query = query.filter(Canje.empleado_id == uuid.UUID(filtros["empleado_id"]))
            if "estado" in filtros and filtros["estado"]:
                query = query.filter(Canje.estado == filtros["estado"])

        total = query.count()
        items = query.order_by(Canje.fecha_solicitud.desc()).offset((pagina - 1) * por_pagina).limit(por_pagina).all()

        return {
            "items": items,
            "total": total,
            "pagina": pagina,
            "por_pagina": por_pagina,
            "total_paginas": math.ceil(total / por_pagina) or 1,
        }

    @staticmethod
    def obtener(db: Session, empresa_id: uuid.UUID, id: str) -> Optional[Canje]:
        return (
            db.query(Canje)
            .filter(Canje.id == uuid.UUID(id), Canje.empresa_id == empresa_id, Canje.deleted_at.is_(None))
            .first()
        )


class ContenidoCMSService:
    """Servicio para contenido CMS."""

    @staticmethod
    def crear(db: Session, empresa_id: uuid.UUID, datos: Dict[str, Any], usuario: str = None) -> ContenidoCMS:
        datos = limpiar_datos(datos)
        if "empleado_id" in datos and datos["empleado_id"]:
            datos["empleado_id"] = uuid.UUID(datos["empleado_id"])
        if usuario:
            datos["updated_by"] = usuario
        contenido = ContenidoCMS(empresa_id=empresa_id, **datos)
        db.add(contenido)
        db.commit()
        db.refresh(contenido)
        return contenido

    @staticmethod
    def obtener(db: Session, empresa_id: uuid.UUID, id: str) -> Optional[ContenidoCMS]:
        return (
            db.query(ContenidoCMS)
            .filter(
                ContenidoCMS.id == uuid.UUID(id),
                ContenidoCMS.empresa_id == empresa_id,
                ContenidoCMS.deleted_at.is_(None),
            )
            .first()
        )

    @staticmethod
    def listar(db: Session, empresa_id: uuid.UUID, tipo: str = None, solo_visibles: bool = False) -> Dict:
        query = db.query(ContenidoCMS).filter(ContenidoCMS.deleted_at.is_(None), ContenidoCMS.empresa_id == empresa_id)

        if tipo:
            query = query.filter(ContenidoCMS.tipo == tipo)

        if solo_visibles:
            ahora = utc_now()
            query = query.filter(
                ContenidoCMS.visible == True,
                or_(ContenidoCMS.fecha_publicacion.is_(None), ContenidoCMS.fecha_publicacion <= ahora),
                or_(ContenidoCMS.fecha_expiracion.is_(None), ContenidoCMS.fecha_expiracion >= ahora),
            )

        items = query.order_by(ContenidoCMS.orden.asc(), ContenidoCMS.created_at.desc()).all()

        return {"items": items, "total": len(items)}

    @staticmethod
    def actualizar(
        db: Session, empresa_id: uuid.UUID, id: str, datos: Dict, usuario: str = None
    ) -> Optional[ContenidoCMS]:
        datos = limpiar_datos(datos)
        contenido = (
            db.query(ContenidoCMS)
            .filter(
                ContenidoCMS.id == uuid.UUID(id),
                ContenidoCMS.empresa_id == empresa_id,
                ContenidoCMS.deleted_at.is_(None),
            )
            .first()
        )
        if not contenido:
            return None
        if "empleado_id" in datos and datos["empleado_id"]:
            datos["empleado_id"] = uuid.UUID(datos["empleado_id"])
        for campo, valor in datos.items():
            if hasattr(contenido, campo) and campo not in ("id", "empresa_id"):
                setattr(contenido, campo, valor)
        contenido.updated_at = utc_now()
        if usuario:
            contenido.updated_by = usuario
        db.commit()
        db.refresh(contenido)
        return contenido

    @staticmethod
    def eliminar(db: Session, empresa_id: uuid.UUID, id: str) -> bool:
        contenido = (
            db.query(ContenidoCMS)
            .filter(
                ContenidoCMS.id == uuid.UUID(id),
                ContenidoCMS.empresa_id == empresa_id,
                ContenidoCMS.deleted_at.is_(None),
            )
            .first()
        )
        if not contenido:
            return False
        contenido.deleted_at = utc_now()
        db.commit()
        return True


class Vista360Service:
    """Servicio para vista 360 de empleados con Star Miles."""

    @staticmethod
    def listar_empleados_360(
        db: Session, empresa_id: uuid.UUID, pagina: int = 1, por_pagina: int = 20, filtros: Dict = None
    ) -> Dict:
        """Lista todos los empleados de la empresa con sus millas, inscripciones y canjes."""
        from sqlalchemy import func as sqlfunc

        from backend.modules.nomina.models import Empleado

        filtros = filtros or {}

        # Expresiones de millas con coalesce para empleados sin cuenta de Star Miles.
        millas_historicas_expr = sqlfunc.coalesce(EmpleadoStarMiles.millas_historicas, 0)
        millas_disponibles_expr = sqlfunc.coalesce(EmpleadoStarMiles.millas_disponibles, 0)

        # Query base desde EMPLEADOS (no desde starmiles_empleados) con outerjoin a la
        # cuenta de millas para poder ordenar/filtrar por millas en la base de datos.
        # Así mostramos TODOS los empleados, tengan o no cuenta de millas.
        query = (
            db.query(Empleado)
            .outerjoin(
                EmpleadoStarMiles,
                and_(
                    EmpleadoStarMiles.empleado_id == Empleado.id,
                    EmpleadoStarMiles.empresa_id == empresa_id,
                    EmpleadoStarMiles.deleted_at.is_(None),
                ),
            )
            .filter(Empleado.deleted_at.is_(None), Empleado.activo == True, Empleado.empresa_id == empresa_id)
        )

        # Filtro de búsqueda por texto
        if filtros.get("buscar"):
            buscar = f"%{filtros['buscar']}%"
            query = query.filter(
                or_(
                    Empleado.nombre.ilike(buscar),
                    Empleado.apellido.ilike(buscar),
                    Empleado.email_corporativo.ilike(buscar),
                )
            )

        # Filtro por rango de millas históricas (acumuladas)
        if filtros.get("millas_min") is not None:
            query = query.filter(millas_historicas_expr >= filtros["millas_min"])
        if filtros.get("millas_max") is not None:
            query = query.filter(millas_historicas_expr <= filtros["millas_max"])

        total = query.count()

        # Ordenamiento dinámico (ranking). Por defecto: millas históricas desc.
        orden = filtros.get("orden") or "millas_historicas"
        direccion = (filtros.get("direccion") or "desc").lower()
        es_desc = direccion != "asc"

        columnas_orden = {
            "millas_historicas": millas_historicas_expr,
            "millas_disponibles": millas_disponibles_expr,
            "nombre": None,  # se maneja aparte (apellido, nombre)
        }
        if orden not in columnas_orden:
            orden = "millas_historicas"

        if orden == "nombre":
            if es_desc:
                query = query.order_by(Empleado.apellido.desc(), Empleado.nombre.desc())
            else:
                query = query.order_by(Empleado.apellido.asc(), Empleado.nombre.asc())
        else:
            col = columnas_orden[orden]
            col_ordenada = col.desc() if es_desc else col.asc()
            # Desempate estable por apellido/nombre
            query = query.order_by(col_ordenada, Empleado.apellido.asc(), Empleado.nombre.asc())

        # Totales globales de la empresa (no paginados) con queries agregadas
        total_millas_acreditadas = (
            db.query(sqlfunc.coalesce(sqlfunc.sum(EmpleadoStarMiles.millas_historicas), 0))
            .filter(EmpleadoStarMiles.empresa_id == empresa_id, EmpleadoStarMiles.deleted_at.is_(None))
            .scalar()
            or 0
        )

        total_millas_canjeadas = (
            db.query(sqlfunc.coalesce(sqlfunc.sum(Canje.star_miles_total), 0))
            .filter(
                Canje.empresa_id == empresa_id, Canje.deleted_at.is_(None), Canje.estado.in_(["aprobado", "entregado"])
            )
            .scalar()
            or 0
        )

        total_inscripciones_global = (
            db.query(sqlfunc.count(InscripcionDesafio.id))
            .filter(InscripcionDesafio.empresa_id == empresa_id, InscripcionDesafio.deleted_at.is_(None))
            .scalar()
            or 0
        )

        total_canjes_global = (
            db.query(sqlfunc.count(Canje.id))
            .filter(Canje.empresa_id == empresa_id, Canje.deleted_at.is_(None))
            .scalar()
            or 0
        )

        empleados = query.offset((pagina - 1) * por_pagina).limit(por_pagina).all()

        # Construir respuesta con detalle
        items = []
        # Posición de ranking (continúa a través de las páginas)
        posicion = (pagina - 1) * por_pagina

        for empleado in empleados:
            posicion += 1
            # Buscar cuenta de millas (puede no existir)
            cuenta = (
                db.query(EmpleadoStarMiles)
                .filter(
                    EmpleadoStarMiles.empleado_id == empleado.id,
                    EmpleadoStarMiles.empresa_id == empresa_id,
                    EmpleadoStarMiles.deleted_at.is_(None),
                )
                .first()
            )

            millas_historicas = cuenta.millas_historicas if cuenta else 0
            millas_disponibles = cuenta.millas_disponibles if cuenta else 0

            # Obtener inscripciones del empleado
            inscripciones = (
                db.query(InscripcionDesafio)
                .filter(
                    InscripcionDesafio.empleado_id == empleado.id,
                    InscripcionDesafio.empresa_id == empresa_id,
                    InscripcionDesafio.deleted_at.is_(None),
                )
                .order_by(InscripcionDesafio.fecha_solicitud.desc())
                .all()
            )

            # Obtener canjes del empleado
            canjes = (
                db.query(Canje)
                .filter(Canje.empleado_id == empleado.id, Canje.empresa_id == empresa_id, Canje.deleted_at.is_(None))
                .order_by(Canje.fecha_solicitud.desc())
                .all()
            )

            # Calcular totales
            perfil_nombre = empleado.perfil_rel.nombre if empleado.perfil_rel else None

            items.append(
                {
                    "id": str(cuenta.id) if cuenta else None,
                    "posicion": posicion,
                    "empleado_id": str(empleado.id),
                    "empleado_nombre": empleado.empleado_nombre_completo,
                    "empleado_email": empleado.email_corporativo,
                    "empleado_cargo": perfil_nombre,
                    "millas_historicas": millas_historicas,
                    "millas_disponibles": millas_disponibles,
                    "total_inscripciones": len(inscripciones),
                    "total_canjes": len(canjes),
                    "inscripciones": [
                        {
                            "id": str(i.id),
                            "desafio_nombre": i.desafio.nombre,
                            "desafio_star_miles": i.desafio.star_miles,
                            "estado": i.estado,
                            "fecha_solicitud": i.fecha_solicitud,
                            "fecha_finalizacion": i.fecha_finalizacion,
                        }
                        for i in inscripciones
                    ],
                    "canjes": [
                        {
                            "id": str(c.id),
                            "item_nombre": c.item.nombre,
                            "cantidad": c.cantidad,
                            "star_miles_total": c.star_miles_total,
                            "estado": c.estado,
                            "fecha_solicitud": c.fecha_solicitud,
                            "fecha_entrega": c.fecha_entrega,
                        }
                        for c in canjes
                    ],
                }
            )

        return {
            "items": items,
            "total": total,
            "pagina": pagina,
            "por_pagina": por_pagina,
            "total_paginas": math.ceil(total / por_pagina) or 1,
            "total_millas_acreditadas": total_millas_acreditadas,
            "total_millas_canjeadas": total_millas_canjeadas,
            "total_inscripciones": total_inscripciones_global,
            "total_canjes": total_canjes_global,
        }

    @staticmethod
    def obtener_empleado_360(db: Session, empresa_id: uuid.UUID, empleado_id: str) -> Optional[Dict]:
        """Obtiene detalle 360 de un empleado específico."""
        from backend.modules.nomina.models import Empleado

        # Buscar primero el empleado
        empleado = (
            db.query(Empleado)
            .filter(
                Empleado.id == uuid.UUID(empleado_id), Empleado.deleted_at.is_(None), Empleado.empresa_id == empresa_id
            )
            .first()
        )

        if not empleado:
            return None

        # Buscar cuenta de millas (puede no existir)
        cuenta = (
            db.query(EmpleadoStarMiles)
            .filter(
                EmpleadoStarMiles.empleado_id == empleado.id,
                EmpleadoStarMiles.empresa_id == empresa_id,
                EmpleadoStarMiles.deleted_at.is_(None),
            )
            .first()
        )

        millas_historicas = cuenta.millas_historicas if cuenta else 0
        millas_disponibles = cuenta.millas_disponibles if cuenta else 0

        # Obtener inscripciones
        inscripciones = (
            db.query(InscripcionDesafio)
            .filter(
                InscripcionDesafio.empleado_id == empleado.id,
                InscripcionDesafio.empresa_id == empresa_id,
                InscripcionDesafio.deleted_at.is_(None),
            )
            .order_by(InscripcionDesafio.fecha_solicitud.desc())
            .all()
        )

        # Obtener canjes
        canjes = (
            db.query(Canje)
            .filter(Canje.empleado_id == empleado.id, Canje.empresa_id == empresa_id, Canje.deleted_at.is_(None))
            .order_by(Canje.fecha_solicitud.desc())
            .all()
        )

        # Obtener nombre del perfil si existe
        perfil_nombre = empleado.perfil_rel.nombre if empleado.perfil_rel else None

        return {
            "id": str(cuenta.id) if cuenta else None,
            "empleado_id": str(empleado.id),
            "empleado_nombre": empleado.empleado_nombre_completo,
            "empleado_email": empleado.email_corporativo,
            "empleado_cargo": perfil_nombre,
            "millas_historicas": millas_historicas,
            "millas_disponibles": millas_disponibles,
            "total_inscripciones": len(inscripciones),
            "total_canjes": len(canjes),
            "inscripciones": [
                {
                    "id": str(i.id),
                    "desafio_nombre": i.desafio.nombre,
                    "desafio_star_miles": i.desafio.star_miles,
                    "estado": i.estado,
                    "fecha_solicitud": i.fecha_solicitud,
                    "fecha_finalizacion": i.fecha_finalizacion,
                }
                for i in inscripciones
            ],
            "canjes": [
                {
                    "id": str(c.id),
                    "item_nombre": c.item.nombre,
                    "cantidad": c.cantidad,
                    "star_miles_total": c.star_miles_total,
                    "estado": c.estado,
                    "fecha_solicitud": c.fecha_solicitud,
                    "fecha_entrega": c.fecha_entrega,
                }
                for c in canjes
            ],
        }


# ─── Servicio de archivos de Star Miles ────────────────────────────────────────

logger = logging.getLogger(__name__)

STARMILES_DIR = Path("/data/files/starmiles")
STARMILES_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_STARMILES_FILE_SIZE = 5 * 1024 * 1024  # 5MB (se acepta más porque se comprime)

# Dimensiones máximas por contexto de uso (ancho, alto).
# Calculadas a partir de los tamaños reales de las cards en la UI,
# con margen 2x para pantallas retina.
IMAGE_SIZE_BY_CONTEXT = {
    "desafio": (800, 400),  # Card grilla 3 cols: ~400px ancho × h-40 (160px)
    "canje": (600, 400),  # Card grilla 4 cols: ~300px ancho × h-48 (192px)
    "cms_banner": (1200, 600),  # Banner full-width home: ~1200px × h-48 (192px)
    "cms_noticia": (800, 400),  # Noticia home: ~350px × h-32 (128px)
    "default": (800, 500),  # Fallback genérico
}

JPEG_QUALITY = 85


class StarMilesFileService:
    """Servicio para manejo de archivos de imágenes de Star Miles."""

    @staticmethod
    def init_directories():
        """Crea los directorios necesarios si no existen."""
        STARMILES_DIR.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def compress_image(content: bytes, context: str = "default") -> bytes:
        """
        Comprime y redimensiona una imagen para que se ajuste al tamaño
        máximo que necesita la UI según el contexto de uso.

        - Redimensiona manteniendo proporción (thumbnail fit).
        - Convierte a JPEG (RGB) con calidad 85.
        - Si la imagen ya es más chica que el máximo, solo recomprime.
        """
        max_size = IMAGE_SIZE_BY_CONTEXT.get(context, IMAGE_SIZE_BY_CONTEXT["default"])

        img = Image.open(BytesIO(content))

        # Respetar orientación EXIF (fotos de celular rotadas)
        try:
            from PIL import ImageOps

            img = ImageOps.exif_transpose(img)
        except Exception:
            pass

        # Redimensionar solo si excede el bounding box
        img.thumbnail(max_size, Image.LANCZOS)

        # Convertir a RGB si tiene canal alpha (PNG con transparencia)
        if img.mode in ("RGBA", "LA", "P"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            background.paste(img, mask=img.split()[-1])
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")

        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        return buffer.getvalue()

    @staticmethod
    async def save_image(file: UploadFile, context: str = "default") -> str:
        """
        Guarda una imagen de Star Miles comprimida y retorna la URL relativa.

        Args:
            file: Archivo subido.
            context: Contexto de uso ('desafio', 'canje', 'cms_banner', 'cms_noticia').
                     Determina las dimensiones máximas de compresión.
        """
        ext = Path(file.filename).suffix.lower()
        if ext not in STARMILES_ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400, detail=f"Tipo de archivo no permitido. Use: {', '.join(STARMILES_ALLOWED_EXTENSIONS)}"
            )

        content = await file.read()
        if len(content) > MAX_STARMILES_FILE_SIZE:
            raise HTTPException(status_code=400, detail="El archivo excede el tamaño máximo de 5MB")

        # Comprimir y redimensionar según contexto
        try:
            compressed = StarMilesFileService.compress_image(content, context)
        except Exception as e:
            logger.error(f"Error al comprimir imagen: {e}", exc_info=True)
            raise HTTPException(
                status_code=400, detail="No se pudo procesar la imagen. Verifique que sea un archivo de imagen válido."
            )

        file_hash = hashlib.sha256(compressed).hexdigest()[:16]
        unique_id = uuid.uuid4().hex[:8]
        filename = f"{file_hash}_{unique_id}.jpg"

        StarMilesFileService.init_directories()
        file_path = STARMILES_DIR / filename
        with open(file_path, "wb") as f:
            f.write(compressed)

        logger.info(
            f"Imagen guardada: context={context}, "
            f"original={len(content)}B, comprimida={len(compressed)}B, "
            f"reduccion={100 - (len(compressed) * 100 // len(content))}%"
        )

        return f"/files/starmiles/{filename}"

    @staticmethod
    def delete_image(url: str) -> bool:
        """Elimina una imagen de Star Miles dado su URL."""
        if not url or not url.startswith("/files/starmiles/"):
            return False

        filename = url.split("/")[-1]
        file_path = (STARMILES_DIR / filename).resolve()

        if not str(file_path).startswith(str(STARMILES_DIR.resolve())):
            return False

        if file_path.exists():
            file_path.unlink()
            return True
        return False
