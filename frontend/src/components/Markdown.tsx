// frontend/src/components/Markdown.tsx
// The one Markdown renderer (GitHub-flavored): stored .md files shown rendered
// (`density="doc"`, the default) and chat message text (`density="chat"`, with
// `breaks`, `highlight` and `copyableCode` switched on by the caller). The
// project has no @tailwindcss/typography plugin, so element styles are applied
// via per-tag component overrides to stay consistent with the app's tokens.
//
// Headings are demoted one level (markdown `#` renders as <h2>): the renderer
// always sits under a page that already owns the <h1>, so a document's own
// title must never become a second one. `#`→h2 … `#####`/`######`→h6.
import ReactMarkdown, { type Components } from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";

import { CodeBlock } from "@/components/CodeBlock";
import { cn } from "@/lib/utils";

const docComponents: Components = {
  h1: (props) => <h2 className="mb-3 mt-5 text-xl font-bold first:mt-0" {...props} />,
  h2: (props) => <h3 className="mb-2 mt-6 text-md font-bold first:mt-0" {...props} />,
  h3: (props) => <h4 className="mb-1.5 mt-4 text-sm font-semibold first:mt-0" {...props} />,
  h4: (props) => <h5 className="mb-1.5 mt-3 font-semibold first:mt-0" {...props} />,
  h5: (props) => <h6 className="mb-1.5 mt-3 font-medium first:mt-0" {...props} />,
  h6: (props) => <h6 className="mb-1.5 mt-3 font-medium first:mt-0" {...props} />,
  p: (props) => <p className="my-2.5 leading-relaxed" {...props} />,
  ul: (props) => <ul className="my-2.5 list-disc space-y-1 pl-6" {...props} />,
  ol: (props) => <ol className="my-2.5 list-decimal space-y-1 pl-6" {...props} />,
  li: (props) => <li className="leading-relaxed" {...props} />,
  a: (props) => (
    <a
      className="text-accent-text underline underline-offset-2"
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
      <code className="rounded-xs bg-chip px-1.5 py-0.5 font-mono text-xs" {...props}>
        {children}
      </code>
    ) : (
      <code className={`${className ?? ""} font-mono text-xs leading-[1.6]`} {...props}>
        {children}
      </code>
    );
  },
  pre: (props) => (
    <pre
      className="my-3 overflow-auto rounded-lg border border-border-subtle bg-code px-3.5 py-3"
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
      className="border border-border bg-surface-sunken px-3 py-1.5 text-left font-label"
      {...props}
    />
  ),
  td: (props) => <td className="border border-border px-3 py-1.5 align-top" {...props} />,
  img: (props) => <img className="my-3 max-w-full rounded-md" {...props} />,
};

const chatComponents: Components = {
  p: ({ children }) => <p className="my-2 leading-relaxed first:mt-0 last:mb-0">{children}</p>,
  ul: ({ children }) => (
    <ul className="my-2 list-disc space-y-1 pl-5 marker:text-muted-foreground">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="my-2 list-decimal space-y-1 pl-5 marker:text-muted-foreground">{children}</ol>
  ),
  li: ({ children }) => <li className="leading-relaxed [&>ol]:my-1 [&>ul]:my-1">{children}</li>,
  h1: ({ children }) => (
    <h1 className="mb-2 mt-4 text-base font-semibold first:mt-0">{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 className="mb-2 mt-4 text-base font-semibold first:mt-0">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="mb-1.5 mt-3 text-sm font-semibold first:mt-0">{children}</h3>
  ),
  a: ({ children, href }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="font-medium text-primary underline underline-offset-2 hover:opacity-80"
    >
      {children}
    </a>
  ),
  blockquote: ({ children }) => (
    <blockquote className="my-2 border-l-2 border-primary/30 pl-3 text-muted-foreground">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-3 border-border" />,
  table: ({ children }) => (
    <div className="my-2 overflow-x-auto rounded-md border border-border">
      <table className="w-full border-collapse text-xs">{children}</table>
    </div>
  ),
  th: ({ children }) => (
    <th className="border-b border-border bg-muted px-2.5 py-1.5 text-left font-medium">
      {children}
    </th>
  ),
  td: ({ children }) => <td className="border-b border-border px-2.5 py-1.5">{children}</td>,
  code: ({ className, children }) => {
    // Fenced blocks carry a language-* class (and rehype-highlight adds hljs);
    // inline code has neither, so render it as a small pill instead.
    const isBlock = /\blanguage-|\bhljs\b/.test(className ?? "");
    if (isBlock) {
      return <code className={cn("hljs", className)}>{children}</code>;
    }
    return (
      <code className="rounded-sm bg-muted px-1.5 py-0.5 font-mono text-xs text-foreground/80">
        {children}
      </code>
    );
  },
};

interface Props {
  children: string;
  /**
   * Where an image's `src` should really point. Used where the bytes are not
   * publicly addressable — a run's own directory is behind the daemon's token,
   * so the page fetches each image and hands this map of object URLs
   * in.
   *
   * Returning undefined means DO NOT RENDER IT, and the name is shown instead.
   * Falling back to the written `src` would point an `<img>` at a path this
   * app does not serve: the SPA answers with its own index.html, so the
   * browser fetches a document, fails to decode it as an image, and shows a
   * broken one — for every image, on every first paint.
   */
  resolveImage?: (src: string) => string | undefined;
  /** `doc`: a stored document (headings demoted under the page's h1).
   *  `chat`: message text — tighter spacing, headings kept as written. */
  density?: "doc" | "chat";
  /** Syntax-highlight fenced code (rehype-highlight; the theme is imported in
   *  main.tsx, `.markdown-body` in index.css neutralises its background). */
  highlight?: boolean;
  /** Keep single newlines as line breaks (remark-breaks), so agent output laid
   *  out one fact per line stays line by line. */
  breaks?: boolean;
  /** Give fenced blocks a Copy button. */
  copyableCode?: boolean;
  /** Per-element overrides applied last, for a caller needing a custom
   *  element (e.g. a link that routes inside the app). */
  components?: Components;
}

export function Markdown({
  children,
  resolveImage,
  density = "doc",
  highlight = false,
  breaks = false,
  copyableCode = false,
  components,
}: Props) {
  const base = density === "chat" ? chatComponents : docComponents;
  const overrides: Components = {
    ...base,
    ...(copyableCode ? { pre: ({ children: c }) => <CodeBlock>{c}</CodeBlock> } : {}),
    ...(resolveImage === undefined
      ? {}
      : {
          img: ({ src, alt, ...props }) => {
            const resolved = typeof src === "string" ? resolveImage(src) : undefined;
            if (resolved === undefined) {
              return (
                <span className="my-3 block text-sm text-muted-foreground">
                  {alt || (typeof src === "string" ? src : "")}
                </span>
              );
            }
            return (
              <img className="my-3 max-w-full rounded-md" src={resolved} alt={alt} {...props} />
            );
          },
        }),
    ...components,
  };
  return (
    <div className={cn("text-sm text-foreground", density === "chat" && "markdown-body")}>
      <ReactMarkdown
        remarkPlugins={breaks ? [remarkGfm, remarkBreaks] : [remarkGfm]}
        rehypePlugins={highlight ? [rehypeHighlight] : []}
        components={overrides}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
