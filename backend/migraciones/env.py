"""
Entorno de Alembic de Dicsys Core (F04). Cómo se usa: docs/Migraciones.md.

- El esquema esperado es Base.metadata con todos los modelos (backend/models_registry.py): `alembic check` falla si
  los modelos y las migraciones no coinciden.
- La base es la de la app (DATABASE_URL). Los tests pasan su propia conexión en config.attributes["connection"].
- `alembic revision` numera las revisiones en orden (0001, 0002...) salvo que se pase --rev-id, y con --autogenerate
  no escribe nada si no hay cambios.
- Las tablas de respaldo hechas a mano (`<tabla>_bkp_<fecha>`, como las recibos_*_bkp_20260722 de producción) no son
  del esquema: autogenerate y `alembic check` no las ven, y ninguna revisión las crea ni las borra.
"""

import re
from logging.config import fileConfig

from alembic import context
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, pool

import backend.models_registry  # noqa: F401
from backend.core.config import settings
from backend.database import Base

config = context.config
if config.config_file_name and config.attributes.get("configurar_logging", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def _numerar(contexto, revision, directivas) -> None:
    """Número de revisión correlativo en vez del hash de Alembic; una autogenerada sin cambios no se escribe."""
    script = directivas[0]
    opciones = config.cmd_opts
    if getattr(opciones, "autogenerate", False) and script.upgrade_ops.is_empty():
        directivas[:] = []
        print("Los modelos y la base coinciden: no hay nada para migrar y no se crea la revisión.")
        return
    if not getattr(opciones, "rev_id", None):
        head = ScriptDirectory.from_config(config).get_current_head()
        script.rev_id = f"{int(head) + 1:04d}" if head else "0001"


RESPALDO_A_MANO = re.compile(r"_bkp_\d{8}$")


def _del_esquema(objeto, nombre, tipo, reflejado, comparado_con) -> bool:
    """Afuera de la comparación: las tablas de respaldo a mano que están en la base y no en los modelos."""
    return not (tipo == "table" and reflejado and comparado_con is None and RESPALDO_A_MANO.search(nombre or ""))


OPCIONES = {
    "target_metadata": Base.metadata,
    "compare_type": True,
    "include_object": _del_esquema,
    "process_revision_directives": _numerar,
}


def _migrar(conexion) -> None:
    context.configure(connection=conexion, **OPCIONES)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    conexion = config.attributes.get("connection")
    if conexion is not None:
        _migrar(conexion)
        return
    motor = create_engine(settings.database_url, poolclass=pool.NullPool)
    try:
        with motor.connect() as conexion:
            _migrar(conexion)
    finally:
        motor.dispose()


if context.is_offline_mode():
    # Hay revisiones que leen datos (0002, 0003): sin conexión no se pueden generar
    raise SystemExit("Sin modo --sql: las migraciones se aplican conectadas a la base (docs/Migraciones.md).")
run_migrations_online()
