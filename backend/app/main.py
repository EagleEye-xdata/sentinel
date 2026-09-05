import logging
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session
from .database import Base, engine, get_db
from .config import settings
from .services.session_window import session_windows
from .api.inspect import inspect_session

# Import API routers
from .api.targets import router as targets_router
from .api.attacks import router as attacks_router
from .api.inspect import router as inspect_router
from .api.tests import router as tests_router
from .api.proxy import router as proxy_router
from .api.reports import router as reports_router
from .api.alerts import router as alerts_router

logger = logging.getLogger("eaglei.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Tables are created on startup rather than at import time, so importing
    # this module (tests, tooling) does not require a reachable database.
    Base.metadata.create_all(engine)
    yield


app = FastAPI(
    title="eagleI — AI Security Testing & Inspection Platform",
    description="3-Panel Architecture: Injection -> Chatbox -> Analyzer",
    version="1.0.0",
    lifespan=lifespan,
)


# CORS Configuration. Origins come from EAGLEI_CORS_ORIGINS (comma-separated).
# Set it to "*" to allow any origin; credentials are then disabled, because
# browsers reject a wildcard origin combined with Allow-Credentials.
_configured = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
_allow_any = "*" in _configured

_default_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]
_origins = ["*"] if _allow_any else sorted(set(_configured) | set(_default_origins))

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=not _allow_any,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


@app.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        database = "connected"
        status = "ok"
    except Exception as exc:
        logger.error(f"Health check database probe failed: {exc}")
        database = "unavailable"
        status = "degraded"

    return {
        "status": status,
        "database": database,
        "judge_provider": settings.judge_provider,
        "mode": "3-panel-unified"
    }


# Include Routers
app.include_router(targets_router)
app.include_router(attacks_router)
app.include_router(inspect_router)
app.include_router(tests_router)
app.include_router(proxy_router)
app.include_router(reports_router)
app.include_router(alerts_router)

__all__ = ["app", "inspect_session", "session_windows"]
