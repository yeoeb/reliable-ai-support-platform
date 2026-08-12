from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.permission import Permission
from app.models.role import Role
from app.models.role_permission import RolePermission
from app.models.user_role import UserRole

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert

class RBACRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_role_by_name(self, name: str) -> Role | None:
        statement = select(Role).where(Role.name == name)
        return self.session.scalar(statement)

    def get_permission_names_for_user(
        self,
        user_id: UUID,
    ) -> set[str]:
        statement = (
            select(Permission.name)
            .join(
                RolePermission,
                RolePermission.permission_id == Permission.id,
            )
            .join(
                Role,
                Role.id == RolePermission.role_id,
            )
            .join(
                UserRole,
                UserRole.role_id == Role.id,
            )
            .where(UserRole.user_id == user_id)
            .distinct()
        )

        return set(self.session.scalars(statement).all())

    def has_permission(
        self,
        user_id: UUID,
        permission_name: str,
    ) -> bool:
        return (
            permission_name
            in self.get_permission_names_for_user(user_id)
        )

    def assign_role(
        self,
        *,
        user_id: UUID,
        role_id: UUID,
    ) -> bool:
        statement = (
            insert(UserRole)
            .values(
                user_id=user_id,
                role_id=role_id,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    UserRole.user_id,
                    UserRole.role_id,
                ]
            )
        )

        result = self.session.execute(statement)

        return result.rowcount > 0


    def remove_role(
        self,
        *,
        user_id: UUID,
        role_id: UUID,
    ) -> bool:
        statement = delete(UserRole).where(
            UserRole.user_id == user_id,
            UserRole.role_id == role_id,
        )

        result = self.session.execute(statement)

        return result.rowcount > 0

    