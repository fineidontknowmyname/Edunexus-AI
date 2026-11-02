from datetime import datetime
import json
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from backend.models.db import (
    BloomLevel,
    CoverageStatus,
    MasteryTrend,
    QuestionDifficulty,
    QuestionType,
    ReviewStatus,
    SessionMode,
    UserRole,
)


class _OrmBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TokenData(BaseModel):
    user_id: UUID | None = None
    role: UserRole | None = None


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    full_name: str = Field(min_length=1, max_length=255)
    role: UserRole = UserRole.student


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(max_length=72)


class UserRead(_OrmBase):
    id: UUID
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    timezone: str = "UTC"
    created_at: datetime


class LoginResponse(BaseModel):
    user: UserRead


class UserUpdate(BaseModel):
    full_name: str | None = None
    is_active: bool | None = None


class ProfileUpdate(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(max_length=72)
    new_password: str = Field(min_length=8, max_length=72)


class ClassCreate(BaseModel):
    name: str
    subject: str | None = None
    subject_id: UUID | None = None
    semester: int | None = None


class ClassRead(_OrmBase):
    """Full class representation returned to educators (includes join_code and educator_id)."""

    id: UUID
    name: str
    subject: str | None
    subject_id: UUID | None = None
    semester: int | None
    join_code: str
    created_at: datetime
    educator_id: UUID


class ClassBrowseRead(_OrmBase):
    """Stripped representation returned to students browsing classes.

    Omits educator_id (unnecessary data exposure) and join_code (the code must
    be obtained from the educator out-of-band; sending it in the browse list
    would defeat the access-control purpose).
    """

    id: UUID
    name: str
    subject: str | None
    semester: int | None


class EnrollRequest(BaseModel):
    """Body required when a student enrolls in a class."""

    join_code: str


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


class ReflectionCreate(BaseModel):
    class_id: UUID
    subject_id: UUID | None = None
    topic: str | None = None
    text: str = Field(min_length=1, max_length=2000)


class ReflectionRead(_OrmBase):
    id: UUID
    text: str
    topic: str | None
    created_at: datetime


class ReflectionClusterRead(_OrmBase):
    id: UUID
    representative_text: str
    cluster_size: int
    computed_at: datetime


class PrerequisiteAdvisory(BaseModel):
    topic: str
    reason: str
    attempted: bool = False


class RecommendationRead(BaseModel):
    id: str | None = None
    routing: str
    learning_tag: str | None
    mode: str
    reason: str | None = None
    sections: list[dict[str, Any]] = []
    documents: list[dict[str, Any]] = []
    has_material: bool = False
    chunk_count: int = 0
    videos: list[dict[str, Any]] = []
    notes: list[dict[str, Any]] = []
    socratic_seed_message: str | None = None
    prerequisite_advisory: PrerequisiteAdvisory | None = None


RecommendationResponse = RecommendationRead


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


def _parse_mastery_v2(v: Any) -> dict[str, Any] | None:
    if v is None:
        return None
    if isinstance(v, dict):
        return v
    if isinstance(v, str):
        try:
            parsed = json.loads(v)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return None
    return None


class TopicMasteryRead(_OrmBase):
    id: UUID
    topic: str
    unit: int | None
    mastery_score: float
    attempt_count: int
    trend: MasteryTrend
    last_attempt_at: datetime | None
    student_id: UUID
    mastery_v2: dict[str, Any] | None = None

    @field_validator("mastery_v2", mode="before")
    @classmethod
    def _validate_mastery_v2(cls, v: Any) -> dict[str, Any] | None:
        return _parse_mastery_v2(v)


class TopicMasterySummary(BaseModel):
    topic: str
    mastery_score: float
    trend: MasteryTrend
    mastery_v2: dict[str, Any] | None = None

    @field_validator("mastery_v2", mode="before")
    @classmethod
    def _validate_mastery_v2(cls, v: Any) -> dict[str, Any] | None:
        return _parse_mastery_v2(v)


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
    message: str = Field(min_length=1, max_length=4000)
    mode: SessionMode = SessionMode.study
    topic: str | None = Field(default=None, max_length=500)


class ChatMessageFlag(BaseModel):
    flagged: bool = True


class QuizRead(_OrmBase):
    id: UUID
    title: str
    description: str | None = None
    unit: int | None = None
    chapter: int | None = None
    status: ReviewStatus
    version: int = 1
    generation_type: str = "manual"
    time_limit_minutes: int | None = None
    passing_percentage: float = 60.0
    created_at: datetime
    updated_at: datetime | None = None
    class_id: UUID


class QuizCreate(BaseModel):
    title: str
    description: str | None = None
    unit: int | None = None
    chapter: int | None = None
    class_id: UUID
    document_id: UUID | None = None
    time_limit_minutes: int | None = None
    passing_percentage: float = 60.0
    status: ReviewStatus = ReviewStatus.draft


class QuizUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    unit: int | None = None
    chapter: int | None = None
    document_id: UUID | None = None
    time_limit_minutes: int | None = None
    passing_percentage: float | None = None
    status: ReviewStatus | None = None


class QuizReorderPayload(BaseModel):
    question_ids: list[UUID]


class CoverageAcknowledgePayload(BaseModel):
    faculty_notes: str | None = None


class QuizGenerateRequest(BaseModel):
    class_id: UUID
    document_id: UUID | None = None
    title: str
    unit: int = 1
    chapter: int = 1
    num_questions: int = Field(default=10, ge=1, le=20)


class TopicQuizRequest(BaseModel):
    class_id: UUID
    topic: str = Field(min_length=1, max_length=500)
    topic_id: UUID | None = None
    num_questions: int = Field(default=5, ge=1, le=10)


class TopicQuizResponse(BaseModel):
    quiz_id: UUID
    title: str
    topic: str
    question_count: int
    status: ReviewStatus


class QuestionStatusUpdate(BaseModel):
    status: ReviewStatus


class QuestionFeedbackCreate(BaseModel):
    category: str = Field(
        ...,
        description=(
            "Feedback category: incorrect_question, incorrect_answer, "
            "incorrect_explanation, unrelated_topic, ambiguous_wording, "
            "incorrect_difficulty, missing_source, technical_failure, other"
        ),
    )
    comment: str | None = Field(default=None, max_length=1000)


class QuestionFeedbackResponse(BaseModel):
    report_id: str
    question_id: str
    quiz_id: str
    category: str
    topic: str | None = None
    status: str = "received"
    created_at: str
    message: str


class QuestionReportItem(BaseModel):
    id: str
    category: str
    comment: str | None = None
    created_at: str
    reporter_role: str


class QuizQuestionCreate(BaseModel):
    question_text: str = Field(min_length=1)
    options: list[str] = Field(min_length=2)
    correct_answer: str | list[str]
    question_type: QuestionType = QuestionType.single_choice
    question_order: int | None = None
    explanation: str | None = None
    points: float = 1.0
    topic: str | None = None
    topic_id: UUID | None = None
    subtopic_id: UUID | None = None
    objective_id: UUID | None = None
    bloom_level: BloomLevel | None = None
    difficulty: QuestionDifficulty = QuestionDifficulty.medium
    partial_credit_allowed: bool = False
    source_document_id: UUID | None = None
    source_page_number: int | None = None


class QuizQuestionUpdate(BaseModel):
    question_text: str | None = None
    options: list[str] | None = None
    correct_answer: str | list[str] | None = None
    question_type: QuestionType | None = None
    question_order: int | None = None
    explanation: str | None = None
    points: float | None = None
    topic: str | None = None
    topic_id: UUID | None = None
    subtopic_id: UUID | None = None
    objective_id: UUID | None = None
    difficulty: QuestionDifficulty | None = None
    status: ReviewStatus | None = None
    partial_credit_allowed: bool | None = None
    source_document_id: UUID | None = None
    source_page_number: int | None = None


class QuizQuestionRead(_OrmBase):
    id: UUID
    quiz_id: UUID
    question_text: str
    options: str
    correct_answer: str
    question_type: str = "single_choice"
    question_order: int = 1
    explanation: str | None = None
    points: float = 1.0
    topic: str | None = None
    topic_id: UUID | None = None
    difficulty: QuestionDifficulty
    status: ReviewStatus
    version: int = 1
    source_document_id: UUID | None = None
    source_document_name: str | None = None
    source_page_number: int | None = None
    document_name: str | None = None
    page: int | None = None
    section_heading: str | None = None
    snippet: str | None = None
    partial_credit_allowed: bool = False
    generation_meta: str | None = None
    provenance: dict[str, Any] | None = None


class SyllabusSubtopicCreate(BaseModel):
    topic_id: UUID
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    order_index: int = 0


class SyllabusSubtopicRead(_OrmBase):
    id: UUID
    topic_id: UUID
    name: str
    description: str | None
    order_index: int
    created_at: datetime


class LearningObjectiveCreate(BaseModel):
    topic_id: UUID
    subtopic_id: UUID | None = None
    code: str | None = None
    statement: str = Field(min_length=1)
    bloom_level: BloomLevel | None = None
    order_index: int = 0


class LearningObjectiveRead(_OrmBase):
    id: UUID
    topic_id: UUID
    subtopic_id: UUID | None
    code: str | None
    statement: str
    bloom_level: str | None
    order_index: int
    created_at: datetime


class QuizCoverageReportRead(_OrmBase):
    id: UUID
    quiz_id: UUID
    document_id: UUID | None
    total_topics: int
    covered_topics: int
    partially_covered_topics: int
    missing_topics: int
    coverage_score: float
    coverage_matrix: str | None
    warnings: str | None
    faculty_acknowledged: bool
    faculty_notes: str | None
    generated_at: datetime


class QuizAttemptCreate(BaseModel):
    answers: dict[str, Any]


class QuizAttemptRead(_OrmBase):
    id: UUID
    score: float | None
    score_ratio: float | None = None
    passing_ratio: float | None = None
    quiz_version: int = 1
    points_earned: float | None = None
    max_points: float | None = None
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


class LearningResourceCreate(BaseModel):
    class_id: str
    topic: str
    topic_id: str | None = None
    title: str = ""
    resource_type: str
    url: str | None = None
    content: str | None = None


class LearningResourceRead(BaseModel):
    id: str
    class_id: str
    topic: str
    topic_id: str | None = None
    subject_id: str | None = None
    title: str
    resource_type: str
    url: str | None = None
    content: str | None = None
    content_length: int | None = None
    truncated: bool = False
    status: str
    helpful_count: int
    report_count: int
    has_voted: bool = False
    uploaded_by_id: str
    uploaded_by_name: str | None = None
    created_at: datetime
    video_id: str | None = None
    channel: str | None = None
    duration: str | None = None
    thumbnail: str | None = None
    source: str | None = None
    embeddable: bool = True


class LearningResourceReview(BaseModel):
    status: str


class ProgressRecommendationItem(BaseModel):
    id: str
    title: str
    resource_type: str
    url: str | None = None
    content: str | None = None
    content_snippet: str | None = None
    source: str
    channel: str | None = None
    duration: str | None = None
    thumbnail: str | None = None
    action: str
    action_label: str
    topic: str
    video_id: str | None = None
    document_id: str | None = None
    file_url: str | None = None
    page_number: int | None = None
    match_type: str | None = None
    match_reason: str | None = None


class WeakTopicRecommendationGroup(BaseModel):
    topic: str
    topic_id: str | None = None
    mastery_score: float
    attempts: int
    evidence_state: str
    mastery_band: str
    resources: list[ProgressRecommendationItem]


class InsufficientEvidenceTopic(BaseModel):
    topic: str
    topic_id: str | None = None
    mastery_score: float
    attempts: int
    evidence_state: str
    reason: str


class ProgressRecommendationsResponse(BaseModel):
    class_id: str
    class_name: str
    subject_id: str | None = None
    subject_name: str | None = None
    weak_topics: list[WeakTopicRecommendationGroup]
    developing_topics: list[WeakTopicRecommendationGroup] = []
    insufficient_evidence_topics: list[InsufficientEvidenceTopic]
    all_topics_strong: bool
    total_tracked_topics: int


class SyllabusStatusRead(BaseModel):
    subject_id: str
    subject_name: str
    status: str
    topic_count: int
    topics: list[dict[str, Any]]
    updated_at: str | None = None


class CurriculumReviewApprovePayload(BaseModel):
    topic_ids: list[str] | None = None


class CurriculumReviewRejectPayload(BaseModel):
    topic_ids: list[str] | None = None


class TopicUpdatePayload(BaseModel):
    topic: str | None = None
    unit: int | None = None
    description: str | None = None


class SubtopicUpdatePayload(BaseModel):
    name: str | None = None
    description: str | None = None


class ObjectiveUpdatePayload(BaseModel):
    code: str | None = None
    statement: str | None = None
    bloom_level: str | None = None
