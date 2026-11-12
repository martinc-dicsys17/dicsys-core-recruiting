"""
Servicios para gestión de menús.
"""

from sqlalchemy.orm import Session

from backend.modules.permisos.menu_models import Menu, MenuItem


class MenuService:
    """Servicio para operaciones de menús."""

    @staticmethod
    def crear_menus_default(db: Session) -> bool:
        """Crea los menús por defecto si no existen."""
        # Verificar si ya hay menús
        if db.query(Menu).first():
            return False

        # Menú Configuración
        admin_menu = Menu(codigo="administracion", nombre="Configuración", icono="settings", orden=1)
        db.add(admin_menu)
        db.flush()

        admin_items = [
            MenuItem(
                menu_id=admin_menu.id,
                codigo="usuarios",
                nombre="Usuarios",
                icono="users",
                ruta="usuarios.list",
                orden=1,
            ),
            MenuItem(
                menu_id=admin_menu.id,
                codigo="permisos",
                nombre="Permisos",
                icono="shield-check",
                ruta="permisos.grupos_list",
                orden=2,
            ),
            MenuItem(
                menu_id=admin_menu.id,
                codigo="actualizacion_datos",
                nombre="Actualización de Datos",
                icono="refresh-cw",
                ruta="sincronizacion.listar",
                orden=3,
            ),
            MenuItem(menu_id=admin_menu.id, codigo="roles", nombre="Roles", icono="user-cog", ruta=None, orden=4),
            MenuItem(
                menu_id=admin_menu.id,
                codigo="configuracion",
                nombre="Configuración",
                icono="sliders",
                ruta=None,
                orden=5,
            ),
        ]
        db.add_all(admin_items)

        # Menú Nómina
        nomina_menu = Menu(codigo="nomina", nombre="Nómina", icono="wallet", orden=2)
        db.add(nomina_menu)
        db.flush()

        nomina_items = [
            MenuItem(
                menu_id=nomina_menu.id,
                codigo="empleados",
                nombre="Empleados",
                icono="users",
                ruta="nomina.empleados_list",
                orden=1,
            ),
            MenuItem(
                menu_id=nomina_menu.id,
                codigo="departamentos",
                nombre="Departamentos",
                icono="building-2",
                ruta="nomina.departamentos_list",
                orden=2,
            ),
            MenuItem(
                menu_id=nomina_menu.id,
                codigo="perfiles",
                nombre="Perfiles",
                icono="briefcase",
                ruta="nomina.perfiles_list",
                orden=3,
            ),
            MenuItem(
                menu_id=nomina_menu.id,
                codigo="categorias",
                nombre="Categorías",
                icono="tag",
                ruta="nomina.categorias_list",
                orden=4,
            ),
            MenuItem(
                menu_id=nomina_menu.id,
                codigo="carreras",
                nombre="Carreras",
                icono="graduation-cap",
                ruta="nomina.carreras_list",
                orden=5,
            ),
            MenuItem(
                menu_id=nomina_menu.id,
                codigo="liquidaciones",
                nombre="Liquidaciones",
                icono="file-text",
                ruta=None,
                orden=6,
            ),
            MenuItem(
                menu_id=nomina_menu.id, codigo="vacaciones", nombre="Vacaciones", icono="calendar", ruta=None, orden=7
            ),
            MenuItem(
                menu_id=nomina_menu.id, codigo="reportes", nombre="Reportes", icono="bar-chart-2", ruta=None, orden=8
            ),
        ]
        db.add_all(nomina_items)

        # Menú Star Miles (todo en uno)
        starmiles_menu = Menu(codigo="starmiles", nombre="Star Miles", icono="star", orden=3)
        db.add(starmiles_menu)
        db.flush()

        starmiles_items = [
            # Empleado - Solo Portal (el resto se accede desde ahí)
            MenuItem(
                menu_id=starmiles_menu.id, codigo="home", nombre="Portal", icono="home", ruta="starmiles.home", orden=1
            ),
            # Aprobador
            MenuItem(
                menu_id=starmiles_menu.id,
                codigo="aprobar_inscripciones",
                nombre="Aprobar Inscripciones",
                icono="clipboard-check",
                ruta="starmiles.aprobador_inscripciones",
                orden=2,
            ),
            MenuItem(
                menu_id=starmiles_menu.id,
                codigo="aprobar_canjes",
                nombre="Aprobar Canjes",
                icono="package-check",
                ruta="starmiles.aprobador_canjes",
                orden=3,
            ),
            # Admin
            MenuItem(
                menu_id=starmiles_menu.id,
                codigo="admin_empleados",
                nombre="Gestionar Empleados",
                icono="users",
                ruta="starmiles.admin_empleados",
                orden=4,
            ),
            MenuItem(
                menu_id=starmiles_menu.id,
                codigo="admin_desafios",
                nombre="Gestionar Desafíos",
                icono="settings",
                ruta="starmiles.admin_desafios",
                orden=5,
            ),
            MenuItem(
                menu_id=starmiles_menu.id,
                codigo="admin_canjes",
                nombre="Gestionar Canjes",
                icono="box",
                ruta="starmiles.admin_items_canje",
                orden=6,
            ),
            MenuItem(
                menu_id=starmiles_menu.id,
                codigo="admin_categorias",
                nombre="Gestionar Categorías",
                icono="tag",
                ruta="starmiles.admin_categorias",
                orden=7,
            ),
            MenuItem(
                menu_id=starmiles_menu.id,
                codigo="admin_cms",
                nombre="Gestionar Contenido",
                icono="file-text",
                ruta="starmiles.admin_cms",
                orden=8,
            ),
        ]
        db.add_all(starmiles_items)

        # Menú HRBP
        hrbp_menu = Menu(codigo="hrbp", nombre="HRBP", icono="heart-handshake", orden=4)
        db.add(hrbp_menu)
        db.flush()

        hrbp_items = [
            MenuItem(
                menu_id=hrbp_menu.id,
                codigo="gestion_items",
                nombre="Gestión de Items",
                icono="package",
                ruta="hrbp.items_list",
                orden=1,
            ),
            MenuItem(
                menu_id=hrbp_menu.id,
                codigo="entregas",
                nombre="Gestión de Entregas",
                icono="gift",
                ruta="hrbp.entregas_list",
                orden=2,
            ),
        ]
        db.add_all(hrbp_items)

        # Menú Administración (Contabilidad)
        admin_contable_menu = Menu(codigo="admin_contable", nombre="Administración", icono="calculator", orden=5)
        db.add(admin_contable_menu)
        db.flush()

        admin_contable_items = [
            MenuItem(
                menu_id=admin_contable_menu.id,
                codigo="licencias",
                nombre="Gestión de Licencias",
                icono="key",
                ruta="administracion.licencias_list",
                orden=1,
            ),
        ]
        db.add_all(admin_contable_items)

        db.commit()
        return True

    @staticmethod
    def crear_menu_administracion(db: Session) -> bool:
        """Crea el menú de Administración si no existe."""
        # Verificar si ya existe
        if db.query(Menu).filter(Menu.codigo == "admin_contable").first():
            return False

        admin_contable_menu = Menu(codigo="admin_contable", nombre="Administración", icono="calculator", orden=5)
        db.add(admin_contable_menu)
        db.flush()

        admin_contable_items = [
            MenuItem(
                menu_id=admin_contable_menu.id,
                codigo="licencias",
                nombre="Gestión de Licencias",
                icono="key",
                ruta="administracion.licencias_list",
                orden=1,
            ),
        ]
        db.add_all(admin_contable_items)

        db.commit()
        return True

    @staticmethod
    def crear_menu_operaciones(db: Session) -> bool:
        """Crea el menú de Operaciones si no existe."""
        # Verificar si ya existe
        if db.query(Menu).filter(Menu.codigo == "operaciones").first():
            return False

        operaciones_menu = Menu(codigo="operaciones", nombre="Operaciones", icono="briefcase", orden=6)
        db.add(operaciones_menu)
        db.flush()

        operaciones_items = [
            MenuItem(
                menu_id=operaciones_menu.id,
                codigo="equipos",
                nombre="Equipos",
                icono="users",
                ruta="operaciones.equipos_list",
                orden=1,
            ),
        ]
        db.add_all(operaciones_items)

        db.commit()
        return True

    @staticmethod
    def agregar_categorias_carreras_nomina(db: Session) -> bool:
        """Agrega Categorías y Carreras al menú de Nómina si no existen."""
        nomina_menu = db.query(Menu).filter(Menu.codigo == "nomina").first()
        if not nomina_menu:
            return False

        cambios = False

        # Agregar Categorías si no existe
        if not db.query(MenuItem).filter(MenuItem.menu_id == nomina_menu.id, MenuItem.codigo == "categorias").first():
            db.add(
                MenuItem(
                    menu_id=nomina_menu.id,
                    codigo="categorias",
                    nombre="Categorías",
                    icono="tag",
                    ruta="nomina.categorias_list",
                    orden=4,
                )
            )
            cambios = True

        # Agregar Carreras si no existe
        if not db.query(MenuItem).filter(MenuItem.menu_id == nomina_menu.id, MenuItem.codigo == "carreras").first():
            db.add(
                MenuItem(
                    menu_id=nomina_menu.id,
                    codigo="carreras",
                    nombre="Carreras",
                    icono="graduation-cap",
                    ruta="nomina.carreras_list",
                    orden=5,
                )
            )
            cambios = True

        if cambios:
            # Reordenar los items que no tienen ruta (próximamente) para que queden al final
            items_sin_ruta = db.query(MenuItem).filter(MenuItem.menu_id == nomina_menu.id, MenuItem.ruta == None).all()
            for i, item in enumerate(items_sin_ruta, start=6):
                item.orden = i

            db.commit()
        return cambios

    @staticmethod
    def actualizar_menu_hrbp_items(db: Session) -> bool:
        """Actualiza el nombre del menú de Items de Entrega a Gestión de Items."""
        item = db.query(MenuItem).filter(MenuItem.codigo == "items_entrega").first()
        if item:
            item.codigo = "gestion_items"
            item.nombre = "Gestión de Items"
            db.commit()
            return True
        return False

    @staticmethod
    def obtener_menus_activos(db: Session) -> list:
        """Obtiene todos los menús activos con sus items."""
        return db.query(Menu).filter(Menu.activo == True, Menu.deleted_at == None).order_by(Menu.orden).all()

    @staticmethod
    def obtener_menus_usuario(db: Session, usuario_id: str) -> list:
        """
        Obtiene los menús a los que tiene acceso un usuario.
        Por ahora devuelve todos los menús activos.
        TODO: Filtrar por permisos del grupo del usuario.
        """
        return MenuService.obtener_menus_activos(db)
