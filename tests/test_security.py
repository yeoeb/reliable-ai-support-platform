from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest

from app.core.config import settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_password_does_not_return_plaintext():
    password = "correct-horse-battery-staple"

    password_hash = hash_password(password)

    assert password_hash != password


def test_verify_password_accepts_correct_password():
    password = "correct-horse-battery-staple"
    password_hash = hash_password(password)

    assert verify_password(password, password_hash) is True


def test_verify_password_rejects_wrong_password():
    password_hash = hash_password(
        "correct-horse-battery-staple"
    )

    assert verify_password(
        "wrong-password",
        password_hash,
    ) is False


def test_access_token_contains_subject():
    user_id = uuid4()

    token = create_access_token(user_id)
    payload = decode_access_token(token)

    assert payload["sub"] == str(user_id)


def test_access_token_contains_iat_and_exp():
    token = create_access_token(uuid4())
    payload = decode_access_token(token)

    assert "iat" in payload
    assert "exp" in payload


def test_decode_rejects_expired_token():
    now = datetime.now(timezone.utc)

    payload = {
        "sub": str(uuid4()),
        "iat": now - timedelta(minutes=10),
        "exp": now - timedelta(minutes=5),
    }

    token = jwt.encode(
        payload,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_decode_rejects_token_without_subject():
    now = datetime.now(timezone.utc)

    token = jwt.encode(
        {
            "iat": now,
            "exp": now + timedelta(minutes=5),
        },
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token)