"""
Servicios para Gestión de Licencias.
"""

import math
import uuid
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from backend.core.utils import utc_now
from backend.modules.innovacion.licencias_models import (
    MONEDA_DEFAULT,
    Herramienta,
    Licencia,
    Proveedor,
)
from backend.modules.innovacion.licencias_utils import normalizar_nombre
from backend.modules.nomina.models import Empleado
from backend.modules.operaciones.models import Equipo, equipo_integrantes


def _uuid_o_none(valor) -> Optional[uuid.UUID]:
    """Parsea un uuid que viene de la request. None si es malformado."""
    try:
        return uuid.UUID(str(valor))
    except ValueError, AttributeError, TypeError:
        return None


class ReferenciaInvalida(Exception):
    """Una FK apunta a una fila que no existe o es de otra empresa.

    Se informa como 404 y sin decir cual de las dos referencias fallo: confirmar
    que un id ajeno existe ya seria filtrar datos de la otra empresa.
    """


class ProveedorService:
    """Catalogo de proveedores, para elegir de los ya creados."""

    @staticmethod
    def listar(db: Session, empresa_id: uuid.UUID) -> List[Proveedor]:
        return (
            db.query(Proveedor)
            .filter(
                Proveedor.deleted_at.is_(None),
                Proveedor.empresa_id == empresa_id,
                Proveedor.activo.is_(True),
            )
            .order_by(Proveedor.nombre)
            .all()
        )

    @staticmethod
    def obtener_o_crear(db: Session, empresa_id: uuid.UUID, nombre: str, usuario: str = None) -> Optional[Proveedor]:
        """Reusa el proveedor por nombre plegado, recuperandolo si fue borrado.

        Asi el alta de una herramienta no obliga a pasar antes por otra
        pantalla, y el nombre repetido con otra capitalizacion reusa el
        proveedor existente en lugar de duplicarlo.
        """
        nombre = (nombre or "").strip()
        normalizado = normalizar_nombre(nombre)
        if not normalizado:
            return None

        existente = (
            db.query(Proveedor)
            .filter(
                Proveedor.empresa_id == empresa_id,
                Proveedor.nombre_normalizado == normalizado,
            )
            .order_by(Proveedor.deleted_at.desc().nullsfirst(), Proveedor.id)
            .first()
        )
        if existente:
            if existente.deleted_at is not None:
                existente.nombre = nombre
                existente.deleted_at = None
                existente.activo = True
                existente.updated_by = usuario
                db.flush()
            return existente

        proveedor = Proveedor(
            empresa_id=empresa_id,
            nombre=nombre,
            nombre_normalizado=normalizado,
            created_by=usuario,
            updated_by=usuario,
        )
        db.add(proveedor)
        db.flush()
        return proveedor

    @staticmethod
    def actualizar(db: Session, empresa_id: uuid.UUID, id: str, nombre: str, usuario: str = None) -> Proveedor:
        """Corrige el nombre conservando las herramientas que lo referencian."""
        proveedor = ProveedorService.validar_de_la_empresa(db, empresa_id, id)
        nombre = nombre.strip()
        normalizado = normalizar_nombre(nombre)
        if not normalizado:
            raise ValueError("El nombre del proveedor es obligatorio")
        duplicado = (
            db.query(Proveedor.id)
            .filter(
                Proveedor.empresa_id == empresa_id,
                Proveedor.nombre_normalizado == normalizado,
                Proveedor.id != proveedor.id,
                Proveedor.deleted_at.is_(None),
            )
            .first()
        )
        if duplicado:
            raise ValueError(f"Ya existe otro proveedor '{nombre}'")
        proveedor.nombre = nombre
        proveedor.nombre_normalizado = normalizado
        proveedor.updated_by = usuario
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise ValueError("El proveedor ya existe")
        db.refresh(proveedor)
        return proveedor

    @staticmethod
    def eliminar(db: Session, empresa_id: uuid.UUID, id: str, usuario: str = None) -> bool:
        """Baja lógica del proveedor, sus herramientas y sus asignaciones en una transacción."""
        proveedor = ProveedorService.validar_de_la_empresa(db, empresa_id, id)
        ahora = utc_now()
        baja = {"deleted_at": ahora, "updated_at": ahora, "updated_by": usuario}
        herramientas = db.query(Herramienta.id).filter(
            Herramienta.empresa_id == empresa_id,
            Herramienta.proveedor_id == proveedor.id,
        )
        db.query(Licencia).filter(
            Licencia.empresa_id == empresa_id,
            Licencia.herramienta_id.in_(herramientas),
            Licencia.deleted_at.is_(None),
        ).update(baja, synchronize_session=False)
        db.query(Herramienta).filter(
            Herramienta.empresa_id == empresa_id,
            Herramienta.proveedor_id == proveedor.id,
            Herramienta.deleted_at.is_(None),
        ).update(baja, synchronize_session=False)
        proveedor.deleted_at = ahora
        proveedor.updated_at = ahora
        proveedor.updated_by = usuario
        db.commit()
        return True

    @staticmethod
    def validar_de_la_empresa(db: Session, empresa_id: uuid.UUID, proveedor_id) -> Proveedor:
        """El id viaja en el body: tiene que ser de la empresa activa."""
        proveedor = (
            db.query(Proveedor)
            .filter(
                Proveedor.id == _uuid_o_none(proveedor_id),
                Proveedor.empresa_id == empresa_id,
                Proveedor.deleted_at.is_(None),
            )
            .first()
        )
        if not proveedor:
            raise ReferenciaInvalida("El proveedor no existe")
        return proveedor


class HerramientaService:
    """Catalogo de herramientas: una fila por herramienta, no por licencia."""

    @staticmethod
    def listar(db: Session, empresa_id: uuid.UUID) -> List[Herramienta]:
        """Lista el catalogo activo para poblar selects y filtros."""
        return (
            db.query(Herramienta)
            .options(joinedload(Herramienta.proveedor_rel))
            .filter(
                Herramienta.deleted_at.is_(None),
                Herramienta.empresa_id == empresa_id,
                Herramienta.activo.is_(True),
            )
            .order_by(Herramienta.nombre)
            .all()
        )

    @staticmethod
    def crear(db: Session, empresa_id: uuid.UUID, datos: Dict[str, Any], usuario: str = None) -> Herramienta:
        """Crea o recupera una herramienta, rechazando nombres ya disponibles."""
        nombre = (datos.get("nombre") or "").strip()
        normalizado = normalizar_nombre(nombre)
        if not normalizado:
            raise ValueError("El nombre de la herramienta es obligatorio")

        existente = (
            db.query(Herramienta)
            .filter(
                Herramienta.empresa_id == empresa_id,
                Herramienta.nombre_normalizado == normalizado,
            )
            .order_by(Herramienta.deleted_at.desc().nullsfirst(), Herramienta.id)
            .first()
        )
        if existente and existente.deleted_at is None:
            raise ValueError(f"La herramienta '{existente.nombre}' ya existe")

        # El proveedor llega elegido del catalogo, o por nombre para crearlo
        # al vuelo sin salir del alta de la herramienta.
        proveedor = None
        if datos.get("proveedor_id"):
            proveedor = ProveedorService.validar_de_la_empresa(db, empresa_id, datos["proveedor_id"])
        elif datos.get("proveedor_nombre"):
            proveedor = ProveedorService.obtener_o_crear(db, empresa_id, datos["proveedor_nombre"], usuario)

        herramienta = existente or Herramienta(
            empresa_id=empresa_id,
            created_by=usuario,
        )
        herramienta.nombre = nombre
        herramienta.nombre_normalizado = normalizado
        herramienta.proveedor_id = proveedor.id if proveedor else None
        herramienta.costo_referencia = datos.get("costo_referencia")
        herramienta.moneda = datos.get("moneda") or MONEDA_DEFAULT
        herramienta.deleted_at = None
        herramienta.activo = True
        herramienta.updated_by = usuario
        db.add(herramienta)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            raise ValueError("La herramienta ya existe")
        db.refresh(herramienta)
        return herramienta

    @staticmethod
    def _de_la_empresa(db: Session, empresa_id: uuid.UUID, id: str) -> Herramienta:
        herramienta = (
            db.query(Herramienta)
            .filter(
                Herramienta.id == _uuid_o_none(id),
                Herramienta.empresa_id == empresa_id,
                Herramienta.deleted_at.is_(None),
            )
            .first()
        )
        if not herramienta:
            raise ReferenciaInvalida("La herramienta no existe")
        return herramienta

    @staticmethod
    def actualizar(
        db: Session, empresa_id: uuid.UUID, id: str, datos: Dict[str, Any], usuario: str = None
    ) -> Herramienta:
        """Corrige nombre, proveedor y costo. Es como se arregla un typo."""
        herramienta = HerramientaService._de_la_empresa(db, empresa_id, id)

        if datos.get("nombre"):
            nombre = datos["nombre"].strip()
            normalizado = normalizar_nombre(nombre)
            if not normalizado:
                raise ValueError("El nombre de la herramienta es obligatorio")
            choca = (
                db.query(Herramienta.id)
                .filter(
                    Herramienta.empresa_id == empresa_id,
                    Herramienta.nombre_normalizado == normalizado,
                    Herramienta.id != herramienta.id,
                    Herramienta.deleted_at.is_(None),
                )
                .first()
            )
            if choca:
                raise ValueError(f"Ya existe otra herramienta '{nombre}'")
            herramienta.nombre = nombre
            herramienta.nombre_normalizado = normalizado

        # Reapuntar el proveedor: una cadena vacía deja la herramienta sin proveedor.
        if "proveedor_id" in datos:
            if datos["proveedor_id"]:
                proveedor = ProveedorService.validar_de_la_empresa(db, empresa_id, datos["proveedor_id"])
                herramienta.proveedor_id = proveedor.id
            else:
                herramienta.proveedor_id = None
        elif datos.get("proveedor_nombre"):
            proveedor = ProveedorService.obtener_o_crear(db, empresa_id, datos["proveedor_nombre"], usuario)
            herramienta.proveedor_id = proveedor.id if proveedor else None

        if "costo_referencia" in datos:
            herramienta.costo_referencia = datos["costo_referencia"]
        if datos.get("moneda"):
            herramienta.moneda = datos["moneda"]

        herramienta.updated_by = usuario
        db.commit()
        db.refresh(herramienta)
        return herramienta

    @staticmethod
    def eliminar(db: Session, empresa_id: uuid.UUID, id: str, usuario: str = None) -> bool:
        """Baja lógica de la herramienta y todas sus asignaciones en la empresa activa."""
        herramienta = HerramientaService._de_la_empresa(db, empresa_id, id)
        ahora = utc_now()
        db.query(Licencia).filter(
            Licencia.empresa_id == empresa_id,
            Licencia.herramienta_id == herramienta.id,
            Licencia.deleted_at.is_(None),
        ).update({"deleted_at": ahora, "updated_at": ahora, "updated_by": usuario}, synchronize_session=False)
        herramienta.deleted_at = ahora
        herramienta.updated_at = ahora
        herramienta.updated_by = usuario
        db.commit()
        return True


class LicenciaService:
    """Servicio para operaciones de Licencias."""

    @staticmethod
    def listar_equipos(db: Session, empresa_id: uuid.UUID) -> List[dict]:
        """Equipos y sus integrantes elegibles, en dos consultas sin fichas de nomina."""
        equipos = (
            db.query(Equipo.id, Equipo.nombre)
            .filter(
                Equipo.deleted_at.is_(None),
                Equipo.empresa_id == empresa_id,
                Equipo.activo.is_(True),
            )
            .order_by(Equipo.nombre, Equipo.id)
            .all()
        )
        opciones = {
            equipo.id: {"id": str(equipo.id), "nombre": equipo.nombre, "empleado_ids": []} for equipo in equipos
        }
        if opciones:
            integrantes = (
                db.query(
                    equipo_integrantes.c.equipo_id,
                    Empleado.id,
                )
                .select_from(equipo_integrantes)
                .join(
                    Empleado,
                    Empleado.id == equipo_integrantes.c.empleado_id,
                )
                .filter(
                    equipo_integrantes.c.equipo_id.in_(opciones),
                    Empleado.empresa_id == empresa_id,
                    Empleado.activo.is_(True),
                    Empleado.deleted_at.is_(None),
                )
                .order_by(Empleado.apellido, Empleado.nombre, Empleado.id)
                .all()
            )
            for integrante in integrantes:
                opciones[integrante.equipo_id]["empleado_ids"].append(str(integrante.id))
        return list(opciones.values())

    @staticmethod
    def listar_empleados(db: Session, empresa_id: uuid.UUID) -> List:
        """Opciones del filtro, sin cargar la ficha ni relaciones de la nomina."""
        return (
            db.query(
                Empleado.id,
                Empleado.apellido,
                Empleado.nombre,
                Empleado.codigo,
            )
            .filter(
                Empleado.empresa_id == empresa_id,
                Empleado.activo.is_(True),
                Empleado.deleted_at.is_(None),
            )
            .order_by(Empleado.apellido, Empleado.nombre, Empleado.id)
            .all()
        )

    @staticmethod
    def _integrantes_activos(db: Session, empresa_id: uuid.UUID):
        """Pertenencias a equipos vigentes de la empresa activa."""
        return (
            db.query(
                equipo_integrantes.c.empleado_id,
                Equipo.id.label("equipo_id"),
                Equipo.nombre.label("equipo_nombre"),
            )
            .select_from(equipo_integrantes)
            .join(Equipo, Equipo.id == equipo_integrantes.c.equipo_id)
            .filter(
                Equipo.empresa_id == empresa_id,
                Equipo.activo.is_(True),
                Equipo.deleted_at.is_(None),
            )
        )

    @staticmethod
    def _validar_referencias(db: Session, empresa_id: uuid.UUID, datos: Dict[str, Any]) -> None:
        """La herramienta y el empleado tienen que ser de la empresa activa.

        El id viaja en el body, asi que sin este chequeo se puede apuntar una
        licencia propia al catalogo de otra empresa y leer su nombre y proveedor
        desde el listado.
        """

        def _uuid(valor, etiqueta):
            # El id llega como texto del body: un valor malformado es una
            # referencia invalida, no un error interno.
            try:
                return uuid.UUID(str(valor))
            except ValueError, AttributeError, TypeError:
                raise ReferenciaInvalida(f"{etiqueta} no existe")

        # Presencia, no verdad: '' debe fallar como referencia invalida,
        # no saltear el chequeo y romper en el insert.
        if datos.get("herramienta_id") is not None:
            herramienta_id = datos["herramienta_id"]
            existe = (
                db.query(Herramienta.id)
                .filter(
                    Herramienta.id == _uuid(herramienta_id, "La herramienta"),
                    Herramienta.empresa_id == empresa_id,
                    Herramienta.activo.is_(True),
                    Herramienta.deleted_at.is_(None),
                )
                .first()
            )
            if not existe:
                raise ReferenciaInvalida("La herramienta no existe")

        if datos.get("empleado_id") is not None:
            empleado_id = datos["empleado_id"]
            existe = (
                db.query(Empleado.id)
                .filter(
                    Empleado.id == _uuid(empleado_id, "El empleado"),
                    Empleado.empresa_id == empresa_id,
                    Empleado.activo.is_(True),
                    Empleado.deleted_at.is_(None),
                )
                .first()
            )
            if not existe:
                raise ReferenciaInvalida("El empleado no existe")

        if "empleado_ids" in datos:
            ids = {_uuid(valor, "El empleado") for valor in datos["empleado_ids"]}
            cantidad = (
                db.query(Empleado.id)
                .filter(
                    Empleado.id.in_(ids),
                    Empleado.empresa_id == empresa_id,
                    Empleado.activo.is_(True),
                    Empleado.deleted_at.is_(None),
                )
                .count()
            )
            if not ids or cantidad != len(ids):
                raise ReferenciaInvalida("Uno o mas empleados no estan disponibles")

    @staticmethod
    def crear(db: Session, empresa_id: uuid.UUID, datos: Dict[str, Any], usuario: str = None) -> Licencia:
        """Crea una nueva licencia. Nace activa: no hay circuito de aprobacion."""
        LicenciaService._validar_referencias(db, empresa_id, datos)
        try:
            datos.setdefault("activa", True)
            if usuario:
                datos["updated_by"] = usuario
            licencia = Licencia(empresa_id=empresa_id, **datos)
            db.add(licencia)
            db.commit()
            db.refresh(licencia)
            return licencia
        except IntegrityError:
            db.rollback()
            raise ValueError("Error al crear la licencia")

    @staticmethod
    def crear_lote(db: Session, empresa_id: uuid.UUID, datos: Dict[str, Any], usuario: str = None) -> int:
        """Valida toda la seleccion y confirma una licencia por persona en conjunto."""
        try:
            comunes = dict(datos)
            empleado_ids = list(dict.fromkeys(_uuid_o_none(valor) for valor in comunes.pop("empleado_ids")))
            licencias = comunes.pop("licencias", None) or [comunes]
            for condiciones in licencias:
                LicenciaService._validar_referencias(
                    db,
                    empresa_id,
                    {**condiciones, "empleado_ids": empleado_ids},
                )
            db.add_all(
                [
                    Licencia(
                        empresa_id=empresa_id,
                        empleado_id=empleado_id,
                        activa=True,
                        updated_by=usuario,
                        **condiciones,
                    )
                    for condiciones in licencias
                    for empleado_id in empleado_ids
                ]
            )
            db.commit()
            return len(empleado_ids) * len(licencias)
        except IntegrityError as error:
            db.rollback()
            raise ValueError("No se pudieron crear las licencias") from error
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def obtener(db: Session, empresa_id: uuid.UUID, id: str) -> Optional[Licencia]:
        """Obtiene una licencia por ID."""
        return (
            db.query(Licencia)
            .filter(Licencia.id == _uuid_o_none(id), Licencia.deleted_at.is_(None), Licencia.empresa_id == empresa_id)
            .first()
        )

    @staticmethod
    def _query_filtrada(db: Session, empresa_id: uuid.UUID, filtros: Dict = None):
        """Query base de licencias con los filtros aplicados, sin orden ni paginado."""
        query = (
            db.query(Licencia)
            .join(Herramienta, Licencia.herramienta_id == Herramienta.id)
            .join(Empleado, Licencia.empleado_id == Empleado.id)
            .outerjoin(Proveedor, Herramienta.proveedor_id == Proveedor.id)
            .filter(Licencia.deleted_at.is_(None), Licencia.empresa_id == empresa_id)
        )

        if not filtros:
            return query

        if filtros.get("buscar"):
            buscar = f"%{filtros['buscar']}%"
            query = query.filter(
                or_(
                    Herramienta.nombre.ilike(buscar),
                    Proveedor.nombre.ilike(buscar),
                    Empleado.apellido.ilike(buscar),
                    Empleado.nombre.ilike(buscar),
                    Licencia.nro_pedido_compra.ilike(buscar),
                )
            )
        empleado_ids = filtros.get("empleado_ids")
        if empleado_ids is None:
            empleado_ids = [filtros["empleado_id"]] if filtros.get("empleado_id") else []
        if empleado_ids:
            ids_validos = [id_ for valor in empleado_ids if (id_ := _uuid_o_none(valor)) is not None]
            query = query.filter(Licencia.empleado_id.in_(ids_validos))
        equipo_ids = filtros.get("equipo_ids") or ([filtros["equipo_id"]] if filtros.get("equipo_id") else [])
        if equipo_ids:
            # Un empleado puede estar en varios equipos: alcanza con pertenecer.
            query = query.filter(
                Licencia.empleado_id.in_(
                    LicenciaService._integrantes_activos(db, empresa_id)
                    .filter(Equipo.id.in_([id_ for valor in equipo_ids if (id_ := _uuid_o_none(valor)) is not None]))
                    .with_entities(equipo_integrantes.c.empleado_id)
                )
            )
        if filtros.get("proveedor_id"):
            proveedor_id = _uuid_o_none(filtros["proveedor_id"])
            query = query.filter(Herramienta.proveedor_id == proveedor_id if proveedor_id else False)
        return query

    @staticmethod
    def _ventana_mes(referencia: date, meses_adelante: int = 0) -> tuple:
        """Primer y ultimo dia del mes desplazado `meses_adelante`."""
        indice = referencia.year * 12 + (referencia.month - 1) + meses_adelante
        primero = date(indice // 12, indice % 12 + 1, 1)
        primero_del_siguiente = date((indice + 1) // 12, (indice + 1) % 12 + 1, 1)
        return primero, primero_del_siguiente - timedelta(days=1)

    @staticmethod
    def _totales_mes_actual(licencias: List[Licencia]) -> List[dict]:
        """Mismo periodo que la tarjeta Mes actual, antes de serializar fechas."""
        primero, ultimo = LicenciaService._ventana_mes(date.today())
        acumulado = {}
        for licencia in licencias:
            if (
                licencia.activa
                and licencia.fecha_inicio <= ultimo
                and (licencia.fecha_fin is None or licencia.fecha_fin >= primero)
            ):
                moneda = licencia.moneda or MONEDA_DEFAULT
                acumulado[moneda] = acumulado.get(moneda, Decimal("0")) + (licencia.costo_mensual or Decimal("0"))
        return [{"moneda": moneda, "total": float(total)} for moneda, total in sorted(acumulado.items())]

    @staticmethod
    def metricas_gasto(db: Session, empresa_id: uuid.UUID, filtros: Dict = None, hoy: date = None) -> Dict:
        """Gasto mensual vigente del mes en curso y del anterior, por moneda.

        Cuenta solo las licencias vigentes cuya vigencia cubre la ventana del
        mes. La diferencia entre ambos meses es lo que se vence o arranca, y
        activar o suspender una licencia mueve los dos numeros.
        """
        hoy = hoy or date.today()
        base = LicenciaService._query_filtrada(db, empresa_id, filtros).filter(Licencia.activa.is_(True))

        def total_del_mes(meses_adelante: int) -> List[dict]:
            primero, ultimo = LicenciaService._ventana_mes(hoy, meses_adelante)
            filas = (
                base.filter(
                    Licencia.fecha_inicio <= ultimo, or_(Licencia.fecha_fin.is_(None), Licencia.fecha_fin >= primero)
                )
                .with_entities(Licencia.moneda, func.coalesce(func.sum(Licencia.costo_mensual), 0))
                .group_by(Licencia.moneda)
                .all()
            )
            return [{"moneda": moneda, "total": float(total)} for moneda, total in filas]

        actual = total_del_mes(0)
        anterior = total_del_mes(-1)

        # Las tres cifras se informan sobre las mismas monedas, rellenando con
        # cero: si una moneda aparece en una tarjeta y falta en otra, se lee
        # como si faltara el dato.
        mapa_actual = {t["moneda"]: t["total"] for t in actual}
        mapa_anterior = {t["moneda"]: t["total"] for t in anterior}
        monedas = sorted(set(mapa_actual) | set(mapa_anterior))

        actual = [{"moneda": m, "total": mapa_actual.get(m, 0.0)} for m in monedas]
        anterior = [{"moneda": m, "total": mapa_anterior.get(m, 0.0)} for m in monedas]
        delta = [
            {
                "moneda": m,
                "total": round(mapa_actual.get(m, 0.0) - mapa_anterior.get(m, 0.0), 2),
            }
            for m in monedas
        ]

        # Los importes no se suman entre monedas, asi que el color de la tarjeta
        # sale del signo: si las monedas van para lados distintos, es mixta y no
        # se pinta, para no dar una senal falsa.
        signos = {1 if d["total"] > 0 else -1 for d in delta if d["total"]}
        if not signos:
            tendencia = "estable"
        elif signos == {1}:
            tendencia = "sube"
        elif signos == {-1}:
            tendencia = "baja"
        else:
            tendencia = "mixta"

        return {
            "mes_actual": actual,
            "mes_anterior": anterior,
            "delta": delta,
            "tendencia": tendencia,
        }

    @staticmethod
    def listar_por_empleado(
        db: Session, empresa_id: uuid.UUID, pagina: int = 1, por_pagina: int = 25, filtros: Dict = None
    ) -> Dict:
        """Una fila por empleado con sus licencias. Pagina empleados, no licencias.

        Solo aparecen empleados que tienen al menos una licencia que pase los
        filtros: la lista responde "quien tiene que", no la nomina completa.
        """
        base = LicenciaService._query_filtrada(db, empresa_id, filtros)

        # Pagina de empleados, ordenada por nombre.
        pagina_empleados = (
            base.with_entities(
                Licencia.empleado_id,
                func.min(Empleado.apellido).label("apellido"),
                func.min(Empleado.nombre).label("nombre"),
            )
            .group_by(Licencia.empleado_id)
            .order_by("apellido", "nombre")
        )

        total_empleados = base.with_entities(func.count(func.distinct(Licencia.empleado_id))).scalar() or 0

        filas = pagina_empleados.offset((pagina - 1) * por_pagina).limit(por_pagina).all()
        items = LicenciaService._grupos_empleados(base, filas)

        return {
            "items": list(items.values()),
            "total": total_empleados,
            "pagina": pagina,
            "por_pagina": por_pagina,
            "total_paginas": math.ceil(total_empleados / por_pagina) or 1,
        }

    @staticmethod
    def _grupos_empleados(base, filas) -> Dict:
        """Carga las licencias de la pagina en una sola consulta para ambas vistas."""
        grupos = {
            fila.empleado_id: {
                "empleado_id": fila.empleado_id,
                "empleado_nombre": f"{fila.apellido}, {fila.nombre}",
                "licencias": [],
            }
            for fila in filas
        }
        if grupos:
            licencias = (
                base.options(
                    joinedload(Licencia.herramienta_rel).joinedload(Herramienta.proveedor_rel),
                    joinedload(Licencia.empleado_rel),
                )
                .filter(Licencia.empleado_id.in_(grupos))
                .order_by(Herramienta.nombre)
                .all()
            )
            for licencia in licencias:
                grupos[licencia.empleado_id]["licencias"].append(licencia)
        for grupo in grupos.values():
            grupo["totales"] = LicenciaService._totales_mes_actual(grupo["licencias"])
        return grupos

    @staticmethod
    def listar_por_equipo(
        db: Session, empresa_id: uuid.UUID, pagina: int = 1, por_pagina: int = 25, filtros: Dict = None
    ) -> Dict:
        """Pagina equipos completos; las metricas conservan empleados sin duplicar."""
        base = LicenciaService._query_filtrada(db, empresa_id, filtros)
        integrantes = LicenciaService._integrantes_activos(db, empresa_id).subquery()
        por_equipo = base.outerjoin(integrantes, integrantes.c.empleado_id == Licencia.empleado_id)
        equipo_ids = (filtros or {}).get("equipo_ids") or (
            [filtros["equipo_id"]] if filtros and filtros.get("equipo_id") else []
        )
        if equipo_ids:
            por_equipo = por_equipo.filter(
                integrantes.c.equipo_id.in_([id_ for valor in equipo_ids if (id_ := _uuid_o_none(valor)) is not None])
            )

        grupos = por_equipo.with_entities(
            integrantes.c.equipo_id,
            integrantes.c.equipo_nombre,
            func.count(func.distinct(Licencia.empleado_id)).label("total_empleados"),
        ).group_by(integrantes.c.equipo_id, integrantes.c.equipo_nombre)
        total = grupos.count()
        total_empleados = base.with_entities(func.count(func.distinct(Licencia.empleado_id))).scalar() or 0
        equipos = (
            grupos.order_by(integrantes.c.equipo_nombre.asc().nullslast(), integrantes.c.equipo_id)
            .offset((pagina - 1) * por_pagina)
            .limit(por_pagina)
            .all()
        )

        items = []
        if equipos:
            ids = [equipo.equipo_id for equipo in equipos if equipo.equipo_id is not None]
            seleccion = integrantes.c.equipo_id.in_(ids)
            if any(equipo.equipo_id is None for equipo in equipos):
                seleccion = or_(seleccion, integrantes.c.equipo_id.is_(None))
            filas = (
                por_equipo.filter(seleccion)
                .with_entities(
                    integrantes.c.equipo_id,
                    Licencia.empleado_id,
                    Empleado.apellido,
                    Empleado.nombre,
                )
                .distinct()
                .order_by(Empleado.apellido, Empleado.nombre, Licencia.empleado_id)
                .all()
            )
            empleados = LicenciaService._grupos_empleados(base, filas)
            empleados_por_equipo = {equipo.equipo_id: [] for equipo in equipos}
            for fila in filas:
                empleados_por_equipo[fila.equipo_id].append(empleados[fila.empleado_id])
            for equipo in equipos:
                miembros = empleados_por_equipo[equipo.equipo_id]
                items.append(
                    {
                        "equipo_id": equipo.equipo_id,
                        "equipo_nombre": equipo.equipo_nombre or "Sin equipo",
                        "empleados": miembros,
                        "total_empleados": equipo.total_empleados,
                        "totales": LicenciaService._totales_mes_actual(
                            [lic for empleado in miembros for lic in empleado["licencias"]]
                        ),
                    }
                )

        return {
            "items": items,
            "total": total,
            "total_empleados": total_empleados,
            "pagina": pagina,
            "por_pagina": por_pagina,
            "total_paginas": math.ceil(total / por_pagina) or 1,
        }

    @staticmethod
    def actualizar(
        db: Session, empresa_id: uuid.UUID, id: str, datos: Dict[str, Any], usuario: str = None
    ) -> Optional[Licencia]:
        """Actualiza una licencia."""
        LicenciaService._validar_referencias(db, empresa_id, datos)
        licencia = (
            db.query(Licencia)
            .filter(Licencia.id == _uuid_o_none(id), Licencia.deleted_at.is_(None), Licencia.empresa_id == empresa_id)
            .first()
        )

        if not licencia:
            return None

        fecha_inicio = datos.get("fecha_inicio", licencia.fecha_inicio)
        fecha_fin = datos.get("fecha_fin", licencia.fecha_fin)
        if fecha_fin is not None and fecha_fin < fecha_inicio:
            raise ValueError("La fecha de fin no puede ser anterior a la fecha de inicio")

        for campo, valor in datos.items():
            if hasattr(licencia, campo) and campo not in ("id", "empresa_id"):
                setattr(licencia, campo, valor)

        licencia.updated_at = utc_now()
        if usuario:
            licencia.updated_by = usuario

        db.commit()
        db.refresh(licencia)
        return licencia

    @staticmethod
    def preparar_revocacion(db: Session, empresa_id: uuid.UUID, datos: Dict):
        return (
            LicenciaService._query_filtrada(db, empresa_id, datos)
            .filter(Licencia.herramienta_id == datos["herramienta_id"])
            .all()
        )

    @staticmethod
    def revocar_lote(db: Session, empresa_id: uuid.UUID, licencia_ids, usuario: str):
        # La confirmación contiene solo las asignaciones revisadas, no nuevas altas.
        cantidad = (
            db.query(Licencia)
            .filter(
                Licencia.id.in_(licencia_ids),
                Licencia.empresa_id == empresa_id,
                Licencia.deleted_at.is_(None),
            )
            .update({Licencia.deleted_at: utc_now(), Licencia.updated_by: usuario}, synchronize_session=False)
        )
        db.commit()
        return cantidad

    @staticmethod
    def eliminar(db: Session, empresa_id: uuid.UUID, id: str, usuario: str = None) -> bool:
        """Baja logica de una licencia, para sacar las que quedaron sucias."""
        licencia = (
            db.query(Licencia)
            .filter(
                Licencia.id == _uuid_o_none(id),
                Licencia.deleted_at.is_(None),
                Licencia.empresa_id == empresa_id,
            )
            .first()
        )
        if not licencia:
            return False

        licencia.deleted_at = utc_now()
        licencia.updated_by = usuario
        db.commit()
        return True

    @staticmethod
    def cambiar_activa(
        db: Session, empresa_id: uuid.UUID, id: str, activa: bool, usuario: str = None
    ) -> Optional[Licencia]:
        """Activa o desactiva una licencia. No hay circuito de aprobacion."""
        licencia = (
            db.query(Licencia)
            .filter(Licencia.id == _uuid_o_none(id), Licencia.deleted_at.is_(None), Licencia.empresa_id == empresa_id)
            .first()
        )

        if not licencia:
            return None

        licencia.activa = activa
        licencia.updated_at = utc_now()
        if usuario:
            licencia.updated_by = usuario

        db.commit()
        db.refresh(licencia)
        return licencia
