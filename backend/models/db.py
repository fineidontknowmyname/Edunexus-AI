import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
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


class DocumentStatus(str, enum.Enum):
    pending = "pending"    # Uploaded, awaiting ingestion
    processing = "processing"  # Ingestion pipeline running
    ready = "ready"        # Chunks stored and indexed
    failed = "failed"      # Ingestion failed


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
    engagement = relationship("Engagement", back_populates="student", uselist=False, cascade="all, delete-orphan")
    learning_states = relationship("LearningState", back_populates="student", cascade="all, delete-orphan")
    chat_sessions = relationship("ChatSession", back_populates="student", cascade="all, delete-orphan")
    quiz_attempts = relationship("QuizAttempt", back_populates="student", cascade="all, delete-orphan")
    uploaded_documents = relationship("Document", back_populates="uploaded_by", cascade="all, delete-orphan")


class Engagement(Base):
    """
    Per-student engagement and streak tracking record.
    Created automatically when a student registers.
    """

    __tablename__ = "engagements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    streak = Column(Integer, default=0, nullable=False)
    longest_streak = Column(Integer, default=0, nullable=False)
    last_active_date = Column(Date, nullable=True)
    total_sessions = Column(Integer, default=0, nullable=False)
    total_messages = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    student_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False)
    student = relationship("User", back_populates="engagement")


class Document(Base):
    """Educator-uploaded course material (PDF, DOCX, etc.)."""

    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(500), nullable=False)
    filename = Column(String(500), nullable=False)
    file_path = Column(String(1000), nullable=False)
    subject = Column(String(255), nullable=True)
    # Syllabus positioning metadata
    unit = Column(Integer, nullable=True)            # Module/unit number
    chapter = Column(Integer, nullable=True)         # Chapter number within unit
    chapter_name = Column(String(500), nullable=True)  # Descriptive chapter title
    class_id = Column(String(255), nullable=True)    # Educator's class/cohort ID
    # Ingestion pipeline state
    status = Column(Enum(DocumentStatus), default=DocumentStatus.pending, nullable=False)
    is_indexed = Column(Boolean, default=False, nullable=False)
    chunk_count = Column(Integer, default=0)
    deleted = Column(Boolean, default=False, nullable=False)  # Soft-delete flag
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    uploaded_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    uploaded_by = relationship("User", back_populates="uploaded_documents")
    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")


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


class Chunk(Base):
    """
    A single processed text chunk derived from a Document.

    Stores the raw text, contextual prefix, embedding vector (serialized as JSON),
    and metadata for RAG retrieval.
    """

    __tablename__ = "chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    text = Column(Text, nullable=False)                  # Raw extracted chunk text
    contextual_prefix = Column(Text, nullable=False)     # Subject/unit/chapter metadata header
    full_text = Column(Text, nullable=False)             # prefix + "\n" + text (embedded)
    embedding = Column(Text, nullable=False)             # JSON-serialized float vector
    subject = Column(String(255), nullable=True)
    chapter = Column(Integer, nullable=True)
    chunk_index = Column(Integer, nullable=False)        # 0-based position in document
    token_count = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False)
    document = relationship("Document", back_populates="chunks")


class ClassContext(Base):
    """
    Educator-defined class/cohort context, including a JSON syllabus map
    tracking chapter teach status for auto-progression.
    """

    __tablename__ = "class_contexts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    class_id = Column(String(255), unique=True, nullable=False, index=True)
    class_name = Column(String(500), nullable=True)
    subject = Column(String(255), nullable=True)
    # JSON structure: {"1": "taught", "2": "not_taught", ...}
    syllabus_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    educator_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    educator = relationship("User")
