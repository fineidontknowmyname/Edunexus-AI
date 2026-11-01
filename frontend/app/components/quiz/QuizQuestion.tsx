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
  selected: string | string[] | null;
  onSelect: (option: string | string[]) => void;
  disabled: boolean;
}) {
  const headingId = `q-${question.id}`;
  const isMultiple = question.question_type === "multiple_choice";
  const points = question.points ?? 1.0;
  const selectedList = Array.isArray(selected) ? selected : selected ? [selected] : [];

  function handleToggleOption(opt: string) {
    if (disabled) return;
    if (isMultiple) {
      const next = selectedList.includes(opt)
        ? selectedList.filter((x) => x !== opt)
        : [...selectedList, opt];
      onSelect(next);
    } else {
      onSelect(opt);
    }
  }

  return (
    <fieldset
      className="min-w-0 rounded-[2px] border border-line bg-surface p-6 sm:p-8"
      aria-labelledby={headingId}
    >
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2.5 font-mono text-[9px] uppercase tracking-[0.1em] text-muted border-b border-line pb-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-red font-semibold">
            [ QUESTION {String(index + 1).padStart(2, "0")} / {String(total).padStart(2, "0")} ]
          </span>
          <span>·</span>
          <span>
            {isMultiple
              ? "MULTIPLE CHOICE"
              : question.question_type === "true_false"
              ? "TRUE / FALSE"
              : "SINGLE CHOICE"}
          </span>
          <span>·</span>
          <span>
            {points} {points === 1 ? "POINT" : "POINTS"}
          </span>
        </div>
        {question.topic && (
          <span className="text-muted">
            TOPIC: {question.topic}
          </span>
        )}
      </div>

      <legend className="sr-only">Question {index + 1}</legend>
      <h3 id={headingId} className="font-serif text-2xl sm:text-[26px] text-ink leading-snug mb-5">
        {question.question_text}
      </h3>

      {isMultiple && (
        <p className="mb-4 font-mono text-[9px] uppercase tracking-wider text-muted italic">
          Select all options that apply.
        </p>
      )}

      <div className="flex flex-col gap-2">
        {question.options.map((option, i) => {
          const isSelected = isMultiple ? selectedList.includes(option) : selected === option;
          const letter = LETTERS[i] || String(i + 1);
          return (
            <label
              key={option}
              className={cn(
                "option flex items-center justify-between cursor-pointer select-none",
                isSelected
                  ? "border-ink bg-surface2 text-ink font-medium"
                  : "border-line text-muted hover:border-red hover:text-ink",
                disabled && "cursor-not-allowed opacity-60"
              )}
            >
              <div className="flex items-center gap-3">
                <span className="text-red font-mono text-[10px] shrink-0">{letter} /</span>
                <span className="font-mono text-xs">{option}</span>
              </div>
              <input
                type={isMultiple ? "checkbox" : "radio"}
                name={question.id}
                checked={isSelected}
                onChange={() => handleToggleOption(option)}
                disabled={disabled}
                className="sr-only"
              />
              <span className="font-mono text-[10px] text-muted">
                {isSelected ? "●" : "○"}
              </span>
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
