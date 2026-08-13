import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from backend.core.database import Base

# ── Enums ─────────────────────────────────────────────────────────────────────

import enum


class UserRole(str, enum.Enum):
    student = "student"
    educator = "educator"
    admin = "admin"


class MasteryLevel(str, enum.Enum):
    not_started = "not_started"
    learning = "learning"
    practicing = "practicing"
    mastered = "mastered"


class QuizStatus(str, enum.Enum):
    draft = "draft"
    published = "published"
    archived = "archived"


# ── Models ────────────────────────────────────────────────────────────────────


class User(Base):
    """Platform user — can be a student or educator."""

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.student)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    learning_states = relationship("LearningState", back_populates="student", cascade="all, delete-orphan")
    chat_sessions = relationship("ChatSession", back_populates="student", cascade="all, delete-orphan")
    quiz_attempts = relationship("QuizAttempt", back_populates="student", cascade="all, delete-orphan")
    uploaded_documents = relationship("Document", back_populates="uploaded_by", cascade="all, delete-orphan")


class Document(Base):
    """Educator-uploaded course material (PDF, DOCX, etc.)."""

    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(500), nullable=False)
    filename = Column(String(500), nullable=False)
    file_path = Column(String(1000), nullable=False)
    subject = Column(String(255), nullable=True)
    is_indexed = Column(Boolean, default=False, nullable=False)
    chunk_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    uploaded_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    uploaded_by = relationship("User", back_populates="uploaded_documents")


class LearningState(Base):
    """
    Per-student mastery tracking for a specific concept / topic.
    The pipeline updates this record after each interaction.
    """

    __tablename__ = "learning_states"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    concept = Column(String(500), nullable=False, index=True)
    subject = Column(String(255), nullable=True)
    mastery_level = Column(Enum(MasteryLevel), default=MasteryLevel.not_started, nullable=False)
    mastery_score = Column(Float, default=0.0, nullable=False)  # 0.0 – 1.0
    evidence_count = Column(Integer, default=0, nullable=False)
    last_interaction = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    student_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    student = relationship("User", back_populates="learning_states")


class ChatSession(Base):
    """A single tutoring conversation thread between a student and the AI."""

    __tablename__ = "chat_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    student_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    student = relationship("User", back_populates="chat_sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")


class ChatMessage(Base):
    """Individual message within a ChatSession."""

    __tablename__ = "chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role = Column(String(20), nullable=False)       # "user" | "assistant"
    content = Column(Text, nullable=False)
    evidence_chunks = Column(Text, nullable=True)   # JSON array of retrieved chunks
    concepts_detected = Column(Text, nullable=True) # JSON array of concept strings
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    session_id = Column(UUID(as_uuid=True), ForeignKey("chat_sessions.id"), nullable=False)
    session = relationship("ChatSession", back_populates="messages")


class Quiz(Base):
    """AI-generated or educator-curated quiz."""

    __tablename__ = "quizzes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(500), nullable=False)
    subject = Column(String(255), nullable=True)
    concept = Column(String(500), nullable=True)
    status = Column(Enum(QuizStatus), default=QuizStatus.draft, nullable=False)
    questions = Column(Text, nullable=False)        # JSON array of question objects
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    attempts = relationship("QuizAttempt", back_populates="quiz", cascade="all, delete-orphan")


class QuizAttempt(Base):
    """A student's single attempt at a Quiz."""

    __tablename__ = "quiz_attempts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    score = Column(Float, nullable=True)            # percentage 0–100
    answers = Column(Text, nullable=True)           # JSON: {question_id: chosen_answer}
    completed = Column(Boolean, default=False)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    student_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    quiz_id = Column(UUID(as_uuid=True), ForeignKey("quizzes.id"), nullable=False)
    student = relationship("User", back_populates="quiz_attempts")
    quiz = relationship("Quiz", back_populates="attempts")
