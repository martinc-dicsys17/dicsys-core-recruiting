"""
Seed de datos iniciales
=======================
Crea la empresa por defecto, departamentos base y empleado administrador.
Los demás datos se cargan via sincronización con Odoo.
"""

from sqlalchemy.orm import Session

from backend.core.utils import utc_now
from backend.modules.empresa.models import Empresa, core_usuario_empresa
from backend.modules.nomina.models import Categoria, Departamento, Perfil
from backend.modules.permisos.models import Grupo, PermisoModulo
from backend.modules.usuarios.models import Usuario

# Flag para habilitar/deshabilitar el seed
SEED_ENABLED = True

# Usuario admin por defecto
# Sin contraseña: la pone crear_usuario_admin_default desde SEED_ADMIN_PASSWORD o aleatoria (F02-P04)
ADMIN_DEFAULT_SEED = {
    "email": "admin@admin.com",
    "nombre": "Administrador",
    "apellido": "",
    "dni": 11111111,
    "rol": "admin",
    "activo": True,
}

# Grupo de permisos por defecto para colaboradores
GRUPO_COLABORADORES_SEED = {
    "nombre": "Colaboradores",
    "descripcion": "Acceso básico para empleados: Star Miles, Innovación y Recibos",
    "permisos": [
        # Star Miles → solo Portal
        {"modulo": "starmiles", "tiene_acceso": True},
        {"modulo": "starmiles.home", "tiene_acceso": True},
        # Innovación → Mi Path + Resumen
        {"modulo": "innovacion", "tiene_acceso": True},
        {"modulo": "innovacion.mi_path", "tiene_acceso": True},
        {"modulo": "innovacion.resumen", "tiene_acceso": True},
        # Mis Recibos → completo
        {"modulo": "recibos", "tiene_acceso": True},
        {"modulo": "recibos.mis_recibos", "tiene_acceso": True},
    ],
}

# Empresa por defecto del sistema
EMPRESA_DEFAULT_SEED = {
    "cuit": "30-71037057-1",
    "razon_social": "DICSYS S.A.",
    "nombre_fantasia": "Dicsys.AI",
    "responsabilidad_afip": "Responsable Inscripto",
    "dominios_email": '["dicsys.com", "dicsys.ai"]',
}

# Departamentos base del sistema
DEPARTAMENTOS_SEED = [
    {"nombre": "Administración", "descripcion": "Área de Administración y Contabilidad"},
    {"nombre": "Calidad", "descripcion": "Área de Calidad"},
    {"nombre": "Comercial", "descripcion": "Área Comercial"},
    {"nombre": "Customer", "descripcion": "Área de Customer Service"},
    {"nombre": "Formaciones", "descripcion": "Área de Formaciones"},
    {"nombre": "HRBP", "descripcion": "Área de Hrbp"},
    {"nombre": "Marketing", "descripcion": "Área de Marketing"},
    {"nombre": "Operaciones", "descripcion": "Área de Operaciones / Delivery"},
    {"nombre": "Reclutamiento", "descripcion": "Área de Reclutamiento"},
    {"nombre": "Soporte IT", "descripcion": "Área de Soporte IT"},
]

# Categorías base de perfiles (todas del depto Operaciones)
CATEGORIAS_SEED = [
    {
        "nombre": "Desarrollo e Ingeniería",
        "descripcion": "Desarrollo de software e ingeniería",
        "departamento": "Operaciones",
    },
    {
        "nombre": "Datos e IA",
        "descripcion": "Datos, analítica e inteligencia artificial",
        "departamento": "Operaciones",
    },
    {
        "nombre": "Infraestructura y Calidad",
        "descripcion": "Infraestructura, DevOps y QA",
        "departamento": "Operaciones",
    },
    {
        "nombre": "Diseño y Experiencia",
        "descripcion": "Diseño UX/UI y experiencia de usuario",
        "departamento": "Operaciones",
    },
    {"nombre": "Gestión y Producto", "descripcion": "Gestión de proyectos y producto", "departamento": "Operaciones"},
]

# Categorías de Management (una por departamento, para perfiles Manager)
CATEGORIAS_MANAGEMENT_SEED = [
    {
        "nombre": f"Management {depto['nombre']}",
        "descripcion": f"Gestión y liderazgo de {depto['nombre']}",
        "departamento": depto["nombre"],
    }
    for depto in DEPARTAMENTOS_SEED
]

# Perfiles base del sistema (categoria es el nombre, se resuelve a categoria_id en el seed)
PERFILES_SEED = [
    {"nombre": "Frontend Developer", "tipo": "DEVELOPER", "categoria": "Desarrollo e Ingeniería"},
    {"nombre": "Backend Developer", "tipo": "DEVELOPER", "categoria": "Desarrollo e Ingeniería"},
    {"nombre": "Full Stack Developer", "tipo": "DEVELOPER", "categoria": "Desarrollo e Ingeniería"},
    {"nombre": "Mobile Developer", "tipo": "DEVELOPER", "categoria": "Desarrollo e Ingeniería"},
    {"nombre": "Software Architect", "tipo": "LIDER", "categoria": "Desarrollo e Ingeniería"},
    {"nombre": "Tech Lead", "tipo": "LIDER", "categoria": "Desarrollo e Ingeniería"},
    {"nombre": "Data Analyst", "tipo": "DEVELOPER", "categoria": "Datos e IA"},
    {"nombre": "Data Scientist", "tipo": "DEVELOPER", "categoria": "Datos e IA"},
    {"nombre": "Data Engineer", "tipo": "DEVELOPER", "categoria": "Datos e IA"},
    {"nombre": "Machine Learning Engineer", "tipo": "DEVELOPER", "categoria": "Datos e IA"},
    {"nombre": "AI Engineer", "tipo": "DEVELOPER", "categoria": "Datos e IA"},
    {"nombre": "QA Analyst", "tipo": "DEVELOPER", "categoria": "Infraestructura y Calidad"},
    {"nombre": "DevOps Engineer", "tipo": "DEVELOPER", "categoria": "Infraestructura y Calidad"},
    {"nombre": "Cloud Architect", "tipo": "LIDER", "categoria": "Infraestructura y Calidad"},
    {"nombre": "Site Reliability Engineer (SRE)", "tipo": "DEVELOPER", "categoria": "Infraestructura y Calidad"},
    {"nombre": "Cybersecurity Specialist", "tipo": "DEVELOPER", "categoria": "Infraestructura y Calidad"},
    {"nombre": "UX/UI Designer", "tipo": "DEVELOPER", "categoria": "Diseño y Experiencia"},
    {"nombre": "Product Designer", "tipo": "DEVELOPER", "categoria": "Diseño y Experiencia"},
    {"nombre": "UX Researcher", "tipo": "DEVELOPER", "categoria": "Diseño y Experiencia"},
    {"nombre": "Product Manager", "tipo": "MANAGER", "categoria": "Gestión y Producto"},
    {"nombre": "Product Owner", "tipo": "LIDER", "categoria": "Gestión y Producto"},
    {"nombre": "Scrum Master", "tipo": "LIDER", "categoria": "Gestión y Producto"},
    {"nombre": "Project Manager", "tipo": "MANAGER", "categoria": "Gestión y Producto"},
    {"nombre": "Business Analyst", "tipo": "DEVELOPER", "categoria": "Gestión y Producto"},
]

# Perfiles Manager (uno por departamento)
PERFILES_MANAGER_SEED = [
    {"nombre": f"Manager {depto['nombre']}", "tipo": "MANAGER", "categoria": f"Management {depto['nombre']}"}
    for depto in DEPARTAMENTOS_SEED
]


def ejecutar_seed(db: Session) -> bool:
    """
    Ejecuta el seed de datos iniciales.
    Crea empresa default, departamentos, categorías, perfiles y empleado admin si no existen.
    """
    if not SEED_ENABLED:
        return False

    cambios = False

    # Crear empresa por defecto si no existe
    cuit_limpio = EMPRESA_DEFAULT_SEED["cuit"].replace("-", "")
    empresa = db.query(Empresa).filter(Empresa.cuit == cuit_limpio, Empresa.deleted_at.is_(None)).first()

    if not empresa:
        empresa = Empresa(
            cuit=cuit_limpio,
            razon_social=EMPRESA_DEFAULT_SEED["razon_social"],
            nombre_fantasia=EMPRESA_DEFAULT_SEED["nombre_fantasia"],
            responsabilidad_afip=EMPRESA_DEFAULT_SEED["responsabilidad_afip"],
            dominios_email=EMPRESA_DEFAULT_SEED["dominios_email"],
        )
        db.add(empresa)
        db.commit()
        print(f"🏭 Empresa default creada: {EMPRESA_DEFAULT_SEED['razon_social']}")
        cambios = True
    elif not empresa.dominios_email:
        empresa.dominios_email = EMPRESA_DEFAULT_SEED["dominios_email"]
        db.commit()
        print(f"🏭 Empresa default actualizada con dominios: {EMPRESA_DEFAULT_SEED['dominios_email']}")
        cambios = True

    empresa_id = empresa.id

    # Crear departamentos si no existen
    for depto_data in DEPARTAMENTOS_SEED:
        existe = (
            db.query(Departamento)
            .filter(
                Departamento.nombre == depto_data["nombre"],
                Departamento.empresa_id == empresa_id,
                Departamento.deleted_at.is_(None),
            )
            .first()
        )

        if not existe:
            depto = Departamento(empresa_id=empresa_id, **depto_data)
            db.add(depto)
            print(f"🏢 Departamento creado: {depto_data['nombre']}")
            cambios = True

    if cambios:
        db.commit()

    # Mapa de departamentos para resolver departamento_id
    deptos_map = {}
    for depto in db.query(Departamento).filter(Departamento.deleted_at.is_(None)).all():
        deptos_map[depto.nombre] = depto.id

    # Crear categorías base + management si no existen
    todas_categorias = CATEGORIAS_SEED + CATEGORIAS_MANAGEMENT_SEED
    for cat_data in todas_categorias:
        existe = (
            db.query(Categoria)
            .filter(
                Categoria.nombre == cat_data["nombre"],
                Categoria.empresa_id == empresa_id,
                Categoria.deleted_at.is_(None),
            )
            .first()
        )

        if not existe:
            data = {k: v for k, v in cat_data.items() if k != "departamento"}
            depto_nombre = cat_data.get("departamento")
            if depto_nombre and depto_nombre in deptos_map:
                data["departamento_id"] = deptos_map[depto_nombre]
            cat = Categoria(empresa_id=empresa_id, **data)
            db.add(cat)
            print(f"📂 Categoría creada: {cat_data['nombre']} (Depto: {depto_nombre})")
            cambios = True
        else:
            # Actualizar departamento_id si la categoría ya existe pero no tiene depto asignado
            depto_nombre = cat_data.get("departamento")
            if depto_nombre and depto_nombre in deptos_map and not existe.departamento_id:
                existe.departamento_id = deptos_map[depto_nombre]
                print(f"📂 Categoría actualizada: {cat_data['nombre']} → Depto: {depto_nombre}")
                cambios = True

    if cambios:
        db.commit()

    # Crear perfiles si no existen (resolviendo categoria_id)
    categorias_map = {}
    for cat in db.query(Categoria).filter(Categoria.deleted_at.is_(None), Categoria.empresa_id == empresa_id).all():
        categorias_map[cat.nombre] = cat.id

    todos_perfiles = PERFILES_SEED + PERFILES_MANAGER_SEED
    for perfil_data in todos_perfiles:
        perfil_data = dict(perfil_data)  # copia para no mutar el original
        existe = (
            db.query(Perfil)
            .filter(
                Perfil.nombre == perfil_data["nombre"], Perfil.empresa_id == empresa_id, Perfil.deleted_at.is_(None)
            )
            .first()
        )

        if not existe:
            cat_nombre = perfil_data.pop("categoria", None)
            if cat_nombre and cat_nombre in categorias_map:
                perfil_data["categoria_id"] = categorias_map[cat_nombre]
            perfil = Perfil(empresa_id=empresa_id, **perfil_data)
            db.add(perfil)
            print(f"👤 Perfil creado: {perfil_data['nombre']}")
            cambios = True

    if cambios:
        db.commit()

    # Vincular usuario admin con la empresa por defecto
    admin_user = (
        db.query(Usuario).filter(Usuario.email == ADMIN_DEFAULT_SEED["email"], Usuario.deleted_at.is_(None)).first()
    )

    if admin_user:
        ya_vinculado = db.execute(
            core_usuario_empresa.select().where(
                core_usuario_empresa.c.usuario_id == admin_user.id,
                core_usuario_empresa.c.empresa_id == empresa_id,
            )
        ).first()

        if not ya_vinculado:
            db.execute(
                core_usuario_empresa.insert().values(
                    usuario_id=admin_user.id,
                    empresa_id=empresa_id,
                    created_at=utc_now(),
                )
            )
            db.commit()
            print(f"🔗 Usuario admin vinculado a empresa: {EMPRESA_DEFAULT_SEED['razon_social']}")
            cambios = True

    # Crear grupo "Colaboradores" con permisos si no existe
    grupo_colab = (
        db.query(Grupo).filter(Grupo.nombre == GRUPO_COLABORADORES_SEED["nombre"], Grupo.deleted_at.is_(None)).first()
    )

    if not grupo_colab:
        grupo_colab = Grupo(
            nombre=GRUPO_COLABORADORES_SEED["nombre"], descripcion=GRUPO_COLABORADORES_SEED["descripcion"], activo=True
        )
        db.add(grupo_colab)
        db.commit()
        db.refresh(grupo_colab)

        for p in GRUPO_COLABORADORES_SEED["permisos"]:
            db.add(PermisoModulo(grupo_id=grupo_colab.id, modulo=p["modulo"], tiene_acceso=p["tiene_acceso"]))
        db.commit()
        print(f"👥 Grupo '{GRUPO_COLABORADORES_SEED['nombre']}' creado con permisos")
        cambios = True

    return cambios
