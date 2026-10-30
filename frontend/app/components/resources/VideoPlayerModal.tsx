"use client";

import { ExternalLink } from "lucide-react";
import { Modal } from "../ui/Modal";
import { Badge, type BadgeTone } from "../ui/Badge";
import type { RecommendationVideo } from "../../lib/types";

interface VideoPlayerModalProps {
  video: RecommendationVideo | null;
  onClose: () => void;
}

export function VideoPlayerModal({ video, onClose }: VideoPlayerModalProps) {
  if (!video) return null;

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

  const embedUrl = `https://www.youtube-nocookie.com/embed/${video.video_id}?autoplay=1&rel=0`;

  return (
    <Modal
      open={Boolean(video)}
      onClose={onClose}
      title={video.title}
      description={`${video.channel}${video.duration ? ` · ${video.duration}` : ""}`}
    >
      <div className="flex flex-col gap-4">
        <div className="flex items-center gap-2">
          <Badge tone={provenanceTone} dot>
            {provenanceLabel}
          </Badge>
          <a
            href={video.url}
            target="_blank"
            rel="noreferrer noopener"
            className="ml-auto inline-flex items-center gap-1 text-xs font-medium text-accent-secondary hover:underline"
          >
            <span>Watch on YouTube</span>
            <ExternalLink className="h-3 w-3" aria-hidden />
          </a>
        </div>

        <div className="relative aspect-video w-full overflow-hidden rounded-xl bg-black shadow-inner">
          <iframe
            src={embedUrl}
            title={video.title}
            className="h-full w-full border-0"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
            allowFullScreen
          />
        </div>
      </div>
    </Modal>
  );
}
