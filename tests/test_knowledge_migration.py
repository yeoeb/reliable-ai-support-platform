from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"
EXPECTED_REVISION = "a61f9b2c3d40"


def get_head_module():
    script = ScriptDirectory.from_config(
        Config(str(ALEMBIC_INI))
    )
    head = script.get_current_head()

    assert head == EXPECTED_REVISION

    revision = script.get_revision(head)
    assert revision is not None
    return revision.module


def test_knowledge_migration_is_linear_head() -> None:
    module = get_head_module()

    assert module.revision == EXPECTED_REVISION
    assert module.down_revision == "9f3c5d7e8a10"


def test_migration_uses_stable_admin_only_permission() -> None:
    module = get_head_module()

    assert (
        module.KNOWLEDGE_MANAGE_PERMISSION_ID
        == "b3333333-3333-4333-8333-333333333333"
    )
    assert (
        module.ADMIN_ROLE_ID
        == "a3333333-3333-4333-8333-333333333333"
    )


def test_upgrade_seeds_knowledge_permission_and_admin_grant(
    monkeypatch,
) -> None:
    module = get_head_module()

    class FakeConnection:
        def __init__(self) -> None:
            self.calls = []

        def execute(
            self,
            statement,
            params,
        ):
            self.calls.append(
                (str(statement), params)
            )

    connection = FakeConnection()

    monkeypatch.setattr(
        module.op,
        "create_table",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        module.op,
        "f",
        lambda name: name,
    )
    monkeypatch.setattr(
        module.op,
        "get_bind",
        lambda: connection,
    )

    module.upgrade()

    combined_sql = "\n".join(
        sql
        for sql, _ in connection.calls
    )

    assert "knowledge:manage" in combined_sql
    assert "role_permissions" in combined_sql
    assert any(
        params.get("admin_role_id")
        == module.ADMIN_ROLE_ID
        for _, params in connection.calls
    )
    assert all(
        "support_agent" not in sql
        and "'user'" not in sql
        for sql, _ in connection.calls
    )


def test_downgrade_removes_permission_before_table(
    monkeypatch,
) -> None:
    module = get_head_module()
    events = []

    class FakeConnection:
        def execute(
            self,
            statement,
            params,
        ):
            events.append(
                ("execute", str(statement), params)
            )

    monkeypatch.setattr(
        module.op,
        "get_bind",
        lambda: FakeConnection(),
    )
    monkeypatch.setattr(
        module.op,
        "drop_table",
        lambda name: events.append(
            ("drop_table", name)
        ),
    )

    module.downgrade()

    assert events[-1] == (
        "drop_table",
        "knowledge_documents",
    )
    sql = "\n".join(
        event[1]
        for event in events[:-1]
    )
    assert "DELETE FROM role_permissions" in sql
    assert "DELETE FROM permissions" in sql
