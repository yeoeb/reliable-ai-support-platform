import subprocess
import time

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def run_docker_compose(*args: str) -> None:
    subprocess.run(
        ["docker", "compose", *args],
        check=True,
    )


def wait_for_readiness(
    expected_status: int,
    *,
    timeout_seconds: float = 10.0,
    poll_seconds: float = 0.25,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_status: int | None = None

    while time.monotonic() < deadline:
        response = client.get("/health/ready")
        last_status = response.status_code

        if last_status == expected_status:
            return

        time.sleep(poll_seconds)

    raise AssertionError(
        "readiness did not reach expected status "
        f"{expected_status}; last status was {last_status}"
    )


def test_readiness_recovers_after_database_restart():
    run_docker_compose("start", "postgres")
    wait_for_readiness(200)

    run_docker_compose("stop", "postgres")
    wait_for_readiness(503)

    run_docker_compose("start", "postgres")
    wait_for_readiness(200)
