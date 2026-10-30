import logging
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
from backend.api.recommendations import router as recommendations_router
from backend.api.reflections import router as reflections_router
from backend.api.resources import router as resources_router
from backend.api.subjects import router as subjects_router
from backend.core.config import get_cors_origins, get_settings, validate_production_settings
from backend.core.csrf import CSRFMiddleware
from backend.core.database import engine
from backend.core.security_headers import SecurityHeadersMiddleware
from backend.core.trailing_slash import TrailingSlashMiddleware
from backend.pipeline.embedder import get_embedding_model
from backend.services import ingestion_runner

logger = logging.getLogger(__name__)

settings = get_settings()
validate_production_settings(settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.embedding_model = None
    print("[STARTUP] Loading embedding model into app.state...")
    app.state.embedding_model = get_embedding_model()
    if settings.run_ingestion_in_process:
        ingestion_runner.start_runner(app.state.embedding_model, settings.ingestion_poll_interval_seconds)
    print("[STARTUP] EduNexus AI ready.")
    yield
    ingestion_runner.stop_runner()
    print("[SHUTDOWN] EduNexus AI shutting down.")


app = FastAPI(
    title="EduNexus AI",
    description="Adaptive AI tutoring and assessment platform.",
    version="0.2.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    redirect_slashes=False,
)

app.add_middleware(CSRFMiddleware)
app.add_middleware(SecurityHeadersMiddleware, hsts=settings.is_production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# TrailingSlashMiddleware is added last so it becomes the *outermost* layer.
# Starlette builds the stack in reverse-add order, meaning the last
# add_middleware() call wraps all earlier ones.  The CSRF middleware therefore
# receives an already-normalised path.
app.add_middleware(TrailingSlashMiddleware)

app.include_router(auth_router,      prefix="/api/v1")
app.include_router(chat_router,      prefix="/api/v1")
app.include_router(classes_router,   prefix="/api/v1")
app.include_router(context_router,   prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
app.include_router(insights_router,  prefix="/api/v1")
app.include_router(progress_router,  prefix="/api/v1")
app.include_router(quizzes_router,   prefix="/api/v1")
app.include_router(recommendations_router, prefix="/api/v1")
app.include_router(reflections_router,     prefix="/api/v1")
app.include_router(resources_router,       prefix="/api/v1")
app.include_router(subjects_router,  prefix="/api/v1")


@app.get("/api/ping", tags=["health"])
def ping():
    return {"status": "ok"}


@app.get("/api/health", tags=["health"])
def health_check():
    db_status = "connected"
    vector_status = "ok"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            conn.execute(text("SELECT '[1,2,3]'::vector <=> '[1,2,4]'::vector"))
    except Exception:  # noqa: BLE001
        logger.exception("Health check database probe failed")
        db_status = "error"
        vector_status = "error"

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
        "pgvector": vector_status,
        "llm": llm_status,
        "model": "loaded" if model_loaded else "loading",
    }
