"""
backend/main.py — EduNexus AI FastAPI application entry point.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from backend.api.auth import router as auth_router
from backend.api.classes import router as classes_router
from backend.api.documents import router as documents_router
from backend.core.config import get_settings
from backend.core.database import engine
from backend.pipeline.embedder import get_embedding_model

settings = get_settings()


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup:
      1. Pre-load the SentenceTransformer embedding model into app.state so that
         background ingestion workers can access it without reloading on every job.

    Schema is owned entirely by Alembic (`alembic upgrade head`) — the app no
    longer calls `Base.metadata.create_all()`. That fallback let the schema
    silently drift out of sync with the migration history; run migrations
    explicitly before starting the server instead.
    """
    app.state.embedding_model = None
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
app.include_router(classes_router,   prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
# Future routers (uncomment as implemented):
# app.include_router(chat_router,      prefix="/api/v1")
# app.include_router(quiz_router,      prefix="/api/v1")
# app.include_router(progress_router,  prefix="/api/v1")
# app.include_router(insights_router,  prefix="/api/v1")


# ── Health check ──────────────────────────────────────────────────────────────
# UptimeRobot pings this every 5 min to keep the Render instance warm. It must
# only report fully healthy once the embedding model is actually loaded — a
# 200 from an app that's still loading is what causes the first real request
# after a cold start to hang for 20+ seconds (see EduNexus AI — Revised
# Architecture Design.md, Issue 2).
#
# The LLM check is config-level ("is a key configured"), not a live API call —
# pinging Groq every 5 minutes from every environment would burn free-tier
# quota for no diagnostic benefit.

@app.get("/api/health", tags=["health"])
async def health_check():
    db_status = "connected"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"error: {e}"

    if settings.llm_provider.lower() == "groq":
        llm_status = "configured" if settings.groq_api_key else "missing_api_key"
    else:
        llm_status = "configured"  # Ollama needs no key; assumed reachable locally

    model_loaded = getattr(app.state, "embedding_model", None) is not None

    all_ok = db_status == "connected" and llm_status == "configured" and model_loaded

    return {
        "status": "ok" if all_ok else "degraded",
        "environment": settings.environment,
        "db": db_status,
        "llm": llm_status,
        "model": "loaded" if model_loaded else "loading",
    }
