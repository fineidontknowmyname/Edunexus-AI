from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from backend.core.config import get_settings

# ── Engine ────────────────────────────────────────────────────────────────────
# pool_size      : number of persistent connections kept alive in the pool.
# max_overflow   : extra connections allowed beyond pool_size under burst load.
# pool_pre_ping  : issues a lightweight "SELECT 1" before handing out a
#                  connection, automatically recycling stale connections.
settings = get_settings()

engine = create_engine(
    settings.database_url,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
)

# ── Session factory ───────────────────────────────────────────────────────────
# autocommit=False  : transactions must be committed explicitly.
# autoflush=False   : prevents implicit flushes before queries, giving full
#                     control over when SQL is emitted.
SessionLocal: sessionmaker[Session] = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)

# ── Declarative base ─────────────────────────────────────────────────────────
# All ORM model classes inherit from Base so SQLAlchemy tracks them and can
# auto-create / migrate their tables.
Base = declarative_base()


# ── Dependency ────────────────────────────────────────────────────────────────
def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a database session per request.

    Usage:
        @router.get("/items")
        def read_items(db: Session = Depends(get_db)):
            ...

    The session is always closed in the `finally` block, even if the
    request handler raises an exception.
    """
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
