"""
Servicios de negocio para Soporte Técnico (v28.0).
Restauración completa de lógica de negocio normalizada.
"""

import logging
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import UploadFile
from sqlalchemy import case, desc, func, insert, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from backend.core.storage import cloud_storage
from backend.core.utils import utc_now
from backend.modules.nomina.models import Departamento, Empleado, Perfil
from backend.modules.soporte.constants import (
    PREFIJO_INVENTARIO,
    ActivoEstado,
    HistorialTipoEvento,
    PedidoEstado,
    TicketEstado,
    TipoOperacion,
    TipoTicket,
)
from backend.modules.soporte.models import (
    Activo,
    ActivoConEspecificaciones,
    ActivoSinEspecificaciones,
    ActivoTipo,
    HistorialActivo,
    Insumo,
    MovimientoInsumo,
    PedidoAprobacion,
    PedidoCompra,
    PedidoPresupuesto,
    SoporteActivosMarca,
    SoporteCategoria,
    SoporteEvidencia,
    SoporteMatrizEstado,
    SoporteSistemaDisponible,
    SoporteSubcategoria,
    SoporteTicketInsumo,
    SoporteTicketsEstado,
    Ticket,
    TicketAltaBaja,
    TicketChecklistItem,
    TicketGeneral,
    TicketMantenimiento,
    TicketReparacion,
)

logger = logging.getLogger("soporte")


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


def _paginate(query, page: int, per_page: int):
    total = query.count()
    offset = (page - 1) * per_page
    items = query.offset(offset).limit(per_page).all()
    return items, total


class SoporteService:
    # ─── Configuración y Maestras ──────────────────────────────────

    @staticmethod
    def obtener_estado_ticket(db: Session, clave: str) -> SoporteTicketsEstado:
        return db.query(SoporteTicketsEstado).filter(SoporteTicketsEstado.clave == clave).first()

    @staticmethod
    def obtener_subcategoria(db: Session, sub_id: uuid.UUID, empresa_id: uuid.UUID = None) -> SoporteSubcategoria:
        query = (
            db.query(SoporteSubcategoria)
            .options(joinedload(SoporteSubcategoria.categoria))
            .filter(SoporteSubcategoria.id == sub_id)
        )
        if empresa_id:
            query = query.filter(SoporteSubcategoria.empresa_id == empresa_id)
        return query.first()

    @staticmethod
    def _es_manager_hrbp(db: Session, empresa_id: uuid.UUID, usuario_dni: int) -> bool:
        """
        Verifica si un usuario puede gestionar altas/bajas de colaboradores.
        Criterios (en orden):
        1. Es el manager_id asignado del departamento de Reclutamiento
        2. Pertenece al departamento de Reclutamiento y tiene perfil tipo MANAGER
        """
        if not usuario_dni:
            return False

        empleado = (
            db.query(Empleado)
            .filter(Empleado.dni == usuario_dni, Empleado.empresa_id == empresa_id, Empleado.deleted_at.is_(None))
            .first()
        )
        if not empleado:
            return False

        # Buscar departamento de Reclutamiento
        depto_reclutamiento = (
            db.query(Departamento)
            .filter(
                Departamento.nombre.ilike("%reclutamiento%"),
                Departamento.empresa_id == empresa_id,
                Departamento.deleted_at.is_(None),
            )
            .first()
        )

        if not depto_reclutamiento:
            return False

        # Criterio 1: Es el manager_id asignado del depto
        if depto_reclutamiento.manager_id and depto_reclutamiento.manager_id == empleado.id:
            return True

        # Criterio 2: Pertenece al depto de Reclutamiento y tiene perfil tipo MANAGER
        if empleado.departamento_id == depto_reclutamiento.id and empleado.perfil_id:
            perfil = db.query(Perfil).filter(Perfil.id == empleado.perfil_id, Perfil.empresa_id == empresa_id).first()
            if perfil and perfil.tipo == "MANAGER":
                return True

        return False

    @staticmethod
    def listar_categorias(
        db: Session,
        empresa_id: uuid.UUID,
        usuario_dni: int = None,
        es_admin: bool = False,
        incluir_vacias: bool = False,
    ) -> List[Dict]:
        """
        Obtiene árbol de categorías y subcategorías v28.0.
        Filtra subcategorías tipo 'alta_baja' si el usuario no es manager de HRBP.

        Args:
            incluir_vacias: Si True, devuelve también las categorías sin subcategorías (para admin/gestión).
                            Si False, solo devuelve categorías con al menos una subcategoría visible.
        """
        query = (
            db.query(SoporteCategoria)
            .options(joinedload(SoporteCategoria.subcategorias))
            .filter(SoporteCategoria.deleted_at.is_(None), SoporteCategoria.empresa_id == empresa_id)
            .order_by(SoporteCategoria.nombre_display)
        )
        categorias = query.all()

        # Verificar si el usuario puede ver categorías de alta/baja
        puede_ver_alta_baja = es_admin or SoporteService._es_manager_hrbp(db, empresa_id, usuario_dni)

        resultado = []
        for cat in categorias:
            subcategorias_filtradas = []
            # Subcategorías ordenadas por nombre y sin soft-deleted
            subs_activas = sorted(
                [s for s in cat.subcategorias if s.deleted_at is None], key=lambda s: s.nombre_display or ""
            )
            for sub in subs_activas:
                # Filtrar subcategorías de tipo alta_baja si no tiene permiso
                if sub.tipo_ticket_asociado == TipoTicket.ALTA_BAJA and not puede_ver_alta_baja:
                    continue

                subcategorias_filtradas.append(
                    {
                        "id": str(sub.id),
                        "nombre": sub.nombre_display,
                        "nombre_normalizado": sub.nombre_normalizado,
                        "tipo_ticket_asociado": sub.tipo_ticket_asociado,
                    }
                )

            # En modo gestión (incluir_vacias=True) devolvemos todas las categorías,
            # incluso las que aún no tienen subcategorías, para poder administrarlas.
            if subcategorias_filtradas or incluir_vacias:
                resultado.append(
                    {
                        "id": str(cat.id),
                        "nombre": cat.nombre_display,
                        "nombre_normalizado": cat.nombre_normalizado,
                        "tipo_ticket_asociado": cat.tipo_ticket_asociado,
                        "subcategorias": subcategorias_filtradas,
                    }
                )

        return resultado

    @staticmethod
    def crear_categoria(db: Session, empresa_id: uuid.UUID, datos: Dict, usuario_email: str):
        """
        Crea una categoría o subcategoría.
        Si datos['parent_id'] viene seteado, crea una SoporteSubcategoria hija de esa categoría.
        Si no, crea una SoporteCategoria de nivel raíz.
        """
        datos = limpiar_datos(datos)
        nombre = datos.get("nombre")
        if not nombre:
            raise ValueError("El nombre de la categoría es obligatorio")
        nombre_norm = nombre.lower().replace(" ", "_")
        tipo_ticket = datos.get("tipo_ticket_asociado") or "generico"
        parent_id = datos.get("parent_id")

        # === SUBCATEGORÍA ===
        if parent_id:
            try:
                parent_uuid = uuid.UUID(str(parent_id))
            except ValueError, TypeError:
                raise ValueError("ID de categoría padre inválido")

            # Validar que la categoría padre existe y pertenece a la empresa
            padre = (
                db.query(SoporteCategoria)
                .filter(
                    SoporteCategoria.id == parent_uuid,
                    SoporteCategoria.empresa_id == empresa_id,
                    SoporteCategoria.deleted_at.is_(None),
                )
                .first()
            )
            if not padre:
                raise ValueError("La categoría padre no existe")

            # Validar unicidad dentro de la categoría padre
            existente = (
                db.query(SoporteSubcategoria)
                .filter(
                    SoporteSubcategoria.empresa_id == empresa_id,
                    SoporteSubcategoria.categoria_id == parent_uuid,
                    SoporteSubcategoria.nombre_normalizado == nombre_norm,
                    SoporteSubcategoria.deleted_at.is_(None),
                )
                .first()
            )
            if existente:
                raise ValueError(f"Ya existe una subcategoría con el nombre '{nombre}' en esa categoría")

            sub = SoporteSubcategoria(
                empresa_id=empresa_id,
                categoria_id=parent_uuid,
                nombre_display=nombre,
                nombre_normalizado=nombre_norm,
                tipo_ticket_asociado=tipo_ticket,
                created_by=usuario_email,
            )
            db.add(sub)
            db.commit()
            db.refresh(sub)
            return sub

        # === CATEGORÍA RAÍZ ===
        existente = (
            db.query(SoporteCategoria)
            .filter(
                SoporteCategoria.empresa_id == empresa_id,
                SoporteCategoria.nombre_normalizado == nombre_norm,
                SoporteCategoria.deleted_at.is_(None),
            )
            .first()
        )
        if existente:
            raise ValueError(f"Ya existe una categoría con el nombre '{nombre}'")

        cat = SoporteCategoria(
            empresa_id=empresa_id,
            nombre_display=nombre,
            nombre_normalizado=nombre_norm,
            tipo_ticket_asociado=tipo_ticket,
            created_by=usuario_email,
        )
        db.add(cat)
        db.commit()
        db.refresh(cat)
        return cat

    @staticmethod
    def actualizar_categoria(db: Session, empresa_id: uuid.UUID, cat_id: str, datos: Dict, usuario_email: str):
        """Actualiza una categoría raíz o una subcategoría.
        Valida unicidad de nombre:
        - Categoría raíz: único por empresa.
        - Subcategoría: único dentro de la categoría padre.
        """
        datos = limpiar_datos(datos)
        try:
            cat_uuid = uuid.UUID(cat_id)
        except ValueError, TypeError:
            raise ValueError("ID de categoría inválido")

        # Intentar buscar primero como categoría raíz
        cat = (
            db.query(SoporteCategoria)
            .filter(
                SoporteCategoria.id == cat_uuid,
                SoporteCategoria.empresa_id == empresa_id,
                SoporteCategoria.deleted_at.is_(None),
            )
            .first()
        )

        # Si no es categoría raíz, buscar como subcategoría
        if not cat:
            subcat = (
                db.query(SoporteSubcategoria)
                .filter(
                    SoporteSubcategoria.id == cat_uuid,
                    SoporteSubcategoria.empresa_id == empresa_id,
                    SoporteSubcategoria.deleted_at.is_(None),
                )
                .first()
            )
            if not subcat:
                raise ValueError("Categoría o subcategoría no encontrada")

            # Validar unicidad del nuevo nombre dentro de la categoría padre
            if "nombre" in datos and datos["nombre"]:
                nuevo_norm = datos["nombre"].lower().replace(" ", "_")
                if nuevo_norm != subcat.nombre_normalizado:
                    existente = (
                        db.query(SoporteSubcategoria)
                        .filter(
                            SoporteSubcategoria.empresa_id == empresa_id,
                            SoporteSubcategoria.categoria_id == subcat.categoria_id,
                            SoporteSubcategoria.nombre_normalizado == nuevo_norm,
                            SoporteSubcategoria.deleted_at.is_(None),
                            SoporteSubcategoria.id != subcat.id,
                        )
                        .first()
                    )
                    if existente:
                        raise ValueError(
                            f"Ya existe una subcategoría con el nombre '{datos['nombre']}' en esa categoría"
                        )
                subcat.nombre_display = datos["nombre"]
                subcat.nombre_normalizado = nuevo_norm
            if "tipo_ticket_asociado" in datos and datos["tipo_ticket_asociado"]:
                subcat.tipo_ticket_asociado = datos["tipo_ticket_asociado"]

            subcat.updated_by = usuario_email
            db.commit()
            db.refresh(subcat)
            return subcat

        # Actualizar categoría raíz
        if "nombre" in datos and datos["nombre"]:
            nuevo_norm = datos["nombre"].lower().replace(" ", "_")
            if nuevo_norm != cat.nombre_normalizado:
                existente = (
                    db.query(SoporteCategoria)
                    .filter(
                        SoporteCategoria.empresa_id == empresa_id,
                        SoporteCategoria.nombre_normalizado == nuevo_norm,
                        SoporteCategoria.deleted_at.is_(None),
                        SoporteCategoria.id != cat.id,
                    )
                    .first()
                )
                if existente:
                    raise ValueError(f"Ya existe una categoría con el nombre '{datos['nombre']}'")
            cat.nombre_display = datos["nombre"]
            cat.nombre_normalizado = nuevo_norm
        if "tipo_ticket_asociado" in datos and datos["tipo_ticket_asociado"]:
            cat.tipo_ticket_asociado = datos["tipo_ticket_asociado"]

        cat.updated_by = usuario_email
        db.commit()
        db.refresh(cat)
        return cat

    @staticmethod
    def eliminar_categoria(db: Session, empresa_id: uuid.UUID, cat_id: str) -> bool:
        """
        Soft delete de una categoría o subcategoría por ID.
        - Si el ID corresponde a una categoría raíz, elimina también todas sus subcategorías.
        - Si el ID corresponde a una subcategoría, elimina solo esa.
        """
        try:
            cat_uuid = uuid.UUID(cat_id)
        except ValueError, TypeError:
            raise ValueError("ID de categoría inválido")

        ahora = utc_now()

        # Intentar primero como categoría raíz
        cat = (
            db.query(SoporteCategoria)
            .filter(
                SoporteCategoria.id == cat_uuid,
                SoporteCategoria.empresa_id == empresa_id,
                SoporteCategoria.deleted_at.is_(None),
            )
            .first()
        )
        if cat:
            # Soft delete de subcategorías asociadas
            db.query(SoporteSubcategoria).filter(
                SoporteSubcategoria.categoria_id == cat.id, SoporteSubcategoria.deleted_at.is_(None)
            ).update({"deleted_at": ahora})

            cat.deleted_at = ahora
            db.commit()
            return True

        # Si no era categoría, probar como subcategoría
        sub = (
            db.query(SoporteSubcategoria)
            .filter(
                SoporteSubcategoria.id == cat_uuid,
                SoporteSubcategoria.empresa_id == empresa_id,
                SoporteSubcategoria.deleted_at.is_(None),
            )
            .first()
        )
        if sub:
            sub.deleted_at = ahora
            db.commit()
            return True

        return False

    # ─── Tickets ───────────────────────────────────────────────────

    @staticmethod
    def _siguiente_numero(db: Session, empresa_id: uuid.UUID) -> int:
        max_num = db.query(func.max(Ticket.numero)).filter(Ticket.empresa_id == empresa_id).scalar()
        return (max_num or 0) + 1

    @staticmethod
    def crear_ticket(db: Session, empresa_id: uuid.UUID, datos: Dict[str, Any], usuario_email: str) -> Ticket:
        """Crea un ticket especializado (Reparación, Alta/Baja, Mant.) v28.0."""
        datos = limpiar_datos(datos)
        numero = SoporteService._siguiente_numero(db, empresa_id)

        # 1. Resolución de Subcategoría
        sub_id = datos.get("subcategoria_id")
        if not sub_id:
            raise ValueError("subcategoria_id es obligatorio")

        sub = SoporteService.obtener_subcategoria(db, uuid.UUID(str(sub_id)), empresa_id)
        if not sub:
            raise ValueError("Subcategoría inexistente")

        # El tipo de ticket lo determina la subcategoría
        tipo_ticket = sub.tipo_ticket_asociado or "generico"

        # 2. Estado Inicial (Maestro)
        estado_inicial = SoporteService.obtener_estado_ticket(db, TicketEstado.ABIERTO)
        if not estado_inicial:
            raise ValueError("Estado 'abierto' no configurado")

        # 3. Datos Base
        datos_base = {
            "empresa_id": empresa_id,
            "numero": numero,
            "titulo": datos["titulo"],
            "descripcion": datos.get("descripcion"),
            "prioridad": datos.get("prioridad", "media"),
            "subcategoria_id": sub.id,
            "estado_id": estado_inicial.id,
            "solicitante_id": uuid.UUID(str(datos["solicitante_id"])),
            "created_by": usuario_email,
            "updated_by": usuario_email,
        }

        if datos.get("asignado_id"):
            datos_base["asignado_id"] = uuid.UUID(str(datos["asignado_id"]))

        # 4. Construcción Polimórfica según tipo_ticket_asociado de la subcategoría
        if tipo_ticket == TipoTicket.REPARACION:
            if not datos.get("activo_id"):
                raise ValueError("Para tickets de reparación debe seleccionar el equipo afectado")
            ticket = TicketReparacion(**datos_base, activo_id=uuid.UUID(str(datos["activo_id"])))
        elif tipo_ticket == TipoTicket.ALTA_BAJA:
            if not datos.get("colaborador_id"):
                raise ValueError("colaborador_id requerido para alta/baja")
            tipo_op = datos.get("tipo_operacion")
            if not tipo_op:
                nombre_sub = sub.nombre_display.lower() if sub.nombre_display else ""
                if "baja" in nombre_sub or "devoluc" in nombre_sub:
                    tipo_op = "baja"
                else:
                    tipo_op = "alta"
            ticket = TicketAltaBaja(
                **datos_base,
                colaborador_id=uuid.UUID(str(datos["colaborador_id"])),
                tipo_operacion=tipo_op,
                modalidad_trabajo=datos.get("modalidad_trabajo"),
                requiere_nextcloud=bool(datos.get("requiere_nextcloud", False)),
                listas_correo=datos.get("listas_correo"),
                necesita_computadora=bool(datos.get("necesita_computadora", False)),
                gama_computadora=datos.get("gama_computadora"),
                cliente_servicio=datos.get("cliente_servicio"),
            )
        elif tipo_ticket == TipoTicket.MANTENIMIENTO:
            if not datos.get("activo_id"):
                raise ValueError("activo_id requerido para mantenimiento")
            ticket = TicketMantenimiento(
                **datos_base,
                activo_id=uuid.UUID(str(datos["activo_id"])),
                fecha_programada=datos.get("fecha_programada"),
                is_preventivo=datos.get("is_preventivo", True),
            )
        else:
            # Ticket genérico: si viene con activo_id, marcarlo como falla para habilitar conversión a reparación
            ticket = TicketGeneral(**datos_base)
            if datos.get("activo_id"):
                ticket.es_falla = True

        db.add(ticket)
        db.commit()
        db.refresh(ticket)

        # Crear checklist automático para tickets de alta/baja
        if tipo_ticket == TipoTicket.ALTA_BAJA:
            tipo_op_final = getattr(ticket, "tipo_operacion", TipoOperacion.ALTA)
            if tipo_op_final == TipoOperacion.ALTA:
                sistemas = datos.get("sistemas_habilitados")
                # None = no vino el campo (usar todos por defecto)
                # [] = lista vacía explícita (no crear ninguno)
                SoporteService._crear_checklist_ticket(
                    db, empresa_id, ticket.id, TipoOperacion.ALTA, usuario_email, sistemas
                )
            else:
                colab_id = uuid.UUID(str(datos["colaborador_id"]))
                items_baja = SoporteService._derivar_checklist_baja(db, empresa_id, colab_id)
                SoporteService._crear_checklist_ticket(
                    db, empresa_id, ticket.id, TipoOperacion.BAJA, usuario_email, items_baja
                )
            db.commit()

        # Recargar el ticket con todas las relaciones para la respuesta
        ticket = (
            db.query(Ticket)
            .options(
                joinedload(Ticket.subcategoria),
                joinedload(Ticket.estado_rel),
                joinedload(Ticket.solicitante),
                joinedload(Ticket.asignado),
            )
            .filter(Ticket.id == ticket.id)
            .first()
        )

        # Si es TicketReparacion o TicketMantenimiento, cargar también el activo
        if isinstance(ticket, (TicketReparacion, TicketMantenimiento)):
            db.refresh(ticket)

        logger.info(f"Ticket #{ticket.numero} creado por {usuario_email} [Tipo: {tipo_ticket}]")
        return ticket

    @staticmethod
    def listar_mis_tickets(db: Session, empresa_id: uuid.UUID, usuario_dni: int) -> Tuple[List[Ticket], int]:
        """Lista tickets donde el empleado vinculado al usuario (por DNI) es el solicitante."""
        from backend.modules.nomina.services import EmpleadoService

        if not usuario_dni:
            return [], 0
        emp = EmpleadoService.obtener_por_dni(db, empresa_id, usuario_dni)
        if not emp:
            return [], 0
        items = (
            db.query(Ticket)
            .options(
                joinedload(Ticket.solicitante),
                joinedload(Ticket.asignado),
                joinedload(Ticket.subcategoria),
                joinedload(Ticket.estado_rel),
            )
            .filter(Ticket.solicitante_id == emp.id, Ticket.empresa_id == empresa_id, Ticket.deleted_at.is_(None))
            .order_by(Ticket.created_at.desc())
            .all()
        )
        return items, len(items)

    @staticmethod
    def listar_tickets(
        db: Session,
        empresa_id: uuid.UUID,
        estado_id: str = None,
        estado_clave: str = None,
        prioridad: str = None,
        sub_id: str = None,
        buscar: str = None,
        solicitante_id: str = None,
        page: int = 1,
        per_page: int = 50,
    ) -> Tuple[List[Ticket], int]:
        """Lista tickets relacionales con filtrado potente (soporta tanto ID como Clave)."""
        query = (
            db.query(Ticket)
            .options(
                joinedload(Ticket.solicitante),
                joinedload(Ticket.asignado),
                joinedload(Ticket.subcategoria),
                joinedload(Ticket.estado_rel),
            )
            .filter(Ticket.deleted_at.is_(None), Ticket.empresa_id == empresa_id)
        )
        if estado_id:
            query = query.filter(Ticket.estado_id == uuid.UUID(estado_id))
        if estado_clave:
            query = query.join(Ticket.estado_rel).filter(SoporteTicketsEstado.clave == estado_clave)
        if prioridad:
            query = query.filter(Ticket.prioridad == prioridad)
        if sub_id:
            # Verificar si es una categoría padre o una subcategoría
            # Primero intentar como subcategoría
            subcat = (
                db.query(SoporteSubcategoria)
                .filter(SoporteSubcategoria.id == uuid.UUID(sub_id), SoporteSubcategoria.empresa_id == empresa_id)
                .first()
            )
            if subcat:
                # Es una subcategoría, filtrar directamente
                query = query.filter(Ticket.subcategoria_id == uuid.UUID(sub_id))
            else:
                # Puede ser una categoría padre, buscar todas sus subcategorías
                cat = (
                    db.query(SoporteCategoria)
                    .filter(SoporteCategoria.id == uuid.UUID(sub_id), SoporteCategoria.empresa_id == empresa_id)
                    .first()
                )
                if cat:
                    # Obtener IDs de todas las subcategorías de esta categoría
                    subcat_ids = [sub.id for sub in cat.subcategorias]
                    if subcat_ids:
                        query = query.filter(Ticket.subcategoria_id.in_(subcat_ids))
                    else:
                        # Categoría sin subcategorías, no hay tickets
                        query = query.filter(Ticket.id == None)  # Forzar resultado vacío
        if solicitante_id:
            query = query.filter(Ticket.solicitante_id == uuid.UUID(solicitante_id))
        if buscar:
            query = query.filter(or_(Ticket.titulo.ilike(f"%{buscar}%"), Ticket.descripcion.ilike(f"%{buscar}%")))

        return _paginate(query.order_by(Ticket.created_at.desc()), page, per_page)

    @staticmethod
    def kanban(db: Session, empresa_id: uuid.UUID, categoria_id: str = None, buscar: str = None) -> Dict:
        """Tablero Kanban puro v28.0 mapeado por estados.
        Optimizado: 2 queries (estados + tickets) en vez de N+1."""
        # 1. Cargar todos los estados ordenados (1 query)
        estados = (
            db.query(SoporteTicketsEstado)
            .order_by(
                case(
                    (SoporteTicketsEstado.clave == TicketEstado.ABIERTO, 1),
                    (SoporteTicketsEstado.clave == TicketEstado.EN_PROGRESO, 2),
                    (SoporteTicketsEstado.clave == TicketEstado.RESUELTO, 3),
                    (SoporteTicketsEstado.clave == TicketEstado.CERRADO, 4),
                    (SoporteTicketsEstado.clave == TicketEstado.CANCELADO, 5),
                    else_=99,
                ),
                SoporteTicketsEstado.nombre.asc(),
            )
            .all()
        )

        # 2. Cargar TODOS los tickets filtrados en un solo query
        query = (
            db.query(Ticket)
            .options(
                joinedload(Ticket.solicitante),
                joinedload(Ticket.subcategoria),
                joinedload(Ticket.estado_rel),
                joinedload(Ticket.asignado),
            )
            .filter(Ticket.deleted_at.is_(None), Ticket.empresa_id == empresa_id)
        )
        if categoria_id:
            cat_uuid = uuid.UUID(categoria_id)
            # Verificar si es una subcategoría o una categoría padre
            es_subcat = (
                db.query(SoporteSubcategoria)
                .filter(SoporteSubcategoria.id == cat_uuid, SoporteSubcategoria.empresa_id == empresa_id)
                .first()
            )
            if es_subcat:
                # Filtrar por subcategoría directa
                query = query.filter(Ticket.subcategoria_id == cat_uuid)
            else:
                # Filtrar por categoría padre (todos los tickets de sus subcategorías)
                query = query.join(SoporteSubcategoria, Ticket.subcategoria_id == SoporteSubcategoria.id).filter(
                    SoporteSubcategoria.categoria_id == cat_uuid
                )
        if buscar:
            query = query.filter(Ticket.titulo.ilike(f"%{buscar}%"))

        todos_tickets = query.all()

        # 3. Agrupar tickets por estado_id en Python (O(n))
        tickets_por_estado = {}
        total_criticos = 0
        for t in todos_tickets:
            tickets_por_estado.setdefault(t.estado_id, []).append(t)
            # Contar críticos activos de paso
            if (
                t.prioridad == "critica"
                and t.estado_rel
                and t.estado_rel.clave in (TicketEstado.ABIERTO, TicketEstado.EN_PROGRESO)
            ):
                total_criticos += 1

        # 4. Armar tablero y stats
        tablero = []
        stats = {}
        for est in estados:
            tickets_est = tickets_por_estado.get(est.id, [])
            stats[est.clave] = len(tickets_est)
            tablero.append(
                {
                    "id": str(est.id),
                    "clave": est.clave,
                    "nombre": est.nombre,
                    "color": est.color,
                    "tickets": tickets_est,
                }
            )

        stats["total"] = len(todos_tickets)
        stats["criticos"] = total_criticos

        return {"kanban": {"columnas": tablero}, "stats": stats}

    @staticmethod
    def obtener_activo(db: Session, empresa_id: uuid.UUID, activo_id: str) -> Optional[Activo]:
        """Obtiene un activo por ID con relaciones precargadas v28.0."""
        try:
            activo_uuid = uuid.UUID(activo_id)
        except Exception:
            return None

        return (
            db.query(Activo)
            .options(
                joinedload(Activo.tipo_rel),
                joinedload(Activo.marca_rel),
                joinedload(Activo.asignado_rel),
                joinedload(Activo.matriz_estado),
            )
            .filter(Activo.id == activo_uuid, Activo.empresa_id == empresa_id, Activo.deleted_at.is_(None))
            .first()
        )

    @staticmethod
    def listar_activos(
        db: Session,
        empresa_id: uuid.UUID,
        tipo_id: str = None,
        estado: str = None,
        buscar: str = None,
        asignado_id: str = None,
    ) -> List[Activo]:
        """Listado de activos puro v28.0 con soporte para asignación."""
        query = (
            db.query(Activo)
            .options(joinedload(Activo.tipo_rel), joinedload(Activo.marca_rel), joinedload(Activo.asignado_rel))
            .filter(Activo.deleted_at.is_(None), Activo.empresa_id == empresa_id)
        )
        if tipo_id:
            query = query.filter(Activo.tipo_id == uuid.UUID(tipo_id))
        if estado:
            query = query.filter(Activo.estado == estado)
        if asignado_id:
            query = query.filter(Activo.asignado_id == uuid.UUID(asignado_id))
        if buscar:
            query = query.filter(or_(Activo.nombre.ilike(f"%{buscar}%"), Activo.numero_serie.ilike(f"%{buscar}%")))
        return query.all()

    # ─── Activos IT y Stock ────────────────────────────────────────

    @staticmethod
    def crear_activo(db: Session, empresa_id: uuid.UUID, datos: Dict[str, Any], usuario_email: str) -> Activo:
        """Crea un equipo en stock normalizado v28.0."""
        datos = limpiar_datos(datos)

        # Validar tipo_id existe
        if not datos.get("tipo_id"):
            raise ValueError("tipo_id es obligatorio")
        tipo = (
            db.query(ActivoTipo)
            .filter(
                ActivoTipo.id == uuid.UUID(str(datos["tipo_id"])),
                ActivoTipo.empresa_id == empresa_id,
                ActivoTipo.deleted_at.is_(None),
            )
            .first()
        )
        if not tipo:
            raise ValueError("El tipo de activo no existe")

        # Validar y sanitizar numero_inventario (OBLIGATORIO)
        if not datos.get("numero_inventario"):
            raise ValueError("El número de inventario es obligatorio")

        try:
            numero_sanitizado = SoporteService._validar_formato_numero_inventario(datos["numero_inventario"])
            datos["numero_inventario"] = numero_sanitizado
        except ValueError as e:
            raise ValueError(str(e))

        # Validar unicidad de numero_inventario pre-commit
        existente = (
            db.query(Activo)
            .filter(
                Activo.empresa_id == empresa_id,
                Activo.numero_inventario == datos["numero_inventario"],
                Activo.deleted_at.is_(None),
            )
            .first()
        )
        if existente:
            raise ValueError(f"Ya existe un activo con el número de inventario '{datos['numero_inventario']}'")

        # Validar marca_id si viene
        marca_id = datos.get("marca_id")
        if marca_id:
            marca = (
                db.query(SoporteActivosMarca)
                .filter(
                    SoporteActivosMarca.id == uuid.UUID(str(marca_id)), SoporteActivosMarca.empresa_id == empresa_id
                )
                .first()
            )
            if not marca:
                raise ValueError("La marca no existe")
        elif datos.get("marca"):
            marca_id = SoporteService.obtener_o_crear_marca(db, datos["marca"], usuario_email, empresa_id)

        # Validar unicidad de numero_serie pre-commit
        if datos.get("numero_serie"):
            existente = (
                db.query(Activo)
                .filter(
                    Activo.empresa_id == empresa_id,
                    Activo.numero_serie == datos["numero_serie"],
                    Activo.deleted_at.is_(None),
                )
                .first()
            )
            if existente:
                raise ValueError(f"Ya existe un activo con el número de serie '{datos['numero_serie']}'")

        clase = "con_especificaciones" if tipo.requiere_especificaciones else "sin_especificaciones"

        datos_base = {
            "empresa_id": empresa_id,
            "nombre": datos["nombre"],
            "tipo_id": tipo.id,
            "marca_id": uuid.UUID(str(marca_id)) if marca_id else None,
            "modelo": datos.get("modelo"),
            "numero_serie": datos.get("numero_serie"),
            "numero_inventario": datos["numero_inventario"],  # Usar el ingresado manualmente
            "created_by": usuario_email,
            "updated_by": usuario_email,
        }

        if datos_base.get("asignado_id"):
            datos_base["estado"] = ActivoEstado.ASIGNADO

        if clase == "con_especificaciones":
            activo = ActivoConEspecificaciones(
                **datos_base,
                procesador=datos.get("procesador"),
                memoria=datos.get("memoria"),
                disco_principal=datos.get("disco_principal"),
                disco_secundario=datos.get("disco_secundario"),
                mac_ethernet=datos.get("mac_ethernet"),
                mac_wifi=datos.get("mac_wifi"),
            )
        else:
            activo = ActivoSinEspecificaciones(**datos_base)

        db.add(activo)

        try:
            db.commit()
            db.refresh(activo)
        except IntegrityError as e:
            db.rollback()
            error_str = str(e).lower()
            if "numero_serie" in error_str or "uq_activo_empresa_serie" in error_str:
                raise ValueError(f"Ya existe un activo con el número de serie '{datos.get('numero_serie')}'")
            elif "numero_inventario" in error_str or "uq_activo_empresa_inventario" in error_str:
                raise ValueError(f"Ya existe un activo con el número de inventario '{activo.numero_inventario}'")
            else:
                raise ValueError("Error al guardar: verifique que los datos no estén duplicados")

        logger.info(f"Activo [{activo.numero_inventario}] creado por {usuario_email}")
        return activo

    @staticmethod
    def _validar_formato_numero_inventario(numero: str) -> str:
        """
        Valida y sanitiza el formato del número de inventario.
        Formato esperado: {PREFIJO}-{NUMERO} (ej: NOT-001, MON-012)

        Returns:
            str: Número sanitizado en formato correcto
        Raises:
            ValueError: Si el formato es inválido
        """
        import re

        # Sanitizar: trim, uppercase, remover espacios
        numero = numero.strip().upper().replace(" ", "")

        # Validar formato: LETRAS-NUMEROS
        if not re.match(r"^[A-Z]{2,4}-\d{1,5}$", numero):
            raise ValueError(
                f"Formato de número de inventario inválido: '{numero}'. "
                "Debe ser PREFIJO-NUMERO (ej: NOT-001, MON-012, PCE-100)"
            )

        # Extraer prefijo y número
        partes = numero.split("-")
        prefijo = partes[0]
        num = partes[1]

        # Validar que el prefijo sea conocido (opcional, pero recomendado)
        prefijos_validos = list(PREFIJO_INVENTARIO.values())
        if prefijo not in prefijos_validos:
            logger.warning(f"Prefijo '{prefijo}' no está en la lista de prefijos conocidos")

        # Normalizar número con padding de 3 dígitos si es menor a 1000
        if len(num) < 3 and int(num) < 1000:
            num = f"{int(num):03d}"

        return f"{prefijo}-{num}"

    @staticmethod
    def actualizar_activo(
        db: Session, empresa_id: uuid.UUID, activo_id: str, datos: Dict[str, Any], usuario_email: str
    ) -> Optional[Activo]:
        activo = (
            db.query(Activo)
            .filter(Activo.id == uuid.UUID(activo_id), Activo.empresa_id == empresa_id, Activo.deleted_at.is_(None))
            .first()
        )
        if not activo:
            return None

        datos = limpiar_datos(datos)

        # 1. Validar y sanitizar formato de numero_inventario si se está editando manualmente
        if "numero_inventario" in datos and datos["numero_inventario"]:
            try:
                numero_sanitizado = SoporteService._validar_formato_numero_inventario(datos["numero_inventario"])
                datos["numero_inventario"] = numero_sanitizado
            except ValueError as e:
                raise ValueError(str(e))

            # Validar unicidad después de sanitizar
            if numero_sanitizado != activo.numero_inventario:
                existente = (
                    db.query(Activo)
                    .filter(
                        Activo.empresa_id == empresa_id,
                        Activo.numero_inventario == numero_sanitizado,
                        Activo.id != uuid.UUID(activo_id),
                        Activo.deleted_at.is_(None),
                    )
                    .first()
                )
                if existente:
                    raise ValueError(f"Ya existe un activo con el número de inventario '{numero_sanitizado}'")

        # 2. Validar unicidad de numero_serie si se está editando
        if "numero_serie" in datos and datos["numero_serie"]:
            numero_serie_nuevo = datos["numero_serie"].strip()
            if numero_serie_nuevo != activo.numero_serie:
                existente = (
                    db.query(Activo)
                    .filter(
                        Activo.empresa_id == empresa_id,
                        Activo.numero_serie == numero_serie_nuevo,
                        Activo.id != uuid.UUID(activo_id),
                        Activo.deleted_at.is_(None),
                    )
                    .first()
                )
                if existente:
                    raise ValueError(f"Ya existe un activo con el número de serie '{numero_serie_nuevo}'")

        # 3. Normalizar Relaciones
        if "tipo_id" in datos and datos["tipo_id"]:
            datos["tipo_id"] = uuid.UUID(str(datos["tipo_id"]))

        if "marca" in datos and datos["marca"]:
            datos["marca_id"] = SoporteService.obtener_o_crear_marca(db, datos["marca"], usuario_email, empresa_id)

        if "marca_id" in datos and datos["marca_id"]:
            datos["marca_id"] = uuid.UUID(str(datos["marca_id"]))

        if "asignado_id" in datos and datos["asignado_id"]:
            datos["asignado_id"] = uuid.UUID(str(datos["asignado_id"]))

        # Integridad de Estado v28.0: Sincronizar estado con asignación
        if datos.get("asignado_id"):
            datos["estado"] = ActivoEstado.ASIGNADO
        elif "estado" in datos and datos["estado"] == ActivoEstado.ASIGNADO and not datos.get("asignado_id"):
            datos["estado"] = ActivoEstado.DISPONIBLE

        # 4. Aplicar cambios
        for campo, valor in datos.items():
            if hasattr(activo, campo) and campo not in ("id", "empresa_id", "clase_activo"):
                setattr(activo, campo, valor)

        activo.updated_at = utc_now()
        activo.updated_by = usuario_email

        try:
            db.commit()
            db.refresh(activo)
        except IntegrityError as e:
            db.rollback()
            error_str = str(e).lower()
            if "numero_serie" in error_str or "uq_activo_empresa_serie" in error_str:
                raise ValueError(f"Ya existe un activo con el número de serie '{datos.get('numero_serie')}'")
            elif "numero_inventario" in error_str or "uq_activo_empresa_inventario" in error_str:
                raise ValueError(f"Ya existe un activo con el número de inventario '{activo.numero_inventario}'")
            else:
                raise ValueError("Error al guardar: verifique que los datos no estén duplicados")

        return activo

    @staticmethod
    def eliminar_activo(db: Session, empresa_id: uuid.UUID, activo_id: str) -> bool:
        """Soft delete de un activo de stock."""
        activo = (
            db.query(Activo)
            .filter(Activo.id == uuid.UUID(activo_id), Activo.empresa_id == empresa_id, Activo.deleted_at.is_(None))
            .first()
        )

        if not activo:
            return False

        activo.deleted_at = utc_now()
        db.commit()

        return True

    # ─── Auditoría e Historial Técnicos ─────────────────────────────

    @staticmethod
    def registrar_evento_tecnico(
        db: Session, empresa_id: uuid.UUID, datos: Dict[str, Any], usuario_dni: int, usuario_email: str
    ) -> HistorialActivo:
        """Registra un evento técnico desde el endpoint, resolviendo el responsable por DNI."""
        from backend.modules.nomina.services import EmpleadoService

        if not usuario_dni:
            raise ValueError("El usuario no tiene DNI asociado")
        emp = EmpleadoService.obtener_por_dni(db, empresa_id, usuario_dni)
        if not emp:
            raise ValueError("No se encontró el empleado asociado al usuario")
        datos["responsable_id"] = str(emp.id)
        return SoporteService.crear_historial(db, empresa_id, datos, usuario_email)

    @staticmethod
    def crear_historial(
        db: Session, empresa_id: uuid.UUID, datos: Dict[str, Any], usuario_email: str
    ) -> HistorialActivo:
        """Registra un evento técnico complejo con trazabilidad física (Matriz Estado)."""
        # 1. Auditoría Física (Matriz)
        matriz_raw = datos.get("matriz_estado", {})
        matriz = SoporteMatrizEstado(
            empresa_id=empresa_id,
            pantalla=matriz_raw.get("pantalla"),
            teclado=matriz_raw.get("teclado"),
            bateria=matriz_raw.get("bateria"),
            carcasa_superior=matriz_raw.get("carcasa_superior"),
            carcasa_inferior=matriz_raw.get("carcasa_inferior"),
            touchpad=matriz_raw.get("touchpad"),
            puertos=matriz_raw.get("puertos"),
            cargador=matriz_raw.get("cargador"),
            created_by=usuario_email,
        )
        db.add(matriz)
        db.flush()

        # 2. Obtener equipo_id (activo_id) con compatibilidad
        activo_id_raw = datos.get("activo_id") or datos.get("equipo_id")
        if not activo_id_raw:
            raise ValueError("activo_id o equipo_id es requerido")

        activo_id = uuid.UUID(str(activo_id_raw))
        activo = db.query(Activo).filter(Activo.id == activo_id, Activo.empresa_id == empresa_id).first()
        if activo:
            activo.matriz_estado_id = matriz.id
            db.add(activo)

        # 3. Guardar Evento de Historial
        hist = HistorialActivo(
            empresa_id=empresa_id,
            activo_id=activo_id,
            colaborador_id=uuid.UUID(str(datos.get("colaborador_id"))) if datos.get("colaborador_id") else None,
            responsable_id=uuid.UUID(str(datos["responsable_id"])),
            tipo_evento=datos["tipo_evento"],
            notas_adicionales=datos.get("notas_adicionales"),
            matriz_estado_id=matriz.id,
            pedido_compra_id=uuid.UUID(str(datos.get("pedido_compra_id"))) if datos.get("pedido_compra_id") else None,
            created_by=usuario_email,
        )
        db.add(hist)
        db.commit()
        db.refresh(hist)
        return hist

    # ─── Gestión de Insumos (Ledger Stock) ──────────────────────────

    @staticmethod
    def registrar_movimiento_insumo(
        db: Session, empresa_id: uuid.UUID, datos: Dict[str, Any], usuario_email: str
    ) -> MovimientoInsumo:
        # Validar insumo_id existe
        try:
            iid = uuid.UUID(str(datos["insumo_id"]))
        except ValueError, KeyError:
            raise ValueError("insumo_id inválido o faltante")

        insumo = (
            db.query(Insumo)
            .filter(Insumo.id == iid, Insumo.empresa_id == empresa_id, Insumo.deleted_at.is_(None))
            .first()
        )
        if not insumo:
            raise ValueError("El insumo no existe")

        mov = MovimientoInsumo(
            empresa_id=empresa_id,
            insumo_id=iid,
            tipo=datos["tipo"],
            cantidad=datos["cantidad"],
            activo_id=uuid.UUID(str(datos["activo_id"])) if datos.get("activo_id") else None,
            empleado_id=uuid.UUID(str(datos["empleado_id"])) if datos.get("empleado_id") else None,
            empleado_asignador_id=uuid.UUID(str(datos["empleado_asignador_id"]))
            if datos.get("empleado_asignador_id")
            else None,
            motivo=datos.get("motivo"),
            created_by=usuario_email,
        )
        db.add(mov)
        db.commit()
        db.refresh(mov)
        return mov

    @staticmethod
    def listar_movimientos(
        db: Session, empresa_id: uuid.UUID, insumo_id: Optional[str] = None, activo_id: Optional[str] = None
    ) -> List[MovimientoInsumo]:
        query = db.query(MovimientoInsumo).options(joinedload(MovimientoInsumo.insumo))
        query = query.filter(MovimientoInsumo.empresa_id == empresa_id)
        if insumo_id:
            query = query.filter(MovimientoInsumo.insumo_id == uuid.UUID(insumo_id))
        if activo_id:
            query = query.filter(MovimientoInsumo.activo_id == uuid.UUID(activo_id))
        return query.order_by(MovimientoInsumo.created_at.desc()).all()

    @staticmethod
    def obtener_o_crear_marca(
        db: Session, nombre: str, usuario_email: str, empresa_id: uuid.UUID
    ) -> Optional[uuid.UUID]:
        """Resuelve una marca por nombre o la crea si no existe para cumplir con DBML relacional."""
        nombre = nombre.strip()
        if not nombre:
            return None

        query = db.query(SoporteActivosMarca).filter(
            SoporteActivosMarca.nombre.ilike(nombre), SoporteActivosMarca.empresa_id == empresa_id
        )
        marca = query.first()
        if not marca:
            marca = SoporteActivosMarca(
                nombre=nombre, empresa_id=empresa_id, created_by=usuario_email, updated_by=usuario_email
            )
            db.add(marca)
            db.commit()
            db.refresh(marca)

        return marca.id

    @staticmethod
    def obtener_historial_activo(db: Session, empresa_id: uuid.UUID, activo_id: str) -> List[Dict[str, Any]]:
        try:
            activo_uuid = uuid.UUID(activo_id)
        except ValueError:
            raise ValueError("ID de activo inválido")
        historiales = (
            db.query(HistorialActivo)
            .options(
                joinedload(HistorialActivo.activo),
                joinedload(HistorialActivo.colaborador),
                joinedload(HistorialActivo.responsable),
                joinedload(HistorialActivo.matriz_estado),
                joinedload(HistorialActivo.pedido_compra),
                joinedload(HistorialActivo.evidencias),
            )
            .filter(HistorialActivo.activo_id == activo_uuid, HistorialActivo.empresa_id == empresa_id)
            .order_by(HistorialActivo.created_at.desc())
            .all()
        )

        # Serializar manualmente las evidencias para que Pydantic las procese correctamente
        result = []
        for hist in historiales:
            hist_dict = {
                "id": hist.id,
                "activo_id": hist.activo_id,
                "tipo_evento": hist.tipo_evento,
                "fecha_hora": hist.fecha_hora,
                "notas_adicionales": hist.notas_adicionales,
                "colaborador_nombre": hist.colaborador_nombre,
                "responsable_nombre": hist.responsable_nombre,
                "pedido_compra_id": hist.pedido_compra_id,
                "estado_pantalla": hist.estado_pantalla,
                "estado_carcasa": hist.estado_carcasa,
                "estado_bateria": hist.estado_bateria,
                "estado_puertos": hist.estado_puertos,
                "estado_teclado_trackpad": hist.estado_teclado_trackpad,
                "estado_audio_camara": hist.estado_audio_camara,
                "evidencias": [
                    {
                        "id": str(ev.id),
                        "url": cloud_storage.get_url(ev.url),  # Convertir key a URL
                        "tipo": ev.tipo,
                        "categoria": ev.categoria,
                    }
                    for ev in hist.evidencias
                ]
                if hist.evidencias
                else [],
            }
            result.append(hist_dict)

        return result

    @staticmethod
    def _crear_checklist_ticket(
        db: Session,
        empresa_id: uuid.UUID,
        ticket_id: str,
        tipo_operacion: str,
        usuario_email: str,
        sistemas_seleccionados: List[str] = None,
    ):
        """
        Crea los ítems del checklist para un ticket de alta/baja leyendo de la tabla soporte_sistemas_disponibles.
        - Alta: usa sistemas_seleccionados (claves). None = usar todos, [] = no crear ninguno.
        - Baja: sistemas_seleccionados son claves de baja ya derivadas.
        """
        if tipo_operacion == TipoOperacion.ALTA:
            if sistemas_seleccionados is None:
                # No se especificaron: usar todos los sistemas de alta activos
                registros = (
                    db.query(SoporteSistemaDisponible)
                    .filter(
                        SoporteSistemaDisponible.empresa_id == empresa_id,
                        SoporteSistemaDisponible.tipo == "alta",
                        SoporteSistemaDisponible.activo == True,
                    )
                    .order_by(SoporteSistemaDisponible.orden)
                    .all()
                )
            else:
                # Lista explícita (puede ser vacía): respetar la selección
                if not sistemas_seleccionados:
                    return
                registros = (
                    db.query(SoporteSistemaDisponible)
                    .filter(
                        SoporteSistemaDisponible.empresa_id == empresa_id,
                        SoporteSistemaDisponible.clave.in_(sistemas_seleccionados),
                        SoporteSistemaDisponible.tipo == "alta",
                        SoporteSistemaDisponible.activo == True,
                    )
                    .order_by(SoporteSistemaDisponible.orden)
                    .all()
                )
        else:
            # Baja: sistemas_seleccionados son claves de baja
            if sistemas_seleccionados:
                registros = (
                    db.query(SoporteSistemaDisponible)
                    .filter(
                        SoporteSistemaDisponible.empresa_id == empresa_id,
                        SoporteSistemaDisponible.clave.in_(sistemas_seleccionados),
                        SoporteSistemaDisponible.tipo == "baja",
                        SoporteSistemaDisponible.activo == True,
                    )
                    .order_by(SoporteSistemaDisponible.orden)
                    .all()
                )
            else:
                registros = (
                    db.query(SoporteSistemaDisponible)
                    .filter(
                        SoporteSistemaDisponible.empresa_id == empresa_id,
                        SoporteSistemaDisponible.tipo == "baja",
                        SoporteSistemaDisponible.activo == True,
                    )
                    .order_by(SoporteSistemaDisponible.orden)
                    .all()
                )

        for r in registros:
            db.add(
                TicketChecklistItem(
                    empresa_id=empresa_id,
                    ticket_id=ticket_id,
                    sistema_id=r.id,
                    item_clave=r.clave,
                    item_label=r.label,
                    orden=r.orden,
                    updated_by=usuario_email,
                )
            )

    @staticmethod
    def _derivar_checklist_baja(db: Session, empresa_id: uuid.UUID, colaborador_id: str) -> List[str]:
        """
        Busca el ticket de alta más reciente del colaborador y devuelve
        las claves de baja correspondientes a los sistemas habilitados.
        Si no hay alta previa, devuelve todas las claves de baja.
        """
        ticket_alta = (
            db.query(TicketAltaBaja)
            .join(Ticket, Ticket.id == TicketAltaBaja.id)
            .filter(
                TicketAltaBaja.colaborador_id == colaborador_id, TicketAltaBaja.tipo_operacion == TipoOperacion.ALTA
            )
            .order_by(Ticket.created_at.desc())
            .first()
        )

        if not ticket_alta:
            # Sin alta previa: devolver None para que se usen todos los de baja
            return None

        # Obtener claves de alta del checklist del ticket de alta
        items_alta = db.query(TicketChecklistItem).filter(TicketChecklistItem.ticket_id == ticket_alta.id).all()
        claves_alta = {item.item_clave for item in items_alta}

        # Buscar los sistemas de baja que referencian esas claves de alta
        sistemas_baja = (
            db.query(SoporteSistemaDisponible)
            .filter(
                SoporteSistemaDisponible.empresa_id == empresa_id,
                SoporteSistemaDisponible.tipo == "baja",
                SoporteSistemaDisponible.clave_alta_ref.in_(claves_alta),
                SoporteSistemaDisponible.activo == True,
            )
            .all()
        )

        return [s.clave for s in sistemas_baja] if sistemas_baja else None

    @staticmethod
    def obtener_checklist(db: Session, empresa_id: uuid.UUID, ticket_id: str) -> List[TicketChecklistItem]:
        return (
            db.query(TicketChecklistItem)
            .filter(TicketChecklistItem.ticket_id == ticket_id, TicketChecklistItem.empresa_id == empresa_id)
            .order_by(TicketChecklistItem.orden)
            .all()
        )

    @staticmethod
    def toggle_checklist_item(
        db: Session, empresa_id: uuid.UUID, item_id: str, usuario_email: str
    ) -> TicketChecklistItem:
        item = (
            db.query(TicketChecklistItem)
            .filter(TicketChecklistItem.id == uuid.UUID(item_id), TicketChecklistItem.empresa_id == empresa_id)
            .first()
        )
        if not item:
            raise ValueError("Ítem no encontrado")
        item.completado = not item.completado
        item.completado_por = usuario_email if item.completado else None
        item.completado_at = utc_now() if item.completado else None
        item.updated_by = usuario_email
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    def obtener_info_colaborador_alta(db: Session, empresa_id: uuid.UUID, colaborador_id: str) -> Dict[str, Any]:
        """
        Devuelve los datos del colaborador necesarios para precargar el formulario de alta IT.
        Solo lee de nómina, no modifica nada.
        """
        empleado = (
            db.query(Empleado)
            .options(
                joinedload(Empleado.departamento_rel).joinedload(Departamento.manager_rel),
            )
            .filter(
                Empleado.id == uuid.UUID(colaborador_id),
                Empleado.empresa_id == empresa_id,
                Empleado.deleted_at.is_(None),
            )
            .first()
        )

        if not empleado:
            raise ValueError("Colaborador no encontrado")

        lider = None
        lider_email = None
        if empleado.departamento_rel and empleado.departamento_rel.manager_rel:
            mgr = empleado.departamento_rel.manager_rel
            lider = f"{mgr.apellido}, {mgr.nombre}"
            lider_email = mgr.email_corporativo

        return {
            "id": str(empleado.id),
            "nombre": empleado.nombre,
            "apellido": empleado.apellido,
            "dni": empleado.dni,
            "telefono_personal": empleado.telefono_personal,
            "email_personal": empleado.email_personal,
            "email_corporativo": empleado.email_corporativo,
            "puesto": empleado.puesto,
            "seniority": empleado.seniority,
            "departamento": empleado.departamento_rel.nombre if empleado.departamento_rel else None,
            "lider": lider,
            "lider_email": lider_email,
            "cliente_servicio": empleado.puesto,  # se usa puesto como referencia inicial
            # Datos personales adicionales para el formulario de alta
            "fecha_alta": empleado.fecha_alta.strftime("%d/%m/%Y") if empleado.fecha_alta else None,
            "dir_laboral_provincia": empleado.dir_laboral_provincia,
            "dir_laboral_localidad": empleado.dir_laboral_localidad,
            "dir_laboral_calle": empleado.dir_laboral_calle,
            "dir_laboral_numero": empleado.dir_laboral_numero,
            "dir_laboral_piso": empleado.dir_laboral_piso,
            "dir_laboral_departamento": empleado.dir_laboral_departamento,
            "dir_laboral_codigo_postal": empleado.dir_laboral_codigo_postal,
        }

    @staticmethod
    def obtener_ticket(db: Session, empresa_id: uuid.UUID, ticket_id: str) -> Ticket:
        """Obtiene un ticket con todas sus relaciones especializadas.
        Optimizado: 1 query con with_polymorphic en vez de query doble.
        Un ticket dado de baja no existe para la consulta, igual que en el listado (PG-20)."""
        ticket = (
            db.query(Ticket)
            .options(
                joinedload(Ticket.subcategoria).joinedload(SoporteSubcategoria.categoria),
                joinedload(Ticket.estado_rel),
                joinedload(Ticket.solicitante),
                joinedload(Ticket.asignado),
            )
            .filter(Ticket.id == uuid.UUID(ticket_id), Ticket.empresa_id == empresa_id, Ticket.deleted_at.is_(None))
            .first()
        )

        if not ticket:
            return None

        # Forzar carga lazy de relaciones polimórficas que no se pueden joinedload desde Ticket base
        # Esto genera 1 query extra solo cuando aplica, en vez de re-hacer el query completo
        if ticket.tipo_ticket in (TipoTicket.REPARACION, TipoTicket.MANTENIMIENTO):
            if hasattr(ticket, "activo_id") and ticket.activo_id:
                # Acceder a la relación dispara lazy load (1 query)
                _ = ticket.activo
        elif ticket.tipo_ticket == TipoTicket.ALTA_BAJA:
            if hasattr(ticket, "activo_id") and ticket.activo_id:
                _ = ticket.activo
            if hasattr(ticket, "matriz_estado_id") and ticket.matriz_estado_id:
                _ = ticket.matriz_estado

        return ticket

    @staticmethod
    def obtener_ticket_completo(db: Session, empresa_id: uuid.UUID, ticket_id: str) -> Optional[Dict]:
        """Obtiene un ticket con evidencias y pedido de compra para la vista de detalle.
        Optimizado: consolida las queries que antes estaban inline en el router."""
        ticket = SoporteService.obtener_ticket(db, empresa_id, ticket_id)
        if not ticket:
            return None

        tid = ticket.id

        # Construir dict base
        ticket_dict = {
            "id": ticket.id,
            "numero": ticket.numero,
            "tipo_ticket": ticket.tipo_ticket,
            "titulo": ticket.titulo,
            "descripcion": ticket.descripcion,
            "prioridad": ticket.prioridad,
            "estado_id": ticket.estado_id,
            "estado_rel": ticket.estado_rel,
            "subcategoria": ticket.subcategoria,
            "solicitante_id": ticket.solicitante_id,
            "solicitante": ticket.solicitante,
            "asignado_id": ticket.asignado_id,
            "asignado": ticket.asignado,
            "es_falla": ticket.es_falla,
            "resolucion": ticket.resolucion,
            "created_at": ticket.created_at,
            "created_by": ticket.created_by,
        }

        # Campos polimórficos
        if ticket.tipo_ticket in (TipoTicket.REPARACION, TipoTicket.MANTENIMIENTO):
            ticket_dict["activo_id"] = getattr(ticket, "activo_id", None)
            ticket_dict["activo"] = getattr(ticket, "activo", None)
            ticket_dict["diagnostico"] = getattr(ticket, "diagnostico", None)
        elif ticket.tipo_ticket == TipoTicket.ALTA_BAJA:
            ticket_dict["colaborador_id"] = getattr(ticket, "colaborador_id", None)
            ticket_dict["colaborador"] = getattr(ticket, "colaborador", None)
            ticket_dict["tipo_operacion"] = getattr(ticket, "tipo_operacion", None)
            ticket_dict["entrega_kit_bienvenida"] = getattr(ticket, "entrega_kit_bienvenida", False)
            ticket_dict["activo_id"] = getattr(ticket, "activo_id", None)
            ticket_dict["activo"] = getattr(ticket, "activo", None)
            ticket_dict["matriz_estado_id"] = getattr(ticket, "matriz_estado_id", None)
            ticket_dict["matriz_estado"] = getattr(ticket, "matriz_estado", None)
            ticket_dict["modalidad_trabajo"] = getattr(ticket, "modalidad_trabajo", None)
            ticket_dict["requiere_nextcloud"] = getattr(ticket, "requiere_nextcloud", False)
            ticket_dict["listas_correo"] = getattr(ticket, "listas_correo", None)
            ticket_dict["necesita_computadora"] = getattr(ticket, "necesita_computadora", False)
            ticket_dict["gama_computadora"] = getattr(ticket, "gama_computadora", None)
            ticket_dict["cliente_servicio"] = getattr(ticket, "cliente_servicio", None)
            colab_id = getattr(ticket, "colaborador_id", None)
            if colab_id:
                try:
                    ticket_dict["colaborador_info"] = SoporteService.obtener_info_colaborador_alta(
                        db, empresa_id, colab_id
                    )
                except Exception:
                    ticket_dict["colaborador_info"] = {}

        # Evidencias (1 query) - solo las no eliminadas
        evidencias = (
            db.query(SoporteEvidencia)
            .filter(
                SoporteEvidencia.ticket_id == tid,
                SoporteEvidencia.empresa_id == empresa_id,
                SoporteEvidencia.deleted_at.is_(None),  # Filtrar evidencias eliminadas
            )
            .all()
        )

        # Convertir keys a URLs para el frontend
        from backend.core.storage import cloud_storage

        evidencias_serializadas = [
            {
                "id": str(ev.id),
                "url": cloud_storage.get_url(ev.url),  # Convertir key a URL
                "tipo": ev.tipo,
                "categoria": ev.categoria,
            }
            for ev in evidencias
        ]
        ticket_dict["evidencias"] = evidencias_serializadas

        # Pedido de compra más reciente (1 query con joinedload)
        pedido = (
            db.query(PedidoCompra)
            .options(
                joinedload(PedidoCompra.estado_rel),
                joinedload(PedidoCompra.solicitante),
                joinedload(PedidoCompra.presupuestos),
                joinedload(PedidoCompra.aprobaciones).joinedload(PedidoAprobacion.aprobador),
            )
            .filter(
                PedidoCompra.ticket_id == tid, PedidoCompra.empresa_id == empresa_id, PedidoCompra.deleted_at.is_(None)
            )
            .order_by(PedidoCompra.created_at.desc())
            .first()
        )
        ticket_dict["pedido_compra"] = pedido

        return ticket_dict

    @staticmethod
    def actualizar_ticket(
        db: Session, empresa_id: uuid.UUID, ticket_id: str, datos: Dict, usuario_email: str = None
    ) -> Ticket:
        """Actualiza campos de un ticket (especialmente para alta/baja: activo_id, matriz, kit)."""
        ticket = db.query(Ticket).filter(Ticket.id == uuid.UUID(ticket_id), Ticket.empresa_id == empresa_id).first()
        if not ticket:
            return None

        datos = limpiar_datos(datos)

        # Actualizar asignado_id si viene en los datos
        if "asignado_id" in datos:
            if datos["asignado_id"]:
                asignado_id = uuid.UUID(str(datos["asignado_id"]))
                # Validar que el empleado pertenece a la misma empresa
                empleado = (
                    db.query(Empleado)
                    .filter(
                        Empleado.id == asignado_id, Empleado.empresa_id == empresa_id, Empleado.deleted_at.is_(None)
                    )
                    .first()
                )
                if not empleado:
                    raise ValueError("El empleado seleccionado no pertenece a esta empresa o no existe")
                ticket.asignado_id = asignado_id
            else:
                ticket.asignado_id = None

        # Para tickets alta_baja, hacer query directo a la tabla hija para asegurar persistencia
        if ticket.tipo_ticket == TipoTicket.ALTA_BAJA:
            ticket_ab = db.query(TicketAltaBaja).filter(TicketAltaBaja.id == uuid.UUID(ticket_id)).first()
            if ticket_ab:
                if "activo_id" in datos and datos["activo_id"]:
                    ticket_ab.activo_id = uuid.UUID(str(datos["activo_id"]))
                if "matriz_estado_id" in datos and datos["matriz_estado_id"]:
                    ticket_ab.matriz_estado_id = uuid.UUID(str(datos["matriz_estado_id"]))
                if "entrega_kit_bienvenida" in datos:
                    ticket_ab.entrega_kit_bienvenida = bool(datos["entrega_kit_bienvenida"])
                ticket_ab.updated_by = usuario_email
                db.commit()
                db.refresh(ticket_ab)
                return ticket_ab

        ticket.updated_by = usuario_email
        db.commit()
        db.refresh(ticket)
        return ticket

    @staticmethod
    def _cerrar_reparacion_activo(
        db: Session,
        empresa_id: uuid.UUID,
        ticket: Ticket,
        ahora: datetime,
        usuario_email: Optional[str],
        motivo: str,
        resolucion: Optional[str] = None,
    ) -> None:
        """
        Cierre físico de una reparación: devuelve el activo al estado previo y deja registro.

        Se usa tanto al resolver como al cancelar/cerrar un ticket de reparación que ya
        había entrado al taller (activo en EN_REPARACION).

        - Si la matriz_salida no fue seteada, hereda matriz_entrada (snapshot por defecto).
        - El activo vuelve a ASIGNADO (si sigue teniendo dueño) o DISPONIBLE.
        - Registra historial técnico con el motivo del cierre.

        Idempotente: si el activo ya no está EN_REPARACION, no hace nada.
        """
        ticket_rep = db.query(TicketReparacion).filter(TicketReparacion.id == ticket.id).first()
        if not ticket_rep or not ticket_rep.activo_id:
            return

        activo = db.query(Activo).filter(Activo.id == ticket_rep.activo_id).first()
        if not activo or activo.estado != ActivoEstado.EN_REPARACION:
            # El activo ya fue devuelto o nunca entró al taller → nada que cerrar.
            return

        tecnico_id = ticket.asignado_id or ticket.solicitante_id

        # 1. Snapshot por defecto de matriz de salida = matriz de entrada
        if not ticket_rep.matriz_salida_id and ticket_rep.matriz_entrada_id:
            ticket_rep.matriz_salida_id = ticket_rep.matriz_entrada_id
        ticket_rep.updated_by = usuario_email

        # 2. Transicionar activo
        activo.estado = ActivoEstado.ASIGNADO if activo.asignado_id else ActivoEstado.DISPONIBLE
        if ticket_rep.matriz_salida_id:
            activo.matriz_estado_id = ticket_rep.matriz_salida_id
        activo.updated_by = usuario_email

        # 3. Historial
        nota = f"{motivo} por ticket T-{ticket.numero}."
        if resolucion:
            nota += f" Resolución: {resolucion}"
        historial = HistorialActivo(
            empresa_id=empresa_id,
            activo_id=ticket_rep.activo_id,
            responsable_id=tecnico_id,
            tipo_evento=HistorialTipoEvento.REPARACION,
            notas_adicionales=nota,
            matriz_estado_id=ticket_rep.matriz_salida_id,
            fecha_hora=ahora,
            created_by=usuario_email,
        )
        db.add(historial)
        logger.info(f"{motivo}: equipo {activo.id} vuelve a '{activo.estado}' por ticket #{ticket.numero}")

    @staticmethod
    def cambiar_estado(
        db: Session,
        empresa_id: uuid.UUID,
        ticket_id: str,
        nuevo_estado_id: str,
        resolucion: str = None,
        usuario_email: str = None,
        usuario_dni: int = None,
    ) -> Ticket:
        """Cambia el estado de un ticket y gestiona fechas de ciclo de vida v28.0."""
        ticket = db.query(Ticket).filter(Ticket.id == uuid.UUID(ticket_id), Ticket.empresa_id == empresa_id).first()
        if not ticket:
            raise ValueError("Ticket no encontrado")

        nuevo_estado = (
            db.query(SoporteTicketsEstado).filter(SoporteTicketsEstado.id == uuid.UUID(nuevo_estado_id)).first()
        )
        if not nuevo_estado:
            raise ValueError("Estado destino inexistente")

        clave = nuevo_estado.clave
        if clave == TicketEstado.RESUELTO and ticket.tipo_ticket == TipoTicket.ALTA_BAJA:
            ticket_ab = db.query(TicketAltaBaja).filter(TicketAltaBaja.id == ticket.id).first()
            if ticket_ab and ticket_ab.tipo_operacion == TipoOperacion.ALTA and not ticket_ab.activo_id:
                raise ValueError(
                    "No se puede resolver un ticket de alta sin asignar un equipo. Primero hacé click en 'Asignar Equipo y Generar Acuerdo'."
                )
            if ticket_ab and ticket_ab.tipo_operacion == TipoOperacion.BAJA and not ticket_ab.activo_id:
                raise ValueError(
                    "No se puede resolver un ticket de baja sin generar el acta de devolución. Primero hacé click en 'Recibir y Revisar Activo Devuelto'."
                )

        ticket.estado_id = nuevo_estado.id
        ticket.updated_by = usuario_email

        ahora = utc_now()

        if clave == TicketEstado.EN_PROGRESO and not ticket.fecha_inicio:
            ticket.fecha_inicio = ahora
            # Asignar automáticamente al técnico que inicia el progreso si no está asignado
            if not ticket.asignado_id and usuario_dni:
                from backend.modules.nomina.services import EmpleadoService

                empleado = EmpleadoService.obtener_por_dni(db, empresa_id, usuario_dni)
                if empleado:
                    ticket.asignado_id = empleado.id
                    logger.info(
                        f"Ticket #{ticket.numero} asignado automáticamente a {empleado.nombre} {empleado.apellido} al iniciar progreso"
                    )
        elif clave == TicketEstado.RESUELTO:
            ticket.fecha_resolucion = ahora
            if resolucion:
                ticket.resolucion = resolucion

            if ticket.tipo_ticket == TipoTicket.ALTA_BAJA:
                ticket_ab = db.query(TicketAltaBaja).filter(TicketAltaBaja.id == ticket.id).first()
                if ticket_ab and ticket_ab.tipo_operacion == TipoOperacion.ALTA:
                    tecnico_id = ticket.asignado_id or ticket.solicitante_id

                    if ticket_ab.activo_id:
                        activo = db.query(Activo).filter(Activo.id == ticket_ab.activo_id).first()
                        if activo:
                            activo.estado = ActivoEstado.ASIGNADO
                            activo.asignado_id = ticket_ab.colaborador_id
                            activo.fecha_asignacion = ahora
                            if ticket_ab.matriz_estado_id:
                                activo.matriz_estado_id = ticket_ab.matriz_estado_id

                            historial = HistorialActivo(
                                empresa_id=empresa_id,
                                activo_id=ticket_ab.activo_id,
                                colaborador_id=ticket_ab.colaborador_id,
                                responsable_id=tecnico_id,
                                tipo_evento=HistorialTipoEvento.ALTA,
                                notas_adicionales=f"Asignación por ticket T-{ticket.numero}: Alta de colaborador",
                                matriz_estado_id=ticket_ab.matriz_estado_id,
                                fecha_hora=ahora,
                                created_by=usuario_email,
                            )
                            db.add(historial)
                            db.flush()  # Para obtener el ID del historial

                            # Copiar evidencias del ticket al historial
                            evidencias_ticket = (
                                db.query(SoporteEvidencia)
                                .filter(
                                    SoporteEvidencia.ticket_id == ticket.id,
                                    SoporteEvidencia.empresa_id == empresa_id,  # Validar empresa
                                    SoporteEvidencia.deleted_at.is_(None),
                                )
                                .all()
                            )

                            for ev in evidencias_ticket:
                                # Actualizar la evidencia para vincularla también al historial
                                ev.historial_id = historial.id
                                ev.activo_id = ticket_ab.activo_id

                            logger.info(
                                f"Equipo {ticket_ab.activo_id} asignado a colaborador {ticket_ab.colaborador_id} al resolver ticket #{ticket.numero}. {len(evidencias_ticket)} evidencias vinculadas al historial."
                            )

                    if ticket_ab.entrega_kit_bienvenida:
                        colaborador = db.query(Empleado).filter(Empleado.id == ticket_ab.colaborador_id).first()
                        colaborador_nombre = (
                            f"{colaborador.nombre} {colaborador.apellido}" if colaborador else "Colaborador"
                        )

                        kit_insumos = (
                            db.query(Insumo)
                            .filter(
                                Insumo.deleted_at.is_(None),
                                Insumo.empresa_id == empresa_id,
                                Insumo.nombre.ilike("%mouse%") | Insumo.nombre.ilike("%auricular%"),
                            )
                            .all()
                        )

                        for insumo in kit_insumos:
                            movimiento = MovimientoInsumo(
                                empresa_id=empresa_id,
                                insumo_id=insumo.id,
                                tipo="consumo",
                                cantidad=1,
                                empleado_id=ticket_ab.colaborador_id,
                                empleado_asignador_id=tecnico_id,
                                motivo=f"Kit de bienvenida - Ticket T-{ticket.numero} Alta de {colaborador_nombre}",
                                fecha_movimiento=ahora,
                                created_by=usuario_email,
                            )
                            db.add(movimiento)
                            db.flush()

                            consumo = SoporteTicketInsumo(
                                empresa_id=empresa_id,
                                ticket_id=ticket.id,
                                insumo_id=insumo.id,
                                cantidad=1,
                                movimiento_insumo_id=movimiento.id,
                                created_by=usuario_email,
                            )
                            db.add(consumo)
                            insumo.stock_actual = max(0, (insumo.stock_actual or 0) - 1)
                            logger.info(
                                f"Kit bienvenida: consumido 1x {insumo.nombre} para {colaborador_nombre} (ticket #{ticket.numero})"
                            )

                elif ticket_ab and ticket_ab.tipo_operacion == TipoOperacion.BAJA:
                    if ticket_ab.activo_id:
                        tecnico_id = ticket.asignado_id or ticket.solicitante_id
                        activo = db.query(Activo).filter(Activo.id == ticket_ab.activo_id).first()
                        if activo:
                            activo.estado = ActivoEstado.DISPONIBLE
                            activo.asignado_id = None
                            activo.fecha_asignacion = None
                            if ticket_ab.matriz_estado_id:
                                activo.matriz_estado_id = ticket_ab.matriz_estado_id

                            historial = HistorialActivo(
                                empresa_id=empresa_id,
                                activo_id=ticket_ab.activo_id,
                                colaborador_id=ticket_ab.colaborador_id,
                                responsable_id=tecnico_id,
                                tipo_evento=HistorialTipoEvento.BAJA,
                                notas_adicionales=f"Devolución por ticket T-{ticket.numero}: Baja de colaborador",
                                matriz_estado_id=ticket_ab.matriz_estado_id,
                                fecha_hora=ahora,
                                created_by=usuario_email,
                            )
                            db.add(historial)
                            db.flush()  # Para obtener el ID del historial

                            # Copiar evidencias del ticket al historial
                            evidencias_ticket = (
                                db.query(SoporteEvidencia)
                                .filter(
                                    SoporteEvidencia.ticket_id == ticket.id,
                                    SoporteEvidencia.empresa_id == empresa_id,  # Validar empresa
                                    SoporteEvidencia.deleted_at.is_(None),
                                )
                                .all()
                            )

                            for ev in evidencias_ticket:
                                # Actualizar la evidencia para vincularla también al historial
                                ev.historial_id = historial.id
                                ev.activo_id = ticket_ab.activo_id

                            logger.info(
                                f"Equipo {ticket_ab.activo_id} devuelto a disponible al resolver ticket #{ticket.numero}. {len(evidencias_ticket)} evidencias vinculadas al historial."
                            )

            elif ticket.tipo_ticket == TipoTicket.REPARACION:
                # Cierre automático: devolver el activo y cerrar historial.
                SoporteService._cerrar_reparacion_activo(
                    db, empresa_id, ticket, ahora, usuario_email, motivo="Cierre de reparación", resolucion=resolucion
                )

        elif clave in (TicketEstado.CANCELADO, TicketEstado.CERRADO):
            ticket.fecha_cierre = ahora
            if not ticket.fecha_resolucion and clave == TicketEstado.CERRADO:
                ticket.fecha_resolucion = ahora

            # Si se cancela/cierra un ticket de reparación que ya había entrado al taller,
            # hay que devolver el activo a su estado previo para que no quede colgado.
            if ticket.tipo_ticket == TipoTicket.REPARACION:
                motivo = "Cancelación de reparación" if clave == TicketEstado.CANCELADO else "Cierre de reparación"
                SoporteService._cerrar_reparacion_activo(
                    db, empresa_id, ticket, ahora, usuario_email, motivo=motivo, resolucion=resolucion
                )
        elif clave == TicketEstado.ABIERTO:
            pass

        db.commit()
        db.refresh(ticket)
        logger.info(f"Ticket #{ticket.numero} movido a {clave} por {usuario_email}")
        return ticket

    @staticmethod
    def iniciar_peritaje(
        db: Session,
        empresa_id: uuid.UUID,
        ticket_id: str,
        diagnostico: str,
        matriz_datos: Dict,
        usuario_email: str,
        activo_id: Optional[str] = None,
    ) -> Ticket:
        """Inicia la reparación técnica de un ticket.

        Cubre dos escenarios:
          A) Ticket genérico con es_falla=True que se promueve a tipo 'reparacion'.
             Requiere activo_id explícito si el ticket aún no lo tiene vinculado.
          B) Ticket nacido como tipo 'reparacion' (subcategoría reparacion).
             El activo ya está asociado. Si está en 'abierto', lo lleva a 'en_progreso'.

        En ambos casos:
          - Crea la matriz de entrada (peritaje físico inicial).
          - Guarda el diagnóstico.
          - Pasa el activo a estado EN_REPARACION.
          - Registra historial técnico.
          - Deja el ticket en 'en_progreso'.
        """
        from sqlalchemy import update as _update

        # 1. Obtener ticket base
        ticket_base = (
            db.query(Ticket)
            .filter(Ticket.id == ticket_id, Ticket.empresa_id == empresa_id, Ticket.deleted_at.is_(None))
            .first()
        )
        if not ticket_base:
            raise ValueError("Ticket no encontrado")

        # 2. Obtener estado destino
        estado_progreso = SoporteService.obtener_estado_ticket(db, "en_progreso")
        if not estado_progreso:
            raise ValueError("Estado 'en_progreso' no configurado")

        # 3. Resolver el activo destino y decidir el escenario
        es_reparacion = ticket_base.tipo_ticket == TipoTicket.REPARACION

        if es_reparacion:
            # Escenario B: ticket ya es de reparación
            ticket_rep = db.query(TicketReparacion).filter(TicketReparacion.id == ticket_id).first()
            if not ticket_rep:
                raise ValueError("Ticket de reparación no encontrado")
            if not ticket_rep.activo_id:
                raise ValueError("El ticket de reparación no tiene un equipo asociado")
            activo_uuid = ticket_rep.activo_id
        else:
            # Escenario A: ticket genérico que se promueve
            # Usamos el activo_id del payload si vino, si no el que ya tenga el ticket
            candidato = activo_id or getattr(ticket_base, "activo_id", None)
            if not candidato:
                raise ValueError("Se requiere un equipo vinculado para iniciar la reparación")
            try:
                activo_uuid = uuid.UUID(str(candidato))
            except ValueError, TypeError:
                raise ValueError("ID de equipo inválido")

        # 4. Verificar que el activo exista y pertenezca a la empresa
        activo = db.query(Activo).filter(Activo.id == activo_uuid, Activo.empresa_id == empresa_id).first()
        if not activo:
            raise ValueError("Equipo no encontrado")

        # 5. Crear matriz de entrada
        matriz = SoporteMatrizEstado(
            empresa_id=empresa_id,
            pantalla=matriz_datos.get("pantalla"),
            teclado=matriz_datos.get("teclado"),
            bateria=matriz_datos.get("bateria"),
            carcasa_superior=matriz_datos.get("carcasa_superior"),
            carcasa_inferior=matriz_datos.get("carcasa_inferior"),
            touchpad=matriz_datos.get("touchpad"),
            puertos=matriz_datos.get("puertos"),
            cargador=matriz_datos.get("cargador"),
            created_by=usuario_email,
        )
        db.add(matriz)
        db.flush()

        # 6. Aplicar cambios según el escenario
        if es_reparacion:
            # Actualizar fila hija + base
            ticket_rep.diagnostico = diagnostico
            ticket_rep.matriz_entrada_id = matriz.id
            ticket_rep.updated_by = usuario_email

            if ticket_base.estado_id != estado_progreso.id:
                ticket_base.estado_id = estado_progreso.id
                ticket_base.fecha_inicio = ticket_base.fecha_inicio or utc_now()
            ticket_base.updated_by = usuario_email
        else:
            # Promover base + crear fila hija
            db.execute(
                _update(Ticket)
                .where(Ticket.id == ticket_id, Ticket.empresa_id == empresa_id)
                .values(
                    tipo_ticket="reparacion",
                    es_falla=True,
                    estado_id=estado_progreso.id,
                    fecha_inicio=utc_now(),
                    updated_by=usuario_email,
                )
            )
            db.execute(
                insert(TicketReparacion.__table__).values(
                    id=ticket_id, activo_id=activo_uuid, diagnostico=diagnostico, matriz_entrada_id=matriz.id
                )
            )

        # 7. Afectar activo (inventario)
        activo.estado = ActivoEstado.EN_REPARACION
        activo.updated_by = usuario_email

        # 8. Registrar historial técnico
        ticket_refrescado = db.query(Ticket).filter(Ticket.id == ticket_id).first()
        SoporteService.crear_historial(
            db,
            empresa_id,
            {
                "activo_id": str(activo.id),
                "responsable_id": str(ticket_refrescado.asignado_id or ticket_refrescado.solicitante_id),
                "tipo_evento": HistorialTipoEvento.REPARACION,
                "notas_adicionales": f"Inicio de reparación técnica. Diagnóstico: {diagnostico}",
                "matriz_estado": matriz_datos,
            },
            usuario_email,
        )

        db.commit()
        db.expire_all()
        logger.info(
            f"Peritaje iniciado en ticket #{ticket_refrescado.numero} "
            f"(escenario={'ya_reparacion' if es_reparacion else 'promocion'})"
        )
        return db.query(Ticket).filter(Ticket.id == ticket_id).first()

    @staticmethod
    def generar_pedido_reparacion(
        db: Session,
        empresa_id: uuid.UUID,
        ticket_id: str,
        tipo_pedido: str,
        descripcion: str,
        monto_estimado: float,
        usuario_email: str,
        insumo_id: str = None,
        cantidad_solicitada: int = 0,
    ) -> PedidoCompra:
        """Genera un pedido de compra vinculado a un ticket de reparacion o mantenimiento."""
        from backend.modules.soporte.models import SoportePedidosEstado

        tid = ticket_id

        ticket = db.query(Ticket).filter(Ticket.id == tid, Ticket.empresa_id == empresa_id).first()
        if not ticket:
            raise ValueError("Ticket no encontrado")

        if ticket.tipo_ticket not in (TipoTicket.REPARACION, TipoTicket.MANTENIMIENTO):
            raise ValueError("Solo los tickets de reparacion o mantenimiento pueden generar pedidos de compra")

        estado_borrador = (
            db.query(SoportePedidosEstado).filter(SoportePedidosEstado.clave == PedidoEstado.BORRADOR).first()
        )
        if not estado_borrador:
            raise ValueError("Estado 'borrador' no configurado para pedidos")

        ahora = utc_now()
        prefijo = f"PC-{ahora.strftime('%Y%m%d')}"
        ultimo = (
            db.query(PedidoCompra)
            .filter(PedidoCompra.numero.like(f"{prefijo}%"), PedidoCompra.empresa_id == empresa_id)
            .order_by(PedidoCompra.numero.desc())
            .first()
        )

        if ultimo:
            try:
                ultimo_num = int(ultimo.numero.split("-")[-1])
                nuevo_num = ultimo_num + 1
            except ValueError, IndexError:
                nuevo_num = 1
        else:
            nuevo_num = 1

        numero = f"{prefijo}-{nuevo_num:04d}"

        pedido = PedidoCompra(
            empresa_id=empresa_id,
            numero=numero,
            tipo_pedido=tipo_pedido,
            descripcion=descripcion,
            monto_estimado=monto_estimado or 0.0,
            requiere_doble_aprobacion=(monto_estimado or 0.0) > 100000,
            estado_id=estado_borrador.id,
            solicitante_id=ticket.asignado_id or ticket.solicitante_id,
            ticket_id=ticket.id,
            insumo_id=uuid.UUID(insumo_id) if insumo_id else None,
            cantidad_solicitada=cantidad_solicitada or 0,
            created_by=usuario_email,
            updated_by=usuario_email,
        )
        db.add(pedido)
        db.commit()
        db.refresh(pedido)

        logger.info(f"Pedido de compra {numero} creado para ticket #{ticket.numero} por {usuario_email}")
        return pedido

    @staticmethod
    def eliminar_ticket(db: Session, empresa_id: uuid.UUID, ticket_id: str):
        """Soft delete de un ticket (v28.0)."""
        ticket = (
            db.query(Ticket)
            .filter(Ticket.id == uuid.UUID(ticket_id), Ticket.empresa_id == empresa_id, Ticket.deleted_at.is_(None))
            .first()
        )
        if not ticket:
            raise ValueError("Ticket no encontrado")

        ticket.deleted_at = utc_now()
        db.commit()

    @staticmethod
    def dashboard_metrics(db: Session, empresa_id: uuid.UUID) -> Dict[str, Any]:
        """Obtiene métricas avanzadas v28.0 cruzando estados relacionales y auditoría.
        Optimizado: reutiliza mapa de estados en vez de queries repetidos."""
        ahora = utc_now()
        hace_7_dias = ahora - timedelta(days=7)
        hace_6_meses = ahora - timedelta(days=180)

        # 1. Cargar mapa de estados una sola vez (1 query)
        estados_all = db.query(SoporteTicketsEstado).all()
        estados_m = {str(e.id): e.clave for e in estados_all}
        clave_a_id = {e.clave: e.id for e in estados_all}

        # 2. Stats Generales por Estado Maestro (1 query)
        res_estados = (
            db.query(Ticket.estado_id, func.count(Ticket.id))
            .filter(Ticket.empresa_id == empresa_id)
            .group_by(Ticket.estado_id)
            .all()
        )
        conteo_estados = {estados_m.get(str(eid), str(eid)): count for eid, count in res_estados}

        stats = {
            "abierto": conteo_estados.get("abierto", 0),
            "abiertos": conteo_estados.get("abierto", 0),
            "en_progreso": conteo_estados.get("en_progreso", 0),
            "resuelto": conteo_estados.get("resuelto", 0),
            "resueltos": conteo_estados.get("resuelto", 0),
            "cerrado": conteo_estados.get("cerrado", 0),
            "cancelado": conteo_estados.get("cancelado", 0),
            "total": sum(conteo_estados.values()),
        }

        # 3. Resueltos en la última semana (1 query, reutiliza clave_a_id)
        resuelto_id = clave_a_id.get(TicketEstado.RESUELTO)
        if resuelto_id:
            stats["resueltos_semana"] = (
                db.query(func.count(Ticket.id))
                .filter(
                    Ticket.empresa_id == empresa_id,
                    Ticket.estado_id == resuelto_id,
                    Ticket.fecha_resolucion >= hace_7_dias,
                )
                .scalar()
                or 0
            )
        else:
            stats["resueltos_semana"] = 0

        # 4. Próximos Mantenimientos (Notebooks) - 1 query con joinedload
        tipo_notebook = db.query(ActivoTipo).filter(ActivoTipo.nombre.ilike("%Notebook%")).first()
        mantenimientos = []
        if tipo_notebook:
            equipos_m = (
                db.query(Activo)
                .options(joinedload(Activo.asignado_rel), joinedload(Activo.tipo_rel))
                .filter(
                    Activo.empresa_id == empresa_id,
                    Activo.tipo_id == tipo_notebook.id,
                    Activo.fecha_ultimo_mantenimiento.isnot(None),
                )
                .order_by(Activo.fecha_ultimo_mantenimiento.asc())
                .limit(5)
                .all()
            )

            for e in equipos_m:
                prox = e.fecha_ultimo_mantenimiento + timedelta(
                    days=30 * (e.tipo_rel.frecuencia_mantenimiento_meses or 6)
                )
                mantenimientos.append(
                    {
                        "id": str(e.id),
                        "nombre": e.nombre,
                        "serie": e.numero_serie,
                        "asignado_a": f"{e.asignado_rel.nombre} {e.asignado_rel.apellido}"
                        if e.asignado_rel
                        else "Staff Soporte",
                        "fecha_estimada": prox.strftime("%d %b"),
                        "dias_restantes": (prox - ahora).days,
                    }
                )

        # 5. Equipos Reemplazo (Top Fallas reales) - 1 query
        top_fallas = (
            db.query(Activo.id, Activo.numero_serie, Activo.nombre, func.count(TicketReparacion.id).label("fallas"))
            .join(TicketReparacion, TicketReparacion.activo_id == Activo.id)
            .filter(
                Activo.empresa_id == empresa_id,
                TicketReparacion.es_falla == True,
                TicketReparacion.created_at >= hace_6_meses,
            )
            .group_by(Activo.id)
            .order_by(desc("fallas"))
            .limit(3)
            .all()
        )

        # 6. Termómetro de Demoras - reutiliza clave_a_id en vez de 2 queries extra
        abierto_id = clave_a_id.get(TicketEstado.ABIERTO)
        progreso_id = clave_a_id.get(TicketEstado.EN_PROGRESO)

        ids_activos = [eid for eid in [abierto_id, progreso_id] if eid]
        demoras = (
            db.query(Ticket)
            .filter(Ticket.empresa_id == empresa_id, Ticket.estado_id.in_(ids_activos))
            .order_by(Ticket.created_at.asc())
            .limit(7)
            .all()
            if ids_activos
            else []
        )

        return {
            "stats": stats,
            "mantenimientos": mantenimientos,
            "reemplazo_top": [{"id": str(f.id), "serie": f.numero_serie, "fallas": f.fallas} for f in top_fallas],
            "demoras": [{"id": str(t.id), "numero": t.numero, "dias": (ahora - t.created_at).days} for t in demoras],
        }

    # ─── Lógica de Inventario y Abastecimiento ───────────────────────

    @staticmethod
    def calcular_stock(db: Session, empresa_id: uuid.UUID, insumo_id: str) -> int:
        """Suma de movimientos: ingresos (+), consumos (-), devoluciones (+)."""
        ingresos = (
            db.query(func.sum(MovimientoInsumo.cantidad))
            .filter(
                MovimientoInsumo.insumo_id == insumo_id,
                MovimientoInsumo.empresa_id == empresa_id,
                MovimientoInsumo.tipo.in_(["ingreso", "devolucion", "ajuste_positivo"]),
            )
            .scalar()
            or 0
        )
        egresos = (
            db.query(func.sum(MovimientoInsumo.cantidad))
            .filter(
                MovimientoInsumo.insumo_id == insumo_id,
                MovimientoInsumo.empresa_id == empresa_id,
                MovimientoInsumo.tipo.in_(["consumo", "ajuste_negativo"]),
            )
            .scalar()
            or 0
        )
        return int(ingresos - egresos)

    @staticmethod
    def agregar_insumo_a_ticket(
        db: Session,
        empresa_id: uuid.UUID,
        ticket_id: str,
        insumo_id: str,
        cantidad: int,
        generar_pedido: bool,
        usuario_email: str,
    ) -> SoporteTicketInsumo:
        """Vincula un insumo a un ticket. Si no hay stock y se marca generar_pedido, crea un PedidoCompra."""
        tid = uuid.UUID(ticket_id)
        iid = uuid.UUID(insumo_id)

        # 1. Verificar Stock
        stock_actual = SoporteService.calcular_stock(db, empresa_id, iid)

        vinc = SoporteTicketInsumo(
            empresa_id=empresa_id,
            ticket_id=tid,
            insumo_id=iid,
            cantidad=cantidad,
            generar_pedido_compra=generar_pedido,
            created_by=usuario_email,
        )

        if stock_actual >= cantidad:
            # Consumir Stock
            mov = SoporteService.registrar_movimiento_insumo(
                db,
                empresa_id,
                {
                    "insumo_id": iid,
                    "tipo": "consumo",
                    "cantidad": cantidad,
                    "motivo": f"Consumo automático por Ticket {ticket_id}",
                },
                usuario_email,
            )
            vinc.movimiento_insumo_id = mov.id
        elif generar_pedido:
            # Crear Pedido de Compra (Draft)
            nuevo_pedido = PedidoCompra(
                empresa_id=empresa_id,
                numero=f"PC-{utc_now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:4]}",
                tipo_pedido="insumo",
                descripcion=f"Reposición automática para Ticket {ticket_id}",
                ticket_id=tid,
                created_by=usuario_email,
            )
            db.add(nuevo_pedido)
            db.flush()
            vinc.pedido_compra_id = nuevo_pedido.id
            logger.warning(f"Stock insuficiente para {insumo_id}. Pedido {nuevo_pedido.numero} generado.")
        else:
            raise ValueError(f"Stock insuficiente ({stock_actual}) y no se autorizó generar pedido de compra.")

        db.add(vinc)
        db.commit()
        db.refresh(vinc)
        return vinc

    @staticmethod
    def obtener_insumos_ticket(db: Session, empresa_id: uuid.UUID, ticket_id: str) -> List[SoporteTicketInsumo]:
        return (
            db.query(SoporteTicketInsumo)
            .options(joinedload(SoporteTicketInsumo.insumo))
            .filter(SoporteTicketInsumo.ticket_id == ticket_id, SoporteTicketInsumo.empresa_id == empresa_id)
            .all()
        )

    # ─── Configuraciones Maestras (Admin) ──────────────────────────

    @staticmethod
    def crear_marca(db: Session, empresa_id: uuid.UUID, nombre: str, usuario_email: str) -> SoporteActivosMarca:
        # Sanitizar: trim, capitalizar primera letra de cada palabra
        nombre = nombre.strip() if nombre else nombre
        if not nombre:
            raise ValueError("El nombre de la marca no puede estar vacío")

        # Capitalizar primera letra de cada palabra (ej: "dell" -> "Dell", "hp" -> "HP")
        nombre = " ".join(word.capitalize() for word in nombre.split())

        # Validar si ya existe (case-insensitive)
        existente = (
            db.query(SoporteActivosMarca)
            .filter(
                SoporteActivosMarca.empresa_id == empresa_id, func.lower(SoporteActivosMarca.nombre) == nombre.lower()
            )
            .first()
        )

        if existente:
            raise ValueError(f"Ya existe una marca con el nombre '{existente.nombre}'")

        marca = SoporteActivosMarca(empresa_id=empresa_id, nombre=nombre, created_by=usuario_email)
        db.add(marca)
        db.commit()
        db.refresh(marca)
        return marca

    @staticmethod
    def listar_estados(db: Session) -> List[SoporteTicketsEstado]:
        return db.query(SoporteTicketsEstado).all()

    @staticmethod
    def listar_valores_matriz(db: Session) -> Dict[str, Any]:
        """Lista los valores permitidos para la matriz de estado (hardcodeados)."""
        valores = [
            {"nombre": "Excelente", "color": "#10b981", "orden": 1},
            {"nombre": "Bueno", "color": "#3b82f6", "orden": 2},
            {"nombre": "Regular", "color": "#f59e0b", "orden": 3},
            {"nombre": "Malo", "color": "#ef4444", "orden": 4},
            {"nombre": "No aplica", "color": "#6b7280", "orden": 5},
        ]
        return {"valores": valores}

    @staticmethod
    def listar_tipos_ticket() -> List[Dict[str, str]]:
        """Lista los tipos de ticket disponibles con metadata para UI.

        Fuente única de verdad: enum TipoTicket. Si agregás un tipo nuevo al enum,
        sumalo acá con su label/color para que el frontend lo muestre automáticamente.
        """
        return [
            {"clave": TipoTicket.GENERICO.value, "label": "Genérico", "color": "gray"},
            {"clave": TipoTicket.REPARACION.value, "label": "Reparación", "color": "red"},
            {"clave": TipoTicket.ALTA_BAJA.value, "label": "Alta/Baja", "color": "blue"},
            {"clave": TipoTicket.MANTENIMIENTO.value, "label": "Mantenimiento", "color": "amber"},
        ]

    @staticmethod
    def listar_marcas(db: Session, empresa_id: uuid.UUID) -> Dict[str, Any]:
        query = db.query(SoporteActivosMarca).filter(SoporteActivosMarca.empresa_id == empresa_id)
        items = query.order_by(SoporteActivosMarca.nombre).all()
        return {"items": items, "total": len(items)}

    @staticmethod
    def obtener_marca(db: Session, empresa_id: uuid.UUID, marca_id: str) -> Optional[SoporteActivosMarca]:
        """Obtiene una marca por ID."""
        try:
            marca_uuid = uuid.UUID(marca_id)
        except ValueError:
            return None

        return (
            db.query(SoporteActivosMarca)
            .filter(SoporteActivosMarca.id == marca_uuid, SoporteActivosMarca.empresa_id == empresa_id)
            .first()
        )

    @staticmethod
    def actualizar_marca(
        db: Session, empresa_id: uuid.UUID, marca_id: str, datos: Dict[str, Any], usuario_email: str
    ) -> Optional[SoporteActivosMarca]:
        """Actualiza una marca existente."""
        marca = SoporteService.obtener_marca(db, empresa_id, marca_id)
        if not marca:
            return None

        datos = limpiar_datos(datos)

        # Validar que el nombre no esté vacío
        if "nombre" in datos:
            nombre = datos["nombre"]
            if not nombre or not nombre.strip():
                raise ValueError("El nombre de la marca no puede estar vacío")

            # Validar unicidad del nombre
            existente = (
                db.query(SoporteActivosMarca)
                .filter(
                    SoporteActivosMarca.empresa_id == empresa_id,
                    SoporteActivosMarca.nombre == nombre,
                    SoporteActivosMarca.id != marca.id,
                )
                .first()
            )
            if existente:
                raise ValueError(f"Ya existe una marca con el nombre '{nombre}'")

            marca.nombre = nombre

        marca.updated_by = usuario_email
        db.commit()
        db.refresh(marca)
        return marca

    @staticmethod
    def eliminar_marca(db: Session, empresa_id: uuid.UUID, marca_id: str) -> bool:
        """Elimina una marca si no está en uso."""
        marca = SoporteService.obtener_marca(db, empresa_id, marca_id)
        if not marca:
            return False

        # Verificar si la marca está en uso por algún activo
        activos_con_marca = (
            db.query(Activo)
            .filter(Activo.marca_id == marca.id, Activo.empresa_id == empresa_id, Activo.deleted_at.is_(None))
            .count()
        )

        if activos_con_marca > 0:
            raise ValueError(f"No se puede eliminar la marca porque está asignada a {activos_con_marca} activo(s)")

        # Eliminar físicamente (no soft delete porque es una tabla maestra simple)
        db.delete(marca)
        db.commit()
        return True

    @staticmethod
    def listar_tipos_activos(db: Session, empresa_id: uuid.UUID, activos_solo: bool = False) -> Dict[str, Any]:
        query = db.query(ActivoTipo).filter(ActivoTipo.deleted_at.is_(None), ActivoTipo.empresa_id == empresa_id)
        if activos_solo:
            query = query.filter(ActivoTipo.activo == True)

        items = query.order_by(ActivoTipo.nombre).all()
        return {"items": items, "total": len(items)}

    @staticmethod
    def crear_tipo_activo(db: Session, datos: Dict[str, Any], usuario_email: str, empresa_id: uuid.UUID) -> ActivoTipo:
        import re
        import unicodedata

        datos = limpiar_datos(datos)

        # Auto-generar clave desde el nombre si no viene
        if not datos.get("clave"):
            nombre = datos.get("nombre", "")
            # Normalizar: quitar acentos, convertir a minúsculas, reemplazar espacios por guiones bajos
            slug = unicodedata.normalize("NFD", nombre.lower())
            slug = re.sub(r"[\u0300-\u036f]", "", slug)  # Quitar diacríticos
            slug = re.sub(r"[^a-z0-9]+", "_", slug)  # Reemplazar no-alfanuméricos por _
            slug = slug.strip("_")  # Quitar guiones al inicio/fin

            # Validar unicidad de la clave
            contador = 0
            clave_base = slug
            while True:
                clave_candidata = f"{clave_base}_{contador}" if contador > 0 else clave_base
                existente = (
                    db.query(ActivoTipo)
                    .filter(
                        ActivoTipo.clave == clave_candidata,
                        ActivoTipo.empresa_id == empresa_id,
                        ActivoTipo.deleted_at.is_(None),
                    )
                    .first()
                )
                if not existente:
                    slug = clave_candidata
                    break
                contador += 1

            datos["clave"] = slug

        # Check if already exists by nombre
        query = db.query(ActivoTipo).filter(
            ActivoTipo.nombre == datos["nombre"], ActivoTipo.empresa_id == empresa_id, ActivoTipo.deleted_at.is_(None)
        )
        existente = query.first()
        if existente:
            return existente

        datos["empresa_id"] = empresa_id
        tipo = ActivoTipo(**datos, created_by=usuario_email)
        db.add(tipo)
        db.commit()
        db.refresh(tipo)
        return tipo

    @staticmethod
    def eliminar_tipo_activo(db: Session, tipo_id: str, empresa_id: uuid.UUID) -> bool:
        """Soft delete de un tipo de activo. Verifica que no tenga activos vinculados."""
        query = db.query(ActivoTipo).filter(
            ActivoTipo.id == uuid.UUID(tipo_id), ActivoTipo.empresa_id == empresa_id, ActivoTipo.deleted_at.is_(None)
        )
        tipo = query.first()
        if not tipo:
            return False
        # Verificar que no haya activos usando este tipo
        activos_count = db.query(Activo).filter(Activo.tipo_id == tipo.id).count()
        if activos_count > 0:
            raise ValueError(f"No se puede eliminar: hay {activos_count} activo(s) usando este tipo")
        tipo.deleted_at = utc_now()
        db.commit()
        return True

    @staticmethod
    def listar_insumos(db: Session, empresa_id: uuid.UUID) -> List[Dict]:
        """Insumos con stock real pre-calculado para la UI.
        Optimizado: 1 query con subquery en vez de N+1 calcular_stock."""
        # Subquery: calcular stock de todos los insumos en un solo query
        ingresos_sq = (
            db.query(MovimientoInsumo.insumo_id, func.coalesce(func.sum(MovimientoInsumo.cantidad), 0).label("total"))
            .filter(
                MovimientoInsumo.empresa_id == empresa_id,
                MovimientoInsumo.tipo.in_(["ingreso", "devolucion", "ajuste_positivo"]),
            )
            .group_by(MovimientoInsumo.insumo_id)
            .subquery()
        )

        egresos_sq = (
            db.query(MovimientoInsumo.insumo_id, func.coalesce(func.sum(MovimientoInsumo.cantidad), 0).label("total"))
            .filter(
                MovimientoInsumo.empresa_id == empresa_id, MovimientoInsumo.tipo.in_(["consumo", "ajuste_negativo"])
            )
            .group_by(MovimientoInsumo.insumo_id)
            .subquery()
        )

        resultados = (
            db.query(
                Insumo,
                (func.coalesce(ingresos_sq.c.total, 0) - func.coalesce(egresos_sq.c.total, 0)).label("stock_calculado"),
            )
            .outerjoin(ingresos_sq, Insumo.id == ingresos_sq.c.insumo_id)
            .outerjoin(egresos_sq, Insumo.id == egresos_sq.c.insumo_id)
            .filter(Insumo.deleted_at.is_(None), Insumo.empresa_id == empresa_id)
            .all()
        )

        return [
            {
                "id": str(insumo.id),
                "nombre": insumo.nombre,
                "descripcion": insumo.descripcion,
                "stock_actual": int(stock_calculado),
                "stock_minimo": insumo.stock_minimo,
                "unidad_medida": insumo.unidad_medida,
                "categoria_id": str(insumo.categoria_id) if insumo.categoria_id else None,
            }
            for insumo, stock_calculado in resultados
        ]

    @staticmethod
    def crear_insumo(db: Session, empresa_id: uuid.UUID, datos: Dict[str, Any], usuario_email: str) -> Insumo:
        datos = limpiar_datos(datos)
        stock_inicial = datos.pop("stock_actual", 0)

        # Validar categoria_id si viene
        if datos.get("categoria_id"):
            cat = (
                db.query(SoporteCategoria)
                .filter(
                    SoporteCategoria.id == uuid.UUID(str(datos["categoria_id"])),
                    SoporteCategoria.empresa_id == empresa_id,
                    SoporteCategoria.deleted_at.is_(None),
                )
                .first()
            )
            if not cat:
                raise ValueError("La categoría no existe")

        insumo = Insumo(empresa_id=empresa_id, **datos, created_by=usuario_email, updated_by=usuario_email)
        db.add(insumo)
        db.commit()
        db.refresh(insumo)

        # Si hay stock inicial, crear un movimiento de ingreso
        if stock_inicial > 0:
            movimiento = MovimientoInsumo(
                empresa_id=empresa_id,
                insumo_id=insumo.id,
                tipo="ingreso",
                cantidad=stock_inicial,
                motivo="Stock inicial al crear el insumo",
                fecha_movimiento=utc_now(),
                created_at=utc_now(),
                created_by=usuario_email,
                updated_by=usuario_email,
            )
            db.add(movimiento)
            db.commit()

        return insumo

    @staticmethod
    def obtener_insumo(db: Session, empresa_id: uuid.UUID, insumo_id: str) -> Optional[Insumo]:
        return (
            db.query(Insumo)
            .filter(Insumo.id == uuid.UUID(insumo_id), Insumo.empresa_id == empresa_id, Insumo.deleted_at.is_(None))
            .first()
        )

    @staticmethod
    def actualizar_insumo(
        db: Session, empresa_id: uuid.UUID, insumo_id: str, datos: Dict[str, Any], usuario_email: str
    ) -> Optional[Insumo]:
        insumo = (
            db.query(Insumo)
            .filter(Insumo.id == uuid.UUID(insumo_id), Insumo.empresa_id == empresa_id, Insumo.deleted_at.is_(None))
            .first()
        )
        if not insumo:
            return None
        datos = limpiar_datos(datos)
        for campo, valor in datos.items():
            if hasattr(insumo, campo) and campo not in ("id", "empresa_id"):
                setattr(insumo, campo, valor)
        insumo.updated_at = utc_now()
        insumo.updated_by = usuario_email
        db.commit()
        db.refresh(insumo)
        return insumo

    @staticmethod
    def eliminar_insumo(db: Session, empresa_id: uuid.UUID, insumo_id: str, usuario_email: str = None) -> bool:
        """Soft delete de insumo."""
        insumo = (
            db.query(Insumo)
            .filter(Insumo.id == uuid.UUID(insumo_id), Insumo.empresa_id == empresa_id, Insumo.deleted_at.is_(None))
            .first()
        )
        if not insumo:
            return False
        insumo.deleted_at = utc_now()
        insumo.deleted_by = usuario_email
        db.commit()
        return True

    @staticmethod
    def ajustar_stock_insumo(
        db: Session, empresa_id: uuid.UUID, insumo_id: str, cantidad: int, motivo: str, usuario_email: str
    ) -> MovimientoInsumo:
        """Ajusta el stock de un insumo creando un movimiento de ingreso o consumo."""
        tipo = "ingreso" if cantidad > 0 else "consumo"
        datos = {
            "insumo_id": insumo_id,
            "tipo": tipo,
            "cantidad": abs(cantidad),
            "motivo": motivo or "Ajuste manual de stock",
        }
        return SoporteService.registrar_movimiento_insumo(db, empresa_id, datos, usuario_email)

    # ─── Pedidos de Compra (Read + Presupuestos) ────────────────────

    @staticmethod
    def listar_pedidos(
        db: Session, empresa_id: uuid.UUID, estado_clave: str = None, ticket_id: str = None, solicitante_id: str = None
    ) -> List[PedidoCompra]:
        """Lista pedidos de compra con filtros opcionales."""
        from backend.modules.soporte.models import SoportePedidosEstado

        query = db.query(PedidoCompra).filter(PedidoCompra.deleted_at.is_(None), PedidoCompra.empresa_id == empresa_id)

        if estado_clave:
            query = query.join(SoportePedidosEstado, PedidoCompra.estado_id == SoportePedidosEstado.id).filter(
                SoportePedidosEstado.clave == estado_clave
            )
        if ticket_id:
            query = query.filter(PedidoCompra.ticket_id == uuid.UUID(ticket_id))
        if solicitante_id:
            query = query.filter(PedidoCompra.solicitante_id == uuid.UUID(solicitante_id))

        return query.order_by(PedidoCompra.created_at.desc()).all()

    @staticmethod
    def obtener_pedido(db: Session, empresa_id: uuid.UUID, pedido_id: str) -> Optional[PedidoCompra]:
        """Obtiene un pedido con presupuestos y aprobaciones."""
        return (
            db.query(PedidoCompra)
            .options(
                joinedload(PedidoCompra.estado_rel),
                joinedload(PedidoCompra.solicitante),
                joinedload(PedidoCompra.insumo_rel),
                joinedload(PedidoCompra.presupuestos),
                joinedload(PedidoCompra.aprobaciones).joinedload(PedidoAprobacion.aprobador),
            )
            .filter(
                PedidoCompra.id == uuid.UUID(pedido_id),
                PedidoCompra.empresa_id == empresa_id,
                PedidoCompra.deleted_at.is_(None),
            )
            .first()
        )

    @staticmethod
    def seleccionar_presupuesto(
        db: Session, empresa_id: uuid.UUID, pedido_id: str, presupuesto_id: str, usuario_email: str
    ) -> PedidoPresupuesto:
        """Marca un presupuesto como seleccionado, deseleccionando los demás del mismo pedido."""
        pid = pedido_id
        # Validar que el pedido pertenece a la empresa
        pedido = (
            db.query(PedidoCompra)
            .filter(PedidoCompra.id == pid, PedidoCompra.empresa_id == empresa_id, PedidoCompra.deleted_at.is_(None))
            .first()
        )
        if not pedido:
            raise ValueError("Pedido no encontrado")

        presupuesto = (
            db.query(PedidoPresupuesto)
            .filter(PedidoPresupuesto.id == uuid.UUID(presupuesto_id), PedidoPresupuesto.pedido_id == pid)
            .first()
        )
        if not presupuesto:
            raise ValueError("Presupuesto no encontrado")

        # Deseleccionar todos los del pedido primero
        db.query(PedidoPresupuesto).filter(PedidoPresupuesto.pedido_id == pid).update({"es_seleccionado": False})

        # Marcar el elegido
        presupuesto.es_seleccionado = True
        presupuesto.updated_by = usuario_email
        db.commit()
        db.refresh(presupuesto)
        logger.info(f"Presupuesto {presupuesto_id} seleccionado en pedido {pedido_id} por {usuario_email}")
        return presupuesto

    @staticmethod
    def cambiar_estado_pedido(
        db: Session,
        empresa_id: uuid.UUID,
        pedido_id: str,
        nueva_clave: str,
        usuario_email: str,
        datos: Dict[str, Any] = None,
    ) -> PedidoCompra:
        """
        Cambia el estado de un pedido de compra.
        Si pasa a 'pendiente_aprobacion', mueve el ticket vinculado a 'en_espera'.

        DEUDA TÉCNICA — Flujo de Pedidos de Compra:
        - No se notifica a administración/compras cuando pasa a pendiente_aprobacion.
        - Las transiciones de aprobación (aprobar/rechazar) usan el mismo permiso que el técnico.
          Debería haber un permiso separado (ej: soporte.aprobar_pedidos).
        - La tabla soporte_pedidos_aprobaciones existe pero no se usa. Solo se setea updated_by.
        - Un pedido puede enviarse a aprobación sin presupuestos adjuntos (definir si es obligatorio).
        - No hay email/webhook al aprobar o rechazar.
        - Las transiciones están hardcodeadas en TRANSICIONES_TECNICO. Migrar a tabla en DB.
        """
        from backend.modules.soporte.models import SoportePedidosEstado

        datos = datos or {}

        pedido = (
            db.query(PedidoCompra)
            .filter(
                PedidoCompra.id == uuid.UUID(pedido_id),
                PedidoCompra.empresa_id == empresa_id,
                PedidoCompra.deleted_at.is_(None),
            )
            .first()
        )
        if not pedido:
            raise ValueError("Pedido no encontrado")

        # DEUDA TÉCNICA: Las transiciones de pedidos están hardcodeadas en este dict.
        # Si se agrega un estado en soporte_pedidos_estados sin actualizar este dict,
        # el pedido queda bloqueado sin error claro (get() devuelve lista vacía).
        # Solución futura: crear tabla soporte_transiciones_pedidos con estado_origen_id,
        # estado_destino_id y rol_permitido, y consultar desde ahí.
        # Ver: docs/modulo/soporte-it/soporte-database-actual.dbml
        TRANSICIONES_TECNICO = {
            PedidoEstado.BORRADOR: [PedidoEstado.PENDIENTE_APROBACION, PedidoEstado.CANCELADO],
            PedidoEstado.RECHAZADO: [PedidoEstado.BORRADOR, PedidoEstado.CANCELADO],
            # Transiciones de administracion (futuro modulo, habilitadas para testing)
            PedidoEstado.PENDIENTE_APROBACION: [PedidoEstado.APROBADO, PedidoEstado.RECHAZADO, PedidoEstado.CANCELADO],
            PedidoEstado.APROBADO: [PedidoEstado.EN_COMPRA, PedidoEstado.CANCELADO],
            PedidoEstado.EN_COMPRA: [PedidoEstado.RECIBIDO, PedidoEstado.CANCELADO],
        }
        estado_actual = db.query(SoportePedidosEstado).filter(SoportePedidosEstado.id == pedido.estado_id).first()
        clave_actual = estado_actual.clave if estado_actual else "borrador"

        permitidas = TRANSICIONES_TECNICO.get(clave_actual, [])
        if nueva_clave not in permitidas:
            raise ValueError(f"No se puede pasar de '{clave_actual}' a '{nueva_clave}'")

        nuevo_estado = db.query(SoportePedidosEstado).filter(SoportePedidosEstado.clave == nueva_clave).first()
        if not nuevo_estado:
            raise ValueError(f"Estado '{nueva_clave}' no configurado")

        pedido.estado_id = nuevo_estado.id
        pedido.updated_by = usuario_email

        # Si pasa a pendiente_aprobacion, mover el ticket vinculado a 'en_espera'
        if nueva_clave == PedidoEstado.PENDIENTE_APROBACION and pedido.ticket_id:
            estado_espera = SoporteService.obtener_estado_ticket(db, TicketEstado.EN_ESPERA)
            if estado_espera:
                ticket = db.query(Ticket).filter(Ticket.id == pedido.ticket_id).first()
                if (
                    ticket
                    and ticket.estado_rel
                    and ticket.estado_rel.clave
                    not in (TicketEstado.RESUELTO, TicketEstado.CERRADO, TicketEstado.CANCELADO)
                ):
                    ticket.estado_id = estado_espera.id
                    ticket.updated_by = usuario_email
                    logger.info(f"Ticket #{ticket.numero} movido a 'en_espera' por pedido {pedido.numero}")

        # Si pasa a recibido y tiene insumo vinculado, registrar ingreso al stock
        if nueva_clave == PedidoEstado.RECIBIDO and pedido.insumo_id:
            cantidad = datos.get("cantidad_recibida", pedido.cantidad_solicitada) or pedido.cantidad_solicitada
            pedido.cantidad_recibida = cantidad
            pedido.fecha_recepcion = utc_now()

            if cantidad > 0:
                movimiento = MovimientoInsumo(
                    empresa_id=empresa_id,
                    insumo_id=pedido.insumo_id,
                    tipo="ingreso",
                    cantidad=cantidad,
                    pedido_compra_id=pedido.id,
                    motivo=f"Recepcion pedido {pedido.numero}",
                    fecha_movimiento=utc_now(),
                    created_by=usuario_email,
                )
                db.add(movimiento)
                logger.info(f"Ingreso de {cantidad}x insumo {pedido.insumo_id} por pedido {pedido.numero}")

        db.commit()
        db.refresh(pedido)
        logger.info(f"Pedido {pedido.numero} cambió de '{clave_actual}' a '{nueva_clave}' por {usuario_email}")
        return pedido

    @staticmethod
    def agregar_presupuesto(
        db: Session,
        empresa_id: uuid.UUID,
        pedido_id: str,
        datos: Dict[str, Any],
        url_archivo: str = None,
        usuario_email: str = None,
    ) -> PedidoPresupuesto:
        """Agrega un presupuesto a un pedido de compra."""
        pedido = (
            db.query(PedidoCompra)
            .filter(
                PedidoCompra.id == uuid.UUID(pedido_id),
                PedidoCompra.empresa_id == empresa_id,
                PedidoCompra.deleted_at.is_(None),
            )
            .first()
        )
        if not pedido:
            raise ValueError("Pedido no encontrado")

        presupuesto = PedidoPresupuesto(
            empresa_id=empresa_id,
            pedido_id=pedido.id,
            proveedor=datos.get("proveedor"),
            articulo_descripcion=datos.get("articulo_descripcion"),
            monto=datos.get("monto"),
            es_obligatorio=datos.get("es_obligatorio", True),
            url_archivo=url_archivo,
            created_by=usuario_email,
        )
        db.add(presupuesto)
        db.commit()
        db.refresh(presupuesto)
        logger.info(f"Presupuesto agregado al pedido {pedido.numero} por {usuario_email}")
        return presupuesto

    @staticmethod
    async def subir_archivo_soporte(
        db: Session,
        ticket_id: str,
        file: UploadFile,
        usuario_email: str,
        empresa_id: uuid.UUID,
        empresa_cuit: str,
        categoria: str = "general",
    ) -> Dict:
        """
        Sube un archivo y registra la evidencia en la base de datos v28.0.

        Estructura de carpetas:
        - Tickets Genéricos: soporte-{CUIT}/tickets/generales/{ticket_id}/
        - Reparaciones: soporte-{CUIT}/tickets/reparaciones/{entrada|proceso|salida}/{ticket_id}/
        - Mantenimientos: soporte-{CUIT}/tickets/mantenimientos/{entrada|proceso|salida}/{ticket_id}/
        - Altas/Bajas: soporte-{CUIT}/tickets/altas-bajas/{evidencias|acuerdos}/{ticket_id}/

        Args:
            categoria: Subcategoría del archivo:
                - Para reparaciones/mantenimientos: "entrada", "proceso", "salida", "estado_equipo"
                - Para altas/bajas: "evidencias", "acuerdos", "acuerdo_firmado"
                - Para genéricos: "general" (default)
        """
        from backend.core.storage import cloud_storage

        content = await file.read()
        ext = Path(file.filename).suffix.lower()

        # Obtener el ticket para determinar su tipo
        ticket = db.query(Ticket).filter(Ticket.id == uuid.UUID(ticket_id), Ticket.empresa_id == empresa_id).first()

        if not ticket:
            raise ValueError("Ticket no encontrado")

        # Determinar tipo de ticket
        tipo_ticket = ticket.tipo_ticket  # 'generico', 'reparacion', 'alta_baja', 'mantenimiento'

        # Construir la carpeta según el tipo de ticket y categoría
        base = f"soporte-{empresa_cuit}/tickets"

        # Normalizar categoría según el tipo de ticket
        if tipo_ticket == TipoTicket.REPARACION:
            # Mapear categorías antiguas a nuevas
            if categoria == "estado_equipo":
                categoria = "entrada"
            elif categoria not in ("entrada", "proceso", "salida"):
                categoria = "proceso"  # Default para reparaciones
            folder = f"{base}/reparaciones/{categoria}/{ticket_id}"

        elif tipo_ticket == TipoTicket.MANTENIMIENTO:
            # Mapear categorías antiguas a nuevas
            if categoria == "estado_equipo":
                categoria = "entrada"
            elif categoria not in ("entrada", "proceso", "salida"):
                categoria = "proceso"  # Default para mantenimientos
            folder = f"{base}/mantenimientos/{categoria}/{ticket_id}"

        elif tipo_ticket == TipoTicket.ALTA_BAJA:
            # Para altas/bajas: evidencias o acuerdos
            if categoria in ("acuerdos", "acuerdo_firmado"):
                folder = f"{base}/altas-bajas/acuerdos/{ticket_id}"
                categoria = "acuerdos"  # Normalizar
            else:
                folder = f"{base}/altas-bajas/evidencias/{ticket_id}"
                categoria = "evidencias"  # Normalizar

        else:
            # Tickets genéricos
            folder = f"{base}/generales/{ticket_id}"
            categoria = "general"

        key = cloud_storage.build_key(folder, content, ext=ext)
        cloud_storage.upload(key, content, file.content_type or "application/octet-stream")

        evidencia = SoporteEvidencia(
            empresa_id=empresa_id,
            url=key,  # Guardar solo la key, no la URL completa
            tipo=file.content_type or "archivo",
            categoria=categoria,
            ticket_id=uuid.UUID(ticket_id),
            created_by=usuario_email,
        )
        db.add(evidencia)
        db.commit()
        db.refresh(evidencia)

        return {"url": cloud_storage.get_url(key), "key": key, "id": str(evidencia.id), "categoria": categoria}

    @staticmethod
    async def subir_presupuesto_pedido(db: Session, pedido_id: str, file: UploadFile, empresa_cuit: str) -> str:
        """
        Sube un archivo de presupuesto para un pedido de compra.

        Estructura: soporte-{CUIT}/pedidos/presupuestos/{pedido_id}/

        Args:
            pedido_id: UUID del pedido de compra
            file: Archivo a subir
            empresa_cuit: CUIT de la empresa

        Returns:
            Key del archivo subido
        """
        from backend.core.storage import cloud_storage

        content = await file.read()
        ext = Path(file.filename).suffix.lower()

        folder = f"soporte-{empresa_cuit}/pedidos/presupuestos/{pedido_id}"
        key = cloud_storage.build_key(folder, content, ext=ext, prefix="presupuesto")
        cloud_storage.upload(key, content, file.content_type or "application/octet-stream")

        return key

    @staticmethod
    async def subir_foto_historial_activo(
        db: Session, activo_id: str, file: UploadFile, empresa_id: uuid.UUID, empresa_cuit: str, usuario_email: str
    ) -> Dict:
        """
        Sube una foto al historial de un activo.

        Estructura: soporte-{CUIT}/activos/historial/{activo_id}/

        Args:
            activo_id: UUID del activo
            file: Archivo de imagen a subir
            empresa_id: UUID de la empresa
            empresa_cuit: CUIT de la empresa
            usuario_email: Email del usuario que sube la foto

        Returns:
            Dict con url, key e id del registro de historial
        """
        from backend.core.storage import cloud_storage

        # Validar que el activo existe
        activo = (
            db.query(Activo)
            .filter(Activo.id == uuid.UUID(activo_id), Activo.empresa_id == empresa_id, Activo.deleted_at.is_(None))
            .first()
        )

        if not activo:
            raise ValueError("Activo no encontrado")

        content = await file.read()
        ext = Path(file.filename).suffix.lower()

        folder = f"soporte-{empresa_cuit}/activos/historial/{activo_id}"
        key = cloud_storage.build_key(folder, content, ext=ext)
        cloud_storage.upload(key, content, file.content_type or "application/octet-stream")

        # Registrar en el historial del activo
        historial = HistorialActivo(
            empresa_id=empresa_id,
            activo_id=activo.id,
            tipo_evento=HistorialTipoEvento.FOTO_AGREGADA,
            notas_adicionales=f"Foto agregada: {file.filename} | key: {key}",
            created_by=usuario_email,
        )
        db.add(historial)
        db.commit()
        db.refresh(historial)

        return {"url": cloud_storage.get_url(key), "key": key, "id": str(historial.id)}

    # ─── Métodos movidos desde routers (lógica de negocio) ──────────

    @staticmethod
    def validar_ticket_no_cerrado(db: Session, empresa_id: uuid.UUID, ticket_id: str):
        """Valida que un ticket no esté en estado resuelto/cerrado/cancelado."""
        ticket = db.query(Ticket).filter(Ticket.id == uuid.UUID(ticket_id), Ticket.empresa_id == empresa_id).first()
        if not ticket:
            raise ValueError("Ticket no encontrado")
        estado = db.query(SoporteTicketsEstado).filter(SoporteTicketsEstado.id == ticket.estado_id).first()
        if estado and estado.clave in (TicketEstado.RESUELTO, TicketEstado.CERRADO, TicketEstado.CANCELADO):
            raise ValueError("No se puede modificar un ticket resuelto/cerrado/cancelado")
        return ticket

    @staticmethod
    def eliminar_evidencia(db: Session, empresa_id: uuid.UUID, ticket_id: str, evidencia_id: str) -> bool:
        """
        Soft delete de una evidencia de un ticket.
        También elimina el archivo físico del storage.
        """
        from backend.core.storage import cloud_storage

        SoporteService.validar_ticket_no_cerrado(db, empresa_id, ticket_id)

        evidencia = (
            db.query(SoporteEvidencia)
            .filter(
                SoporteEvidencia.id == uuid.UUID(evidencia_id),
                SoporteEvidencia.ticket_id == ticket_id,
                SoporteEvidencia.empresa_id == empresa_id,
                SoporteEvidencia.deleted_at.is_(None),
            )
            .first()
        )

        if not evidencia:
            raise ValueError("Evidencia no encontrada")

        # Eliminar archivo físico del storage
        if evidencia.url:
            try:
                cloud_storage.delete(evidencia.url)
                logger.info(f"Archivo eliminado del storage: {evidencia.url}")
            except Exception as e:
                logger.warning(f"No se pudo eliminar el archivo del storage: {evidencia.url}. Error: {e}")
                # Continuar con el soft delete aunque falle la eliminación física

        # Soft delete en la base de datos
        evidencia.deleted_at = utc_now()
        db.commit()
        return True

    @staticmethod
    def crear_matriz_estado(
        db: Session, empresa_id: uuid.UUID, datos: Dict[str, Any], usuario_email: str
    ) -> SoporteMatrizEstado:
        """Crea una nueva matriz de estado físico para un equipo."""
        matriz = SoporteMatrizEstado(
            id=uuid.uuid4(),
            empresa_id=empresa_id,
            pantalla=datos.get("pantalla"),
            teclado=datos.get("teclado"),
            bateria=datos.get("bateria"),
            carcasa_superior=datos.get("carcasa_superior"),
            carcasa_inferior=datos.get("carcasa_inferior"),
            touchpad=datos.get("touchpad"),
            puertos=datos.get("puertos"),
            cargador=datos.get("cargador"),
            created_at=utc_now(),
            created_by=usuario_email,
        )
        db.add(matriz)
        db.commit()
        db.refresh(matriz)
        return matriz

    @staticmethod
    def listar_sistemas_disponibles(db: Session, empresa_id: uuid.UUID) -> List[Dict]:
        """Devuelve el catálogo de sistemas habilitables en un alta."""
        query = db.query(SoporteSistemaDisponible).filter(
            SoporteSistemaDisponible.tipo == "alta",
            SoporteSistemaDisponible.activo == True,
            SoporteSistemaDisponible.empresa_id == empresa_id,
        )
        sistemas = query.order_by(SoporteSistemaDisponible.orden).all()
        return [{"clave": s.clave, "label": s.label, "orden": s.orden} for s in sistemas]

    @staticmethod
    def buscar_activos_disponibles(db: Session, empresa_id: uuid.UUID, q: str = "", todos: bool = False) -> List[Dict]:
        """Busca equipos disponibles para asignar."""
        query = (
            db.query(Activo)
            .options(joinedload(Activo.tipo_rel), joinedload(Activo.marca_rel), joinedload(Activo.matriz_estado))
            .filter(Activo.deleted_at.is_(None), Activo.empresa_id == empresa_id)
        )
        if not todos:
            query = query.filter(Activo.estado == "disponible")

        if q:
            search_term = f"%{q}%"
            query = query.filter(
                or_(
                    Activo.nombre.ilike(search_term),
                    Activo.numero_serie.ilike(search_term),
                    Activo.numero_inventario.ilike(search_term),
                    Activo.modelo.ilike(search_term),
                )
            )

        activos = query.limit(50).all()

        resultado = []
        for activo in activos:
            tipo_nombre = activo.tipo_rel.nombre if activo.tipo_rel else "N/A"
            marca_nombre = activo.marca_rel.nombre if activo.marca_rel else "N/A"
            item = {
                "id": str(activo.id),
                "nombre": activo.nombre,
                "tipo": tipo_nombre,
                "marca": marca_nombre,
                "modelo": activo.modelo or "",
                "numero_serie": activo.numero_serie or "",
                "numero_inventario": activo.numero_inventario or "",
                "display": f"{activo.nombre} - {tipo_nombre} {marca_nombre} ({activo.numero_serie or 'S/N'})",
                "matriz_estado": None,
            }
            if activo.matriz_estado:
                item["matriz_estado"] = {
                    "pantalla": activo.matriz_estado.pantalla,
                    "teclado": activo.matriz_estado.teclado,
                    "bateria": activo.matriz_estado.bateria,
                    "carcasa_superior": activo.matriz_estado.carcasa_superior,
                    "carcasa_inferior": activo.matriz_estado.carcasa_inferior,
                    "touchpad": activo.matriz_estado.touchpad,
                    "puertos": activo.matriz_estado.puertos,
                    "cargador": activo.matriz_estado.cargador,
                }
            resultado.append(item)

        return resultado

    @staticmethod
    def listar_usuarios_asignacion(db: Session, empresa_id: uuid.UUID) -> Dict:
        """Lista empleados activos del departamento de Soporte para asignación de tickets."""
        # Buscar el departamento de Soporte (con búsqueda flexible)
        dept_soporte = (
            db.query(Departamento)
            .filter(
                Departamento.empresa_id == empresa_id,
                Departamento.deleted_at.is_(None),
                or_(
                    func.lower(Departamento.nombre).like("%soporte%"),
                    func.lower(Departamento.nombre).like("%it%"),
                    func.lower(Departamento.nombre).like("%sistemas%"),
                    func.lower(Departamento.nombre).like("%tecnolog%"),
                ),
            )
            .first()
        )

        # Si no se encuentra el departamento, retornar lista vacía por seguridad
        if not dept_soporte:
            logger.warning(
                f"⚠️ No se encontró departamento de Soporte para empresa {empresa_id}. No se mostrarán usuarios para asignación."
            )
            return {"usuarios": [], "mensaje": "No se encontró el departamento de Soporte. Contacte al administrador."}

        logger.info(f"✅ Departamento de Soporte encontrado: {dept_soporte.nombre} (ID: {dept_soporte.id})")

        # Filtrar empleados del departamento de Soporte
        empleados = (
            db.query(Empleado)
            .filter(
                Empleado.activo == True,
                Empleado.deleted_at.is_(None),
                Empleado.empresa_id == empresa_id,
                Empleado.departamento_id == dept_soporte.id,
            )
            .order_by(Empleado.apellido, Empleado.nombre)
            .all()
        )

        logger.info(f"📋 Empleados de Soporte encontrados: {len(empleados)}")

        return {"usuarios": [{"id": str(e.id), "nombre": f"{e.apellido}, {e.nombre}"} for e in empleados]}

    @staticmethod
    def listar_consumos_formateados(
        db: Session, empresa_id: uuid.UUID, insumo_id: Optional[str] = None, activo_id: Optional[str] = None
    ) -> List[Dict]:
        """Lista movimientos de insumos formateados para la UI."""
        query = db.query(MovimientoInsumo).options(joinedload(MovimientoInsumo.insumo))
        query = query.filter(MovimientoInsumo.empresa_id == empresa_id)
        if insumo_id:
            query = query.filter(MovimientoInsumo.insumo_id == uuid.UUID(insumo_id))
        if activo_id:
            query = query.filter(MovimientoInsumo.activo_id == uuid.UUID(activo_id))
        items = query.order_by(MovimientoInsumo.created_at.desc()).all()
        resultado = []
        for m in items:
            resultado.append(
                {
                    "id": str(m.id),
                    "fecha_consumo": m.fecha_movimiento.isoformat() if m.fecha_movimiento else None,
                    "insumo_nombre": m.insumo.nombre if m.insumo else None,
                    "insumo_id": str(m.insumo_id) if m.insumo_id else None,
                    "equipo_nombre": m.activo.nombre if m.activo else None,
                    "activo_id": str(m.activo_id) if m.activo_id else None,
                    "empleado_nombre": f"{m.empleado.apellido}, {m.empleado.nombre}" if m.empleado else None,
                    "empleado_id": str(m.empleado_id) if m.empleado_id else None,
                    "cantidad": m.cantidad,
                    "tipo": m.tipo,
                    "motivo": m.motivo,
                    "usuario_nombre": m.empleado_asignador.empleado_nombre_completo
                    if m.empleado_asignador
                    else (m.created_by or None),
                }
            )
        return resultado
