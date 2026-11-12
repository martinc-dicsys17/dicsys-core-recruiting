"""Adopción de las bases de antes de Alembic: controla las migraciones ad hoc, alinea lo que create_all no alineaba y
borra core_schema_migrations.

Hasta F04 el esquema lo armaba el backend al arrancar: create_all (que crea tablas pero no altera las que existen) y
migraciones ad hoc anotadas en core_schema_migrations. Una base de esa época se adopta con `alembic stamp 0001` y
`alembic upgrade head` (docs/Migraciones.md) y pasa por acá:

1. Si no había aplicado todas las migraciones ad hoc, la adopción se corta: `alembic check` ve columnas, tablas e
   índices, pero no los CHECK ni los cambios de datos que hacían.
2. Se alinea con los modelos lo que create_all nunca cambió en las bases existentes (visto al adoptar una copia de una
   base de desarrollo real): la unicidad del número de ticket y de pedido pasó a ser por empresa (0f02f6c, abril de
   2026) y las bases viejas siguen con la global, que hace fallar el primer ticket de la segunda empresa; la PK y las
   FK de innovacion_licencias conservan los nombres de admin_licencias; y quedan defaults de servidor de los ALTER ad
   hoc que los modelos no declaran.

En una base creada por Alembic no hay core_schema_migrations y esta revisión no hace nada.

Revisión: 0002
Anterior: 0001
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, Sequence[str], None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Las que anotaban su paso. Las otras dos (deleted_at e índice de notificaciones internas, columnas de auditoría de
# soporte_matriz_estado) agregan columnas e índices, que sí ve `alembic check`.
MIGRACIONES_AD_HOC = (
    "innovacion_licencias_modelo_final_v1",
    "starmiles_dic_144_inscripcion_unica_v1",
    "recibos_duplicado_opcional_v1",
    "proveedores_acuerdo_si_no_v1",
    "proveedores_importacion_rechazos_v1",
    "proveedores_sin_checklist_v1",
    "proveedores_autogeneracion_v1",
    "proveedores_auditoria_documentos_v1",
)

# (tabla, unicidad global de antes, unicidad por empresa del modelo)
NUMERO_POR_EMPRESA = (
    ("soporte_tickets", "soporte_tickets_numero_key", "uq_ticket_empresa_numero"),
    ("soporte_pedidos_compra", "soporte_pedidos_compra_numero_key", "uq_pedido_empresa_numero"),
)
# Constraints de innovacion_licencias que conservan el nombre de cuando la tabla era admin_licencias
SUFIJOS_DE_ADMIN_LICENCIAS = ("pkey", "empleado_id_fkey", "empresa_id_fkey")
# Columnas que los ALTER ad hoc agregaron con DEFAULT y que en los modelos no tienen default de servidor
DEFAULTS_AD_HOC = (
    ("soporte_matriz_estado", "created_at"),
    ("soporte_matriz_estado", "updated_at"),
    ("starmiles_desafios", "inscripcion_unica_por_empleado"),
)


def _hay_constraint(conexion, tabla: str, nombre: str) -> bool:
    return bool(
        conexion.execute(
            sa.text("SELECT 1 FROM pg_constraint WHERE conname = :nombre AND conrelid = to_regclass(:tabla)"),
            {"nombre": nombre, "tabla": tabla},
        ).scalar()
    )


def _alinear_con_los_modelos(conexion) -> None:
    for tabla, global_, por_empresa in NUMERO_POR_EMPRESA:
        if _hay_constraint(conexion, tabla, global_):
            op.drop_constraint(global_, tabla, type_="unique")
        if not _hay_constraint(conexion, tabla, por_empresa):
            op.create_unique_constraint(por_empresa, tabla, ["empresa_id", "numero"])
    for sufijo in SUFIJOS_DE_ADMIN_LICENCIAS:
        if _hay_constraint(conexion, "innovacion_licencias", f"admin_licencias_{sufijo}"):
            op.execute(
                f"ALTER TABLE innovacion_licencias RENAME CONSTRAINT admin_licencias_{sufijo} "
                f"TO innovacion_licencias_{sufijo}"
            )
    for tabla, columna in DEFAULTS_AD_HOC:
        op.alter_column(tabla, columna, server_default=None)


def upgrade() -> None:
    conexion = op.get_bind()
    if not sa.inspect(conexion).has_table("core_schema_migrations"):
        return
    aplicadas = set(conexion.execute(sa.text("SELECT id FROM core_schema_migrations")).scalars())
    faltan = [migracion for migracion in MIGRACIONES_AD_HOC if migracion not in aplicadas]
    if faltan:
        raise RuntimeError(
            "La base no aplicó todas las migraciones ad hoc de antes de Alembic (faltan: " + ", ".join(faltan) + "). "
            "Levantá una vez el backend de la última versión sin Alembic para que las aplique y repetí "
            "`alembic upgrade head` (docs/Migraciones.md, adopción)."
        )
    _alinear_con_los_modelos(conexion)
    op.drop_table("core_schema_migrations")


def downgrade() -> None:
    """No se deshace: core_schema_migrations solo la usaban las migraciones ad hoc, que ya no existen, y lo alineado es
    el esquema de los modelos."""
