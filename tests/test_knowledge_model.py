from sqlalchemy import UniqueConstraint

from app.models.knowledge_document import KnowledgeDocument


def test_knowledge_document_schema_contract() -> None:
    table = KnowledgeDocument.__table__

    assert table.name == "knowledge_documents"

    columns = table.c
    assert columns.title.type.length == 200
    assert columns.source_type.type.length == 20
    assert columns.source_name.type.length == 255
    assert columns.content_hash.type.length == 64
    assert columns.content.nullable is False
    assert columns.created_by_user_id.nullable is False
    assert not columns.created_by_user_id.foreign_keys

    unique_constraints = [
        constraint
        for constraint in table.constraints
        if isinstance(
            constraint,
            UniqueConstraint,
        )
    ]
    assert any(
        [
            column.name
            for column in constraint.columns
        ]
        == ["source_name", "content_hash"]
        for constraint in unique_constraints
    )
