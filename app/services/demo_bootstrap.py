from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import RoleNotFoundError
from app.integrations.embeddings import EmbeddingProvider
from app.models.user_role import UserRole
from app.repositories.rbac import RBACRepository
from app.repositories.user import UserRepository
from app.schemas.knowledge import KnowledgeDocumentCreate
from app.schemas.user import UserCreate
from app.services.auth import authenticate_user
from app.services.embedding import EmbeddingService
from app.services.knowledge import KnowledgeService
from app.services.rbac import RBACService
from app.services.user import UserService


DEMO_KNOWLEDGE_FILES = (
    ("Password reset", "password-reset.md"),
    ("VPN access", "vpn-access.md"),
    ("Escalation policy", "escalation-policy.md"),
)


class DemoBootstrapError(Exception):
    """Base error for the development-only demo bootstrap."""


class DemoEnvironmentError(DemoBootstrapError):
    """Raised when the bootstrap is requested outside development."""


class ExistingUserPromotionRequiredError(DemoBootstrapError):
    """Raised when an authenticated non-admin was not opted into promotion."""


class LiveAIConfigurationError(DemoBootstrapError):
    """Raised when live AI was enabled without a configured provider."""


@dataclass(frozen=True)
class DemoKnowledgeSeed:
    title: str
    source_name: str
    content: str


@dataclass(frozen=True)
class DemoKnowledgeResult:
    document_id: UUID
    source_name: str
    changed: bool
    embedded: bool
    embedding_changed: bool | None


@dataclass(frozen=True)
class DemoBootstrapResult:
    administrator_user_id: UUID
    administrator_created: bool
    admin_role_changed: bool
    knowledge: tuple[DemoKnowledgeResult, ...]
    live_ai_enabled: bool


def load_demo_knowledge(directory: Path) -> tuple[DemoKnowledgeSeed, ...]:
    root = directory.resolve(strict=True)
    seeds: list[DemoKnowledgeSeed] = []

    for title, filename in DEMO_KNOWLEDGE_FILES:
        path = (root / filename).resolve(strict=True)
        if path.parent != root:
            raise ValueError("Demo Knowledge path escaped its configured root")

        seeds.append(
            DemoKnowledgeSeed(
                title=title,
                source_name=f"demo/{filename}",
                content=path.read_text(encoding="utf-8"),
            )
        )

    return tuple(seeds)


class DemoBootstrapService:
    def __init__(
        self,
        session: Session,
        *,
        app_env: str,
        embedding_provider: EmbeddingProvider | None = None,
        embedding_model: str = "text-embedding-3-small",
        embedding_dimensions: int = 1536,
        embedding_batch_size: int = 32,
        chunk_size: int = 1000,
        chunk_overlap: int = 150,
    ) -> None:
        self.session = session
        self.app_env = app_env
        self.user_repository = UserRepository(session)
        self.rbac_repository = RBACRepository(session)
        self.user_service = UserService(session)
        self.rbac_service = RBACService(session)
        self.knowledge_service = KnowledgeService(session)
        self.embedding_service = (
            EmbeddingService(
                session,
                embedding_provider,
                embedding_model=embedding_model,
                embedding_dimensions=embedding_dimensions,
                embedding_batch_size=embedding_batch_size,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
            if embedding_provider is not None
            else None
        )

    def _require_development(self) -> None:
        if self.app_env.strip().lower() != "development":
            raise DemoEnvironmentError(
                "Demo bootstrap is allowed only in development"
            )

    def _has_admin_role(self, user_id: UUID) -> bool:
        role = self.rbac_repository.get_role_by_name("admin")
        if role is None:
            raise RoleNotFoundError

        statement = select(UserRole.user_id).where(
            UserRole.user_id == user_id,
            UserRole.role_id == role.id,
        )
        return self.session.scalar(statement) is not None

    def _resolve_administrator(
        self,
        *,
        data: UserCreate,
        promote_existing: bool,
    ) -> tuple[UUID, bool, bool]:
        email = str(data.email)
        existing = self.user_repository.get_by_email(email)

        if existing is None:
            user = self.user_service.create_user(data)
            self.rbac_service.assign_role(
                actor_user_id=user.id,
                user_id=user.id,
                role_name="admin",
            )
            return user.id, True, True

        user = authenticate_user(
            self.session,
            email=email,
            password=data.password,
        )

        if self._has_admin_role(user.id):
            self.session.rollback()
            return user.id, False, False

        if not promote_existing:
            self.session.rollback()
            raise ExistingUserPromotionRequiredError(
                "Existing authenticated user is not an administrator"
            )

        self.rbac_service.assign_role(
            actor_user_id=user.id,
            user_id=user.id,
            role_name="admin",
        )
        return user.id, False, True

    def bootstrap(
        self,
        *,
        administrator: UserCreate,
        knowledge_seeds: Sequence[DemoKnowledgeSeed],
        promote_existing: bool = False,
        enable_live_ai: bool = False,
    ) -> DemoBootstrapResult:
        self._require_development()

        if enable_live_ai and self.embedding_service is None:
            raise LiveAIConfigurationError(
                "Live AI requires a configured embedding provider"
            )

        try:
            user_id, user_created, role_changed = (
                self._resolve_administrator(
                    data=administrator,
                    promote_existing=promote_existing,
                )
            )

            knowledge_results: list[DemoKnowledgeResult] = []
            for seed in knowledge_seeds:
                ingest_result = self.knowledge_service.ingest(
                    actor_user_id=user_id,
                    data=KnowledgeDocumentCreate(
                        title=seed.title,
                        source_type="markdown",
                        source_name=seed.source_name,
                        content=seed.content,
                    ),
                )

                embedding_changed: bool | None = None
                if enable_live_ai:
                    assert self.embedding_service is not None
                    embedding_result = (
                        self.embedding_service.embed_document(
                            actor_user_id=user_id,
                            document_id=ingest_result.document.id,
                        )
                    )
                    embedding_changed = embedding_result.changed

                knowledge_results.append(
                    DemoKnowledgeResult(
                        document_id=ingest_result.document.id,
                        source_name=seed.source_name,
                        changed=ingest_result.changed,
                        embedded=enable_live_ai,
                        embedding_changed=embedding_changed,
                    )
                )

            return DemoBootstrapResult(
                administrator_user_id=user_id,
                administrator_created=user_created,
                admin_role_changed=role_changed,
                knowledge=tuple(knowledge_results),
                live_ai_enabled=enable_live_ai,
            )
        except Exception:
            self.session.rollback()
            raise
