import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";

const COMPONENTS: Components = {
  p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  em: ({ children }) => <em className="italic">{children}</em>,
  h1: ({ children }) => <h3 className="text-base font-semibold mt-3 mb-1 first:mt-0">{children}</h3>,
  h2: ({ children }) => <h3 className="text-base font-semibold mt-3 mb-1 first:mt-0">{children}</h3>,
  h3: ({ children }) => <h4 className="text-sm font-semibold mt-2 mb-1 first:mt-0">{children}</h4>,
  ul: ({ children }) => <ul className="list-disc list-outside pl-5 mb-2 flex flex-col gap-0.5">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal list-outside pl-5 mb-2 flex flex-col gap-0.5">{children}</ol>,
  li: ({ children }) => <li>{children}</li>,
  hr: () => <hr className="my-3 border-subtle" />,
  blockquote: ({ children }) => (
    <blockquote className="border-l-2 border-accent-secondary pl-3 my-2 text-secondary">{children}</blockquote>
  ),
  code: ({ children }) => (
    <code className="bg-surface-muted rounded px-1 py-0.5 text-[0.85em] font-mono">{children}</code>
  ),
  pre: ({ children }) => (
    <pre className="bg-surface-muted rounded-md p-3 my-2 overflow-x-auto text-[0.85em] font-mono">{children}</pre>
  ),
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noreferrer" className="text-accent-secondary hover:underline">
      {children}
    </a>
  ),
  table: ({ children }) => (
    <div className="overflow-x-auto my-2">
      <table className="border-collapse text-xs w-full">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="border-b border-strong">{children}</thead>,
  th: ({ children }) => <th className="text-left font-semibold px-2 py-1">{children}</th>,
  td: ({ children }) => <td className="px-2 py-1 border-t border-subtle">{children}</td>,
};

export function MarkdownMessage({ content }: { content: string }) {
  return (
    <div className="text-sm leading-relaxed [&>*:last-child]:mb-0">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={COMPONENTS}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
