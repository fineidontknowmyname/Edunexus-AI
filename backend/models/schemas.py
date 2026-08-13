from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from backend.models.db import MasteryLevel, QuizStatus, UserRole

# ── Shared config ─────────────────────────────────────────────────────────────

class _OrmBase(BaseModel):
    """All response schemas inherit from this to enable ORM mode."""
    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────────────────────────────────────
# Auth
# ─────────────────────────────────────────────────────────────────────────────

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: UUID | None = None
    role: UserRole | None = None


# ─────────────────────────────────────────────────────────────────────────────
# User
# ─────────────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1, max_length=255)
    role: UserRole = UserRole.student


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserRead(_OrmBase):
    id: UUID
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime


class UserUpdate(BaseModel):
    full_name: str | None = None
    is_active: bool | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Document
# ─────────────────────────────────────────────────────────────────────────────

class DocumentRead(_OrmBase):
    id: UUID
    title: str
    filename: str
    subject: str | None
    is_indexed: bool
    chunk_count: int
    created_at: datetime
    uploaded_by_id: UUID


class DocumentCreate(BaseModel):
    title: str
    subject: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Learning State
# ─────────────────────────────────────────────────────────────────────────────

class LearningStateRead(_OrmBase):
    id: UUID
    concept: str
    subject: str | None
    mastery_level: MasteryLevel
    mastery_score: float
    evidence_count: int
    last_interaction: datetime | None
    student_id: UUID


class LearningStateSummary(BaseModel):
    """Lightweight snapshot used in student progress views."""
    concept: str
    mastery_level: MasteryLevel
    mastery_score: float


# ─────────────────────────────────────────────────────────────────────────────
# Chat
# ─────────────────────────────────────────────────────────────────────────────

class ChatMessageRead(_OrmBase):
    id: UUID
    role: str
    content: str
    created_at: datetime


class ChatSessionRead(_OrmBase):
    id: UUID
    subject: str | None
    created_at: datetime
    student_id: UUID


class ChatSessionDetail(ChatSessionRead):
    messages: list[ChatMessageRead] = []


class ChatRequest(BaseModel):
    """Payload the client sends for each tutoring message."""
    session_id: UUID | None = None     # omit to start a new session
    message: str = Field(min_length=1)
    subject: str | None = None


class ChatResponse(BaseModel):
    session_id: UUID
    message_id: UUID
    answer: str
    evidence: list[dict[str, Any]] = []
    concepts_detected: list[str] = []


# ─────────────────────────────────────────────────────────────────────────────
# Quiz
# ─────────────────────────────────────────────────────────────────────────────

class QuizRead(_OrmBase):
    id: UUID
    title: str
    subject: str | None
    concept: str | None
    status: QuizStatus
    created_at: datetime


class QuizCreate(BaseModel):
    title: str
    subject: str | None = None
    concept: str | None = None
    questions: list[dict[str, Any]]


class QuizAttemptCreate(BaseModel):
    answers: dict[str, Any]  # {question_index: chosen_answer}


class QuizAttemptRead(_OrmBase):
    id: UUID
    score: float | None
    completed: bool
    started_at: datetime
    completed_at: datetime | None
    student_id: UUID
    quiz_id: UUID


# ─────────────────────────────────────────────────────────────────────────────
# Insights (educator-facing aggregates)
# ─────────────────────────────────────────────────────────────────────────────

class ConceptInsight(BaseModel):
    concept: str
    average_mastery: float
    student_count: int
    struggling_count: int   # students with mastery_score < 0.4


class StudentInsightSummary(BaseModel):
    student_id: UUID
    full_name: str
    email: EmailStr
    average_mastery: float
    concepts_tracked: int


# ─────────────────────────────────────────────────────────────────────────────
# Generic responses
# ─────────────────────────────────────────────────────────────────────────────

class MessageResponse(BaseModel):
    message: str


class ErrorResponse(BaseModel):
    detail: str
