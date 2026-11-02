import type { RecommendationResponse } from "./types";

export type RecommendationMode = RecommendationResponse["mode"];

interface RecommendationPresentation {
  label: string;
  title: string;
  description: string;
  primaryCta: string;
  secondaryCta: string;
}

const presentations: Record<RecommendationMode, RecommendationPresentation> = {
  ai_session: {
    label: "Guided support",
    title: "Work through it together",
    description: "A guided walkthrough can help you address the topic step by step.",
    primaryCta: "Take a Test",
    secondaryCta: "Start guided session",
  },
  diagnostic: {
    label: "Diagnostic",
    title: "Diagnostic check recommended",
    description: "A short assessment can calibrate what to focus on next.",
    primaryCta: "Take a Test",
    secondaryCta: "Ask Tutor",
  },
  verification: {
    label: "Verification",
    title: "Verification check",
    description: "A few more questions can verify consistent understanding.",
    primaryCta: "Take a Test",
    secondaryCta: "Ask Tutor",
  },
  reinforce: {
    label: "Practice",
    title: "Targeted practice recommended",
    description: "A short practice assessment can help strengthen this topic.",
    primaryCta: "Take a Test",
    secondaryCta: "Learn Concept",
  },
  advance: {
    label: "Advance",
    title: "High estimated understanding",
    description: "Explore advanced resources or challenge your understanding.",
    primaryCta: "Take a Test",
    secondaryCta: "Explore resources",
  },
  initial_assessment: {
    label: "Baseline",
    title: "Establish your baseline",
    description: "An initial assessment can establish your current understanding.",
    primaryCta: "Take a Test",
    secondaryCta: "Learn Concept",
  },
  static: {
    label: "Learning support",
    title: "Recommended next steps",
    description: "Review the available class resources or check your understanding.",
    primaryCta: "Take a Test",
    secondaryCta: "Learn Concept",
  },
};

export function getRecommendationPresentation(
  mode: RecommendationMode,
  reason?: string | null,
): RecommendationPresentation {
  const presentation = presentations[mode];
  return {
    ...presentation,
    description: reason?.trim() || presentation.description,
  };
}

export function getProgressRecommendationMode(
  attempts: number,
  evidenceState?: string | null,
  masteryBand?: string | null,
): RecommendationMode {
  if (attempts <= 0 || evidenceState === "none" || evidenceState === "insufficient") {
    return "initial_assessment";
  }
  if (masteryBand === "low") return "ai_session";
  if (masteryBand === "high") return "advance";
  if (masteryBand === "medium") return "reinforce";
  return "static";
}
