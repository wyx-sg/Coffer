// src/components/preview/CodeEditor.tsx — the editable sibling of CodeView (Foundations 0.2 · Code editor): the same
// CodeMirror look, line numbers and syntax colours, in a field's frame (border, focus halo, invalid state), growing
// with its text between `minHeight` and `maxHeight`. Callers add their own marks through `extensions` (a custom
// tool's body template marks its `{holes}`).
import { useMemo } from "react";
import CodeMirror from "@uiw/react-codemirror";
import type { Extension } from "@codemirror/state";
import { EditorView } from "@codemirror/view";

import { cn } from "@/lib/utils";
import type { PreviewLanguage } from "@/lib/preview/language";
import { languageExtension } from "./codemirrorLang";
import { codeViewHighlighting, codeViewTheme } from "./codemirrorTheme";

interface CodeEditorProps {
  value: string;
  onChange: (value: string) => void;
  language: PreviewLanguage;
  id?: string;
  ariaLabel?: string;
  /** Marks the frame invalid (the danger border and halo). */
  invalid?: boolean;
  /** Shown while the editor is empty. */
  placeholder?: string;
  minHeight?: string;
  maxHeight?: string;
  extensions?: readonly Extension[];
  className?: string;
}

export function CodeEditor({
  value,
  onChange,
  language,
  id,
  ariaLabel,
  invalid = false,
  placeholder,
  minHeight = "8rem",
  maxHeight = "24rem",
  extensions = [],
  className,
}: CodeEditorProps) {
  const all = useMemo(() => {
    const exts: Extension[] = [codeViewTheme, codeViewHighlighting, EditorView.lineWrapping];
    const lang = languageExtension(language);
    if (lang) exts.push(lang);
    if (id || ariaLabel || invalid)
      exts.push(
        EditorView.contentAttributes.of({
          ...(id ? { id } : {}),
          ...(ariaLabel ? { "aria-label": ariaLabel } : {}),
          ...(invalid ? { "aria-invalid": "true" } : {}),
        }),
      );
    return [...exts, ...extensions];
  }, [language, id, ariaLabel, invalid, extensions]);

  return (
    <div
      className={cn(
        "overflow-hidden rounded-md border border-border bg-code transition-[border-color,box-shadow] duration-fast ease-standard",
        "focus-within:border-accent focus-within:ring-[3px] focus-within:ring-accent-soft",
        invalid &&
          "border-danger ring-[3px] ring-danger-soft focus-within:border-danger focus-within:ring-danger-soft",
        className,
      )}
    >
      <CodeMirror
        value={value}
        onChange={onChange}
        theme="none"
        minHeight={minHeight}
        maxHeight={maxHeight}
        placeholder={placeholder}
        extensions={all}
        basicSetup={{
          lineNumbers: true,
          foldGutter: false,
          highlightActiveLine: false,
          highlightActiveLineGutter: false,
          highlightSelectionMatches: false,
          searchKeymap: false,
          autocompletion: false,
          closeBrackets: true,
          bracketMatching: true,
        }}
      />
    </div>
  );
}
