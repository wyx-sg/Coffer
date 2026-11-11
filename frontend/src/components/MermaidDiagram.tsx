// frontend/src/components/MermaidDiagram.tsx
// A ```mermaid fenced block drawn as its diagram — every Markdown preview
// (Markdown.tsx) hands such a block here. Every diagram type Mermaid itself
// draws is supported; Coffer adds no list of its own.
//
// Mermaid is large, so it is loaded the first time a page actually holds a
// diagram, never in the main bundle. Until it has drawn, and for good when it
// cannot (a syntax error, a type this Mermaid version does not know), the
// block reads as the code block it is written as; a failure adds one quiet
// line saying so. The library runs with `securityLevel: "strict"`: labels are
// sanitised, click handlers and HTML labels are off, so a document's diagram
// never runs code (ADR docs/decisions/markdown-diagrams-render-with-mermaid.md).
// The palette follows the app's light / dark theme (Mermaid's greyscale
// "neutral" and "dark" themes, closest to the app's own surfaces).
import { useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";

import { useResolvedTheme, type ResolvedTheme } from "@/lib/theme";

type Drawn = { status: "drawing" } | { status: "drawn"; svg: string } | { status: "failed" };

// Mermaid's configuration is global, so one diagram is drawn at a time: each
// sets the theme it needs, then renders, without another diagram's
// `initialize` landing in between.
let queue: Promise<unknown> = Promise.resolve();

function draw(id: string, source: string, theme: ResolvedTheme): Promise<string> {
  const job = queue.then(async () => {
    const { default: mermaid } = await import("mermaid");
    mermaid.initialize({
      startOnLoad: false,
      securityLevel: "strict",
      theme: theme === "dark" ? "dark" : "neutral",
      fontFamily: getComputedStyle(document.body).fontFamily,
    });
    try {
      // `parse` throws on a bad diagram, so Mermaid never draws its own
      // error picture into the page.
      await mermaid.parse(source);
      const { svg } = await mermaid.render(id, source);
      return svg;
    } finally {
      // A failed render can leave its scratch element behind in <body>.
      document.getElementById(`d${id}`)?.remove();
      document.getElementById(id)?.remove();
    }
  });
  queue = job.catch(() => undefined);
  return job;
}

export function MermaidDiagram({ source }: { source: string }) {
  const { t } = useTranslation();
  const theme = useResolvedTheme();
  // Mermaid uses the id as an element id and CSS selector: keep it plain.
  const id = `mermaid-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  const [drawn, setDrawn] = useState<Drawn>({ status: "drawing" });

  useEffect(() => {
    let live = true;
    draw(id, source, theme).then(
      (svg) => live && setDrawn({ status: "drawn", svg }),
      () => live && setDrawn({ status: "failed" }),
    );
    return () => {
      live = false;
    };
  }, [id, source, theme]);

  if (drawn.status === "drawn") {
    return (
      <div
        data-testid="mermaid-diagram"
        role="img"
        aria-label={t("preview.diagram.label")}
        className="my-3 overflow-x-auto [&>svg]:mx-auto [&>svg]:h-auto [&>svg]:max-w-full"
        // Mermaid's own output under securityLevel "strict" (sanitised by it).
        dangerouslySetInnerHTML={{ __html: drawn.svg }}
      />
    );
  }
  return (
    <div data-testid="mermaid-source" className="my-3">
      {drawn.status === "failed" ? (
        <p data-testid="mermaid-failed" className="mb-1.5 text-xs text-text-muted">
          {t("preview.diagram.failed")}
        </p>
      ) : null}
      <pre className="overflow-auto rounded-lg border border-border-subtle bg-code px-3.5 py-3">
        <code className="font-mono text-xs leading-[1.6]">{source}</code>
      </pre>
    </div>
  );
}
