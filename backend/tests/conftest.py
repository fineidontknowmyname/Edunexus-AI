import os
from pathlib import Path
import uuid
import pytest
from fastapi.testclient import TestClient

# Ensure .env.test is loaded if present
test_env = Path(__file__).resolve().parent.parent / ".env.test"
if test_env.exists():
    from dotenv import load_dotenv
    load_dotenv(test_env, override=False)

from backend.main import app
from backend.core.database import SessionLocal, get_db
from backend.core.security import create_access_token, hash_password
from backend.models.db import Class, ClassEnrollment, Misconception, TopicMastery, User, UserRole


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def educator_user(db):
    user = User(
        email=f"edu_{uuid.uuid4().hex[:8]}@test.edunexus.io",
        hashed_password=hash_password("testpassword123"),
        full_name="Professor Test",
        role=UserRole.educator,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    yield user

    # Cleanup
    db.delete(user)
    db.commit()


@pytest.fixture
def student_user(db):
    user = User(
        email=f"stu_{uuid.uuid4().hex[:8]}@test.edunexus.io",
        hashed_password=hash_password("testpassword123"),
        full_name="Student Test",
        role=UserRole.student,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    yield user

    # Cleanup
    db.query(TopicMastery).filter(TopicMastery.student_id == user.id).delete()
    db.query(Misconception).filter(Misconception.student_id == user.id).delete()
    db.query(ClassEnrollment).filter(ClassEnrollment.student_id == user.id).delete()
    db.delete(user)
    db.commit()


@pytest.fixture
def student_user_2(db):
    user = User(
        email=f"stu2_{uuid.uuid4().hex[:8]}@test.edunexus.io",
        hashed_password=hash_password("testpassword123"),
        full_name="Student Test Two",
        role=UserRole.student,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    yield user

    # Cleanup
    db.query(TopicMastery).filter(TopicMastery.student_id == user.id).delete()
    db.query(Misconception).filter(Misconception.student_id == user.id).delete()
    db.query(ClassEnrollment).filter(ClassEnrollment.student_id == user.id).delete()
    db.delete(user)
    db.commit()


@pytest.fixture
def sample_class(db, educator_user):
    class_row = Class(
        name=f"Physics 101 - {uuid.uuid4().hex[:6]}",
        subject="Physics",
        semester=1,
        educator_id=educator_user.id,
        join_code=uuid.uuid4().hex[:8].upper(),
    )
    db.add(class_row)
    db.commit()
    db.refresh(class_row)
    yield class_row

    # Cleanup
    db.query(TopicMastery).filter(TopicMastery.class_id == class_row.id).delete()
    db.query(Misconception).filter(Misconception.class_id == class_row.id).delete()
    db.query(ClassEnrollment).filter(ClassEnrollment.class_id == class_row.id).delete()
    db.delete(class_row)
    db.commit()


def auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(user.id, user.role.value)
    return {"Authorization": f"Bearer {token}"}
