"""add controlled tool calling permission

Revision ID: d94c6e7f8a03
Revises: c83b5d6e7f92
Create Date: 2026-09-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d94c6e7f8a03"
down_revision: Union[str, Sequence[str], None] = "c83b5d6e7f92"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SUPPORT_AGENT_ROLE_ID = "a2222222-2222-4222-8222-222222222222"
ADMIN_ROLE_ID = "a3333333-3333-4333-8333-333333333333"
SYSTEM_READ_PERMISSION_ID = "b5555555-5555-4555-8555-555555555555"


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            INSERT INTO permissions (id, name, description)
            VALUES (
                CAST(:permission_id AS uuid),
                'system:read',
                'Read bounded internal platform diagnostics'
            )
            """
        ),
        {"permission_id": SYSTEM_READ_PERMISSION_ID},
    )
    connection.execute(
        sa.text(
            """
            INSERT INTO role_permissions (role_id, permission_id)
            VALUES
                (
                    CAST(:support_role_id AS uuid),
                    CAST(:permission_id AS uuid)
                ),
                (
                    CAST(:admin_role_id AS uuid),
                    CAST(:permission_id AS uuid)
                )
            """
        ),
        {
            "support_role_id": SUPPORT_AGENT_ROLE_ID,
            "admin_role_id": ADMIN_ROLE_ID,
            "permission_id": SYSTEM_READ_PERMISSION_ID,
        },
    )


def downgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            DELETE FROM role_permissions
            WHERE permission_id = CAST(:permission_id AS uuid)
            """
        ),
        {"permission_id": SYSTEM_READ_PERMISSION_ID},
    )
    connection.execute(
        sa.text(
            """
            DELETE FROM permissions
            WHERE id = CAST(:permission_id AS uuid)
            """
        ),
        {"permission_id": SYSTEM_READ_PERMISSION_ID},
    )
