from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, ForeignKeyConstraint, UniqueConstraint


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"
EXPECTED_REVISION = "b72a4c5d6e81"


def get_embedding_migration_module():
    script = ScriptDirectory.from_config(
        Config(str(ALEMBIC_INI))
    )
    revision = script.get_revision(
        EXPECTED_REVISION
    )
    assert revision is not None
    return revision.module


def test_embedding_migration_is_linear_head() -> None:
    script = ScriptDirectory.from_config(
        Config(str(ALEMBIC_INI))
    )

    assert script.get_heads() == [
        EXPECTED_REVISION
    ]

    module = get_embedding_migration_module()
    assert module.revision == EXPECTED_REVISION
    assert module.down_revision == "a61f9b2c3d40"


def test_upgrade_enables_vector_and_creates_vector_1536(
    monkeypatch,
) -> None:
    module = get_embedding_migration_module()
    events = []

    monkeypatch.setattr(
        module.op,
        "execute",
        lambda statement: events.append(
            ("execute", statement)
        ),
    )
    monkeypatch.setattr(
        module.op,
        "f",
        lambda name: name,
    )

    def create_table(name, *items, **kwargs):
        events.append(
            ("create_table", name, items)
        )

    monkeypatch.setattr(
        module.op,
        "create_table",
        create_table,
    )
    monkeypatch.setattr(
        module.op,
        "create_index",
        lambda *args, **kwargs: events.append(
            ("create_index", args, kwargs)
        ),
    )

    module.upgrade()

    assert events[0] == (
        "execute",
        "CREATE EXTENSION IF NOT EXISTS vector",
    )

    create_event = next(
        event
        for event in events
        if event[0] == "create_table"
    )
    assert create_event[1] == "knowledge_chunks"

    items = create_event[2]
    columns = {
        item.name: item
        for item in items
        if isinstance(item, Column)
    }

    assert isinstance(
        columns["embedding"].type,
        Vector,
    )
    assert columns["embedding"].type.dim == 1536

    fk = next(
        item
        for item in items
        if isinstance(
            item,
            ForeignKeyConstraint,
        )
    )
    assert fk.ondelete == "CASCADE"

    unique = next(
        item
        for item in items
        if isinstance(
            item,
            UniqueConstraint,
        )
    )
    assert [
        column.name
        for column in unique.columns
    ] == [
        "document_id",
        "chunk_index",
        "embedding_config_hash",
    ]


def test_downgrade_drops_table_but_not_vector_extension(
    monkeypatch,
) -> None:
    module = get_embedding_migration_module()
    events = []

    monkeypatch.setattr(
        module.op,
        "drop_index",
        lambda *args, **kwargs: events.append(
            ("drop_index", args, kwargs)
        ),
    )
    monkeypatch.setattr(
        module.op,
        "drop_table",
        lambda name: events.append(
            ("drop_table", name)
        ),
    )
    monkeypatch.setattr(
        module.op,
        "execute",
        lambda statement: events.append(
            ("execute", statement)
        ),
    )

    module.downgrade()

    assert (
        "drop_table",
        "knowledge_chunks",
    ) in events
    assert not any(
        event[0] == "execute"
        and "DROP EXTENSION" in event[1]
        for event in events
    )
