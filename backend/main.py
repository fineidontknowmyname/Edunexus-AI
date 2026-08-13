"""
backend/main.py — EduNexus AI FastAPI application entry point.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import get_settings
from backend.core.database import Base, engine

settings = get_settings()


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: create all tables (idempotent — skipped if they already exist).
    Use Alembic migrations in production; this covers local dev / testing.
    """
    Base.metadata.create_all(bind=engine)
    yield
    # Shutdown: nothing to tear down for now.


# ── App factory ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="EduNexus AI",
    description="Adaptive AI tutoring and assessment platform.",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Tighten allowed_origins for production via environment config.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"] if settings.environment == "development" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers (registered once the sub-modules are implemented) ─────────────────
# from backend.api.routes import auth_router, chat_router, quiz_router, upload_router
# app.include_router(auth_router,   prefix="/api/v1/auth",    tags=["auth"])
# app.include_router(chat_router,   prefix="/api/v1/chat",    tags=["chat"])
# app.include_router(quiz_router,   prefix="/api/v1/quiz",    tags=["quiz"])
# app.include_router(upload_router, prefix="/api/v1/upload",  tags=["upload"])


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/api/health", tags=["health"])
async def health_check():
    return {"status": "ok", "environment": settings.environment}
