// frontend/src/components/Markdown.tsx
// Shared read-only Markdown renderer (GitHub-flavored). Used wherever a stored
// .md file is shown rendered rather than raw (KB document preview, etc.). The
// project has no @tailwindcss/typography plugin, so element styles are applied
// via per-tag component overrides to stay consistent with the app's tokens.
//
// Headings are demoted one level (markdown `#` renders as <h2>): the renderer
// always sits under a page that already owns the <h1>, so a document's own
// title must never become a second one. `#`→h2 … `#####`/`######`→h6.
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";

const components: Components = {
  h1: (props) => (
    <h2 className="mb-3 mt-5 font-serif text-2xl tracking-tight first:mt-0" {...props} />
  ),
  h2: (props) => (
    <h3 className="mb-2 mt-5 font-serif text-xl tracking-tight first:mt-0" {...props} />
  ),
  h3: (props) => <h4 className="mb-2 mt-4 text-lg font-medium first:mt-0" {...props} />,
  h4: (props) => <h5 className="mb-1.5 mt-3 font-medium first:mt-0" {...props} />,
  h5: (props) => <h6 className="mb-1.5 mt-3 font-medium first:mt-0" {...props} />,
  h6: (props) => <h6 className="mb-1.5 mt-3 font-medium first:mt-0" {...props} />,
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
      <code className="rounded-sm bg-secondary px-1.5 py-0.5 font-mono text-sm" {...props}>
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
  img: (props) => <img className="my-3 max-w-full rounded-md" {...props} />,
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
}

export function Markdown({ children, resolveImage }: Props) {
  const overrides: Components =
    resolveImage === undefined
      ? components
      : {
          ...components,
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
        };
  return (
    <div className="text-sm text-foreground">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={overrides}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
