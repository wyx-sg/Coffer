// src/components/preview/CodeView.tsx
// Read-only, syntax-highlighted preview for any text/code/JSON/log file, built on
// CodeMirror 6. This is the single primitive every raw (non-Markdown) preview in
// Coffer renders through — config files, skill files, MCP config/schema, raw
// logs, chat tool-call payloads — replacing the old hand-styled <pre> blocks.
// Cmd/Ctrl+F opens the shared <FindWidget>; we drive the search ourselves
// (findHighlight.ts) instead of CodeMirror's native panel so the find UX matches
// the rendered-Markdown previews exactly. The viewer never mutates the file —
// editing happens in the user's own editor via the <FileActions> bar.
import { useEffect, useMemo, useRef, useState } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { EditorView, keymap } from "@codemirror/view";

import { cn } from "@/lib/utils";
import { languageForFile, type PreviewLanguage } from "@/lib/preview/language";
import { languageExtension } from "./codemirrorLang";
import { computeMatches, findField, findTheme, setMatchesEffect } from "./findHighlight";
import { FindWidget } from "./FindWidget";
import { useFind, type FindEngine } from "./useFind";

interface CodeViewProps {
  /** File content to display (read-only). */
  value: string;
  /** File name used to infer the language when `language` is not given. */
  filename?: string;
  /** Explicit language override (e.g. "json" for serialized payloads). */
  language?: PreviewLanguage;
  /** Fixed editor height (CSS length), e.g. "20rem". Scrolls past it. */
  height?: string;
  /** Max height before scrolling; the editor grows to content up to this. */
  maxHeight?: string;
  /** Show the line-number gutter (default true). */
  lineNumbers?: boolean;
  /** Accessible label for the editor region. */
  ariaLabel?: string;
  className?: string;
}

const baseTheme = EditorView.theme({
  "&": { backgroundColor: "transparent", color: "inherit", fontSize: "0.75rem" },
  "&.cm-focused": { outline: "none" },
  ".cm-content": { fontFamily: "var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace)" },
  ".cm-scroller": { lineHeight: "1.5" },
  ".cm-gutters": {
    backgroundColor: "transparent",
    color: "hsl(var(--muted-foreground))",
    border: "none",
  },
  ".cm-cursor": { borderLeftColor: "transparent" },
});

function makeCmEngine(view: EditorView): FindEngine {
  let matches = computeMatches("", "", false);
  return {
    apply(query, caseSensitive) {
      matches = computeMatches(view.state.doc.toString(), query, caseSensitive);
      view.dispatch({ effects: setMatchesEffect.of({ matches, active: -1 }) });
      return matches.length;
    },
    setActive(index) {
      const match = matches[index];
      if (!match) return;
      view.dispatch({
        effects: [
          setMatchesEffect.of({ matches, active: index }),
          EditorView.scrollIntoView(match.from, { y: "center" }),
        ],
      });
    },
    clear() {
      matches = [];
      view.dispatch({ effects: setMatchesEffect.of({ matches: [], active: -1 }) });
    },
  };
}

export function CodeView({
  value,
  filename,
  language,
  height,
  maxHeight,
  lineNumbers = true,
  ariaLabel,
  className,
}: CodeViewProps) {
  const [engine, setEngine] = useState<FindEngine | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const find = useFind(engine);

  // Keep the CM keymap's find trigger pointing at the latest openFind without
  // rebuilding the (memoized) extension array on every render.
  const openFindRef = useRef(find.openFind);
  openFindRef.current = find.openFind;

  const extensions = useMemo(() => {
    const exts = [
      findField,
      findTheme,
      baseTheme,
      EditorView.editable.of(false),
      EditorView.contentAttributes.of({ tabindex: "0" }),
      keymap.of([
        {
          key: "Mod-f",
          preventDefault: true,
          run: () => {
            openFindRef.current();
            return true;
          },
        },
      ]),
    ];
    const lang = languageExtension(language ?? languageForFile(filename));
    if (lang) exts.push(lang);
    return exts;
  }, [language, filename]);

  useEffect(() => {
    if (find.open) inputRef.current?.focus();
  }, [find.open]);

  return (
    <div
      className={cn("relative overflow-hidden rounded border", className)}
      onKeyDown={(e) => {
        if ((e.metaKey || e.ctrlKey) && (e.key === "f" || e.key === "F")) {
          e.preventDefault();
          find.openFind();
          inputRef.current?.focus();
        } else if (e.key === "Escape" && find.open) {
          e.preventDefault();
          find.closeFind();
        }
      }}
    >
      <CodeMirror
        value={value}
        editable={false}
        readOnly
        theme="none"
        height={height}
        maxHeight={maxHeight}
        extensions={extensions}
        aria-label={ariaLabel}
        basicSetup={{
          lineNumbers,
          foldGutter: false,
          highlightActiveLine: false,
          highlightActiveLineGutter: false,
          highlightSelectionMatches: false,
          searchKeymap: false,
          autocompletion: false,
          closeBrackets: false,
          bracketMatching: false,
        }}
        onCreateEditor={(view) => setEngine(() => makeCmEngine(view))}
      />
      {find.open ? (
        <FindWidget
          ref={inputRef}
          query={find.query}
          count={find.count}
          active={find.active}
          caseSensitive={find.caseSensitive}
          onQueryChange={find.setQuery}
          onToggleCase={find.toggleCaseSensitive}
          onNext={find.next}
          onPrev={find.prev}
          onClose={find.closeFind}
        />
      ) : null}
    </div>
  );
}
