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
