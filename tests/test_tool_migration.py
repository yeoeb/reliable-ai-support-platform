import importlib.util
from pathlib import Path
from unittest.mock import MagicMock


ROOT = Path(__file__).resolve().parents[1]
PATH = (
    ROOT
    / "migrations"
    / "versions"
    / "d94c6e7f8a03_add_system_read_tool_permission.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location(
        "tool_permission_migration",
        PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tool_permission_migration_contract(
    monkeypatch,
) -> None:
    module = load_module()
    connection = MagicMock()
    monkeypatch.setattr(
        module.op,
        "get_bind",
        lambda: connection,
    )

    module.upgrade()

    assert connection.execute.call_count == 2
    permission_sql = str(
        connection.execute.call_args_list[0].args[0]
    )
    grants_sql = str(
        connection.execute.call_args_list[1].args[0]
    )
    assert "system:read" in permission_sql
    assert "role_permissions" in grants_sql
    params = connection.execute.call_args_list[1].args[1]
    assert params["support_role_id"] == (
        module.SUPPORT_AGENT_ROLE_ID
    )
    assert params["admin_role_id"] == module.ADMIN_ROLE_ID
    assert "user_role_id" not in params

    connection.reset_mock()
    module.downgrade()
    assert connection.execute.call_count == 2
