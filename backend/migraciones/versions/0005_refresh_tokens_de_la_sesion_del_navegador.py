"""Refresh tokens rotativos de la sesión del navegador (F07-P03, D-12).

Tabla auth_refresh_tokens (backend/modules/auth/models.py): se guarda el SHA-256 de cada token, su sesión (familia),
el usuario, la empresa activa, cuándo vence, cuándo se rotó y cuándo se revocó.

Revisión: 0005
Anterior: 0004
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "auth_refresh_tokens",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("jti", sa.String(length=64), nullable=False),
        sa.Column("familia", sa.UUID(), nullable=False),
        sa.Column("usuario_id", sa.UUID(), nullable=False),
        sa.Column("empresa_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expira_at", sa.DateTime(), nullable=False),
        sa.Column("rotado_at", sa.DateTime(), nullable=True),
        sa.Column("revocado_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["empresa_id"], ["core_empresas.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["usuario_id"], ["core_usuarios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("jti"),
    )
    op.create_index(op.f("ix_auth_refresh_tokens_familia"), "auth_refresh_tokens", ["familia"], unique=False)
    op.create_index(op.f("ix_auth_refresh_tokens_usuario_id"), "auth_refresh_tokens", ["usuario_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_auth_refresh_tokens_usuario_id"), table_name="auth_refresh_tokens")
    op.drop_index(op.f("ix_auth_refresh_tokens_familia"), table_name="auth_refresh_tokens")
    op.drop_table("auth_refresh_tokens")
