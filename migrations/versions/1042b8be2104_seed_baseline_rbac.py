"""seed baseline rbac

Revision ID: 1042b8be2104
Revises: 372ee9523e8c
Create Date: 2026-08-12 14:16:13.859780

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1042b8be2104'
down_revision: Union[str, Sequence[str], None] = '372ee9523e8c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


USER_ROLE_ID = "a1111111-1111-4111-8111-111111111111"
SUPPORT_AGENT_ROLE_ID = "a2222222-2222-4222-8222-222222222222"
ADMIN_ROLE_ID = "a3333333-3333-4333-8333-333333333333"

USERS_READ_PERMISSION_ID = "b1111111-1111-4111-8111-111111111111"
RBAC_MANAGE_PERMISSION_ID = "b2222222-2222-4222-8222-222222222222"


def upgrade() -> None:
    connection = op.get_bind()

    connection.execute(
        sa.text(
            """
            INSERT INTO roles (id, name, description)
            VALUES
                (CAST(:user_id AS uuid), 'user',
                 'Default authenticated user'),
                (CAST(:support_id AS uuid), 'support_agent',
                 'Support operations user'),
                (CAST(:admin_id AS uuid), 'admin',
                 'RBAC administrator')
            """
        ),
        {
            "user_id": USER_ROLE_ID,
            "support_id": SUPPORT_AGENT_ROLE_ID,
            "admin_id": ADMIN_ROLE_ID,
        },
    )

    connection.execute(
        sa.text(
            """
            INSERT INTO permissions (id, name, description)
            VALUES
                (CAST(:users_read_id AS uuid), 'users:read',
                 'Read user information'),
                (CAST(:rbac_manage_id AS uuid), 'rbac:manage',
                 'Manage RBAC role assignments')
            """
        ),
        {
            "users_read_id": USERS_READ_PERMISSION_ID,
            "rbac_manage_id": RBAC_MANAGE_PERMISSION_ID,
        },
    )

    connection.execute(
        sa.text(
            """
            INSERT INTO role_permissions (role_id, permission_id)
            VALUES
                (
                    CAST(:support_id AS uuid),
                    CAST(:users_read_id AS uuid)
                ),
                (
                    CAST(:admin_id AS uuid),
                    CAST(:users_read_id AS uuid)
                ),
                (
                    CAST(:admin_id AS uuid),
                    CAST(:rbac_manage_id AS uuid)
                )
            """
        ),
        {
            "support_id": SUPPORT_AGENT_ROLE_ID,
            "admin_id": ADMIN_ROLE_ID,
            "users_read_id": USERS_READ_PERMISSION_ID,
            "rbac_manage_id": RBAC_MANAGE_PERMISSION_ID,
        },
    )

    connection.execute(
        sa.text(
            """
            INSERT INTO user_roles (user_id, role_id)
            SELECT
                users.id,
                CAST(:user_role_id AS uuid)
            FROM users
            ON CONFLICT (user_id, role_id) DO NOTHING
            """
        ),
        {
            "user_role_id": USER_ROLE_ID,
        },
    )


def downgrade() -> None:
    connection = op.get_bind()

    connection.execute(
        sa.text(
            """
            DELETE FROM user_roles
            WHERE role_id = CAST(:user_role_id AS uuid)
            """
        ),
        {
            "user_role_id": USER_ROLE_ID,
        },
    )

    connection.execute(
        sa.text(
            """
            DELETE FROM role_permissions
            WHERE role_id IN (
                CAST(:support_id AS uuid),
                CAST(:admin_id AS uuid)
            )
            """
        ),
        {
            "support_id": SUPPORT_AGENT_ROLE_ID,
            "admin_id": ADMIN_ROLE_ID,
        },
    )

    connection.execute(
        sa.text(
            """
            DELETE FROM permissions
            WHERE id IN (
                CAST(:users_read_id AS uuid),
                CAST(:rbac_manage_id AS uuid)
            )
            """
        ),
        {
            "users_read_id": USERS_READ_PERMISSION_ID,
            "rbac_manage_id": RBAC_MANAGE_PERMISSION_ID,
        },
    )

    connection.execute(
        sa.text(
            """
            DELETE FROM roles
            WHERE id IN (
                CAST(:user_id AS uuid),
                CAST(:support_id AS uuid),
                CAST(:admin_id AS uuid)
            )
            """
        ),
        {
            "user_id": USER_ROLE_ID,
            "support_id": SUPPORT_AGENT_ROLE_ID,
            "admin_id": ADMIN_ROLE_ID,
        },
    )
