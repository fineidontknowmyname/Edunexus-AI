import sys
from contextlib import asynccontextmanager

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from backend.api.auth import router as auth_router
from backend.api.chat import router as chat_router
from backend.api.classes import router as classes_router
from backend.api.context import router as context_router
from backend.api.documents import router as documents_router
from backend.api.insights import router as insights_router
from backend.api.progress import router as progress_router
from backend.api.quizzes import router as quizzes_router
from backend.api.subjects import router as subjects_router
from backend.core.config import get_cors_origins, get_settings
from backend.core.database import SessionLocal, engine
from backend.pipeline.embedder import get_embedding_model

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.embedding_model = None
    print("[STARTUP] Loading embedding model into app.state...")
    app.state.embedding_model = get_embedding_model()
    try:
        from backend.services.ingestion_jobs import sweep_stale

        db = SessionLocal()
        try:
            sweep_stale(db)
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        print(f"[STARTUP] Stale-job sweep skipped: {exc}")
    print("[STARTUP] EduNexus AI ready.")
    yield
    print("[SHUTDOWN] EduNexus AI shutting down.")


app = FastAPI(
    title="EduNexus AI",
    description="Adaptive AI tutoring and assessment platform.",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router,      prefix="/api/v1")
app.include_router(chat_router,      prefix="/api/v1")
app.include_router(classes_router,   prefix="/api/v1")
app.include_router(context_router,   prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
app.include_router(insights_router,  prefix="/api/v1")
app.include_router(progress_router,  prefix="/api/v1")
app.include_router(quizzes_router,   prefix="/api/v1")
app.include_router(subjects_router,  prefix="/api/v1")


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
        llm_status = "configured"

    model_loaded = getattr(app.state, "embedding_model", None) is not None

    all_ok = db_status == "connected" and llm_status == "configured" and model_loaded

    return {
        "status": "ok" if all_ok else "degraded",
        "environment": settings.environment,
        "db": db_status,
        "llm": llm_status,
        "model": "loaded" if model_loaded else "loading",
    }
