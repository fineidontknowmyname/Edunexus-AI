import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
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
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import relationship

from backend.core.database import Base

EMBEDDING_DIM = 384  # all-MiniLM-L6-v2 output dimension

# ── Enums ─────────────────────────────────────────────────────────────────────


class UserRole(str, enum.Enum):
    student = "student"
    educator = "educator"
    admin = "admin"


class DocumentStatus(str, enum.Enum):
    pending = "pending"        # Uploaded, awaiting ingestion
    processing = "processing"  # Ingestion pipeline running
    ready = "ready"             # Chunks stored and indexed
    failed = "failed"           # Ingestion failed


class ReviewStatus(str, enum.Enum):
    """Shared by quizzes and quiz_questions — the educator review workflow."""
    pending_review = "pending_review"
    approved = "approved"
    rejected = "rejected"


class QuestionDifficulty(str, enum.Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"


class MasteryTrend(str, enum.Enum):
    improving = "improving"
    stable = "stable"
    declining = "declining"
    not_started = "not_started"


class SourceType(str, enum.Enum):
    curriculum = "curriculum"
    general_knowledge = "general_knowledge"


class SessionMode(str, enum.Enum):
    study = "study"
    revision = "revision"
    exam_focus = "exam_focus"


class ContextTier(str, enum.Enum):
    strong = "strong"
    moderate_weak = "moderate_weak"
    significant_gaps = "significant_gaps"


# ── Core: Users & Classes ────────────────────────────────────────────────────


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

    engagement = relationship("Engagement", back_populates="student", uselist=False, cascade="all, delete-orphan")
    topic_masteries = relationship("TopicMastery", back_populates="student", cascade="all, delete-orphan")
    chat_sessions = relationship("ChatSession", back_populates="student", cascade="all, delete-orphan")
    quiz_attempts = relationship("QuizAttempt", back_populates="student", cascade="all, delete-orphan")
    uploaded_documents = relationship("Document", back_populates="uploaded_by", cascade="all, delete-orphan")
    taught_classes = relationship("Class", back_populates="educator", cascade="all, delete-orphan")


class Class(Base):
    """A single class/cohort taught by one educator (e.g. 'OS Sem 5 - Section A')."""

    __tablename__ = "classes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(500), nullable=False)
    subject = Column(String(255), nullable=True)
    semester = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    educator_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    educator = relationship("User", back_populates="taught_classes")
    enrollments = relationship("ClassEnrollment", back_populates="class_", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="class_", cascade="all, delete-orphan")
    context = relationship("ClassContext", back_populates="class_", uselist=False, cascade="all, delete-orphan")


class ClassEnrollment(Base):
    """Student-class membership."""

    __tablename__ = "class_enrollments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    enrolled_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    class_ = relationship("Class", back_populates="enrollments")
    student = relationship("User")


# ── Curriculum content ───────────────────────────────────────────────────────


class Document(Base):
    """Educator-uploaded course material (PDF, DOCX, PPTX)."""

    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(500), nullable=False)
    filename = Column(String(500), nullable=False)
    file_path = Column(String(1000), nullable=False)
    subject = Column(String(255), nullable=True)
    unit = Column(Integer, nullable=True)
    chapter = Column(Integer, nullable=True)
    chapter_name = Column(String(500), nullable=True)
    status = Column(Enum(DocumentStatus), default=DocumentStatus.pending, nullable=False)
    is_indexed = Column(Boolean, default=False, nullable=False)
    chunk_count = Column(Integer, default=0)
    deleted = Column(Boolean, default=False, nullable=False)  # Soft-delete flag
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=False)
    uploaded_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    class_ = relationship("Class", back_populates="documents")
    uploaded_by = relationship("User", back_populates="uploaded_documents")
    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")


class Chunk(Base):
    """A single processed + embedded text segment derived from a Document."""

    __tablename__ = "chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    text = Column(Text, nullable=False)                        # Raw extracted chunk text
    contextual_prefix = Column(Text, nullable=False)           # Subject/unit/chapter metadata header
    full_text = Column(Text, nullable=False)                   # prefix + "\n" + text (embedded)
    embedding = Column(Vector(EMBEDDING_DIM), nullable=False)  # pgvector — cosine similarity via HNSW
    subject = Column(String(255), nullable=True)
    unit = Column(Integer, nullable=True)
    chapter = Column(Integer, nullable=True)
    chunk_index = Column(Integer, nullable=False)               # 0-based position in document
    token_count = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False)
    document = relationship("Document", back_populates="chunks")


class ResponseCache(Base):
    """Semantic cache of AI chat responses, keyed by query embedding + context tier."""

    __tablename__ = "response_cache"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    query_embedding = Column(Vector(EMBEDDING_DIM), nullable=False)
    subject = Column(String(255), nullable=True)
    chapter = Column(Integer, nullable=True)
    context_tier = Column(Enum(ContextTier), nullable=False)
    response_text = Column(Text, nullable=False)
    chunk_ids_used = Column(ARRAY(UUID(as_uuid=True)), nullable=True)
    source_type = Column(Enum(SourceType), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)  # TTL checked on read


class ClassContext(Base):
    """
    Educator-defined teaching state for a class: syllabus progress, upcoming
    assessments, and free-text emphasis notes. One row per Class.
    """

    __tablename__ = "class_context"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), unique=True, nullable=False)
    syllabus_json = Column(Text, nullable=True)       # {"1": "taught", "2": "not_taught", ...}
    assessments_json = Column(Text, nullable=True)    # [{"name", "date", "covers": [...]}]
    teacher_emphasis = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    class_ = relationship("Class", back_populates="context")


# ── Student learning state ───────────────────────────────────────────────────


class TopicMastery(Base):
    """Per-student, per-topic mastery estimate — the core evidence-based state."""

    __tablename__ = "topic_mastery"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topic = Column(String(500), nullable=False, index=True)
    unit = Column(Integer, nullable=True)
    mastery_score = Column(Float, default=0.0, nullable=False)   # 0.0 – 1.0
    attempt_count = Column(Integer, default=0, nullable=False)
    last_attempt_at = Column(DateTime, nullable=True)
    trend = Column(Enum(MasteryTrend), default=MasteryTrend.not_started, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    student_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=False)
    student = relationship("User", back_populates="topic_masteries")


class Misconception(Base):
    """A specific, named error pattern detected for a student on a topic."""

    __tablename__ = "misconceptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topic = Column(String(500), nullable=False)
    description = Column(Text, nullable=False)
    detected_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    resolved = Column(Boolean, default=False, nullable=False)

    student_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=False)
    source_quiz_attempt_id = Column(UUID(as_uuid=True), ForeignKey("quiz_attempts.id"), nullable=True)


class InteractionPattern(Base):
    """Tracks how many times a student has asked about a topic (Rule 5 input)."""

    __tablename__ = "interaction_patterns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topic = Column(String(500), nullable=False)
    questions_asked = Column(Integer, default=0, nullable=False)
    last_asked_at = Column(DateTime, default=datetime.utcnow)

    student_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)


class Engagement(Base):
    """Per-student engagement and streak tracking record."""

    __tablename__ = "engagement"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    current_streak = Column(Integer, default=0, nullable=False)
    longest_streak = Column(Integer, default=0, nullable=False)
    last_interaction_date = Column(Date, nullable=True)
    staleness_flag = Column(Boolean, default=False, nullable=False)
    total_sessions = Column(Integer, default=0, nullable=False)
    total_messages = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    student_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False)
    student = relationship("User", back_populates="engagement")


# ── Chat ──────────────────────────────────────────────────────────────────────


class ChatSession(Base):
    """A single tutoring conversation thread between a student and the AI."""

    __tablename__ = "chat_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject = Column(String(255), nullable=True)
    mode = Column(Enum(SessionMode), default=SessionMode.study, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    student_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=True)
    student = relationship("User", back_populates="chat_sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")


class ChatMessage(Base):
    """Individual message within a ChatSession."""

    __tablename__ = "chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role = Column(String(20), nullable=False)       # "user" | "assistant"
    content = Column(Text, nullable=False)
    source_type = Column(Enum(SourceType), nullable=True)
    chunk_ids_used = Column(ARRAY(UUID(as_uuid=True)), nullable=True)
    flagged_by_student = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    session_id = Column(UUID(as_uuid=True), ForeignKey("chat_sessions.id"), nullable=False)
    session = relationship("ChatSession", back_populates="messages")


# ── Quizzes ───────────────────────────────────────────────────────────────────


class Quiz(Base):
    """AI-generated quiz, subject to educator review before publishing."""

    __tablename__ = "quizzes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(500), nullable=False)
    unit = Column(Integer, nullable=True)
    chapter = Column(Integer, nullable=True)
    generation_type = Column(String(50), default="standard", nullable=False)  # standard | misconception_targeted
    status = Column(Enum(ReviewStatus), default=ReviewStatus.pending_review, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=False)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True)
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reviewed_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    questions = relationship("QuizQuestion", back_populates="quiz", cascade="all, delete-orphan")
    attempts = relationship("QuizAttempt", back_populates="quiz", cascade="all, delete-orphan")


class QuizQuestion(Base):
    """A single MCQ within a Quiz, individually approved/rejected by the educator."""

    __tablename__ = "quiz_questions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_text = Column(Text, nullable=False)
    options = Column(Text, nullable=False)              # JSON array of option strings
    correct_answer = Column(Text, nullable=False)
    difficulty = Column(Enum(QuestionDifficulty), default=QuestionDifficulty.medium, nullable=False)
    status = Column(Enum(ReviewStatus), default=ReviewStatus.pending_review, nullable=False)

    quiz_id = Column(UUID(as_uuid=True), ForeignKey("quizzes.id"), nullable=False)
    source_chunk_id = Column(UUID(as_uuid=True), ForeignKey("chunks.id"), nullable=True)
    quiz = relationship("Quiz", back_populates="questions")


class QuizAttempt(Base):
    """A student's single attempt at a Quiz."""

    __tablename__ = "quiz_attempts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    score = Column(Float, nullable=True)            # percentage 0–100
    answers = Column(Text, nullable=True)            # JSON: {question_id: chosen_answer}
    topic_scores = Column(Text, nullable=True)        # JSON: {topic: score}
    completed = Column(Boolean, default=False)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    student_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    quiz_id = Column(UUID(as_uuid=True), ForeignKey("quizzes.id"), nullable=False)
    student = relationship("User", back_populates="quiz_attempts")
    quiz = relationship("Quiz", back_populates="attempts")


# ── Educator tools ────────────────────────────────────────────────────────────


class EducatorNote(Base):
    """A teacher's free-text note on a specific student — feeds future AI context."""

    __tablename__ = "educator_notes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    note = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    educator_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=False)


class PrerequisiteMap(Base):
    """
    Static topic-dependency config, kept in schema for parity with the reference
    design. NOT currently populated or read by application code — the runtime
    prerequisite check (backend/core/prerequisites.py) loads from
    backend/data/prerequisites_os.json instead. See CONTEXT doc change log.
    """

    __tablename__ = "prerequisite_map"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject = Column(String(255), nullable=False)
    topic = Column(String(500), nullable=False)
    requires = Column(ARRAY(Text), nullable=True)
