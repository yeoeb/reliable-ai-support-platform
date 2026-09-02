from uuid import UUID

from app.repositories.rbac import RBACRepository


class AuthorizationService:
    def __init__(
        self,
        rbac_repository: RBACRepository,
    ) -> None:
        self.rbac_repository = rbac_repository

    def get_effective_permissions(
        self,
        user_id: UUID,
    ) -> set[str]:
        return self.rbac_repository.get_permission_names_for_user(
            user_id
        )

    def has_permission(
        self,
        *,
        user_id: UUID,
        permission: str,
    ) -> bool:
        permissions = self.get_effective_permissions(user_id)

        return permission in permissions