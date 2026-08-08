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


def test_readiness_recovers_after_database_restart():
    run_docker_compose("start", "postgres")
    time.sleep(2)

    response = client.get("/health/ready")
    assert response.status_code == 200

    run_docker_compose("stop", "postgres")

    response = client.get("/health/ready")
    assert response.status_code == 503

    run_docker_compose("start", "postgres")
    time.sleep(2)

    response = client.get("/health/ready")
    assert response.status_code == 200