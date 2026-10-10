"use client";

import { DragEvent, FormEvent, Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { CheckCircle2, FileText, FileUp, Loader2, Plus, School, Trash2, UploadCloud, XCircle } from "lucide-react";
import { apiFetch, errorMessage } from "../../lib/api";
import { useApi } from "../../lib/hooks/useApi";
import { usePoll } from "../../lib/hooks/usePoll";
import { useClassParam, useClasses } from "../../lib/hooks/useClasses";
import { UPLOAD_MAX_BYTES } from "../../lib/constants";
import { formatBytes, formatRelative } from "../../lib/format";
import type { ClassRow, DocumentRow, JobStatus, Subject, UploadJobResponse } from "../../lib/types";
import { Card, CardHeader } from "../../components/ui/Card";
import { Input, Select } from "../../components/ui/Input";
import { Button } from "../../components/ui/Button";
import { Alert, EmptyState, ErrorState, PageSkeleton, SkeletonText } from "../../components/ui/Feedback";
import { ConfirmDialog } from "../../components/ui/Modal";
import { PageContainer, PageHeader } from "../../components/ui/PageHeader";
import { ClassPicker } from "../../components/layout/ClassPicker";
import { DocumentStatusBadge } from "../../components/educator/DocumentStatusBadge";
import { SyllabusChecklist } from "../../components/progress/SyllabusChecklist";
import { cn } from "../../lib/cn";

const ACCEPTED = [".pdf", ".pptx", ".docx", ".txt"];

function validateFile(file: File): string | null {
  const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
  if (!ACCEPTED.includes(ext)) return `“${file.name}” isn't a supported file type. Use PDF, PPTX, DOCX or TXT.`;
  if (file.size > UPLOAD_MAX_BYTES) {
    return `“${file.name}” is ${formatBytes(file.size)}. The maximum upload size is ${formatBytes(UPLOAD_MAX_BYTES)}. Try splitting it into smaller chapters.`;
  }
  if (file.size === 0) return `“${file.name}” is empty.`;
  return null;
}

export default function UploadPage() {
  return (
    <Suspense fallback={<PageContainer><PageSkeleton /></PageContainer>}>
      <UploadPageInner />
    </Suspense>
  );
}

function UploadPageInner() {
  const classes = useClasses();
  const [classId, setClassId] = useClassParam(classes.data);
  const subjects = useApi<Subject[]>("/subjects");

  if (classes.error) {
    return (
      <PageContainer>
        <PageHeader title="Curriculum" />
        <ErrorState message={classes.error} onRetry={classes.reload} />
      </PageContainer>
    );
  }
  if (!classes.data) {
    return (
      <PageContainer>
        <PageSkeleton />
      </PageContainer>
    );
  }

  const activeClass = classes.data.find((c) => c.id === classId) ?? null;

  return (
    <PageContainer>
      <PageHeader
        title="Curriculum"
        description="Upload chapters and notes. The tutor answers from these first, and quizzes are generated from them."
        actions={<ClassPicker classes={classes.data} value={classId} onChange={setClassId} />}
      />

      {classes.data.length === 0 ? (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
          <EmptyState
            icon={<School className="h-5 w-5" />}
            title="Create your first class"
            description="Classes group your students and their course material. Create one to start uploading."
          />
          <CreateClassCard subjects={subjects.data ?? []} onCreated={(c) => { classes.reload(); setClassId(c.id); }} />
        </div>
      ) : activeClass ? (
        <ClassMaterials key={activeClass.id} activeClass={activeClass} subjects={subjects.data ?? []} onClassCreated={(c) => { classes.reload(); setClassId(c.id); }} />
      ) : null}
    </PageContainer>
  );
}

function CreateClassCard({ subjects, onCreated }: { subjects: Subject[]; onCreated: (c: ClassRow) => void }) {
  const [name, setName] = useState("");
  const [subjectId, setSubjectId] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setSaving(true);
    setError(null);
    try {
      const created = await apiFetch<ClassRow>("/classes/", {
        method: "POST",
        body: { name: name.trim(), subject_id: subjectId || subjects[0]?.id || null },
      });
      setName("");
      onCreated(created);
    } catch (err) {
      setError(errorMessage(err, "Couldn't create the class."));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader icon={<Plus className="h-4 w-4" />} title="New class" />
      <form onSubmit={handleCreate} className="flex flex-col gap-3">
        <Input label="Class name" placeholder="e.g. OS Sem 5, Section A" value={name} onChange={(e) => setName(e.target.value)} required />
        {subjects.length > 0 && (
          <Select label="Subject" value={subjectId || subjects[0].id} onChange={(e) => setSubjectId(e.target.value)}>
            {subjects.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </Select>
        )}
        {error && <Alert tone="danger">{error}</Alert>}
        <Button type="submit" variant="secondary" loading={saving} disabled={!name.trim()}>
          Create class
        </Button>
      </form>
    </Card>
  );
}

function ClassMaterials({
  activeClass,
  subjects,
  onClassCreated,
}: {
  activeClass: ClassRow;
  subjects: Subject[];
  onClassCreated: (c: ClassRow) => void;
}) {
  const documents = useApi<DocumentRow[]>(`/documents/?class_id=${activeClass.id}`);
  const [pendingDelete, setPendingDelete] = useState<DocumentRow | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const reloadDocs = documents.reload;

  const anyProcessing = (documents.data ?? []).some((d) => d.status === "processing" || d.status === "pending");
  useEffect(() => {
    if (!anyProcessing) return;
    const timer = setInterval(reloadDocs, 4000);
    return () => clearInterval(timer);
  }, [anyProcessing, reloadDocs]);

  async function confirmDelete() {
    if (!pendingDelete) return;
    setDeleting(true);
    setListError(null);
    try {
      await apiFetch(`/documents/${pendingDelete.id}`, { method: "DELETE" });
      documents.mutate((prev) => prev?.filter((d) => d.id !== pendingDelete.id) ?? null);
      setPendingDelete(null);
    } catch (err) {
      setListError(errorMessage(err, "Couldn't delete that document."));
      setPendingDelete(null);
    } finally {
      setDeleting(false);
    }
  }

  return (
    <>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <UploadCard activeClass={activeClass} subjects={subjects} onUploaded={reloadDocs} />
        <div className="flex flex-col gap-6">
          <SyllabusChecklist classId={activeClass.id} documents={documents.data ?? []} />
          <CreateClassCard subjects={subjects} onCreated={onClassCreated} />
        </div>
      </div>

      <Card padded={false}>
        <div className="p-5 pb-0 sm:p-6 sm:pb-0">
          <CardHeader
            icon={<FileText className="h-4 w-4" />}
            title="Documents"
            description={`Course material for ${activeClass.name}.`}
            actions={anyProcessing ? <span className="inline-flex items-center gap-1.5 text-xs text-info"><Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />Refreshing while documents index</span> : undefined}
          />
        </div>
        {listError && <Alert tone="danger" className="mx-5 mb-4 sm:mx-6">{listError}</Alert>}
        {documents.error && !documents.data ? (
          <div className="p-5 pt-0 sm:p-6 sm:pt-0"><ErrorState message={documents.error} onRetry={documents.reload} /></div>
        ) : !documents.data ? (
          <div className="p-5 pt-0 sm:p-6 sm:pt-0"><SkeletonText lines={4} /></div>
        ) : documents.data.length === 0 ? (
          <div className="p-5 pt-0 sm:p-6 sm:pt-0">
            <EmptyState
              compact
              icon={<FileUp className="h-5 w-5" />}
              title="No documents yet"
              description="Upload your first chapter above. Students can ask about it as soon as it's indexed."
            />
          </div>
        ) : (
          <>
            <div className="hidden overflow-x-auto md:block">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-y border-subtle bg-surface-muted/50 text-left text-xs font-medium uppercase tracking-wide text-tertiary">
                    <th scope="col" className="px-6 py-2.5 font-medium">Title</th>
                    <th scope="col" className="px-3 py-2.5 font-medium">Unit / Chapter</th>
                    <th scope="col" className="px-3 py-2.5 font-medium">Status</th>
                    <th scope="col" className="px-3 py-2.5 text-right font-medium">Chunks</th>
                    <th scope="col" className="px-3 py-2.5 font-medium">Added</th>
                    <th scope="col" className="px-6 py-2.5"><span className="sr-only">Actions</span></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-subtle">
                  {documents.data.map((doc) => (
                    <tr key={doc.id} className="hover:bg-surface-muted/40">
                      <td className="max-w-xs px-6 py-3">
                        <p className="truncate font-medium text-primary">{doc.title}</p>
                        <p className="truncate text-xs text-tertiary">{doc.chapter_name || doc.filename}</p>
                      </td>
                      <td className="px-3 py-3 text-secondary">{doc.unit ?? "—"} / {doc.chapter ?? "—"}</td>
                      <td className="px-3 py-3"><DocumentStatusBadge status={doc.status} /></td>
                      <td className="px-3 py-3 text-right tabular-nums text-secondary">{doc.chunk_count}</td>
                      <td className="whitespace-nowrap px-3 py-3 text-tertiary">{formatRelative(doc.created_at)}</td>
                      <td className="px-6 py-3 text-right">
                        <Button variant="ghost" size="icon" aria-label={`Delete ${doc.title}`} onClick={() => setPendingDelete(doc)}>
                          <Trash2 className="h-4 w-4" aria-hidden />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <ul className="divide-y divide-subtle border-t border-subtle md:hidden">
              {documents.data.map((doc) => (
                <li key={doc.id} className="flex items-start justify-between gap-3 px-5 py-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-primary">{doc.title}</p>
                    <p className="text-xs text-tertiary">
                      Unit {doc.unit ?? "—"} · Ch {doc.chapter ?? "—"} · {doc.chunk_count} chunks
                    </p>
                    <div className="mt-1.5"><DocumentStatusBadge status={doc.status} /></div>
                  </div>
                  <Button variant="ghost" size="icon" aria-label={`Delete ${doc.title}`} onClick={() => setPendingDelete(doc)}>
                    <Trash2 className="h-4 w-4" aria-hidden />
                  </Button>
                </li>
              ))}
            </ul>
          </>
        )}
      </Card>

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete this document?"
        description={pendingDelete ? `“${pendingDelete.title}” and its indexed content will be removed. The tutor will stop citing it.` : undefined}
        confirmLabel="Delete document"
        loading={deleting}
        onConfirm={confirmDelete}
        onCancel={() => setPendingDelete(null)}
      />
    </>
  );
}

function UploadCard({
  activeClass,
  subjects,
  onUploaded,
}: {
  activeClass: ClassRow;
  subjects: Subject[];
  onUploaded: () => void;
}) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [title, setTitle] = useState("");
  const [subjectId, setSubjectId] = useState(activeClass.subject_id ?? "");
  const [unit, setUnit] = useState(1);
  const [chapter, setChapter] = useState(1);
  const [chapterName, setChapterName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [job, setJob] = useState<{ id: string; title: string } | null>(null);

  const effectiveSubject = subjectId || subjects[0]?.id || "";

  const { data: jobStatus, error: jobError } = usePoll<JobStatus>(job?.id ?? null, () => apiFetch<JobStatus>(`/documents/status/${job?.id}`), {
    intervalMs: 3000,
    until: (d) => d.status === "ready" || d.status === "failed",
  });

  const jobDone = jobStatus?.status === "ready" || jobStatus?.status === "failed";
  useEffect(() => {
    if (jobDone) onUploaded();
  }, [jobDone, onUploaded]);

  function pick(selected: File | null) {
    setUploadError(null);
    if (!selected) return;
    const problem = validateFile(selected);
    setFileError(problem);
    setFile(problem ? null : selected);
    if (!problem && !title) setTitle(selected.name.replace(/\.[^/.]+$/, ""));
  }

  function handleDrop(e: DragEvent<HTMLLabelElement>) {
    e.preventDefault();
    setDragActive(false);
    pick(e.dataTransfer.files?.[0] ?? null);
  }

  async function handleUpload(e: FormEvent) {
    e.preventDefault();
    if (!file || submitting) return;
    const problem = validateFile(file);
    if (problem) {
      setFileError(problem);
      return;
    }
    setUploadError(null);
    setSubmitting(true);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("class_id", activeClass.id);
    formData.append("title", title.trim() || file.name);
    if (effectiveSubject) formData.append("subject_id", effectiveSubject);
    formData.append("unit", String(unit));
    formData.append("chapter", String(chapter));
    formData.append("chapter_name", chapterName);

    try {
      const result = await apiFetch<UploadJobResponse>("/documents/upload", { method: "POST", body: formData });
      setJob({ id: result.job_id, title: title.trim() || file.name });
      setFile(null);
      setTitle("");
      setChapterName("");
      setChapter((c) => c + 1);
      if (fileInputRef.current) fileInputRef.current.value = "";
      onUploaded();
    } catch (err) {
      setUploadError(errorMessage(err, "Upload failed."));
    } finally {
      setSubmitting(false);
    }
  }

  const step = !job ? 0 : !jobStatus || jobStatus.status === "processing" ? 1 : jobStatus.status === "ready" ? 2 : -1;

  return (
    <Card>
      <CardHeader icon={<UploadCloud className="h-4 w-4" />} title="Upload a chapter" description={`Adds to ${activeClass.name}. PDF, PPTX, DOCX or TXT, up to ${formatBytes(UPLOAD_MAX_BYTES)}.`} />
      <form onSubmit={handleUpload} className="flex flex-col gap-4">
        <label
          htmlFor="file-input"
          onDragOver={(e) => {
            e.preventDefault();
            setDragActive(true);
          }}
          onDragLeave={() => setDragActive(false)}
          onDrop={handleDrop}
          className={cn(
            "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-4 py-8 text-center transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-focus",
            dragActive ? "border-accent-secondary bg-accent-secondary/8" : fileError ? "border-danger/50" : "border-strong hover:border-accent-secondary/60 hover:bg-surface-muted/50"
          )}
        >
          <input
            ref={fileInputRef}
            id="file-input"
            type="file"
            accept={ACCEPTED.join(",")}
            className="sr-only"
            onChange={(e) => pick(e.target.files?.[0] ?? null)}
          />
          <span className="flex h-10 w-10 items-center justify-center rounded-full bg-surface-muted text-secondary" aria-hidden>
            <FileUp className="h-5 w-5" />
          </span>
          {file ? (
            <span className="text-sm">
              <span className="font-medium text-primary">{file.name}</span>
              <span className="text-tertiary"> · {formatBytes(file.size)}</span>
              <span className="mt-0.5 block text-xs text-accent-secondary">Click to choose a different file</span>
            </span>
          ) : (
            <span className="text-sm text-secondary">
              <span className="font-medium text-accent-secondary">Choose a file</span> or drag it here
            </span>
          )}
        </label>
        {fileError && <Alert tone="danger">{fileError}</Alert>}

        <Input label="Title" value={title} onChange={(e) => setTitle(e.target.value)} required placeholder="e.g. Chapter 3: Process Scheduling" />
        {subjects.length === 0 ? (
          <Alert tone="warning" title="No subjects yet">
            Create one on the{" "}
            <Link href="/subjects" className="font-medium underline">Subjects</Link> page so topics can be tagged.
          </Alert>
        ) : (
          <Select label="Subject" value={effectiveSubject} onChange={(e) => setSubjectId(e.target.value)}>
            {subjects.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </Select>
        )}
        <div className="grid grid-cols-2 gap-3">
          <Input label="Unit" type="number" min={1} value={unit} onChange={(e) => setUnit(Number(e.target.value))} />
          <Input label="Chapter" type="number" min={1} value={chapter} onChange={(e) => setChapter(Number(e.target.value))} />
        </div>
        <Input label="Chapter name" value={chapterName} onChange={(e) => setChapterName(e.target.value)} placeholder="e.g. Process Scheduling" hint="Shown in the syllabus checklist." />

        {uploadError && <Alert tone="danger" title="Upload failed">{uploadError}</Alert>}

        <Button type="submit" disabled={!file} loading={submitting} icon={<UploadCloud className="h-4 w-4" aria-hidden />}>
          {submitting ? "Uploading…" : "Upload and index"}
        </Button>
      </form>

      {job && (
        <div className="mt-5 rounded-lg border border-subtle bg-surface-muted/50 p-4" aria-live="polite">
          <p className="truncate text-sm font-medium text-primary">{job.title}</p>
          <ol className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
            {["Uploaded", "Indexing", "Ready"].map((label, i) => {
              const done = step > i || (step === 2 && i === 2);
              const current = step === i;
              return (
                <li key={label} className="flex items-center gap-2">
                  <span className={cn("inline-flex items-center gap-1 font-medium", done ? "text-success" : current ? "text-info" : "text-tertiary")}>
                    {done ? <CheckCircle2 className="h-3.5 w-3.5" aria-hidden /> : current ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden /> : <span className="h-3.5 w-3.5 rounded-full border border-strong" aria-hidden />}
                    {label}
                  </span>
                  {i < 2 && <span className="h-px w-5 bg-strong" aria-hidden />}
                </li>
              );
            })}
          </ol>
          {jobStatus?.status === "ready" && (
            <p className="mt-2 text-xs text-secondary">{jobStatus.chunk_count ?? 0} passages indexed. Students can ask about this now.</p>
          )}
          {jobStatus?.status === "failed" && (
            <p className="mt-2 flex items-start gap-1.5 text-xs text-danger">
              <XCircle className="mt-px h-3.5 w-3.5 shrink-0" aria-hidden />
              {jobStatus.detail || "Indexing failed. Try re-uploading the file."}
            </p>
          )}
          {jobError && !jobDone && <p className="mt-2 text-xs text-warning">Status check failed: {jobError}. Retrying…</p>}
        </div>
      )}
    </Card>
  );
}
