// src/components/preview/findHighlight.ts
// CodeMirror in-document find: a StateField of mark decorations driven by a
// StateEffect, plus the pure match scanner. <CodeView> dispatches setMatches to
// paint all matches (and the active one) and drive next/previous — this is what
// the shared <FindWidget> talks to for code/text previews (the rendered-Markdown
// equivalent lives in domFind.ts).
import { StateEffect, StateField } from "@codemirror/state";
import { Decoration, type DecorationSet, EditorView } from "@codemirror/view";

export interface CmMatch {
  from: number;
  to: number;
}

export const setMatchesEffect = StateEffect.define<{ matches: CmMatch[]; active: number }>();

const matchMark = Decoration.mark({ class: "cm-find-match" });
const activeMark = Decoration.mark({ class: "cm-find-match cm-find-match-active" });

export const findField = StateField.define<DecorationSet>({
  create() {
    return Decoration.none;
  },
  update(deco, tr) {
    deco = deco.map(tr.changes);
    for (const effect of tr.effects) {
      if (effect.is(setMatchesEffect)) {
        const { matches, active } = effect.value;
        deco = Decoration.set(
          matches.map((m, i) => (i === active ? activeMark : matchMark).range(m.from, m.to)),
          true,
        );
      }
    }
    return deco;
  },
  provide: (field) => EditorView.decorations.from(field),
});

/** Match highlight colors, scoped to the editor so they don't leak globally. */
export const findTheme = EditorView.baseTheme({
  ".cm-find-match": { backgroundColor: "rgba(253, 224, 71, 0.45)", borderRadius: "2px" },
  ".cm-find-match-active": { backgroundColor: "rgba(251, 191, 36, 0.9)" },
});

/** All occurrences of `query` in `doc`, in document order (empty when blank). */
export function computeMatches(doc: string, query: string, caseSensitive: boolean): CmMatch[] {
  if (!query) return [];
  const haystack = caseSensitive ? doc : doc.toLowerCase();
  const needle = caseSensitive ? query : query.toLowerCase();
  const out: CmMatch[] = [];
  let i = haystack.indexOf(needle);
  while (i !== -1) {
    out.push({ from: i, to: i + needle.length });
    i = haystack.indexOf(needle, i + needle.length);
  }
  return out;
}
