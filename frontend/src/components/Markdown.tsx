// frontend/src/components/Markdown.tsx
// Shared read-only Markdown renderer (GitHub-flavored). Used wherever a stored
// .md file is shown rendered rather than raw (KB document preview, etc.). The
// project has no @tailwindcss/typography plugin, so element styles are applied
// via per-tag component overrides to stay consistent with the app's tokens.
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";

const components: Components = {
  h1: (props) => (
    <h1 className="mb-3 mt-5 font-serif text-2xl tracking-tight first:mt-0" {...props} />
  ),
  h2: (props) => (
    <h2 className="mb-2 mt-5 font-serif text-xl tracking-tight first:mt-0" {...props} />
  ),
  h3: (props) => <h3 className="mb-2 mt-4 text-lg font-medium first:mt-0" {...props} />,
  h4: (props) => <h4 className="mb-1.5 mt-3 font-medium first:mt-0" {...props} />,
  p: (props) => <p className="my-2.5 leading-relaxed" {...props} />,
  ul: (props) => <ul className="my-2.5 list-disc space-y-1 pl-6" {...props} />,
  ol: (props) => <ol className="my-2.5 list-decimal space-y-1 pl-6" {...props} />,
  li: (props) => <li className="leading-relaxed" {...props} />,
  a: (props) => (
    <a
      className="text-primary underline underline-offset-2"
      target="_blank"
      rel="noreferrer"
      {...props}
    />
  ),
  blockquote: (props) => (
    <blockquote className="my-3 border-l-2 border-border pl-4 text-muted-foreground" {...props} />
  ),
  hr: (props) => <hr className="my-5 border-border" {...props} />,
  code: ({ className, children, ...props }) => {
    const inline = !String(className ?? "").includes("language-");
    return inline ? (
      <code className="rounded bg-secondary px-1.5 py-0.5 font-mono text-[0.85em]" {...props}>
        {children}
      </code>
    ) : (
      <code className={`${className ?? ""} font-mono text-sm`} {...props}>
        {children}
      </code>
    );
  },
  pre: (props) => (
    <pre
      className="my-3 overflow-auto rounded-md border border-border bg-secondary/40 p-3"
      {...props}
    />
  ),
  table: (props) => (
    <div className="my-3 overflow-x-auto">
      <table className="w-full border-collapse text-sm" {...props} />
    </div>
  ),
  th: (props) => (
    <th
      className="border border-border bg-secondary/50 px-3 py-1.5 text-left font-medium"
      {...props}
    />
  ),
  td: (props) => <td className="border border-border px-3 py-1.5 align-top" {...props} />,
  img: (props) => <img className="my-3 max-w-full rounded" {...props} />,
};

export function Markdown({ children }: { children: string }) {
  return (
    <div className="text-sm text-foreground">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
