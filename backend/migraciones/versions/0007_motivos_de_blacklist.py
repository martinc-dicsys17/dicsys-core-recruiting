"""Recruiting: catálogo de motivos de Blacklist (recruiting_motivos_blacklist) con sus seis motivos iniciales.

Los motivos se insertan con SQL sobre la conexión, en el orden de presentación (ids 1 a 6). Si ya existe un motivo con
el mismo nombre no se pisa ni se duplica, así que la revisión es idempotente. La secuencia del id queda en el máximo.

downgrade borra la tabla y con ella lo que tuviera.

Revisión: 0007
Anterior: 0006
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0007'
down_revision: Union[str, Sequence[str], None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# En el orden en que se presentan en el combo (sin tildes: dato nuevo)
MOTIVOS = (
    "Conducta inapropiada",
    "Datos falsos en el CV",
    "Abandono del proceso",
    "Incumplimiento de acuerdos",
    "Conflicto de intereses",
    "Otro motivo",
)


def upgrade() -> None:
    op.create_table('recruiting_motivos_blacklist',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('motivo', sa.String(length=150), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('motivo')
    )
    conexion = op.get_bind()
    for numero, motivo in enumerate(MOTIVOS, start=1):
        conexion.execute(
            sa.text(
                "INSERT INTO recruiting_motivos_blacklist (id, motivo) VALUES (:id, :motivo) "
                "ON CONFLICT (motivo) DO NOTHING"
            ),
            {"id": numero, "motivo": motivo},
        )
    conexion.execute(
        sa.text(
            "SELECT setval(pg_get_serial_sequence('recruiting_motivos_blacklist', 'id'), "
            "(SELECT MAX(id) FROM recruiting_motivos_blacklist))"
        )
    )


def downgrade() -> None:
    op.drop_table('recruiting_motivos_blacklist')
