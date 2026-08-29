import type { QuizQuestionStudent } from "../../lib/types";

export function QuizQuestion({
  question,
  index,
  selected,
  onSelect,
  disabled,
}: {
  question: QuizQuestionStudent;
  index: number;
  selected: string | null;
  onSelect: (option: string) => void;
  disabled: boolean;
}) {
  return (
    <div className="border border-subtle rounded-lg p-4">
      <p className="text-sm font-medium text-primary mb-3">
        {index + 1}. {question.question_text}
      </p>
      <div className="flex flex-col gap-2">
        {question.options.map((option) => (
          <label
            key={option}
            className={`flex items-center gap-2 px-3 py-2 rounded-md border text-sm cursor-pointer ${
              selected === option ? "border-accent-secondary bg-accent-secondary/10" : "border-subtle hover:bg-app"
            } ${disabled ? "cursor-not-allowed opacity-70" : ""}`}
          >
            <input
              type="radio"
              name={question.id}
              checked={selected === option}
              onChange={() => onSelect(option)}
              disabled={disabled}
            />
            {option}
          </label>
        ))}
      </div>
    </div>
  );
}
