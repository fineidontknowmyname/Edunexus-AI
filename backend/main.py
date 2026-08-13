"""
backend/main.py — EduNexus AI FastAPI application entry point.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.auth import router as auth_router
from backend.api.documents import router as documents_router
from backend.core.config import get_settings
from backend.core.database import Base, engine
from backend.pipeline.embedder import get_embedding_model

settings = get_settings()


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup:
      1. Create all DB tables (idempotent — skipped if they already exist).
         Use Alembic migrations in production; this covers local dev / testing.
      2. Pre-load the SentenceTransformer embedding model into app.state so that
         background ingestion workers can access it without reloading on every job.
    """
    print("[STARTUP] Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("[STARTUP] Loading embedding model into app.state...")
    app.state.embedding_model = get_embedding_model()
    print("[STARTUP] EduNexus AI ready.")
    yield
    # Shutdown: nothing to tear down for now.
    print("[SHUTDOWN] EduNexus AI shutting down.")


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

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth_router,      prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
# Future routers (uncomment as implemented):
# app.include_router(chat_router,      prefix="/api/v1")
# app.include_router(quiz_router,      prefix="/api/v1")
# app.include_router(progress_router,  prefix="/api/v1")
# app.include_router(insights_router,  prefix="/api/v1")


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/api/health", tags=["health"])
async def health_check():
    return {"status": "ok", "environment": settings.environment}
