import pytest

import app.db.session as db_session


class FakeSession:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def test_get_db_closes_session(monkeypatch):
    fake_session = FakeSession()

    monkeypatch.setattr(
        db_session,
        "SessionLocal",
        lambda: fake_session,
    )

    generator = db_session.get_db()

    db = next(generator)

    assert db is fake_session

    with pytest.raises(StopIteration):
        next(generator)

    assert fake_session.closed is True
def test_get_db_closes_session_when_exception_occurs(monkeypatch):
    fake_session = FakeSession()

    monkeypatch.setattr(
        db_session,
        "SessionLocal",
        lambda: fake_session,
    )

    generator = db_session.get_db()

    db = next(generator)

    assert db is fake_session

    with pytest.raises(RuntimeError):
        generator.throw(RuntimeError("route failed"))

    assert fake_session.closed is True