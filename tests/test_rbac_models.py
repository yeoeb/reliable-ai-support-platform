from sqlalchemy import UniqueConstraint

import app.models  # noqa: F401
from app.db.base import Base


def test_rbac_tables_are_registered() -> None:
    table_names = Base.metadata.tables.keys()

    assert "roles" in table_names
    assert "permissions" in table_names
    assert "user_roles" in table_names
    assert "role_permissions" in table_names


def test_role_schema() -> None:
    table = Base.metadata.tables["roles"]

    assert set(table.columns.keys()) == {
        "id",
        "name",
        "description",
    }

    assert table.c.id.primary_key is True
    assert table.c.name.nullable is False

    unique_columns = {
        tuple(constraint.columns.keys())
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert ("name",) in unique_columns


def test_permission_schema() -> None:
    table = Base.metadata.tables["permissions"]

    assert set(table.columns.keys()) == {
        "id",
        "name",
        "description",
    }

    assert table.c.id.primary_key is True
    assert table.c.name.nullable is False

    unique_columns = {
        tuple(constraint.columns.keys())
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert ("name",) in unique_columns


def test_user_role_schema() -> None:
    table = Base.metadata.tables["user_roles"]

    assert set(table.columns.keys()) == {
        "user_id",
        "role_id",
    }

    primary_key_columns = {
        column.name for column in table.primary_key.columns
    }

    assert primary_key_columns == {
        "user_id",
        "role_id",
    }

    foreign_keys = {
        foreign_key.target_fullname: foreign_key.ondelete
        for foreign_key in table.foreign_keys
    }

    assert foreign_keys == {
        "users.id": "CASCADE",
        "roles.id": "CASCADE",
    }


def test_role_permission_schema() -> None:
    table = Base.metadata.tables["role_permissions"]

    assert set(table.columns.keys()) == {
        "role_id",
        "permission_id",
    }

    primary_key_columns = {
        column.name for column in table.primary_key.columns
    }

    assert primary_key_columns == {
        "role_id",
        "permission_id",
    }

    foreign_keys = {
        foreign_key.target_fullname: foreign_key.ondelete
        for foreign_key in table.foreign_keys
    }

    assert foreign_keys == {
        "roles.id": "CASCADE",
        "permissions.id": "CASCADE",
    }