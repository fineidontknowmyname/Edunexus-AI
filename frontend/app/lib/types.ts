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
