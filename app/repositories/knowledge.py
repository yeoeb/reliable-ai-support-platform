from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.knowledge_document import KnowledgeDocument


class KnowledgeRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(
        self,
        document_id: UUID,
    ) -> KnowledgeDocument | None:
        statement = select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id
        )
        return self.session.scalar(statement)

    def get_by_source_name_and_hash(
        self,
        *,
        source_name: str,
        content_hash: str,
    ) -> KnowledgeDocument | None:
        statement = select(KnowledgeDocument).where(
            KnowledgeDocument.source_name == source_name,
            KnowledgeDocument.content_hash == content_hash,
        )
        return self.session.scalar(statement)

    def create(
        self,
        *,
        title: str,
        source_type: str,
        source_name: str,
        content: str,
        content_hash: str,
        created_by_user_id: UUID,
    ) -> KnowledgeDocument:
        document = KnowledgeDocument(
            title=title,
            source_type=source_type,
            source_name=source_name,
            content=content,
            content_hash=content_hash,
            created_by_user_id=created_by_user_id,
        )
        self.session.add(document)
        self.session.flush()
        return document
