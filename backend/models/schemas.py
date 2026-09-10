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


class ProfileUpdate(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class ClassCreate(BaseModel):
    name: str
    subject: str | None = None
    subject_id: UUID | None = None
    semester: int | None = None


class ClassRead(_OrmBase):
    id: UUID
    name: str
    subject: str | None
    subject_id: UUID | None = None
    semester: int | None
    created_at: datetime
    educator_id: UUID


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class CategoryRead(_OrmBase):
    id: UUID
    name: str
    created_at: datetime
    created_by: UUID


class SubjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    category_id: UUID


class SubjectRead(_OrmBase):
    id: UUID
    name: str
    category_id: UUID
    created_at: datetime
    created_by: UUID


class TopicNode(BaseModel):
    topic: str = Field(min_length=1, max_length=500)
    description: str | None = None
    requires: list[str] = []
    related_concepts: list[str] = []


class TopicGraphDraft(BaseModel):
    subject_id: UUID
    topics: list[TopicNode]


class TopicGraphConfirm(BaseModel):
    topics: list[TopicNode]


class TopicRename(BaseModel):
    old_topic: str = Field(min_length=1)
    new_topic: str = Field(min_length=1, max_length=500)


class UnclassifiedChunk(BaseModel):
    chunk_id: UUID
    document_id: UUID
    document_title: str
    unit: int | None
    chapter: int | None
    text_preview: str


class ChunkTopicPatch(BaseModel):
    topic: str = Field(min_length=1, max_length=500)


class MisconceptionRuleNode(BaseModel):
    topic: str = Field(min_length=1, max_length=500)
    name: str | None = None
    description: str = Field(min_length=1)
    wrong_answer_keywords: list[str] = []
    question_keywords: list[str] = []


class MisconceptionRulesConfirm(BaseModel):
    rules: list[MisconceptionRuleNode]


class AssessmentEntry(BaseModel):
    name: str
    date: str
    covers: list[str] = []


class ClassContextRead(BaseModel):
    class_id: UUID
    syllabus: dict[str, str]
    assessments: list[AssessmentEntry]
    teacher_emphasis: str | None


class SyllabusUpdate(BaseModel):
    chapter: int
    status: str = Field(pattern="^(taught|not_taught)$")


class AssessmentsUpdate(BaseModel):
    assessments: list[AssessmentEntry]


class EducatorNoteCreate(BaseModel):
    student_id: UUID
    class_id: UUID
    note: str = Field(min_length=1)


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
