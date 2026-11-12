"""
Seed de datos maestros para el módulo de Soporte IT.
Solo pobla tablas maestras que el sistema necesita para funcionar.
Incluye seed de marcas de equipos (laptops, celulares, servidores).
"""

import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.modules.empresa.models import Empresa
from backend.modules.nomina.models import Departamento
from backend.modules.soporte.models import (
    SoporteActivosMarca,
    SoporteCategoria,
    SoportePedidosEstado,
    SoporteSistemaDisponible,
    SoporteSubcategoria,
    SoporteTicketsEstado,
)

logger = logging.getLogger("soporte")


# Lista unificada de todas las marcas (sin clasificación por tipo de dispositivo)
MARCAS = [
    # Laptops
    "Acer",
    "Alienware",
    "Apple",
    "Asus",
    "Banghó",
    "BGH",
    "Chuwi",
    "Compaq",
    "Dell",
    "Exo",
    "Framework",
    "Gigabyte",
    "HP",
    "Huawei",
    "Lenovo",
    "LG",
    "Microsoft",
    "MSI",
    "Noblex",
    "Panasonic",
    "PCBOX",
    "Philco",
    "Razer",
    "Samsung",
    "Sony",
    "Toshiba",
    "Vaio",
    "Xiaomi",
    # Celulares
    "Alcatel",
    "BlackBerry",
    "Google",
    "Honor",
    "HTC",
    "Infinix",
    "Motorola",
    "Nokia",
    "OnePlus",
    "Oppo",
    "Poco",
    "Realme",
    "TCL",
    "Tecno",
    "Vivo",
    "ZTE",
    # Servidores
    "Cisco",
    "Fujitsu",
    "Hitachi",
    "HPE",
    "IBM",
    "Inspur",
    "Oracle",
    "Quanta",
    "Supermicro",
]

# Estados de tickets (maestros requeridos por lógica de negocio)
ESTADOS_TICKETS = [
    {"nombre": "Abierto", "clave": "abierto", "color": "#3b82f6"},
    {"nombre": "En Progreso", "clave": "en_progreso", "color": "#f59e0b"},
    {"nombre": "En Espera", "clave": "en_espera", "color": "#a855f7"},
    {"nombre": "Pendiente Usuario", "clave": "pendiente_usuario", "color": "#8b5cf6"},
    {"nombre": "Pendiente Proveedor", "clave": "pendiente_proveedor", "color": "#ec4899"},
    {"nombre": "Resuelto", "clave": "resuelto", "color": "#10b981"},
    {"nombre": "Cerrado", "clave": "cerrado", "color": "#6b7280"},
    {"nombre": "Cancelado", "clave": "cancelado", "color": "#ef4444"},
]

# Estados de pedidos de compra (maestros requeridos por lógica de negocio)
ESTADOS_PEDIDOS = [
    {"nombre": "Borrador", "clave": "borrador", "color": "#9ca3af"},
    {"nombre": "Pendiente Aprobación", "clave": "pendiente_aprobacion", "color": "#f59e0b"},
    {"nombre": "Aprobado", "clave": "aprobado", "color": "#10b981"},
    {"nombre": "Rechazado", "clave": "rechazado", "color": "#ef4444"},
    {"nombre": "En Compra", "clave": "en_compra", "color": "#3b82f6"},
    {"nombre": "Recibido", "clave": "recibido", "color": "#059669"},
    {"nombre": "Cancelado", "clave": "cancelado", "color": "#6b7280"},
]

# Sistemas disponibles para checklist de alta/baja de colaborador
SISTEMAS_ALTA_SEED = [
    {"clave": "alta_email", "label": "Alta de email", "orden": 1, "tipo": "alta"},
    {"clave": "alta_odoo", "label": "Usuario de Odoo", "orden": 2, "tipo": "alta"},
    {"clave": "alta_webex", "label": "Usuario de Webex", "orden": 3, "tipo": "alta"},
    {"clave": "alta_svn", "label": "Alta en SVN según perfil del usuario", "orden": 4, "tipo": "alta"},
    {"clave": "alta_nextcloud", "label": "Alta en Nextcloud", "orden": 5, "tipo": "alta"},
    {"clave": "rc_equipo", "label": "RC de entrega de equipo", "orden": 6, "tipo": "alta"},
    {"clave": "lista_correos", "label": "Agregar a lista de correos", "orden": 7, "tipo": "alta"},
    {"clave": "softwares", "label": "Consultar softwares requeridos según proyecto", "orden": 8, "tipo": "alta"},
]

SISTEMAS_BAJA_SEED = [
    {
        "clave": "baja_email",
        "label": "Baja de usuario de mail",
        "orden": 1,
        "tipo": "baja",
        "clave_alta_ref": "alta_email",
    },
    {"clave": "baja_odoo", "label": "Baja de Odoo", "orden": 2, "tipo": "baja", "clave_alta_ref": "alta_odoo"},
    {"clave": "baja_webex", "label": "Webex", "orden": 3, "tipo": "baja", "clave_alta_ref": "alta_webex"},
    {"clave": "baja_svn", "label": "SVN", "orden": 4, "tipo": "baja", "clave_alta_ref": "alta_svn"},
    {"clave": "baja_nextcloud", "label": "Nextcloud", "orden": 5, "tipo": "baja", "clave_alta_ref": "alta_nextcloud"},
    {
        "clave": "mail_equipo",
        "label": "Mail recupero equipo (si tiene máquina Dicsys)",
        "orden": 6,
        "tipo": "baja",
        "clave_alta_ref": "rc_equipo",
    },
    {
        "clave": "baja_correos",
        "label": "Eliminar correo de la lista (CBA-BSAS)",
        "orden": 7,
        "tipo": "baja",
        "clave_alta_ref": "lista_correos",
    },
]

# Categorías y subcategorías de tickets
CATEGORIAS_SUBCATEGORIAS = {
    "Hardware": {
        "tipo_ticket_asociado": "reparacion",
        "subcategorias": [
            "Notebook",
            "PC Escritorio",
            "Monitor",
            "Teclado",
            "Mouse",
            "Impresora",
            "Auriculares",
            "Webcam",
            "Otro Hardware",
        ],
    },
    "Software": {
        "tipo_ticket_asociado": "generico",
        "subcategorias": [
            "Sistema Operativo",
            "Aplicaciones",
            "Licencias",
            "Antivirus",
            "Actualizaciones",
            "Instalación",
            "Configuración",
            "Otro Software",
        ],
    },
    "Red y Conectividad": {
        "tipo_ticket_asociado": "generico",
        "subcategorias": ["Internet", "WiFi", "VPN", "Acceso Remoto", "Email", "Firewall", "Router", "Otro Red"],
    },
    "Cuentas y Accesos": {
        "tipo_ticket_asociado": "generico",
        "subcategorias": [
            "Creación Usuario",
            "Reseteo Contraseña",
            "Permisos",
            "Desbloqueo Cuenta",
            "Acceso Sistemas",
            "Otro Acceso",
        ],
    },
    "Alta/Baja Colaborador": {
        "tipo_ticket_asociado": "alta_baja",
        "subcategorias": [
            "Alta Colaborador",
            "Baja Colaborador",
            "Cambio Equipo",
            "Devolución Equipo",
            "Otro Alta/Baja",
        ],
    },
    "Mantenimiento": {
        "tipo_ticket_asociado": "mantenimiento",
        "subcategorias": [
            "Mantenimiento Preventivo",
            "Mantenimiento Correctivo",
            "Limpieza Equipo",
            "Actualización Hardware",
            "Otro Mantenimiento",
        ],
    },
    "Consulta General": {
        "tipo_ticket_asociado": "generico",
        "subcategorias": ["Asesoramiento", "Capacitación", "Documentación", "Solicitud Información", "Otra Consulta"],
    },
}


def ejecutar_seed_soporte(db: Session, usuario_email: str = "admin@admin.com") -> bool:
    """
    Pobla tablas maestras que el sistema necesita para funcionar.
    NO seedea marcas, tipos de activos ni insumos (se cargan desde la UI).
    """
    hubo_cambios = False
    pendiente = False

    # 1. Estados de tickets
    for estado_data in ESTADOS_TICKETS:
        existe = db.query(SoporteTicketsEstado).filter(SoporteTicketsEstado.clave == estado_data["clave"]).first()
        if not existe:
            db.add(SoporteTicketsEstado(**estado_data, created_by=usuario_email))
            print(f"🎫 Estado ticket creado: {estado_data['nombre']}")
            pendiente = True

    if pendiente:
        db.commit()
        hubo_cambios = True
        pendiente = False

    # 2. Estados de pedidos
    for estado_data in ESTADOS_PEDIDOS:
        existe = db.query(SoportePedidosEstado).filter(SoportePedidosEstado.clave == estado_data["clave"]).first()
        if not existe:
            db.add(SoportePedidosEstado(**estado_data, created_by=usuario_email))
            print(f"🛒 Estado pedido creado: {estado_data['nombre']}")
            pendiente = True

    if pendiente:
        db.commit()
        hubo_cambios = True
        pendiente = False

    # 3. Sistemas disponibles para alta/baja (requiere empresa_id por empresa)
    empresas = db.query(Empresa).filter(Empresa.deleted_at.is_(None)).all()
    for empresa in empresas:
        for sistema_data in SISTEMAS_ALTA_SEED + SISTEMAS_BAJA_SEED:
            existe = (
                db.query(SoporteSistemaDisponible)
                .filter(
                    SoporteSistemaDisponible.clave == sistema_data["clave"],
                    SoporteSistemaDisponible.empresa_id == empresa.id,
                )
                .first()
            )
            if not existe:
                db.add(SoporteSistemaDisponible(**sistema_data, empresa_id=empresa.id, created_by=usuario_email))
                print(f"⚙️ Sistema disponible creado: {sistema_data['clave']}")
                pendiente = True

        if pendiente:
            db.commit()
            hubo_cambios = True
            pendiente = False

        # 4. Categorías y subcategorías (por empresa)
        depto_soporte = (
            db.query(Departamento)
            .filter(
                Departamento.nombre == "Soporte IT",
                Departamento.empresa_id == empresa.id,
                Departamento.deleted_at.is_(None),
            )
            .first()
        )

        for cat_nombre, cat_config in CATEGORIAS_SUBCATEGORIAS.items():
            nombre_normalizado = cat_nombre.lower().replace(" ", "_").replace("/", "_")

            categoria = (
                db.query(SoporteCategoria)
                .filter(
                    SoporteCategoria.nombre_normalizado == nombre_normalizado, SoporteCategoria.empresa_id == empresa.id
                )
                .first()
            )

            if not categoria:
                categoria = SoporteCategoria(
                    empresa_id=empresa.id,
                    nombre_display=cat_nombre,
                    nombre_normalizado=nombre_normalizado,
                    tipo_ticket_asociado=cat_config["tipo_ticket_asociado"],
                    departamento_id=depto_soporte.id if depto_soporte else None,
                    created_by=usuario_email,
                )
                db.add(categoria)
                db.flush()
                print(f"📁 Categoría creada: {cat_nombre} (empresa {empresa.id})")
                pendiente = True

            for subcat_nombre in cat_config["subcategorias"]:
                subcat_normalizado = subcat_nombre.lower().replace(" ", "_")

                existe_subcat = (
                    db.query(SoporteSubcategoria)
                    .filter(
                        SoporteSubcategoria.categoria_id == categoria.id,
                        SoporteSubcategoria.nombre_normalizado == subcat_normalizado,
                    )
                    .first()
                )

                if not existe_subcat:
                    db.add(
                        SoporteSubcategoria(
                            empresa_id=empresa.id,
                            categoria_id=categoria.id,
                            nombre_display=subcat_nombre,
                            nombre_normalizado=subcat_normalizado,
                            tipo_ticket_asociado=cat_config["tipo_ticket_asociado"],
                            created_by=usuario_email,
                        )
                    )
                    print(f"  └─ Subcategoría creada: {subcat_nombre}")
                    pendiente = True

        if pendiente:
            db.commit()
            hubo_cambios = True
            pendiente = False

    return hubo_cambios


def seed_marcas(db: Session, empresa_id, usuario_email: str = "sistema@dicsys.com") -> dict:
    """
    Pobla la tabla soporte_activos_marcas con todas las marcas disponibles.

    Args:
        db: Sesión de base de datos
        empresa_id: ID de la empresa (UUID)
        usuario_email: Email del usuario que ejecuta el seed (por defecto: sistema)

    Returns:
        dict: Estadísticas de la operación (creadas, existentes, errores)
    """
    stats = {"creadas": 0, "existentes": 0, "errores": 0}

    # Eliminar duplicados y ordenar alfabéticamente
    marcas_unicas = sorted(set(MARCAS))

    logger.info(f"Iniciando seed de {len(marcas_unicas)} marcas para empresa {empresa_id}")

    for nombre_marca in marcas_unicas:
        try:
            # Verificar si ya existe
            existente = (
                db.query(SoporteActivosMarca)
                .filter(SoporteActivosMarca.empresa_id == empresa_id, SoporteActivosMarca.nombre == nombre_marca)
                .first()
            )

            if existente:
                stats["existentes"] += 1
                continue

            # Crear nueva marca
            marca = SoporteActivosMarca(empresa_id=empresa_id, nombre=nombre_marca, created_by=usuario_email)
            db.add(marca)
            db.flush()  # Flush para detectar errores antes del commit final
            stats["creadas"] += 1
            print(f"🏷️  Marca creada: {nombre_marca}")

        except IntegrityError as e:
            db.rollback()
            logger.warning(f"Error de integridad al crear marca '{nombre_marca}': {e}")
            stats["errores"] += 1
            continue
        except Exception as e:
            db.rollback()
            logger.error(f"Error inesperado al crear marca '{nombre_marca}': {e}")
            stats["errores"] += 1
            continue

    # Commit final de todas las marcas creadas
    try:
        db.commit()
        logger.info(
            f"Seed de marcas completado: {stats['creadas']} creadas, {stats['existentes']} existentes, {stats['errores']} errores"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error al hacer commit final del seed de marcas: {e}")
        raise

    return stats


def ejecutar_seed_marcas_todas_empresas(db: Session, usuario_email: str = "sistema@dicsys.com") -> dict:
    """
    Ejecuta el seed de marcas para todas las empresas activas en el sistema.

    Args:
        db: Sesión de base de datos
        usuario_email: Email del usuario que ejecuta el seed

    Returns:
        dict: Estadísticas por empresa
    """
    empresas = db.query(Empresa).filter(Empresa.deleted_at.is_(None)).all()
    resultados = {}

    for empresa in empresas:
        print(f"\n📦 Ejecutando seed de marcas para empresa: {empresa.razon_social} ({empresa.id})")
        stats = seed_marcas(db, empresa.id, usuario_email)
        resultados[str(empresa.id)] = {"razon_social": empresa.razon_social, "stats": stats}
        print(f"   ✅ {stats['creadas']} creadas, {stats['existentes']} ya existían, {stats['errores']} errores")

    return resultados
