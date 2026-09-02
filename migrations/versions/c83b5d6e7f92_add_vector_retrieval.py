"""add exact vector retrieval permission and config index

Revision ID: c83b5d6e7f92
Revises: b72a4c5d6e81
Create Date: 2026-09-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c83b5d6e7f92"
down_revision: Union[str, Sequence[str], None] = "b72a4c5d6e81"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SUPPORT_AGENT_ROLE_ID = "a2222222-2222-4222-8222-222222222222"
ADMIN_ROLE_ID = "a3333333-3333-4333-8333-333333333333"
KNOWLEDGE_READ_PERMISSION_ID = (
    "b4444444-4444-4444-8444-444444444444"
)


def upgrade() -> None:
    op.create_index(
        "ix_knowledge_chunks_embedding_config_hash",
        "knowledge_chunks",
        ["embedding_config_hash"],
    )

    connection = op.get_bind()

    connection.execute(
        sa.text(
            """
            INSERT INTO permissions (id, name, description)
            VALUES (
                CAST(:permission_id AS uuid),
                'knowledge:read',
                'Read internal knowledge retrieval results'
            )
            """
        ),
        {
            "permission_id": KNOWLEDGE_READ_PERMISSION_ID,
        },
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
            "permission_id": KNOWLEDGE_READ_PERMISSION_ID,
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
        {
            "permission_id": KNOWLEDGE_READ_PERMISSION_ID,
        },
    )

    connection.execute(
        sa.text(
            """
            DELETE FROM permissions
            WHERE id = CAST(:permission_id AS uuid)
            """
        ),
        {
            "permission_id": KNOWLEDGE_READ_PERMISSION_ID,
        },
    )

    op.drop_index(
        "ix_knowledge_chunks_embedding_config_hash",
        table_name="knowledge_chunks",
    )
