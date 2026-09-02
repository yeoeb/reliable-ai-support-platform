from fastapi import FastAPI

from app.api.middleware.request_logging import RequestLoggingMiddleware
from app.api.routes.admin import router as admin_router
from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.api.routes.users import router as users_router
from app.core.config import settings
from app.core.logging import configure_logging


configure_logging(settings.log_level)

app = FastAPI(
    title="Reliable AI Support Operations Platform",
    description="Enterprise AI support backend",
    version="0.1.0",
)

app.include_router(health_router)
app.include_router(users_router)
app.include_router(auth_router)
app.include_router(admin_router)