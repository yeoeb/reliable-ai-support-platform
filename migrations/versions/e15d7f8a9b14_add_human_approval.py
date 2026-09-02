"""add durable human approval

Revision ID: e15d7f8a9b14
Revises: d94c6e7f8a03
Create Date: 2026-09-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e15d7f8a9b14"
down_revision: Union[str, Sequence[str], None] = "d94c6e7f8a03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ADMIN_ROLE_ID = "a3333333-3333-4333-8333-333333333333"
APPROVAL_DECIDE_PERMISSION_ID = (
    "b6666666-6666-4666-8666-666666666666"
)


def upgrade() -> None:
    op.create_table(
        "approval_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "requested_by_user_id",
            sa.Uuid(),
            nullable=False,
        ),
        sa.Column(
            "tool_name",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "arguments",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "decided_by_user_id",
            sa.Uuid(),
            nullable=True,
        ),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "executed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint(
            "id",
            name=op.f("pk_approval_requests"),
        ),
    )
    op.create_index(
        op.f("ix_approval_requests_requested_by_user_id"),
        "approval_requests",
        ["requested_by_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_approval_requests_status"),
        "approval_requests",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_approval_requests_expires_at"),
        "approval_requests",
        ["expires_at"],
        unique=False,
    )

    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            INSERT INTO permissions (id, name, description)
            VALUES (
                CAST(:permission_id AS uuid),
                'approval:decide',
                'Inspect and decide pending higher-risk tool actions'
            )
            """
        ),
        {
            "permission_id": APPROVAL_DECIDE_PERMISSION_ID,
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
            "permission_id": APPROVAL_DECIDE_PERMISSION_ID,
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
            "permission_id": APPROVAL_DECIDE_PERMISSION_ID,
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
            "permission_id": APPROVAL_DECIDE_PERMISSION_ID,
        },
    )

    op.drop_index(
        op.f("ix_approval_requests_expires_at"),
        table_name="approval_requests",
    )
    op.drop_index(
        op.f("ix_approval_requests_status"),
        table_name="approval_requests",
    )
    op.drop_index(
        op.f("ix_approval_requests_requested_by_user_id"),
        table_name="approval_requests",
    )
    op.drop_table("approval_requests")
