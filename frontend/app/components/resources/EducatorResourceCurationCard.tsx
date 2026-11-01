"use client";

import { useEffect, useState } from "react";
import { PlusCircle, Video, FileText, ExternalLink } from "lucide-react";
import { Card, CardHeader } from "../ui/Card";
import { Input, Select } from "../ui/Input";
import { Button, ButtonLink } from "../ui/Button";
import { Alert, SkeletonText } from "../ui/Feedback";
import { apiFetch, errorMessage } from "../../lib/api";
import type { ClassCurationTopicsResponse } from "../../lib/types";

interface EducatorResourceCurationCardProps {
  classId: string;
  onResourceCreated?: () => void;
}

export function EducatorResourceCurationCard({
  classId,
  onResourceCreated,
}: EducatorResourceCurationCardProps) {
  const [loading, setLoading] = useState(true);
  const [curationData, setCurationData] = useState<ClassCurationTopicsResponse | null>(null);
  const [selectedTopicId, setSelectedTopicId] = useState<string>("");
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(() => {
      setLoading(true);
      setError(null);
      setSuccess(null);
    }, 0);

    apiFetch<ClassCurationTopicsResponse>(`/classes/${classId}/curation-topics`)
      .then((data) => {
        if (cancelled) return;
        setCurationData(data);
        if (data.topics && data.topics.length > 0) {
          setSelectedTopicId(data.topics[0].id);
        } else {
          setSelectedTopicId("");
        }
      })
      .catch((err) => {
        if (cancelled) return;
        setError(errorMessage(err, "Failed to load syllabus topics for this class."));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [classId]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!url.trim()) {
      setError("Please provide a YouTube video URL.");
      return;
    }

    const currentTopics = curationData?.topics ?? [];
    const activeTopic = currentTopics.find((t) => t.id === selectedTopicId) || currentTopics[0];

    if (!activeTopic) {
      setError("No valid syllabus topic selected.");
      return;
    }

    setSubmitting(true);
    setError(null);
    setSuccess(null);

    try {
      const res = await apiFetch<{ title: string; topic: string }>("/resources", {
        method: "POST",
        body: {
          class_id: classId,
          topic: activeTopic.topic,
          topic_id: activeTopic.id,
          url: url.trim(),
          title: title.trim(),
          resource_type: "youtube",
        },
      });

      setSuccess(`Curated video added: "${res.title}" for topic "${res.topic}" is now approved for students!`);
      setUrl("");
      setTitle("");
      onResourceCreated?.();
    } catch (err) {
      setError(errorMessage(err, "Failed to add curated video resource."));
    } finally {
      setSubmitting(false);
    }
  }

  const selectedTopicObj = curationData?.topics.find((t) => t.id === selectedTopicId);

  return (
    <Card>
      <CardHeader
        icon={<Video className="h-5 w-5 text-danger" />}
        title="Curate YouTube Video"
        description="Add faculty-approved educational videos dynamically mapped to your approved syllabus topics."
      />

      {loading ? (
        <div className="mt-4 flex flex-col gap-3">
          <SkeletonText lines={3} />
        </div>
      ) : curationData?.status === "no_syllabus" ? (
        <div className="mt-4 flex flex-col gap-4">
          <Alert tone="warning" title="Syllabus Required">
            {curationData.message ||
              `No approved syllabus found for "${curationData.subject_name || "this class"}". Faculty curation requires an approved syllabus so resources map to validated curriculum topics.`}
          </Alert>
          <div className="flex items-center justify-between rounded-[2px] border border-dashed border-line p-4 bg-surface2">
            <div className="flex items-center gap-3">
              <FileText className="h-5 w-5 text-accent-red shrink-0" />
              <div>
                <p className="font-serif text-[15px] text-ink">Syllabus Management</p>
                <p className="text-xs text-muted">
                  Upload syllabus PDF/DOCX, extract topics, review, and approve the curriculum.
                </p>
              </div>
            </div>
            <ButtonLink href="/subjects" variant="primary" size="sm" icon={<ExternalLink className="h-3.5 w-3.5" />}>
              Manage Syllabus
            </ButtonLink>
          </div>
        </div>
      ) : curationData?.status === "no_subject" ? (
        <div className="mt-4">
          <Alert tone="danger" title="No Subject Linked">
            {curationData.message || "This class is not associated with an academic subject."}
          </Alert>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="mt-4 flex flex-col gap-4">
          {error && <Alert tone="danger">{error}</Alert>}
          {success && (
            <Alert tone="success" title="Resource Added">
              {success}
            </Alert>
          )}

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <Select
                label={`Approved Syllabus Topic (${curationData?.subject_name || "Curriculum"})`}
                value={selectedTopicId}
                onChange={(e) => setSelectedTopicId(e.target.value)}
                required
              >
                {curationData?.topics.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.topic}
                  </option>
                ))}
              </Select>
              {selectedTopicObj?.description && (
                <p className="mt-1 text-xs text-secondary line-clamp-1">
                  {selectedTopicObj.description}
                </p>
              )}
            </div>

            <Input
              label="YouTube URL"
              type="url"
              placeholder="https://www.youtube.com/watch?v=..."
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              required
            />
          </div>

          <Input
            label="Custom Title (Optional)"
            placeholder="Leave blank to automatically retrieve YouTube video title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />

          <div className="flex items-center justify-between pt-1">
            <span className="text-xs text-tertiary">
              Source: Approved syllabus ({curationData?.topics.length ?? 0} topics available)
            </span>
            <Button
              type="submit"
              variant="primary"
              disabled={submitting || !url.trim() || !selectedTopicId}
              icon={<PlusCircle className="h-4 w-4" />}
            >
              {submitting ? "Validating & Adding…" : "Add to Approved Resources"}
            </Button>
          </div>
        </form>
      )}
    </Card>
  );
}
