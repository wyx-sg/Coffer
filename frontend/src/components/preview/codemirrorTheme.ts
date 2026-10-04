// src/components/preview/codemirrorTheme.ts
// CodeMirror's chrome and syntax colours, read from the colour tokens so the
// read-only code viewer follows the light / dark theme. CodeMirror's own
// default highlight style is written for a light page (dark blues and purples
// that vanish on the dark code fill), so it is replaced rather than extended.
import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { EditorView } from "@codemirror/view";
import { tags } from "@lezer/highlight";

const token = (name: string, alpha?: number) =>
  alpha === undefined ? `rgb(var(--${name}))` : `rgb(var(--${name}) / ${alpha})`;

/** Editor chrome: text, gutters, selection and cursor on the code fill. */
export const codeViewTheme = EditorView.theme({
  "&": {
    backgroundColor: token("code"),
    color: token("text"),
    fontSize: "12px",
  },
  "&.cm-focused": { outline: "none" },
  ".cm-content": {
    fontFamily: '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace',
    caretColor: token("text"),
  },
  ".cm-scroller": { lineHeight: "1.6" },
  ".cm-gutters": {
    backgroundColor: token("code"),
    color: token("text-subtle"),
    border: "none",
  },
  ".cm-cursor, .cm-dropCursor": { borderLeftColor: token("text") },
  "&.cm-focused .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection": {
    backgroundColor: token("accent", 0.2),
  },
});

/** Syntax colours drawn from the text, accent and status roles. */
const codeHighlightStyle = HighlightStyle.define([
  { tag: [tags.comment, tags.lineComment, tags.blockComment], color: token("text-subtle") },
  { tag: [tags.keyword, tags.operatorKeyword, tags.modifier], color: token("danger") },
  {
    tag: [tags.propertyName, tags.attributeName, tags.definition(tags.name)],
    color: token("accent-text"),
  },
  { tag: [tags.string, tags.special(tags.string), tags.regexp], color: token("success") },
  { tag: [tags.number, tags.bool, tags.null, tags.atom], color: token("warning") },
  { tag: [tags.tagName, tags.typeName, tags.className], color: token("danger") },
  { tag: [tags.meta, tags.punctuation, tags.bracket, tags.separator], color: token("text-muted") },
  { tag: tags.heading, fontWeight: "600" },
  { tag: tags.invalid, color: token("danger") },
]);

export const codeViewHighlighting = syntaxHighlighting(codeHighlightStyle);
