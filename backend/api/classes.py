import secrets
import string
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.api import access
from backend.api.dependencies import CurrentUser, RequireEducator, RequireStudent
from backend.core.database import get_db
from backend.models import schemas
from backend.models.db import Class, ClassContext, ClassEnrollment

router = APIRouter(prefix="/classes", tags=["classes"])

DbDep = Annotated[Session, Depends(get_db)]

# Characters used in join codes: uppercase alphanumeric, excluding visually
# ambiguous chars (0/O, 1/I/L) so codes are easy to read and type.
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def _generate_join_code(db: Session) -> str:
    """Generate a unique 8-character join code for a class.

    Retries up to 10 times on the off-chance of a collision (probability is
    negligible for realistic numbers of classes).
    """
    for _ in range(10):
        code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))
        existing = db.query(Class).filter(Class.join_code == code).first()
        if existing is None:
            return code
    # Practically unreachable but fail loudly rather than silently
    raise RuntimeError("Failed to generate a unique join code after 10 attempts.")


# ── Educator: create class ────────────────────────────────────────────────────

@router.post("/", response_model=schemas.ClassRead, status_code=201)
def create_class(
    payload: schemas.ClassCreate,
    db: DbDep,
    current_user: CurrentUser,
    _educator: Annotated[None, RequireEducator],
):
    print(f"[CLASSES] Creating class '{payload.name}' for educator {current_user.id}")

    subject_name = payload.subject
    if payload.subject_id is not None:
        from backend.models.db import Subject

        subject_row = db.get(Subject, payload.subject_id)
        if subject_row is None:
            raise HTTPException(
                status_code=404,
                detail=f"Subject '{payload.subject_id}' not found.",
            )
        subject_name = subject_row.name

    join_code = _generate_join_code(db)
    class_row = Class(
        name=payload.name,
        subject=subject_name,
        subject_id=payload.subject_id,
        semester=payload.semester,
        educator_id=current_user.id,
        join_code=join_code,
    )
    db.add(class_row)
    db.flush()
    db.add(ClassContext(class_id=class_row.id))
    db.commit()
    db.refresh(class_row)
    print(
        f"[CLASSES SUCCESS] Class created: id={class_row.id} name='{class_row.name}' "
        f"join_code={class_row.join_code}"
    )
    return class_row


# ── List enrolled / owned classes ────────────────────────────────────────────

@router.get("/", response_model=list[schemas.ClassRead])
def list_classes(db: DbDep, current_user: CurrentUser):
    from backend.models.db import UserRole

    if current_user.role == UserRole.educator:
        rows = db.query(Class).filter(Class.educator_id == current_user.id).all()
        print(f"[CLASSES] Educator {current_user.id} owns {len(rows)} class(es)")
        return rows

    enrolled_class_ids = (
        db.query(ClassEnrollment.class_id)
        .filter(ClassEnrollment.student_id == current_user.id)
        .subquery()
    )
    rows = db.query(Class).filter(Class.id.in_(enrolled_class_ids)).all()
    print(f"[CLASSES] Student {current_user.id} enrolled in {len(rows)} class(es)")
    return rows


# ── Browse all classes (students discover, not yet enrolled) ─────────────────

@router.get("/browse", response_model=list[schemas.ClassBrowseRead])
def browse_classes(db: DbDep, current_user: CurrentUser):
    """Return all classes except ones the current student is already enrolled in.

    join_code and educator_id are intentionally excluded from the response:
    - join_code must be obtained from the educator out-of-band (access control).
    - educator_id is an internal FK not relevant to students.
    """
    already_enrolled = (
        db.query(ClassEnrollment.class_id)
        .filter(ClassEnrollment.student_id == current_user.id)
    )
    rows = db.query(Class).filter(Class.id.not_in(already_enrolled)).all()
    print(f"[CLASSES] Browse — {len(rows)} class(es) available to student {current_user.id}")
    return rows


# ── Enroll (student supplies join code) ──────────────────────────────────────

@router.post("/{class_id}/enroll", response_model=schemas.MessageResponse, status_code=201)
def enroll_in_class(
    class_id: str,
    payload: schemas.EnrollRequest,
    db: DbDep,
    current_user: CurrentUser,
    _student: Annotated[None, RequireStudent],
):
    """Enroll the current student in a class.

    The student must supply the correct join_code for the class; without it
    the request is rejected with 403.

    Safety properties:
    - parse_uuid() converts the path param to a UUID or returns 404 (not 500).
    - ON CONFLICT DO NOTHING is atomic; no TOCTOU race condition.
    - IntegrityError fallback handles the case where the unique constraint
      exists but the dialect-level ON CONFLICT isn't available (should not
      happen on Postgres, but keeps the endpoint safe across migration states).
    """
    print(f"[CLASSES] Enroll attempt: student={current_user.id} class={class_id}")

    parsed_id = access.parse_uuid(class_id, "Class")
    class_row = db.get(Class, parsed_id)
    if class_row is None:
        print(f"[CLASSES ERROR] Enroll rejected — class '{class_id}' not found.")
        raise HTTPException(status_code=404, detail="Class not found.")

    # ── Validate join code ────────────────────────────────────────────────────
    if class_row.join_code.upper() != payload.join_code.strip().upper():
        print(
            f"[CLASSES ERROR] Enroll rejected — wrong join code for class {class_id} "
            f"(student={current_user.id})"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Incorrect join code.",
        )

    # ── Atomic upsert (no duplicate-check race condition) ────────────────────
    stmt = (
        pg_insert(ClassEnrollment)
        .values(class_id=class_row.id, student_id=current_user.id)
        .on_conflict_do_nothing(index_elements=["class_id", "student_id"])
    )
    try:
        db.execute(stmt)
        db.commit()
    except IntegrityError:
        # Fallback: unique constraint exists but ON CONFLICT path missed it.
        # Roll back and report gracefully instead of crashing.
        db.rollback()
        print(
            f"[CLASSES] IntegrityError on duplicate enroll — "
            f"student={current_user.id} class={class_id}"
        )
        return {"message": "Already enrolled."}

    print(
        f"[CLASSES SUCCESS] Student {current_user.id} enrolled in "
        f"'{class_row.name}' ({class_id})"
    )
    return {"message": f"Enrolled in '{class_row.name}'."}


# ── Leave (student removes their own enrollment) ──────────────────────────────

@router.delete("/{class_id}/enroll", status_code=204)
def leave_class(
    class_id: str,
    db: DbDep,
    current_user: CurrentUser,
    _student: Annotated[None, RequireStudent],
):
    """Remove the current student's enrollment from a class.

    Only the student's own enrollment is deleted.  All learning data
    (topic_mastery, misconceptions, quiz_attempts, chat_sessions, reflections)
    is preserved so history is intact if the student re-enrols later.
    """
    print(f"[CLASSES] Leave attempt: student={current_user.id} class={class_id}")

    parsed_id = access.parse_uuid(class_id, "Class")
    enrollment = (
        db.query(ClassEnrollment)
        .filter(
            ClassEnrollment.class_id == parsed_id,
            ClassEnrollment.student_id == current_user.id,
        )
        .first()
    )
    if enrollment is None:
        print(
            f"[CLASSES ERROR] Leave rejected — student {current_user.id} "
            f"not enrolled in class {class_id}."
        )
        raise HTTPException(status_code=404, detail="Not enrolled in this class.")

    db.delete(enrollment)
    db.commit()
    print(
        f"[CLASSES SUCCESS] Student {current_user.id} left class {class_id}. "
        f"Learning data preserved."
    )
    return Response(status_code=204)
