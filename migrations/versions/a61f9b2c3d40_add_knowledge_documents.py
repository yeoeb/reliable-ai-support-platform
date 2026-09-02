"""add knowledge documents and knowledge manage permission

Revision ID: a61f9b2c3d40
Revises: 9f3c5d7e8a10
Create Date: 2026-09-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a61f9b2c3d40"
down_revision: Union[str, Sequence[str], None] = "9f3c5d7e8a10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ADMIN_ROLE_ID = "a3333333-3333-4333-8333-333333333333"
KNOWLEDGE_MANAGE_PERMISSION_ID = (
    "b3333333-3333-4333-8333-333333333333"
)


def upgrade() -> None:
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("source_name", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name=op.f("pk_knowledge_documents"),
        ),
        sa.UniqueConstraint(
            "source_name",
            "content_hash",
            name=(
                "uq_knowledge_documents_"
                "source_name_content_hash"
            ),
        ),
    )

    connection = op.get_bind()

    connection.execute(
        sa.text(
            """
            INSERT INTO permissions (id, name, description)
            VALUES (
                CAST(:permission_id AS uuid),
                'knowledge:manage',
                'Manage knowledge document ingestion'
            )
            """
        ),
        {
            "permission_id": KNOWLEDGE_MANAGE_PERMISSION_ID,
        },
    )

    connection.execute(
        sa.text(
            """
            INSERT INTO role_permissions (role_id, permission_id)
            VALUES (
                CAST(:admin_role_id AS uuid),
                CAST(:permission_id AS uuid)
            )
            """
        ),
        {
            "admin_role_id": ADMIN_ROLE_ID,
            "permission_id": KNOWLEDGE_MANAGE_PERMISSION_ID,
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
            "permission_id": KNOWLEDGE_MANAGE_PERMISSION_ID,
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
            "permission_id": KNOWLEDGE_MANAGE_PERMISSION_ID,
        },
    )

    op.drop_table("knowledge_documents")
