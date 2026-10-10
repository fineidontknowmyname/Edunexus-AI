import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";

const COMPONENTS: Components = {
  p: ({ children }) => <p className="mb-3 last:mb-0">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold text-primary">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  h1: ({ children }) => <h3 className="mb-2 mt-4 text-[0.9375rem] font-semibold text-primary first:mt-0">{children}</h3>,
  h2: ({ children }) => <h3 className="mb-2 mt-4 text-[0.9375rem] font-semibold text-primary first:mt-0">{children}</h3>,
  h3: ({ children }) => <h4 className="mb-1.5 mt-3 text-sm font-semibold text-primary first:mt-0">{children}</h4>,
  h4: ({ children }) => <h5 className="mb-1 mt-3 text-sm font-semibold text-primary first:mt-0">{children}</h5>,
  ul: ({ children }) => <ul className="mb-3 flex list-outside list-disc flex-col gap-1 pl-5 marker:text-tertiary last:mb-0">{children}</ul>,
  ol: ({ children }) => <ol className="mb-3 flex list-outside list-decimal flex-col gap-1 pl-5 marker:text-tertiary last:mb-0">{children}</ol>,
  li: ({ children }) => <li className="pl-0.5 [&>p]:mb-1">{children}</li>,
  hr: () => <hr className="my-4 border-subtle" />,
  blockquote: ({ children }) => (
    <blockquote className="my-3 border-l-2 border-accent-secondary bg-accent-secondary/5 py-1 pl-3 pr-2 text-secondary">{children}</blockquote>
  ),
  code: ({ children, className }) => (
    <code
      className={
        className
          ? `${className} font-mono`
          : "rounded bg-surface-muted px-1.5 py-0.5 font-mono text-[0.85em] text-primary [pre_&]:bg-transparent [pre_&]:p-0"
      }
    >
      {children}
    </code>
  ),
  pre: ({ children }) => (
    <pre className="my-3 overflow-x-auto rounded-lg border border-subtle bg-surface-muted p-3 font-mono text-[0.8125rem] leading-relaxed text-primary [&_code]:bg-transparent [&_code]:p-0">
      {children}
    </pre>
  ),
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noreferrer noopener" className="font-medium text-accent-secondary underline decoration-accent-secondary/40 underline-offset-2 hover:decoration-accent-secondary">
      {children}
    </a>
  ),
  table: ({ children }) => (
    <div className="my-3 overflow-x-auto rounded-lg border border-subtle">
      <table className="w-full border-collapse text-[0.8125rem]">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-surface-muted">{children}</thead>,
  th: ({ children }) => <th className="whitespace-nowrap px-3 py-2 text-left font-semibold text-primary">{children}</th>,
  td: ({ children }) => <td className="border-t border-subtle px-3 py-2 align-top">{children}</td>,
};

export function MarkdownMessage({ content }: { content: string }) {
  return (
    <div className="min-w-0 break-words text-sm leading-relaxed text-primary [&>*:last-child]:mb-0">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={COMPONENTS}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
