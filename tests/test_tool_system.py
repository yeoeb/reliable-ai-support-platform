from sqlalchemy.exc import OperationalError

from app.tools import system


def test_platform_readiness_ready(monkeypatch) -> None:
    monkeypatch.setattr(
        system,
        "check_database_connection",
        lambda: None,
    )
    result = system.platform_readiness(
        system.PlatformReadinessArguments()
    )
    assert result == {"status": "ready"}


def test_platform_readiness_unavailable(monkeypatch) -> None:
    def fail():
        raise OperationalError(
            "SELECT 1",
            {},
            Exception("db down"),
        )

    monkeypatch.setattr(
        system,
        "check_database_connection",
        fail,
    )
    result = system.platform_readiness(
        system.PlatformReadinessArguments()
    )
    assert result == {"status": "unavailable"}
