from __future__ import annotations

import logging
from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.errors import (
    InvalidKnowledgeContentError,
    PersistenceUnavailableError,
)
from app.models.knowledge_document import KnowledgeDocument
from app.repositories.knowledge import KnowledgeRepository
from app.schemas.knowledge import KnowledgeDocumentCreate
from app.services.audit import AuditService


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class KnowledgeIngestResult:
    document: KnowledgeDocument
    changed: bool


def normalize_knowledge_content(content: str) -> str:
    normalized = (
        content.replace("\r\n", "\n")
        .replace("\r", "\n")
        .strip()
    )

    if not normalized:
        raise InvalidKnowledgeContentError(
            "Knowledge content is empty after normalization"
        )

    return normalized


def hash_knowledge_content(content: str) -> str:
    return sha256(
        content.encode("utf-8")
    ).hexdigest()


class KnowledgeService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = KnowledgeRepository(session)
        self.audit_service = AuditService(session)

    def ingest(
        self,
        *,
        actor_user_id: UUID,
        data: KnowledgeDocumentCreate,
    ) -> KnowledgeIngestResult:
        normalized_content = normalize_knowledge_content(
            data.content
        )
        content_hash = hash_knowledge_content(
            normalized_content
        )
        content_length = len(normalized_content)

        try:
            document = (
                self.repository.get_by_source_name_and_hash(
                    source_name=data.source_name,
                    content_hash=content_hash,
                )
            )
            changed = False

            if document is None:
                try:
                    with self.session.begin_nested():
                        document = self.repository.create(
                            title=data.title,
                            source_type=data.source_type,
                            source_name=data.source_name,
                            content=normalized_content,
                            content_hash=content_hash,
                            created_by_user_id=actor_user_id,
                        )
                    changed = True
                except IntegrityError:
                    document = (
                        self.repository
                        .get_by_source_name_and_hash(
                            source_name=data.source_name,
                            content_hash=content_hash,
                        )
                    )
                    if document is None:
                        raise
                    changed = False

            self.audit_service.record(
                actor_user_id=actor_user_id,
                action="knowledge.document.ingest",
                target_type="knowledge_document",
                target_id=str(document.id),
                outcome="success",
                event_metadata={
                    "source_type": document.source_type,
                    "content_hash": document.content_hash,
                    "content_length": len(document.content),
                    "changed": changed,
                },
            )

            self.session.commit()

            logger.info(
                "Knowledge document ingested",
                extra={
                    "event": "knowledge.document.ingested",
                    "document_id": str(document.id),
                    "source_type": document.source_type,
                    "content_length": len(document.content),
                    "changed": changed,
                },
            )

            return KnowledgeIngestResult(
                document=document,
                changed=changed,
            )

        except SQLAlchemyError as exc:
            self.session.rollback()

            logger.error(
                "Knowledge document persistence failed",
                extra={
                    "event": (
                        "knowledge.document."
                        "persistence_failure"
                    ),
                    "source_type": data.source_type,
                    "content_length": content_length,
                },
            )

            raise PersistenceUnavailableError from exc
