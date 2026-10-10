import type { QuizQuestionStudent } from "../../lib/types";
import { cn } from "../../lib/cn";

const LETTERS = "ABCDEFGH";

export function QuizQuestion({
  question,
  index,
  total,
  selected,
  onSelect,
  disabled,
}: {
  question: QuizQuestionStudent;
  index: number;
  total: number;
  selected: string | null;
  onSelect: (option: string) => void;
  disabled: boolean;
}) {
  const headingId = `q-${question.id}`;
  return (
    <fieldset className="min-w-0 rounded-xl border border-subtle bg-surface p-5 shadow-card sm:p-6" aria-labelledby={headingId}>
      <div className="mb-1 flex items-center justify-between gap-2 text-xs text-tertiary">
        <span className="font-medium">
          Question {index + 1} of {total}
        </span>
        {question.topic && <span className="truncate">{question.topic}</span>}
      </div>
      <legend className="sr-only">Question {index + 1}</legend>
      <p id={headingId} className="mb-4 text-[0.9375rem] font-medium leading-relaxed text-primary">
        {question.question_text}
      </p>
      <div className="flex flex-col gap-2">
        {question.options.map((option, i) => {
          const isSelected = selected === option;
          return (
            <label
              key={option}
              className={cn(
                "flex items-start gap-3 rounded-lg border px-3.5 py-3 text-sm transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-focus",
                isSelected ? "border-accent-secondary bg-accent-secondary/8 text-primary" : "border-subtle text-secondary hover:border-strong hover:bg-surface-muted/60",
                disabled ? "cursor-not-allowed opacity-70" : "cursor-pointer"
              )}
            >
              <input
                type="radio"
                name={question.id}
                checked={isSelected}
                onChange={() => onSelect(option)}
                disabled={disabled}
                className="sr-only"
              />
              <span
                className={cn(
                  "flex h-6 w-6 shrink-0 items-center justify-center rounded-md border text-xs font-semibold",
                  isSelected ? "border-accent-secondary bg-accent-secondary text-on-accent" : "border-strong text-tertiary"
                )}
                aria-hidden
              >
                {LETTERS[i] ?? i + 1}
              </span>
              <span className="pt-0.5">{option}</span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
