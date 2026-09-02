import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB


ROOT = Path(__file__).resolve().parents[1]
PATH = (
    ROOT
    / "migrations"
    / "versions"
    / "e15d7f8a9b14_add_human_approval.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location(
        "approval_migration",
        PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_approval_migration_contract(
    monkeypatch,
) -> None:
    module = load_module()
    connection = MagicMock()
    created = {}

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
    monkeypatch.setattr(
        module.op,
        "create_table",
        lambda name, *items, **kwargs: created.update(
            {
                "name": name,
                "items": items,
            }
        ),
    )
    monkeypatch.setattr(
        module.op,
        "create_index",
        lambda *args, **kwargs: None,
    )

    module.upgrade()

    assert module.down_revision == "d94c6e7f8a03"
    assert created["name"] == "approval_requests"

    columns = {
        item.name: item
        for item in created["items"]
        if isinstance(item, Column)
    }
    assert isinstance(
        columns["arguments"].type,
        JSONB,
    )
    assert columns["expires_at"].nullable is False
    assert columns["executed_at"].nullable is True

    assert connection.execute.call_count == 2
    permission_sql = str(
        connection.execute.call_args_list[0].args[0]
    )
    grants_sql = str(
        connection.execute.call_args_list[1].args[0]
    )
    assert "approval:decide" in permission_sql
    assert "role_permissions" in grants_sql

    grant_params = (
        connection.execute.call_args_list[1].args[1]
    )
    assert grant_params == {
        "admin_role_id": module.ADMIN_ROLE_ID,
        "permission_id": (
            module.APPROVAL_DECIDE_PERMISSION_ID
        ),
    }
    assert "support_role_id" not in grant_params
    assert "user_role_id" not in grant_params


def test_approval_migration_downgrade_removes_grant_permission_and_table(
    monkeypatch,
) -> None:
    module = load_module()
    connection = MagicMock()
    events = []

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

    module.downgrade()

    assert connection.execute.call_count == 2
    assert events[-1] == (
        "drop_table",
        "approval_requests",
    )
