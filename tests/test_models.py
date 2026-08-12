from app.db.base import Base
from app.models import User


def test_user_table_is_registered() -> None:
    assert "users" in Base.metadata.tables


def test_user_columns_exist() -> None:
    expected_columns = {
        "id",
        "email",
        "display_name",
        "is_active",
        "created_at",
        "updated_at",
    }

    assert set(User.__table__.columns.keys()) == expected_columns


def test_user_id_is_primary_key() -> None:
    primary_key_columns = {
        column.name for column in User.__table__.primary_key.columns
    }

    assert primary_key_columns == {"id"}


def test_user_email_is_unique() -> None:
    assert User.__table__.c.email.unique is True


def test_user_email_is_indexed() -> None:
    indexed_columns = {
        column.name
        for index in User.__table__.indexes
        for column in index.columns
    }

    assert "email" in indexed_columns


def test_required_user_columns_are_not_nullable() -> None:
    required_columns = {
        "id",
        "email",
        "display_name",
        "is_active",
        "created_at",
        "updated_at",
    }

    for column_name in required_columns:
        assert User.__table__.c[column_name].nullable is False