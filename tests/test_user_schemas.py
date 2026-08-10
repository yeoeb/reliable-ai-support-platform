import pytest

from pydantic import ValidationError

from datetime import UTC, datetime
from uuid import uuid4

from app.schemas.user import UserCreate, UserRead

def test_user_create_accepts_valid_input():
    user = UserCreate(
        email="alice@example.com",
        display_name="  Alice  ",
    )

    assert str(user.email) == "alice@example.com"
    assert user.display_name == "Alice"


def test_user_create_rejects_invalid_email():
    with pytest.raises(ValidationError):
        UserCreate(
            email="not-an-email",
            display_name="Alice",
        )


def test_user_create_rejects_empty_display_name():
    with pytest.raises(ValidationError):
        UserCreate(
            email="alice@example.com",
            display_name="   ",
        )


def test_user_create_rejects_extra_fields():
    with pytest.raises(ValidationError):
        UserCreate.model_validate(
            {
                "email": "alice@example.com",
                "display_name": "Alice",
                "role": "admin",
            }
        )

def test_user_read_accepts_object_attributes():
    class FakeUser:
        id = uuid4()
        email = "alice@example.com"
        display_name = "Alice"
        is_active = True
        created_at = datetime.now(UTC)
        updated_at = datetime.now(UTC)

    user = UserRead.model_validate(FakeUser())

    assert user.id == FakeUser.id
    assert str(user.email) == "alice@example.com"
    assert user.display_name == "Alice"
    assert user.is_active is True

def test_user_read_only_contains_public_fields():
    class FakeUser:
        id = uuid4()
        email = "alice@example.com"
        display_name = "Alice"
        is_active = True
        created_at = datetime.now(UTC)
        updated_at = datetime.now(UTC)

        password_hash = "should-not-be-exposed"
        internal_note = "private"

    user = UserRead.model_validate(FakeUser())

    data = user.model_dump()

    assert "password_hash" not in data
    assert "internal_note" not in data