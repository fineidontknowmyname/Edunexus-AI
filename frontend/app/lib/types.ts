export type UserRole = "student" | "educator" | "admin";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export interface Token {
  access_token: string;
  token_type: string;
}

export interface ClassRow {
  id: string;
  name: string;
  subject: string | null;
  semester: number | null;
  created_at: string;
  educator_id: string;
}

export type DocumentStatus = "pending" | "processing" | "ready" | "failed";

export interface DocumentRow {
  id: string;
  title: string;
  filename: string;
  subject: string | null;
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

export type SessionMode = "study" | "revision" | "exam_focus";
export type SourceType = "curriculum" | "general_knowledge";

export interface ChatMessageUI {
  id: string | null;
  role: "user" | "assistant";
  content: string;
  sourceType?: SourceType;
  citationCount?: number;
  flagged?: boolean;
  streaming?: boolean;
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

export type ReviewStatus = "pending_review" | "approved" | "rejected";
export type Difficulty = "easy" | "medium" | "hard";

export interface QuizQuestionReview {
  id: string;
  question_text: string;
  options: string[];
  correct_answer: string;
  topic: string | null;
  difficulty: Difficulty;
  status: ReviewStatus;
}

export interface QuizQuestionStudent {
  id: string;
  question_text: string;
  options: string[];
  topic: string | null;
  difficulty: Difficulty;
}

export interface PendingQuiz {
  id: string;
  title: string;
  unit: number | null;
  chapter: number | null;
  status: ReviewStatus;
  created_at: string;
  questions: QuizQuestionReview[];
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
  questions: QuizQuestionStudent[];
}

export interface QuizAttemptResult {
  attempt_id: string;
  score: number;
  topic_scores: Record<string, number>;
  results: { question_id: string; correct: boolean; correct_answer: string; chosen: string | null }[];
  updated_mastery: Record<string, { mastery_score: number; trend: string; attempt_count: number }>;
}
