"""Secretos de usuario en claro a hash: códigos de respaldo del 2FA (F02-P02) y magic links pendientes (F02-P03).

Antes corría en cada arranque del backend. Como revisión corre una vez por base, y también en una restaurada de un
backup de antes de Alembic, que se adopta con stamp + upgrade y pasa por acá. Los códigos y links que ya tienen los
usuarios siguen valiendo: la validación hashea lo que llega.

Revisión: 0003
Anterior: 0002
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from backend.modules.usuarios import secretos

revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conexion = op.get_bind()
    codigos = conexion.execute(
        sa.text("SELECT id, totp_backup_codes FROM core_usuarios WHERE totp_backup_codes IS NOT NULL")
    ).all()
    for usuario_id, guardados in codigos:
        migrados = secretos.migrar(guardados)
        if migrados is not None:
            conexion.execute(
                sa.text("UPDATE core_usuarios SET totp_backup_codes = :c WHERE id = :id"),
                {"c": migrados, "id": usuario_id},
            )

    links = conexion.execute(
        sa.text(
            "SELECT id, magic_link_token FROM core_usuarios "
            "WHERE magic_link_token IS NOT NULL AND magic_link_token NOT LIKE :prefijo"
        ),
        {"prefijo": secretos.PREFIJO_MAGIC_LINK + "%"},
    ).all()
    for usuario_id, token in links:
        conexion.execute(
            sa.text("UPDATE core_usuarios SET magic_link_token = :t WHERE id = :id"),
            {"t": secretos.hash_magic_link(token), "id": usuario_id},
        )


def downgrade() -> None:
    """Un hash no vuelve a quedar en claro, y la app solo valida contra el hash: no hay nada que deshacer."""
