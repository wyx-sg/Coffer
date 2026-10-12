// src/components/custom-tools/holeMarks.ts — the CodeMirror marks a tool's templates give their holes: `{name}` (an
// input) and `{env:NAME}` (an environment's variable) drawn as an accent chip, so a template reads as JSON with
// blanks in it rather than as broken JSON.
import {
  Decoration,
  EditorView,
  MatchDecorator,
  ViewPlugin,
  type ViewUpdate,
} from "@codemirror/view";
import type { DecorationSet } from "@codemirror/view";

const holeMark = Decoration.mark({ class: "cm-hole" });

const decorator = new MatchDecorator({
  regexp: /\{(?:env:[A-Za-z_][A-Za-z0-9_]{0,63}|[A-Za-z_][A-Za-z0-9_.-]*)\}/g,
  decoration: () => holeMark,
});

const plugin = ViewPlugin.fromClass(
  class {
    marks: DecorationSet;
    constructor(view: EditorView) {
      this.marks = decorator.createDeco(view);
    }
    update(update: ViewUpdate) {
      this.marks = decorator.updateDeco(update, this.marks);
    }
  },
  { decorations: (v) => v.marks },
);

const theme = EditorView.theme({
  ".cm-hole, .cm-hole *": {
    color: "rgb(var(--accent-text)) !important",
  },
  ".cm-hole": {
    backgroundColor: "rgb(var(--accent) / 0.12)",
    borderRadius: "3px",
  },
});

/** The marks, as one `extensions` entry. */
export const holeMarks = [plugin, theme];
