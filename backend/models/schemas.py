from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from backend.models.db import MasteryTrend, ReviewStatus, SessionMode, UserRole


class _OrmBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: UUID | None = None
    role: UserRole | None = None


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


class ClassCreate(BaseModel):
    name: str
    subject: str | None = None
    semester: int | None = None


class ClassRead(_OrmBase):
    id: UUID
    name: str
    subject: str | None
    semester: int | None
    created_at: datetime
    educator_id: UUID


class DocumentRead(_OrmBase):
    id: UUID
    title: str
    filename: str
    subject: str | None
    unit: int | None
    chapter: int | None
    chapter_name: str | None
    is_indexed: bool
    chunk_count: int
    created_at: datetime
    uploaded_by_id: UUID
    class_id: UUID


class DocumentCreate(BaseModel):
    title: str
    subject: str | None = None


class TopicMasteryRead(_OrmBase):
    id: UUID
    topic: str
    unit: int | None
    mastery_score: float
    attempt_count: int
    trend: MasteryTrend
    last_attempt_at: datetime | None
    student_id: UUID


class TopicMasterySummary(BaseModel):
    topic: str
    mastery_score: float
    trend: MasteryTrend


class ChatMessageRead(_OrmBase):
    id: UUID
    role: str
    content: str
    created_at: datetime


class ChatSessionRead(_OrmBase):
    id: UUID
    subject: str | None
    mode: SessionMode
    created_at: datetime
    student_id: UUID


class ChatSessionDetail(ChatSessionRead):
    messages: list[ChatMessageRead] = []


class ChatRequest(BaseModel):
    session_id: UUID | None = None
    class_id: UUID | None = None
    message: str = Field(min_length=1)
    mode: SessionMode = SessionMode.study


class ChatMessageFlag(BaseModel):
    flagged: bool = True


class QuizRead(_OrmBase):
    id: UUID
    title: str
    unit: int | None
    chapter: int | None
    status: ReviewStatus
    created_at: datetime
    class_id: UUID


class QuizCreate(BaseModel):
    title: str
    unit: int | None = None
    chapter: int | None = None
    class_id: UUID


class QuizGenerateRequest(BaseModel):
    class_id: UUID
    document_id: UUID | None = None
    title: str
    unit: int = 1
    chapter: int = 1
    num_questions: int = Field(default=10, ge=1, le=20)


class QuestionStatusUpdate(BaseModel):
    status: ReviewStatus


class QuizAttemptCreate(BaseModel):
    answers: dict[str, Any]


class QuizAttemptRead(_OrmBase):
    id: UUID
    score: float | None
    completed: bool
    started_at: datetime
    completed_at: datetime | None
    student_id: UUID
    quiz_id: UUID


class ConceptInsight(BaseModel):
    concept: str
    average_mastery: float
    student_count: int
    struggling_count: int


class StudentInsightSummary(BaseModel):
    student_id: UUID
    full_name: str
    email: EmailStr
    average_mastery: float
    concepts_tracked: int


class MessageResponse(BaseModel):
    message: str


class ErrorResponse(BaseModel):
    detail: str
