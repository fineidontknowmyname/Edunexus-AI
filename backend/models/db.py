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
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import relationship

from backend.core.database import Base

EMBEDDING_DIM = 384


class UserRole(str, enum.Enum):
    student = "student"
    educator = "educator"
    admin = "admin"


class DocumentStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    ready = "ready"
    failed = "failed"


class ReviewStatus(str, enum.Enum):
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
    socratic = "socratic"


class ContextTier(str, enum.Enum):
    strong = "strong"
    moderate_weak = "moderate_weak"
    significant_gaps = "significant_gaps"


class IngestionJobStatus(str, enum.Enum):
    queued = "queued"
    processing = "processing"
    done = "done"
    failed = "failed"


class Category(Base):
    __tablename__ = "categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    subjects = relationship("Subject", back_populates="category", cascade="all, delete-orphan")


class Subject(Base):
    __tablename__ = "subjects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    category_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    category = relationship("Category", back_populates="subjects")
    topics = relationship("PrerequisiteMap", back_populates="subject_", cascade="all, delete-orphan")


class User(Base):
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
    __tablename__ = "classes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(500), nullable=False)
    subject = Column(String(255), nullable=True)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=True)
    semester = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    educator_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    educator = relationship("User", back_populates="taught_classes")
    enrollments = relationship("ClassEnrollment", back_populates="class_", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="class_", cascade="all, delete-orphan")
    context = relationship("ClassContext", back_populates="class_", uselist=False, cascade="all, delete-orphan")


class ClassEnrollment(Base):
    __tablename__ = "class_enrollments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    enrolled_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    class_ = relationship("Class", back_populates="enrollments")
    student = relationship("User")


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(500), nullable=False)
    filename = Column(String(500), nullable=False)
    file_path = Column(String(1000), nullable=False)
    subject = Column(String(255), nullable=True)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=True)
    unit = Column(Integer, nullable=True)
    chapter = Column(Integer, nullable=True)
    chapter_name = Column(String(500), nullable=True)
    status = Column(Enum(DocumentStatus), default=DocumentStatus.pending, nullable=False)
    is_indexed = Column(Boolean, default=False, nullable=False)
    chunk_count = Column(Integer, default=0)
    deleted = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=False)
    uploaded_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    class_ = relationship("Class", back_populates="documents")
    uploaded_by = relationship("User", back_populates="uploaded_documents")
    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")


class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    text = Column(Text, nullable=False)
    contextual_prefix = Column(Text, nullable=False)
    full_text = Column(Text, nullable=False)
    embedding = Column(Vector(EMBEDDING_DIM), nullable=False)
    subject = Column(String(255), nullable=True)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=True)
    topic = Column(String(500), nullable=True)
    unit = Column(Integer, nullable=True)
    chapter = Column(Integer, nullable=True)
    chunk_index = Column(Integer, nullable=False)
    token_count = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=True)
    document = relationship("Document", back_populates="chunks")


class ResponseCache(Base):
    __tablename__ = "response_cache"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    query_embedding = Column(Vector(EMBEDDING_DIM), nullable=False)
    subject = Column(String(255), nullable=True)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=True)
    chapter = Column(Integer, nullable=True)
    context_tier = Column(Enum(ContextTier), nullable=False)
    learning_tag = Column(String(50), nullable=True)
    response_text = Column(Text, nullable=False)
    chunk_ids_used = Column(ARRAY(UUID(as_uuid=True)), nullable=True)
    source_type = Column(Enum(SourceType), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ClassContext(Base):
    __tablename__ = "class_context"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), unique=True, nullable=False)
    syllabus_json = Column(Text, nullable=True)
    assessments_json = Column(Text, nullable=True)
    teacher_emphasis = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    class_ = relationship("Class", back_populates="context")


class TopicMastery(Base):
    __tablename__ = "topic_mastery"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topic = Column(String(500), nullable=False, index=True)
    unit = Column(Integer, nullable=True)
    mastery_score = Column(Float, default=0.0, nullable=False)
    attempt_count = Column(Integer, default=0, nullable=False)
    last_attempt_at = Column(DateTime, nullable=True)
    last_quiz_passed = Column(Boolean, nullable=True)
    trend = Column(Enum(MasteryTrend), default=MasteryTrend.not_started, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    student_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=False)
    student = relationship("User", back_populates="topic_masteries")


class Misconception(Base):
    __tablename__ = "misconceptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topic = Column(String(500), nullable=False)
    description = Column(Text, nullable=False)
    detected_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    resolved = Column(Boolean, default=False, nullable=False)

    student_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=False)
    source_quiz_attempt_id = Column(UUID(as_uuid=True), ForeignKey("quiz_attempts.id"), nullable=True)


class MisconceptionRule(Base):
    __tablename__ = "misconception_rules"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topic = Column(String(500), nullable=False)
    name = Column(String(255), nullable=True)
    description = Column(Text, nullable=False)
    wrong_answer_keywords = Column(ARRAY(Text), nullable=True)
    question_keywords = Column(ARRAY(Text), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)


class InteractionPattern(Base):
    __tablename__ = "interaction_patterns"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topic = Column(String(500), nullable=False)
    questions_asked = Column(Integer, default=0, nullable=False)
    last_asked_at = Column(DateTime, default=datetime.utcnow)

    student_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)


class TopicBehavior(Base):
    __tablename__ = "topic_behavior"
    __table_args__ = (
        UniqueConstraint("student_id", "subject_id", "topic", name="uq_topic_behavior_student_subject_topic"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    topic = Column(String(500), nullable=False)
    message_count = Column(Integer, default=0, nullable=False)
    follow_up_count = Column(Integer, default=0, nullable=False)
    qt_conceptual = Column(Integer, default=0, nullable=False)
    qt_example = Column(Integer, default=0, nullable=False)
    qt_direct = Column(Integer, default=0, nullable=False)
    learning_tag = Column(String(50), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    student_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=True)


class Engagement(Base):
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


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject = Column(String(255), nullable=True)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=True)
    mode = Column(Enum(SessionMode), default=SessionMode.study, nullable=False)
    socratic_state = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    student_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=True)
    student = relationship("User", back_populates="chat_sessions")
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    source_type = Column(Enum(SourceType), nullable=True)
    chunk_ids_used = Column(ARRAY(UUID(as_uuid=True)), nullable=True)
    flagged_by_student = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    session_id = Column(UUID(as_uuid=True), ForeignKey("chat_sessions.id"), nullable=False)
    session = relationship("ChatSession", back_populates="messages")


class Quiz(Base):
    __tablename__ = "quizzes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(500), nullable=False)
    unit = Column(Integer, nullable=True)
    chapter = Column(Integer, nullable=True)
    generation_type = Column(String(50), default="standard", nullable=False)
    status = Column(Enum(ReviewStatus), default=ReviewStatus.pending_review, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=False)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True)
    created_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reviewed_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    questions = relationship("QuizQuestion", back_populates="quiz", cascade="all, delete-orphan")
    attempts = relationship("QuizAttempt", back_populates="quiz", cascade="all, delete-orphan")


class QuizQuestion(Base):
    __tablename__ = "quiz_questions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_text = Column(Text, nullable=False)
    options = Column(Text, nullable=False)
    correct_answer = Column(Text, nullable=False)
    topic = Column(String(500), nullable=True)
    difficulty = Column(Enum(QuestionDifficulty), default=QuestionDifficulty.medium, nullable=False)
    status = Column(Enum(ReviewStatus), default=ReviewStatus.pending_review, nullable=False)

    quiz_id = Column(UUID(as_uuid=True), ForeignKey("quizzes.id"), nullable=False)
    source_chunk_id = Column(UUID(as_uuid=True), ForeignKey("chunks.id"), nullable=True)
    quiz = relationship("Quiz", back_populates="questions")


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    score = Column(Float, nullable=True)
    answers = Column(Text, nullable=True)
    topic_scores = Column(Text, nullable=True)
    completed = Column(Boolean, default=False)
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    student_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    quiz_id = Column(UUID(as_uuid=True), ForeignKey("quizzes.id"), nullable=False)
    student = relationship("User", back_populates="quiz_attempts")
    quiz = relationship("Quiz", back_populates="attempts")


class EducatorNote(Base):
    __tablename__ = "educator_notes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    note = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    educator_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    class_id = Column(UUID(as_uuid=True), ForeignKey("classes.id"), nullable=False)


class PrerequisiteMap(Base):
    __tablename__ = "prerequisite_map"
    __table_args__ = (
        UniqueConstraint("subject_id", "topic", name="uq_prerequisite_map_subject_topic"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject = Column(String(255), nullable=True)
    subject_id = Column(UUID(as_uuid=True), ForeignKey("subjects.id"), nullable=True)
    topic = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    requires = Column(ARRAY(Text), nullable=True)
    related_concepts = Column(ARRAY(Text), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    subject_ = relationship("Subject", back_populates="topics")


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status = Column(Enum(IngestionJobStatus), default=IngestionJobStatus.queued, nullable=False, index=True)
    attempts = Column(Integer, default=0, nullable=False)
    claimed_at = Column(DateTime, nullable=True)
    error = Column(Text, nullable=True)
    chunk_count = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False)
