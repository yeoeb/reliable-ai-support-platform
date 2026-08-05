from fastapi import FastAPI

from app.api.routes.health import router as health_router


app = FastAPI(
    title="Reliable AI Support Operations Platform",
    description="Enterprise AI support backend",
    version="0.1.0",
)

app.include_router(health_router)