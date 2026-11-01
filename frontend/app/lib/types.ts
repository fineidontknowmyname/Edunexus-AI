export type UserRole = "student" | "educator" | "admin";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export interface LoginResponse {
  user: User;
}

export interface ClassRow {
  id: string;
  name: string;
  subject: string | null;
  subject_id: string | null;
  semester: number | null;
  join_code?: string;
  created_at: string;
  educator_id: string;
}

export interface ClassBrowseRow {
  id: string;
  name: string;
  subject: string | null;
  semester: number | null;
}

export interface Category {
  id: string;
  name: string;
  created_at: string;
  created_by: string;
}

export interface Subject {
  id: string;
  name: string;
  category_id: string;
  created_at: string;
  created_by: string;
}

export interface TopicNode {
  topic: string;
  description: string | null;
  requires: string[];
  related_concepts: string[];
}

export interface TopicGraphResponse {
  subject_id: string;
  topics: TopicNode[];
}

export interface UnclassifiedChunk {
  chunk_id: string;
  document_id: string;
  document_title: string;
  unit: number | null;
  chapter: number | null;
  text_preview: string;
}

export interface MisconceptionRule {
  topic: string;
  name: string | null;
  description: string;
  wrong_answer_keywords: string[];
  question_keywords: string[];
}

export type DocumentStatus = "pending" | "processing" | "ready" | "failed";

export interface DocumentRow {
  id: string;
  title: string;
  filename: string;
  subject: string | null;
  subject_id: string | null;
  unit: number | null;
  chapter: number | null;
  chapter_name: string | null;
  status: DocumentStatus;
  chunk_count: number;
  created_at: string;
}

export interface ClassContextResponse {
  class_id: string;
  syllabus: Record<string, "taught" | "not_taught">;
  assessments: { name: string; date: string; covers: string[] }[];
  teacher_emphasis: string | null;
}

export interface UploadJobResponse {
  document_id: string;
  job_id: string;
  status: string;
}

export interface JobStatus {
  document_id: string;
  status: "processing" | "ready" | "failed";
  detail?: string | null;
  chunk_count?: number;
}

export type SessionMode = "study" | "revision" | "exam_focus" | "socratic";
export type SourceType = "curriculum" | "general_knowledge";

export interface ChatMessageUI {
  key: string;
  id: string | null;
  role: "user" | "assistant";
  content: string;
  sourceType?: SourceType;
  citationCount?: number;
  flagged?: boolean;
  streaming?: boolean;
  verificationFailed?: boolean;
  failed?: boolean;
  errorDetail?: string;
  retryMessage?: string;
  misconceptionResolved?: string | null;
  createdAt?: string;
}

export interface ChatHistoryMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  source_type: SourceType | null;
  flagged_by_student: boolean;
  created_at: string;
}

export interface ChatHistoryResponse {
  session_id: string;
  mode: SessionMode;
  messages: ChatHistoryMessage[];
}

export interface ChatSessionSummary {
  session_id: string;
  subject: string | null;
  mode: SessionMode;
  created_at: string;
  preview: string;
}

export type ReviewStatus = "pending_review" | "approved" | "rejected" | "draft" | "archived";
export type Difficulty = "easy" | "medium" | "hard";
export type QuestionType = "single_choice" | "multiple_choice" | "true_false";

export interface QuizQuestionReview {
  id: string;
  question_text: string;
  options: string[];
  correct_answer: string | string[];
  topic: string | null;
  difficulty: Difficulty;
  status: ReviewStatus;
  question_type?: QuestionType;
  question_order?: number;
  points?: number;
  partial_credit_allowed?: boolean;
  explanation?: string | null;
  source_page_number?: number | null;
  source_document_id?: string | null;
  provenance?: {
    generator?: string;
    prompt_version?: string;
    model_index?: number | null;
    bloom_level?: string | null;
    chunk_index?: number | null;
    validation?: {
      schema?: boolean;
      duplicate_check?: boolean;
      grounding?: boolean;
    };
    batch_requested?: number;
    batch_rejected?: number;
    generated_at?: string;
  } | null;
  report_count?: number;
  curriculum_mappings?: {
    id: string;
    topic_id: string | null;
    subtopic_id: string | null;
    objective_id: string | null;
    bloom_level?: string | null;
  }[];
}

export interface QuizQuestionStudent {
  id: string;
  question_text: string;
  options: string[];
  topic: string | null;
  difficulty: Difficulty;
  question_type?: QuestionType;
  question_order?: number;
  points?: number;
  partial_credit_allowed?: boolean;
}

export interface PendingQuiz {
  id: string;
  title: string;
  description?: string | null;
  unit: number | null;
  chapter: number | null;
  status: ReviewStatus;
  version?: number;
  created_at: string;
  questions: QuizQuestionReview[];
}

export interface QuizSummaryFaculty {
  id: string;
  title: string;
  description: string | null;
  unit: number | null;
  chapter: number | null;
  status: ReviewStatus;
  version: number;
  time_limit_minutes: number | null;
  passing_percentage: number | null;
  question_count: number;
  created_at: string;
  updated_at: string | null;
}

export interface AvailableQuiz {
  id: string;
  title: string;
  unit: number | null;
  chapter: number | null;
  question_count: number;
}

export interface QuizDetail {
  id: string;
  title: string;
  class_id?: string | null;
  questions: QuizQuestionStudent[];
  held_question_count?: number;
}

export interface QuizAttemptSummary {
  id: string;
  quiz_id: string;
  quiz_title?: string;
  quiz_version?: number;
  score: number;
  topic_scores: Record<string, number>;
  completed_at: string | null;
}

export interface QuizAttemptDetail {
  id: string;
  attempt_id: string;
  quiz_id: string;
  class_id?: string | null;
  quiz_title?: string;
  quiz_version?: number;
  score: number;
  topic_scores: Record<string, number>;
  completed: boolean;
  completed_at: string | null;
  answers: {
    question_id: string;
    topic?: string | null;
    is_correct?: boolean | null;
    difficulty?: string | null;
  }[];
  results: {
    question_id: string;
    correct: boolean;
    correct_answer: string | string[];
    chosen: string | string[] | null;
    points_possible?: number;
    earned_points?: number;
    question_type?: QuestionType;
    explanation?: string | null;
    topic?: string | null;
  }[];
  quiz: QuizDetail | null;
  updated_mastery: Record<string, { mastery_score: number; trend: string; attempt_count: number }>;
}

export type RoutingMap = Record<string, RoutingLabel>;

export interface QuizAttemptResult {
  attempt_id: string;
  score: number;
  class_id?: string | null;
  topic_scores: Record<string, number>;
  results: {
    question_id: string;
    correct: boolean;
    correct_answer: string | string[];
    chosen: string | string[] | null;
    points_possible?: number;
    earned_points?: number;
    question_type?: QuestionType;
    explanation?: string | null;
  }[];
  updated_mastery: Record<string, { mastery_score: number; trend: string; attempt_count: number }>;
}

export interface QuestionReportItem {
  id: string;
  category: string;
  comment?: string | null;
  created_at: string;
  reporter_role: string;
}

export interface CoverageWarning {
  code: string;
  severity: string;
  message: string;
  unmapped_question_ids?: string[];
  topic_id?: string;
  topic_name?: string;
  objective_id?: string;
}

export interface CoverageTopicMatrixItem {
  topic_id: string;
  topic_name: string;
  unit?: number | null;
  status: string;
  question_count: number;
  question_ids?: string[];
  total_subtopics?: number;
  covered_subtopics?: number;
  total_objectives?: number;
  covered_objectives?: number;
  explanation?: string;
}

export interface CoverageReport {
  id?: string;
  quiz_id: string;
  total_questions: number;
  mapped_questions: number;
  unmapped_questions?: {
    question_id: string;
    question_order?: number;
    question_text?: string;
    reason?: string;
  }[] | number;
  total_topics?: number;
  covered_topics?: number;
  partially_covered_topics?: number;
  missing_topics?: number;
  coverage_score: number;
  coverage_matrix: CoverageTopicMatrixItem[];
  warnings: CoverageWarning[];
  advisory_notice?: string;
  acknowledged?: boolean;
  faculty_acknowledged?: boolean;
  acknowledged_at?: string | null;
  faculty_notes?: string | null;
  created_at?: string;
  generated_at?: string;
}

export type MasteryTrend = "improving" | "stable" | "declining" | "not_started";

export interface LearningPathEntry {
  topic: string;
  priority: number;
  mastery_score: number;
  attempts: number;
  trend: MasteryTrend;
  in_assessment_scope: boolean;
  syllabus_index: number;
}

export interface LearningPathResponse {
  cold_start: boolean;
  path: LearningPathEntry[];
}

export interface DashboardMasteryEntry {
  topic: string;
  score: number;
  trend: MasteryTrend;
  attempts: number;
}

export interface DashboardUpcomingFocus {
  assessment_name: string;
  days_remaining: number;
  topics_in_scope: string[];
  weak_topics_in_scope: string[];
}

export interface DashboardResponse {
  mastery: DashboardMasteryEntry[];
  engagement: { current_streak: number; longest_streak: number; staleness_flag: boolean };
  upcoming_focus: DashboardUpcomingFocus | null;
  stale_topics: string[];
}

export interface HeatmapEntry {
  topic: string;
  average_mastery: number;
  student_count: number;
  struggling_count: number;
}

export interface MisconceptionSummary {
  topic: string;
  description: string;
  count: number;
}

export interface ClassConfusionEntry {
  representative_text: string;
  cluster_size: number;
  computed_at: string;
}

export interface ClassInsightsResponse {
  heatmap: HeatmapEntry[];
  misconceptions: MisconceptionSummary[];
  class_confusion: ClassConfusionEntry[];
}

export interface AtRiskStudent {
  student_id: string;
  full_name: string;
  email: string;
  weak_topics_in_scope: string[];
  days_remaining: number;
}

export interface TrendingTopic {
  topic: string;
  questions_asked: number;
}

export interface FlaggedMessage {
  message_id: string;
  student_name: string;
  content: string;
  source_type: SourceType | null;
  created_at: string;
}

export interface EducatorNoteEntry {
  id: string;
  note: string;
  created_at: string;
}

export interface StudentFullContext {
  context: {
    student_id: string;
    mastery: Record<string, { score: number; attempts: number; trend: string }>;
    weak_topics: string[];
    strong_topics: string[];
    misconceptions: { topic: string; description: string }[];
    interaction_patterns: Record<string, { questions_asked: number; last_asked: string | null }>;
    engagement: { current_streak: number; last_interaction: string | null; staleness_flag: boolean };
    latest_educator_note: string | null;
    upcoming_focus: DashboardUpcomingFocus | null;
  };
  notes: EducatorNoteEntry[];
  learning_path: LearningPathEntry[];
}

export interface ReflectionCreate {
  class_id: string;
  subject_id?: string | null;
  topic?: string | null;
  text: string;
}

export interface ReflectionRead {
  id: string;
  text: string;
  topic: string | null;
  created_at: string;
}

export interface RecommendationSection {
  chunk_id: string;
  text: string;
  similarity: number;
}

export interface RecommendationVideo {
  video_id: string;
  title: string;
  channel: string;
  url: string;
  helpful_count?: number;
  duration?: string | null;
  thumbnail?: string | null;
  source?: "faculty" | "student_suggested" | "auto" | null;
  embeddable?: boolean;
}



export interface CurationTopicItem {
  id: string;
  topic: string;
  description: string | null;
  requires: string[];
  related_concepts: string[];
}

export interface ClassCurationTopicsResponse {
  class_id: string;
  subject_id: string | null;
  subject_name: string | null;
  status: "approved" | "no_syllabus" | "no_subject";
  topics: CurationTopicItem[];
  message: string | null;
}

export interface ProgressRecommendationItem {
  id: string;
  resource_type: "youtube" | "notes" | "quiz";
  title: string;
  url?: string | null;
  content?: string | null;
  content_snippet?: string | null;
  video_id?: string | null;
  document_id?: string | null;
  file_url?: string | null;
  channel?: string | null;
  duration?: string | null;
  thumbnail?: string | null;
  source: "faculty" | "student_suggested" | "auto" | "system" | string;
  embeddable?: boolean;
  action: "watch" | "read" | "practise" | string;
  action_label?: string;
  action_url?: string | null;
  badge_label?: string;
  badge_color?: string;
  topic?: string;
}

export interface WeakTopicRecommendationGroup {
  topic_id?: string | null;
  topic: string;
  topic_name?: string;
  mastery_score: number;
  mastery_band: string;
  evidence_state: string;
  attempts: number;
  accuracy?: number;
  resources: ProgressRecommendationItem[];
  recommendations?: ProgressRecommendationItem[];
}

export interface InsufficientEvidenceTopic {
  topic_id?: string | null;
  topic: string;
  topic_name?: string;
  mastery_score?: number;
  attempts?: number;
  evidence_state?: string;
  reason?: string;
  message?: string;
  suggested_action?: string;
  action_url?: string | null;
}

export interface ProgressRecommendationsResponse {
  class_id: string;
  class_name?: string;
  subject_id?: string | null;
  subject_name?: string | null;
  weak_topics: WeakTopicRecommendationGroup[];
  insufficient_evidence_topics?: InsufficientEvidenceTopic[];
  insufficient_evidence?: InsufficientEvidenceTopic[];
  all_topics_strong?: boolean;
  total_tracked_topics?: number;
  total_recommended_resources?: number;
}

export interface TopicQuizPrepContext {
  topic: string;
  topic_id?: string | null;
  class_id?: string | null;
  class_name?: string | null;
  subject_id?: string | null;
  subject_name?: string | null;
  mastery_score?: number | null;
  attempts?: number;
}

export interface TopicQuizGenerateRequest {
  class_id: string;
  topic: string;
  topic_id?: string | null;
  num_questions?: number;
}

export interface TopicQuizResponse {
  quiz_id: string;
  title: string;
  topic: string;
  question_count: number;
  status: string;
}

export interface RecommendationNote {
  resource_id: string;
  title: string;
  content: string;
  content_length?: number;
  truncated?: boolean;
  author_role: string;
  helpful_count?: number;
}

export type RoutingLabel = "reinforce" | "advance" | "intervene";

export interface RecommendationResponse {
  id?: string | null;
  routing: RoutingLabel;
  learning_tag: string | null;
  mode: "static" | "ai_session" | "diagnostic" | "verification" | "advance" | "initial_assessment";
  sections: RecommendationSection[];
  videos: RecommendationVideo[];
  notes?: RecommendationNote[];
  socratic_seed_message: string | null;
  reason?: string | null;
}

export interface LearningResourceRow {
  id: string;
  class_id: string;
  topic: string;
  title: string;
  resource_type: "youtube" | "notes";
  url?: string | null;
  content?: string | null;
  content_length?: number | null;
  truncated?: boolean;
  status: "pending_review" | "approved" | "rejected";
  helpful_count: number;
  report_count: number;
  has_voted: boolean;
  uploaded_by_id: string;
  uploaded_by_name?: string | null;
  created_at: string;
  video_id?: string | null;
  channel?: string | null;
  duration?: string | null;
  thumbnail?: string | null;
  source?: "faculty" | "student_suggested" | "auto" | null;
  embeddable?: boolean;
}


