"""
Constantes y Enums para el módulo de Soporte Técnico.
Usar siempre estos enums en vez de strings sueltos en services/routers.
"""

from enum import Enum


class TicketEstado(str, Enum):
    """Claves de soporte_tickets_estados (tabla maestra en DB)."""

    ABIERTO = "abierto"
    EN_PROGRESO = "en_progreso"
    EN_ESPERA = "en_espera"
    PENDIENTE_USUARIO = "pendiente_usuario"
    PENDIENTE_PROVEEDOR = "pendiente_proveedor"
    RESUELTO = "resuelto"
    CERRADO = "cerrado"
    CANCELADO = "cancelado"


class PedidoEstado(str, Enum):
    """Claves de soporte_pedidos_estados (tabla maestra en DB)."""

    BORRADOR = "borrador"
    PENDIENTE_APROBACION = "pendiente_aprobacion"
    APROBADO = "aprobado"
    RECHAZADO = "rechazado"
    EN_COMPRA = "en_compra"
    RECIBIDO = "recibido"
    CANCELADO = "cancelado"


class TipoTicket(str, Enum):
    """Valores del campo tipo_ticket / polymorphic_identity."""

    GENERICO = "generico"
    REPARACION = "reparacion"
    ALTA_BAJA = "alta_baja"
    MANTENIMIENTO = "mantenimiento"


class TipoOperacion(str, Enum):
    """Valores del campo tipo_operacion en TicketAltaBaja."""

    ALTA = "alta"
    BAJA = "baja"


class ActivoEstado(str, Enum):
    """Valores del campo estado en soporte_activos."""

    DISPONIBLE = "disponible"
    ASIGNADO = "asignado"
    EN_REPARACION = "en_reparacion"
    DADO_DE_BAJA = "dado_de_baja"


class HistorialTipoEvento(str, Enum):
    """Valores del campo tipo_evento en soporte_historial_activo."""

    ALTA = "Alta"
    BAJA = "Baja"
    REPARACION = "Reparacion"
    MANTENIMIENTO = "Mantenimiento Preventivo"
    FOTO_AGREGADA = "Foto Agregada"


# Mapeo de clave de tipo de activo → prefijo de número de inventario
# Formato: {PREFIJO}-{NUMERO_AUTOINCREMENTAL:03d} → ej: NOT-001, MON-012
PREFIJO_INVENTARIO = {
    "notebook": "NOT",
    "pc_escritorio": "PCE",
    "monitor": "MON",
    "teclado": "TEC",
    "mouse": "MOU",
    "auriculares": "AUR",
    "webcam": "WEB",
    "impresora": "IMP",
    "router": "ROU",
    "switch": "SWI",
    "disco_externo": "DIS",
    "cargador": "CAR",
    "docking_station": "DOC",
    "celular": "CEL",
    "servidor": "SER",
    "otro": "OTR",
}
