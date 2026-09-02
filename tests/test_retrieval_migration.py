from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"
EXPECTED_REVISION = "c83b5d6e7f92"


def get_module():
    script = ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))
    revision = script.get_revision(EXPECTED_REVISION)
    assert revision is not None
    return revision.module


def test_retrieval_migration_is_linear_head() -> None:
    script = ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))
    assert script.get_heads() == [EXPECTED_REVISION]
    assert get_module().down_revision == "b72a4c5d6e81"


def test_upgrade_adds_btree_index_and_support_admin_permission(
    monkeypatch,
) -> None:
    module = get_module()
    events = []

    class FakeConnection:
        def execute(self, statement, params):
            events.append(("execute", str(statement), params))

    monkeypatch.setattr(
        module.op,
        "create_index",
        lambda *args, **kwargs: events.append(
            ("create_index", args, kwargs)
        ),
    )
    monkeypatch.setattr(
        module.op,
        "get_bind",
        lambda: FakeConnection(),
    )

    module.upgrade()

    index_event = events[0]
    assert index_event[0] == "create_index"
    assert index_event[1][0] == (
        "ix_knowledge_chunks_embedding_config_hash"
    )
    assert index_event[1][1] == "knowledge_chunks"
    assert index_event[1][2] == ["embedding_config_hash"]

    sql = "\n".join(
        event[1]
        for event in events
        if event[0] == "execute"
    )
    assert "knowledge:read" in sql
    assert "role_permissions" in sql
    assert "'user'" not in sql

    grant_params = next(
        event[2]
        for event in events
        if event[0] == "execute"
        and "role_permissions" in event[1]
    )
    assert grant_params["support_role_id"] == module.SUPPORT_AGENT_ROLE_ID
    assert grant_params["admin_role_id"] == module.ADMIN_ROLE_ID


def test_permission_uuid_is_stable() -> None:
    module = get_module()
    assert (
        module.KNOWLEDGE_READ_PERMISSION_ID
        == "b4444444-4444-4444-8444-444444444444"
    )


def test_downgrade_removes_permission_and_index(
    monkeypatch,
) -> None:
    module = get_module()
    events = []

    class FakeConnection:
        def execute(self, statement, params):
            events.append(("execute", str(statement), params))

    monkeypatch.setattr(module.op, "get_bind", lambda: FakeConnection())
    monkeypatch.setattr(
        module.op,
        "drop_index",
        lambda *args, **kwargs: events.append(
            ("drop_index", args, kwargs)
        ),
    )

    module.downgrade()

    sql = "\n".join(
        event[1]
        for event in events
        if event[0] == "execute"
    )
    assert "DELETE FROM role_permissions" in sql
    assert "DELETE FROM permissions" in sql
    assert events[-1][0] == "drop_index"
    assert events[-1][1][0] == (
        "ix_knowledge_chunks_embedding_config_hash"
    )


def test_migration_does_not_create_ann_index() -> None:
    source = Path(get_module().__file__).read_text(
        encoding="utf-8"
    ).lower()
    assert "hnsw" not in source
    assert "ivfflat" not in source
    assert "vector_cosine_ops" not in source
