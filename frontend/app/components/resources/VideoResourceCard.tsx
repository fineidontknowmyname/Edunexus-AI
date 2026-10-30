"use client";

import { useState } from "react";
import Image from "next/image";
import { Clock, PlayCircle, ThumbsUp } from "lucide-react";
import { Badge, type BadgeTone } from "../ui/Badge";
import type { RecommendationVideo } from "../../lib/types";
import { apiFetch } from "../../lib/api";

interface VideoResourceCardProps {
  video: RecommendationVideo;
  onPlay: (video: RecommendationVideo) => void;
  resourceId?: string;
  initialHelpfulCount?: number;
  hasVotedInitially?: boolean;
}

export function VideoResourceCard({
  video,
  onPlay,
  resourceId,
  initialHelpfulCount,
  hasVotedInitially = false,
}: VideoResourceCardProps) {
  const [helpfulCount, setHelpfulCount] = useState(
    initialHelpfulCount ?? video.helpful_count ?? 0
  );
  const [hasVoted, setHasVoted] = useState(hasVotedInitially);
  const [voting, setVoting] = useState(false);

  const provenanceTone: BadgeTone =
    video.source === "faculty"
      ? "green"
      : video.source === "student_suggested"
      ? "blue"
      : "gray";

  const provenanceLabel =
    video.source === "faculty"
      ? "Faculty Curated"
      : video.source === "student_suggested"
      ? "Student Suggested"
      : "Auto Discovered";

  const thumbUrl =
    video.thumbnail || `https://i.ytimg.com/vi/${video.video_id}/hqdefault.jpg`;

  async function handleVote(e: React.MouseEvent) {
    e.stopPropagation();
    if (!resourceId || hasVoted || voting) return;
    setVoting(true);
    try {
      const res = await apiFetch<{ helpful_count: number }>(
        `/resources/${resourceId}/vote`,
        { method: "POST" }
      );
      setHelpfulCount(res.helpful_count);
      setHasVoted(true);
    } catch {
      // Ignored
    } finally {
      setVoting(false);
    }
  }

  return (
    <div
      onClick={() => onPlay(video)}
      className="group flex flex-col sm:flex-row items-start gap-3 rounded-xl border border-subtle bg-surface p-3 shadow-card transition-all hover:border-accent-secondary/50 hover:shadow-card-hover cursor-pointer"
    >
      <div className="relative aspect-video w-full sm:w-40 shrink-0 overflow-hidden rounded-lg bg-surface-muted">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={thumbUrl}
          alt={video.title}
          className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
          loading="lazy"
        />
        <div className="absolute inset-0 flex items-center justify-center bg-black/25 transition-opacity group-hover:bg-black/10">
          <PlayCircle className="h-9 w-9 text-white drop-shadow-md transition-transform group-hover:scale-110" />
        </div>
        {video.duration && video.duration !== "Video" && (
          <span className="absolute bottom-1 right-1 rounded bg-black/80 px-1 py-0.5 text-[10px] font-medium text-white">
            {video.duration}
          </span>
        )}
      </div>

      <div className="flex min-w-0 flex-1 flex-col justify-between self-stretch py-0.5">
        <div>
          <div className="flex flex-wrap items-center gap-1.5 mb-1">
            <Badge tone={provenanceTone} dot>
              {provenanceLabel}
            </Badge>
            <span className="text-xs text-tertiary">· {video.channel}</span>
          </div>
          <h4 className="text-sm font-semibold text-primary line-clamp-2 group-hover:text-accent-secondary">
            {video.title}
          </h4>
        </div>

        <div className="mt-2.5 flex items-center justify-between text-xs text-tertiary">
          <span className="inline-flex items-center gap-1 font-medium text-accent-secondary group-hover:underline">
            Watch in player
          </span>

          {resourceId && (
            <button
              type="button"
              onClick={handleVote}
              disabled={hasVoted || voting}
              className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 transition-colors ${
                hasVoted
                  ? "bg-accent-secondary/15 text-accent-secondary font-medium"
                  : "hover:bg-surface-muted text-tertiary"
              }`}
              title="Helpful resource"
            >
              <ThumbsUp className="h-3 w-3" />
              <span>{helpfulCount}</span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
