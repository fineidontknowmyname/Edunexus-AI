"use client";

import { DragEvent, FormEvent, useCallback, useEffect, useState } from "react";
import { apiFetch, ApiError } from "../../lib/api";
import { usePoll } from "../../lib/hooks/usePoll";
import type { ClassRow, DocumentRow, JobStatus, UploadJobResponse } from "../../lib/types";
import { Card } from "../../components/ui/Card";
import { Input } from "../../components/ui/Input";
import { Button } from "../../components/ui/Button";
import { Badge } from "../../components/ui/Badge";
import { SyllabusChecklist } from "../../components/progress/SyllabusChecklist";

const STATUS_TONE: Record<DocumentRow["status"], "gray" | "blue" | "green" | "red"> = {
  pending: "gray",
  processing: "blue",
  ready: "green",
  failed: "red",
};

export default function UploadPage() {
  const [classes, setClasses] = useState<ClassRow[]>([]);
  const [classId, setClassId] = useState<string>("");
  const [classesLoading, setClassesLoading] = useState(true);

  const [documents, setDocuments] = useState<DocumentRow[]>([]);
  const [docsLoading, setDocsLoading] = useState(false);

  const [newClassName, setNewClassName] = useState("");
  const [creatingClass, setCreatingClass] = useState(false);

  const [file, setFile] = useState<File | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [title, setTitle] = useState("");
  const [subject, setSubject] = useState("Operating Systems");
  const [unit, setUnit] = useState(1);
  const [chapter, setChapter] = useState(1);
  const [chapterName, setChapterName] = useState("");

  const [jobId, setJobId] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const loadClasses = useCallback(async () => {
    setClassesLoading(true);
    try {
      const rows = await apiFetch<ClassRow[]>("/classes/");
      setClasses(rows);
      if (rows.length > 0 && !classId) setClassId(rows[0].id);
    } finally {
      setClassesLoading(false);
    }
  }, [classId]);

  useEffect(() => {
    loadClasses();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleCreateClass(e: FormEvent) {
    e.preventDefault();
    if (!newClassName.trim()) return;
    setCreatingClass(true);
    try {
      const created = await apiFetch<ClassRow>("/classes/", {
        method: "POST",
        body: { name: newClassName, subject },
      });
      setNewClassName("");
      await loadClasses();
      setClassId(created.id);
    } finally {
      setCreatingClass(false);
    }
  }

  const loadDocuments = useCallback(async () => {
    if (!classId) return;
    setDocsLoading(true);
    try {
      const rows = await apiFetch<DocumentRow[]>(`/documents/?class_id=${classId}`);
      setDocuments(rows);
    } finally {
      setDocsLoading(false);
    }
  }, [classId]);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  const { data: jobStatus } = usePoll<JobStatus>(
    () => apiFetch<JobStatus>(`/documents/status/${jobId}`),
    {
      enabled: jobId !== null,
      intervalMs: 3000,
      until: (data) => data.status === "ready" || data.status === "failed",
    }
  );

  useEffect(() => {
    if (jobStatus?.status === "ready" || jobStatus?.status === "failed") {
      loadDocuments();
    }
  }, [jobStatus?.status, loadDocuments]);

  function handleDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragActive(false);
    const dropped = e.dataTransfer.files?.[0];
    if (dropped) {
      setFile(dropped);
      if (!title) setTitle(dropped.name.replace(/\.[^/.]+$/, ""));
    }
  }

  async function handleUpload(e: FormEvent) {
    e.preventDefault();
    if (!file || !classId) return;
    setUploadError(null);
    setSubmitting(true);
    setJobId(null);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("class_id", classId);
    formData.append("title", title || file.name);
    formData.append("subject", subject);
    formData.append("unit", String(unit));
    formData.append("chapter", String(chapter));
    formData.append("chapter_name", chapterName);

    try {
      const result = await apiFetch<UploadJobResponse>("/documents/upload", {
        method: "POST",
        body: formData,
      });
      setJobId(result.job_id);
      setFile(null);
    } catch (err) {
      setUploadError(err instanceof ApiError ? err.message : "Upload failed.");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(documentId: string) {
    await apiFetch(`/documents/${documentId}`, { method: "DELETE" });
    loadDocuments();
  }

  return (
    <div className="max-w-3xl mx-auto flex flex-col gap-6">
      <h1 className="text-2xl font-bold text-gray-900">Curriculum Upload</h1>

      <Card>
        <h2 className="font-semibold text-gray-900 mb-3">Class</h2>
        {classesLoading ? (
          <p className="text-sm text-gray-500">Loading classes…</p>
        ) : classes.length > 0 ? (
          <select
            className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
            value={classId}
            onChange={(e) => setClassId(e.target.value)}
          >
            {classes.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} {c.subject ? `— ${c.subject}` : ""}
              </option>
            ))}
          </select>
        ) : (
          <p className="text-sm text-gray-500 mb-3">
            You have no classes yet — create one to start uploading curriculum.
          </p>
        )}

        <form onSubmit={handleCreateClass} className="flex gap-2 mt-3">
          <Input
            placeholder="New class name (e.g. OS Sem 5 - Section A)"
            value={newClassName}
            onChange={(e) => setNewClassName(e.target.value)}
            className="flex-1"
          />
          <Button type="submit" variant="secondary" loading={creatingClass}>
            Create class
          </Button>
        </form>
      </Card>

      <Card>
        <h2 className="font-semibold text-gray-900 mb-3">Upload document</h2>
        <form onSubmit={handleUpload} className="flex flex-col gap-4">
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setDragActive(true);
            }}
            onDragLeave={() => setDragActive(false)}
            onDrop={handleDrop}
            className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
              dragActive ? "border-blue-500 bg-blue-50" : "border-gray-300"
            }`}
            onClick={() => document.getElementById("file-input")?.click()}
          >
            <input
              id="file-input"
              type="file"
              accept=".pdf,.pptx,.docx,.txt"
              className="hidden"
              onChange={(e) => {
                const selected = e.target.files?.[0] ?? null;
                setFile(selected);
                if (selected && !title) setTitle(selected.name.replace(/\.[^/.]+$/, ""));
              }}
            />
            {file ? (
              <p className="text-sm text-gray-700">
                {file.name} <span className="text-gray-400">({(file.size / 1024).toFixed(0)} KB)</span>
              </p>
            ) : (
              <p className="text-sm text-gray-500">
                Drag & drop a PDF, PPTX, or DOCX file here, or click to browse
              </p>
            )}
          </div>

          <Input label="Title" value={title} onChange={(e) => setTitle(e.target.value)} required />
          <div className="grid grid-cols-3 gap-3">
            <Input label="Subject" value={subject} onChange={(e) => setSubject(e.target.value)} />
            <Input
              label="Unit"
              type="number"
              min={1}
              value={unit}
              onChange={(e) => setUnit(Number(e.target.value))}
            />
            <Input
              label="Chapter"
              type="number"
              min={1}
              value={chapter}
              onChange={(e) => setChapter(Number(e.target.value))}
            />
          </div>
          <Input
            label="Chapter name"
            value={chapterName}
            onChange={(e) => setChapterName(e.target.value)}
            placeholder="e.g. Process Scheduling"
          />

          {uploadError && <p className="text-sm text-red-600">{uploadError}</p>}

          <Button type="submit" disabled={!file || !classId} loading={submitting}>
            Upload
          </Button>
        </form>

        {jobStatus && (
          <div className="mt-4 flex items-center gap-2 text-sm">
            <span className="text-gray-600">Ingestion status:</span>
            <Badge tone={STATUS_TONE[jobStatus.status === "processing" ? "processing" : jobStatus.status]}>
              {jobStatus.status === "processing" ? "Processing…" : jobStatus.status}
            </Badge>
            {jobStatus.status === "ready" && (
              <span className="text-gray-500">
                Ready — {jobStatus.chunk_count ?? 0} chunks indexed. You can now ask questions about this content.
              </span>
            )}
            {jobStatus.status === "failed" && (
              <span className="text-red-600">{jobStatus.detail}</span>
            )}
          </div>
        )}
      </Card>

      <Card>
        <h2 className="font-semibold text-gray-900 mb-3">Documents</h2>
        {docsLoading ? (
          <p className="text-sm text-gray-500">Loading…</p>
        ) : documents.length === 0 ? (
          <p className="text-sm text-gray-500">No documents uploaded yet for this class.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gray-500 border-b border-gray-200">
                <th className="py-2 font-medium">Title</th>
                <th className="py-2 font-medium">Unit / Chapter</th>
                <th className="py-2 font-medium">Status</th>
                <th className="py-2 font-medium">Chunks</th>
                <th className="py-2 font-medium"></th>
              </tr>
            </thead>
            <tbody>
              {documents.map((doc) => (
                <tr key={doc.id} className="border-b border-gray-100">
                  <td className="py-2 text-gray-900">{doc.title}</td>
                  <td className="py-2 text-gray-600">
                    {doc.unit ?? "—"} / {doc.chapter ?? "—"}
                  </td>
                  <td className="py-2">
                    <Badge tone={STATUS_TONE[doc.status]}>{doc.status}</Badge>
                  </td>
                  <td className="py-2 text-gray-600">{doc.chunk_count}</td>
                  <td className="py-2 text-right">
                    <button
                      onClick={() => handleDelete(doc.id)}
                      className="text-xs text-red-600 hover:underline"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      {classId && <SyllabusChecklist classId={classId} documents={documents} />}
    </div>
  );
}
