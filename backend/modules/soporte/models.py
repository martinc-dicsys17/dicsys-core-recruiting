"""
Modelos para el módulo de Soporte Técnico (v28.0).

Convenciones:
- TODOS los usuarios son empleados → nomina_empleados
- Eliminación de campos JSONB → Tablas relacionales
- Auditoría integral con created_by/updated_by (Email)
"""

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import backref, relationship

from backend.core.utils import utc_now
from backend.database import Base
from backend.modules.nomina.models import Empleado

# ═══════════════════════════════════════════════════════════════
# TABLAS MAESTRAS DE CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════════


class SoporteTicketsEstado(Base):
    """Estados para soporte_tickets (>5 estados según norma)."""

    __tablename__ = "soporte_tickets_estados"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre = Column(String(100), nullable=False)
    clave = Column(String(100), nullable=False, unique=True)
    color = Column(String(50), nullable=True)

    created_at = Column(DateTime, nullable=False, default=utc_now)
    created_by = Column(String(255), nullable=True)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)


class SoportePedidosEstado(Base):
    """Estados para soporte_pedidos_compra."""

    __tablename__ = "soporte_pedidos_estados"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nombre = Column(String(100), nullable=False)
    clave = Column(String(100), nullable=False, unique=True)
    color = Column(String(50), nullable=True)

    created_at = Column(DateTime, nullable=False, default=utc_now)
    created_by = Column(String(255), nullable=True)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)


class SoporteActivosMarca(Base):
    """Marcas maestras: Lenovo, Dell, HP, etc."""

    __tablename__ = "soporte_activos_marcas"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    nombre = Column(String(100), nullable=False)

    created_at = Column(DateTime, nullable=False, default=utc_now)
    created_by = Column(String(255), nullable=True)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)

    __table_args__ = (UniqueConstraint("empresa_id", "nombre", name="uq_marca_empresa_nombre"),)


class ActivoTipo(Base):
    """Tipos de equipos (notebook, monitor, etc.)."""

    __tablename__ = "soporte_activos_tipos"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    nombre = Column(String(100), nullable=False)
    clave = Column(String(100), nullable=False)
    requiere_especificaciones = Column(Boolean, nullable=False, default=False)
    frecuencia_mantenimiento_meses = Column(Integer, default=0)
    activo = Column(Boolean, nullable=False, default=True)

    deleted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    created_by = Column(String(255), nullable=True)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)

    __table_args__ = (
        UniqueConstraint("empresa_id", "nombre", name="uq_tipo_activo_empresa_nombre"),
        UniqueConstraint("empresa_id", "clave", name="uq_tipo_activo_empresa_clave"),
    )


# ═══════════════════════════════════════════════════════════════
# SISTEMAS DISPONIBLES PARA ALTA/BAJA
# ═══════════════════════════════════════════════════════════════


class SoporteSistemaDisponible(Base):
    """Catálogo de sistemas que se pueden habilitar/deshabilitar en alta/baja de colaborador."""

    __tablename__ = "soporte_sistemas_disponibles"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    clave = Column(String(100), nullable=False)
    label = Column(String(255), nullable=False)
    orden = Column(Integer, nullable=False, default=0)
    # 'alta' o 'baja' — indica si es un item de alta o de baja
    tipo = Column(String(10), nullable=False, default="alta")
    # Para items de baja: clave del sistema de alta al que corresponde
    clave_alta_ref = Column(String(100), nullable=True)
    activo = Column(Boolean, nullable=False, default=True)

    created_at = Column(DateTime, nullable=False, default=utc_now)
    created_by = Column(String(255), nullable=True)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)

    __table_args__ = (UniqueConstraint("empresa_id", "clave", name="uq_sistema_disponible_empresa_clave"),)


# ═══════════════════════════════════════════════════════════════
# CATEGORÍAS Y SUBCATEGORÍAS
# ═══════════════════════════════════════════════════════════════


class SoporteCategoria(Base):
    """Categorías principales de tickets (Padre)."""

    __tablename__ = "soporte_categorias"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    nombre_display = Column(String(100), nullable=False)
    nombre_normalizado = Column(String(100), nullable=False)
    tipo_ticket_asociado = Column(String(20), nullable=False, default="generico")
    departamento_id = Column(UUID(as_uuid=True), ForeignKey("nomina_departamentos.id"), nullable=True)

    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    created_by = Column(String(255), nullable=True)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)


class SoporteSubcategoria(Base):
    """Subcategorías vinculadas a una categoría principal."""

    __tablename__ = "soporte_subcategorias"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    categoria_id = Column(UUID(as_uuid=True), ForeignKey("soporte_categorias.id"), nullable=False)
    nombre_display = Column(String(100), nullable=False)
    nombre_normalizado = Column(String(100), nullable=False)
    tipo_ticket_asociado = Column(String(20), nullable=False, default="generico")
    departamento_id = Column(UUID(as_uuid=True), ForeignKey("nomina_departamentos.id"), nullable=True)

    categoria = relationship(SoporteCategoria, backref="subcategorias")

    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    created_by = Column(String(255), nullable=True)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)


# ═══════════════════════════════════════════════════════════════
# MÓDULO DE SOPORTE - MATRIZ DE ESTADO
# ═══════════════════════════════════════════════════════════════


class SoporteMatrizEstado(Base):
    """Matriz de estado físico descriptiva (Varchar)."""

    __tablename__ = "soporte_matriz_estado"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    pantalla = Column(String(50))
    teclado = Column(String(50))
    bateria = Column(String(50))
    carcasa_superior = Column(String(50))
    carcasa_inferior = Column(String(50))
    touchpad = Column(String(50))
    puertos = Column(String(50))
    cargador = Column(String(50))

    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    created_by = Column(String(255), nullable=True)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)


# ═══════════════════════════════════════════════════════════════
# MÓDULO DE SOPORTE - TICKETS (Joined Table Inheritance)
# ═══════════════════════════════════════════════════════════════


class Ticket(Base):
    """Modelo base de Ticket de soporte técnico."""

    __tablename__ = "soporte_tickets"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    numero = Column(Integer, nullable=False)
    tipo_ticket = Column(String(20), nullable=False, default="generico")
    titulo = Column(String(200), nullable=False)
    descripcion = Column(Text, nullable=True)
    estado_id = Column(UUID(as_uuid=True), ForeignKey("soporte_tickets_estados.id"), nullable=False)
    prioridad = Column(String(50), nullable=False, default="media")
    subcategoria_id = Column(UUID(as_uuid=True), ForeignKey("soporte_subcategorias.id"), nullable=False)
    es_falla = Column(Boolean, nullable=False, default=False)

    # === Usuarios del sistema ===
    solicitante_id = Column(UUID(as_uuid=True), ForeignKey("nomina_empleados.id"), nullable=False)
    asignado_id = Column(UUID(as_uuid=True), ForeignKey("nomina_empleados.id"), nullable=True)

    resolucion = Column(Text, nullable=True)
    fecha_inicio = Column(DateTime, nullable=True)
    fecha_resolucion = Column(DateTime, nullable=True)
    fecha_cierre = Column(DateTime, nullable=True)

    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    created_by = Column(String(255), nullable=True)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)

    solicitante = relationship(Empleado, foreign_keys=[solicitante_id], backref="tickets_creados")
    asignado = relationship(Empleado, foreign_keys=[asignado_id], backref="tickets_asignados")
    subcategoria = relationship(SoporteSubcategoria, backref="tickets")
    estado_rel = relationship(SoporteTicketsEstado)

    __table_args__ = (UniqueConstraint("empresa_id", "numero", name="uq_ticket_empresa_numero"),)
    __mapper_args__ = {"polymorphic_on": tipo_ticket, "with_polymorphic": "*"}


class TicketGeneral(Ticket):
    __mapper_args__ = {"polymorphic_identity": "generico"}


class TicketReparacion(Ticket):
    """Ticket de reparación técnica.

    DEUDA TÉCNICA — Flujo de cierre:
    - Al resolver, matriz_salida_id se copia desde matriz_entrada_id (snapshot por defecto).
      No hay UI para capturar el estado físico real al salir del taller.
    - costo_total_final queda en 0. No se integra con insumos consumidos ni costo del pedido.
    - solucion no se usa. Al resolver se guarda solo 'resolucion' genérica en la tabla base.
    - El botón "REPARAR" del dashboard registra reparaciones por fuera del sistema de tickets (solo historial).
    """

    __tablename__ = "soporte_tickets_reparacion"
    id = Column(UUID(as_uuid=True), ForeignKey("soporte_tickets.id", ondelete="CASCADE"), primary_key=True)
    activo_id = Column(UUID(as_uuid=True), ForeignKey("soporte_activos.id"), nullable=False)
    diagnostico = Column(Text)
    solucion = Column(Text)
    costo_estimado = Column(Numeric(10, 2), default=0.0)
    costo_total_final = Column(Numeric(10, 2), default=0.0)
    matriz_entrada_id = Column(UUID(as_uuid=True), ForeignKey("soporte_matriz_estado.id"))
    matriz_salida_id = Column(UUID(as_uuid=True), ForeignKey("soporte_matriz_estado.id"))

    activo = relationship("Activo", foreign_keys=[activo_id])
    matriz_entrada = relationship(SoporteMatrizEstado, foreign_keys=[matriz_entrada_id])
    matriz_salida = relationship(SoporteMatrizEstado, foreign_keys=[matriz_salida_id])

    __mapper_args__ = {"polymorphic_identity": "reparacion"}


class TicketAltaBaja(Ticket):
    __tablename__ = "soporte_tickets_alta_baja"
    id = Column(UUID(as_uuid=True), ForeignKey("soporte_tickets.id", ondelete="CASCADE"), primary_key=True)
    colaborador_id = Column(UUID(as_uuid=True), ForeignKey("nomina_empleados.id"), nullable=False)
    tipo_operacion = Column(String(10), nullable=False)
    entrega_kit_bienvenida = Column(Boolean, default=False)
    activo_id = Column(UUID(as_uuid=True), ForeignKey("soporte_activos.id"), nullable=True)
    matriz_estado_id = Column(UUID(as_uuid=True), ForeignKey("soporte_matriz_estado.id"))
    # Campos del proceso de alta IT
    modalidad_trabajo = Column(String(30), nullable=True)  # Presencial, Remoto, Híbrido
    requiere_nextcloud = Column(Boolean, default=False)
    listas_correo = Column(Text, nullable=True)
    necesita_computadora = Column(Boolean, default=False)
    gama_computadora = Column(String(50), nullable=True)  # Básica, Media, Alta gama
    cliente_servicio = Column(String(200), nullable=True)  # Autocompleta desde nómina

    colaborador = relationship(Empleado, foreign_keys=[colaborador_id])
    activo = relationship("Activo", foreign_keys=[activo_id])
    matriz_estado = relationship(SoporteMatrizEstado)

    __mapper_args__ = {"polymorphic_identity": "alta_baja"}


class TicketMantenimiento(Ticket):
    __tablename__ = "soporte_tickets_mantenimiento"
    id = Column(UUID(as_uuid=True), ForeignKey("soporte_tickets.id", ondelete="CASCADE"), primary_key=True)
    activo_id = Column(UUID(as_uuid=True), ForeignKey("soporte_activos.id"), nullable=False)
    mantenimiento_id = Column(
        UUID(as_uuid=True), ForeignKey("soporte_mantenimiento_evento.id"), nullable=True
    )  # Alineado (line 596)
    detalle_tecnico = Column(Text)
    is_preventivo = Column(Boolean, default=True)  # Alineado (line 599)
    fecha_programada = Column(DateTime)
    se_realizo = Column(Boolean, default=False)

    activo = relationship("Activo", foreign_keys=[activo_id])
    __mapper_args__ = {"polymorphic_identity": "mantenimiento"}


# ═══════════════════════════════════════════════════════════════
# ACTIVOS IT
# ═══════════════════════════════════════════════════════════════


class Activo(Base):
    __tablename__ = "soporte_activos"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    clase_activo = Column(String(30), nullable=False, default="sin_especificaciones")
    nombre = Column(String(200), nullable=False)
    tipo_id = Column(UUID(as_uuid=True), ForeignKey("soporte_activos_tipos.id"), nullable=False)
    marca_id = Column(UUID(as_uuid=True), ForeignKey("soporte_activos_marcas.id"))
    modelo = Column(String(100))
    numero_serie = Column(String(100))
    numero_inventario = Column(String(50))
    estado = Column(String(50), default="disponible")
    asignado_id = Column(UUID(as_uuid=True), ForeignKey("nomina_empleados.id"))
    fecha_asignacion = Column(DateTime)
    fecha_compra = Column(DateTime)
    fecha_fin_garantia = Column(DateTime)
    notas = Column(Text)
    fecha_ultimo_mantenimiento = Column(DateTime)
    matriz_estado_id = Column(UUID(as_uuid=True), ForeignKey("soporte_matriz_estado.id"))

    created_at = Column(DateTime, nullable=False, default=utc_now)
    created_by = Column(String(255))
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255))
    deleted_at = Column(DateTime, nullable=True, default=None)

    tipo_rel = relationship(ActivoTipo)
    marca_rel = relationship(SoporteActivosMarca)
    asignado_rel = relationship(Empleado, foreign_keys=[asignado_id])
    matriz_estado = relationship(SoporteMatrizEstado)

    @property
    def tipo_display(self):
        return self.tipo_rel.nombre if self.tipo_rel else "General"

    @property
    def marca_nombre(self):
        return self.marca_rel.nombre if self.marca_rel else "Genérica"

    __table_args__ = (
        UniqueConstraint("empresa_id", "numero_serie", name="uq_activo_empresa_serie"),
        UniqueConstraint("empresa_id", "numero_inventario", name="uq_activo_empresa_inventario"),
    )

    __mapper_args__ = {"polymorphic_on": clase_activo, "with_polymorphic": "*"}


class ActivoConEspecificaciones(Activo):
    __tablename__ = "soporte_activos_especificaciones"
    id = Column(UUID(as_uuid=True), ForeignKey("soporte_activos.id", ondelete="CASCADE"), primary_key=True)
    procesador = Column(String(150))
    memoria = Column(String(50))
    disco_principal = Column(String(100))
    disco_secundario = Column(String(100))
    mac_ethernet = Column(String(100))
    mac_wifi = Column(String(100))
    __mapper_args__ = {"polymorphic_identity": "con_especificaciones"}


class ActivoSinEspecificaciones(Activo):
    __mapper_args__ = {"polymorphic_identity": "sin_especificaciones"}


# ═══════════════════════════════════════════════════════════════
# INSUMOS Y AUDITORÍA
# ═══════════════════════════════════════════════════════════════


class Insumo(Base):
    __tablename__ = "soporte_insumos"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    nombre = Column(String(150), nullable=False)
    descripcion = Column(String(255))
    stock_actual = Column(Integer, default=0)  # Alineado (line 282)
    stock_minimo = Column(Integer, default=0)
    unidad_medida = Column(String(20), default="unidades")  # Alineado (line 284)
    categoria_id = Column(UUID(as_uuid=True), ForeignKey("soporte_categorias.id"))  # Alineado (line 285)

    deleted_at = Column(DateTime, nullable=True, default=None)
    deleted_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=utc_now)
    created_by = Column(String(255))
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255))


class SoporteTicketInsumo(Base):
    """Consumo de insumos vinculado a un ticket."""

    __tablename__ = "soporte_tickets_insumos"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("soporte_tickets.id", ondelete="CASCADE"), nullable=False)
    insumo_id = Column(UUID(as_uuid=True), ForeignKey("soporte_insumos.id"), nullable=False)
    cantidad = Column(Integer, default=1)
    costo_unitario = Column(Numeric(10, 2), default=0.0)
    generar_pedido_compra = Column(Boolean, default=False)
    movimiento_insumo_id = Column(UUID(as_uuid=True), ForeignKey("soporte_movimientos_insumos.id"))
    pedido_compra_id = Column(UUID(as_uuid=True), ForeignKey("soporte_pedidos_compra.id"))

    created_at = Column(DateTime, default=utc_now)
    created_by = Column(String(255))
    updated_by = Column(String(255))

    ticket = relationship(Ticket, backref="insumos_detalle")
    insumo = relationship(Insumo)


class MovimientoInsumo(Base):
    __tablename__ = "soporte_movimientos_insumos"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    insumo_id = Column(UUID(as_uuid=True), ForeignKey("soporte_insumos.id"), nullable=False)
    tipo = Column(String(20), nullable=False)  # ingreso, consumo, devolucion, ajuste
    cantidad = Column(Integer, nullable=False)
    activo_id = Column(UUID(as_uuid=True), ForeignKey("soporte_activos.id"))
    empleado_id = Column(UUID(as_uuid=True), ForeignKey("nomina_empleados.id"))
    empleado_asignador_id = Column(UUID(as_uuid=True), ForeignKey("nomina_empleados.id"))
    pedido_compra_id = Column(UUID(as_uuid=True), ForeignKey("soporte_pedidos_compra.id"))
    motivo = Column(String(255))
    fecha_movimiento = Column(DateTime, default=utc_now)

    created_at = Column(DateTime, default=utc_now)
    created_by = Column(String(255))
    updated_by = Column(String(255))

    insumo = relationship("Insumo", foreign_keys=[insumo_id])
    activo = relationship("Activo", foreign_keys=[activo_id])
    empleado = relationship(Empleado, foreign_keys=[empleado_id])
    empleado_asignador = relationship(Empleado, foreign_keys=[empleado_asignador_id])


class SoporteEvidencia(Base):
    """Centralización de evidencias técnicas."""

    __tablename__ = "soporte_evidencias"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    url = Column(String(500), nullable=False)
    tipo = Column(String(50), nullable=False)
    categoria = Column(String(50), nullable=False, default="general")  # general, acuerdo_firmado, estado_equipo
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("soporte_tickets.id"))
    activo_id = Column(UUID(as_uuid=True), ForeignKey("soporte_activos.id"))
    historial_id = Column(UUID(as_uuid=True), ForeignKey("soporte_historial_activo.id"))

    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    created_by = Column(String(255))
    updated_by = Column(String(255))


# ═══════════════════════════════════════════════════════════════
# COMPRAS (v24.0+)
# ═══════════════════════════════════════════════════════════════


class PedidoCompra(Base):
    __tablename__ = "soporte_pedidos_compra"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    numero = Column(String(50), nullable=False)
    tipo_pedido = Column(String(20), default="insumo")  # insumo, servicio
    descripcion = Column(Text)
    monto_estimado = Column(Numeric(12, 2), default=0.0)
    monto_final = Column(Numeric(12, 2), default=0.0)
    estado_id = Column(UUID(as_uuid=True), ForeignKey("soporte_pedidos_estados.id"))
    fecha_solicitud = Column(DateTime, default=utc_now)
    fecha_recepcion = Column(DateTime, nullable=True)
    solicitante_id = Column(UUID(as_uuid=True), ForeignKey("nomina_empleados.id"))
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("soporte_tickets.id"))
    insumo_id = Column(UUID(as_uuid=True), ForeignKey("soporte_insumos.id"), nullable=True)
    cantidad_solicitada = Column(Integer, default=0)
    cantidad_recibida = Column(Integer, default=0)
    notas = Column(Text)
    deleted_at = Column(DateTime, nullable=True)
    requiere_doble_aprobacion = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=utc_now)
    created_by = Column(String(255))
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255))

    estado_rel = relationship("SoportePedidosEstado")
    solicitante = relationship(Empleado, foreign_keys=[solicitante_id])
    insumo_rel = relationship("Insumo", foreign_keys=[insumo_id])
    presupuestos = relationship("PedidoPresupuesto", backref="pedido", cascade="all, delete-orphan")
    aprobaciones = relationship(
        "PedidoAprobacion", backref="pedido", order_by="PedidoAprobacion.orden_aprobacion", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("empresa_id", "numero", name="uq_pedido_empresa_numero"),)


class PedidoPresupuesto(Base):
    __tablename__ = "soporte_pedidos_presupuestos"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    pedido_id = Column(UUID(as_uuid=True), ForeignKey("soporte_pedidos_compra.id"))
    proveedor = Column(String(200))
    url_archivo = Column(String(500), nullable=True)  # Alineado (line 668)
    articulo_descripcion = Column(Text)
    monto = Column(Numeric(12, 2))  # Alineado
    es_seleccionado = Column(Boolean, default=False)
    es_obligatorio = Column(Boolean, default=True)  # TRUE = obligatorio, FALSE = opcional

    created_at = Column(DateTime, default=utc_now)
    created_by = Column(String(255))
    updated_by = Column(String(255))


class PedidoAprobacion(Base):
    __tablename__ = "soporte_pedidos_aprobaciones"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    pedido_id = Column(UUID(as_uuid=True), ForeignKey("soporte_pedidos_compra.id"))
    departamento_id = Column(UUID(as_uuid=True), ForeignKey("nomina_departamentos.id"))
    aprobador_id = Column(UUID(as_uuid=True), ForeignKey("nomina_empleados.id"))
    estado = Column(String(50), default="pendiente")
    fecha_decision = Column(DateTime)
    observaciones = Column(Text)
    orden_aprobacion = Column(Integer, default=1)

    created_at = Column(DateTime, default=utc_now)
    created_by = Column(String(255))
    updated_by = Column(String(255))

    aprobador = relationship(Empleado, foreign_keys=[aprobador_id])


# ═══════════════════════════════════════════════════════════════
# AUDITORÍA FÍSICA Y EVENTOS
# ═══════════════════════════════════════════════════════════════


class HistorialActivo(Base):
    __tablename__ = "soporte_historial_activo"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    activo_id = Column(UUID(as_uuid=True), ForeignKey("soporte_activos.id"))
    colaborador_id = Column(UUID(as_uuid=True), ForeignKey("nomina_empleados.id"))
    responsable_id = Column(UUID(as_uuid=True), ForeignKey("nomina_empleados.id"))
    fecha_hora = Column(DateTime, default=utc_now)
    tipo_evento = Column(String(50))
    notas_adicionales = Column(Text)
    matriz_estado_id = Column(UUID(as_uuid=True), ForeignKey("soporte_matriz_estado.id"))
    pedido_compra_id = Column(UUID(as_uuid=True), ForeignKey("soporte_pedidos_compra.id"))

    @property
    def colaborador_nombre(self):
        return f"{self.colaborador.apellido}, {self.colaborador.nombre}" if self.colaborador else None

    @property
    def responsable_nombre(self):
        return f"{self.responsable.apellido}, {self.responsable.nombre}" if self.responsable else "Sistema"

    @property
    def estado_pantalla(self):
        return self.matriz_estado.pantalla if self.matriz_estado else None

    @property
    def estado_carcasa(self):
        return self.matriz_estado.carcasa_superior if self.matriz_estado else None

    @property
    def estado_bateria(self):
        return self.matriz_estado.bateria if self.matriz_estado else None

    @property
    def estado_puertos(self):
        return self.matriz_estado.puertos if self.matriz_estado else None

    @property
    def estado_teclado_trackpad(self):
        return self.matriz_estado.teclado if self.matriz_estado else None

    @property
    def estado_audio_camara(self):
        return self.matriz_estado.touchpad if self.matriz_estado else None

    created_at = Column(DateTime, default=utc_now)
    created_by = Column(String(255))
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255))

    activo = relationship("Activo", backref=backref("historial", order_by=fecha_hora.desc()))
    colaborador = relationship(Empleado, foreign_keys=[colaborador_id])
    responsable = relationship(Empleado, foreign_keys=[responsable_id])
    matriz_estado = relationship(SoporteMatrizEstado)
    pedido_compra = relationship("PedidoCompra", foreign_keys=[pedido_compra_id])
    evidencias = relationship("SoporteEvidencia", foreign_keys="SoporteEvidencia.historial_id", backref="historial")


class TicketChecklistItem(Base):
    """Ítems del checklist de proceso para tickets de alta/baja."""

    __tablename__ = "soporte_ticket_checklist_items"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    ticket_id = Column(UUID(as_uuid=True), ForeignKey("soporte_tickets.id", ondelete="CASCADE"), nullable=False)
    sistema_id = Column(UUID(as_uuid=True), ForeignKey("soporte_sistemas_disponibles.id"), nullable=True)
    item_clave = Column(String(100), nullable=False)
    item_label = Column(String(255), nullable=False)
    completado = Column(Boolean, nullable=False, default=False)
    completado_por = Column(String(255), nullable=True)
    completado_at = Column(DateTime, nullable=True)
    orden = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)

    sistema = relationship("SoporteSistemaDisponible", foreign_keys=[sistema_id])


class MantenimientoEvento(Base):
    __tablename__ = "soporte_mantenimiento_evento"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    activo_id = Column(UUID(as_uuid=True), ForeignKey("soporte_activos.id"))
    asignado_id = Column(UUID(as_uuid=True), ForeignKey("nomina_empleados.id"))
    fecha_ejecucion = Column(DateTime, default=utc_now)
    estado_anterior = Column(String(20))
    estado_nuevo = Column(String(20))
    fecha_hora = Column(DateTime, default=utc_now)
    notas = Column(Text)

    created_at = Column(DateTime, default=utc_now)
    created_by = Column(String(255))
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255))

    activo = relationship("Activo", backref=backref("mantenimientos", order_by=fecha_hora.desc()))
    asignado = relationship(Empleado, foreign_keys=[asignado_id])
