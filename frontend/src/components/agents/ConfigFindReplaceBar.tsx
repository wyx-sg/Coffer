// frontend/src/components/agents/ConfigFindReplaceBar.tsx — spec 004.
// A compact, dependency-free find/replace toolbar for the config editor. It
// operates purely on plain strings over the editable textarea (no CodeMirror):
//   * Find        — live match count + "Find next" (selects + scrolls, wraps).
//   * Replace      — replaces the currently selected match (or the first match).
//   * Replace all  — replaces every occurrence; marks the editor dirty.
//   * Case toggle  — optional case-sensitive matching.
// Replacements mutate the content via `onContentChange`; they never auto-save.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

// Count non-overlapping occurrences of `needle` in `haystack`.
function countMatches(haystack: string, needle: string, caseSensitive: boolean): number {
  if (!needle) return 0;
  const h = caseSensitive ? haystack : haystack.toLowerCase();
  const n = caseSensitive ? needle : needle.toLowerCase();
  let count = 0;
  let i = h.indexOf(n);
  while (i !== -1) {
    count += 1;
    i = h.indexOf(n, i + n.length);
  }
  return count;
}

// Index of the first match at or after `from`, wrapping to the start. -1 if none.
function nextIndex(haystack: string, needle: string, from: number, caseSensitive: boolean): number {
  if (!needle) return -1;
  const h = caseSensitive ? haystack : haystack.toLowerCase();
  const n = caseSensitive ? needle : needle.toLowerCase();
  const found = h.indexOf(n, from);
  return found !== -1 ? found : h.indexOf(n);
}

export function ConfigFindReplaceBar({
  content,
  onContentChange,
  textareaRef,
}: {
  content: string;
  onContentChange: (next: string) => void;
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
}) {
  const { t } = useTranslation();
  const [find, setFind] = useState("");
  const [replace, setReplace] = useState("");
  const [caseSensitive, setCaseSensitive] = useState(false);
  // A selection to apply *after* the next render. Replace mutates `content` via
  // onContentChange, so the textarea's DOM value only reflects the new text on
  // the following render — selecting/scrolling synchronously would target the
  // stale value (and the selection would be wiped by the controlled update).
  // We stash the target here and apply it once `content` has been committed.
  const [pending, setPending] = useState<{ start: number; end: number } | null>(null);

  const matches = countMatches(content, find, caseSensitive);

  // Scroll the textarea so the line containing `offset` is roughly centered.
  // setSelectionRange selects the text but does NOT scroll a <textarea> to
  // reveal it, so without this the match could be selected off-screen — the
  // "jump to the matching line" behaviour the find bar is meant to provide.
  function scrollToOffset(ta: HTMLTextAreaElement, offset: number) {
    const line = ta.value.slice(0, offset).split("\n").length - 1;
    const style = getComputedStyle(ta);
    let lineHeight = parseFloat(style.lineHeight);
    if (!Number.isFinite(lineHeight)) {
      // `line-height: normal` reports as NaN; approximate from the font size.
      lineHeight = (parseFloat(style.fontSize) || 12) * 1.4;
    }
    ta.scrollTop = Math.max(0, line * lineHeight - ta.clientHeight / 2);
  }

  function selectMatch(start: number, end: number) {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.focus();
    ta.setSelectionRange(start, end);
    scrollToOffset(ta, start);
  }

  // Apply a deferred selection once the new content has been committed to the
  // textarea (covers Replace, which changes `content` before we can select).
  useEffect(() => {
    if (!pending) return;
    selectMatch(pending.start, pending.end);
    setPending(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [content, pending]);

  function findNext() {
    if (!find) return;
    const ta = textareaRef.current;
    // Search from just after the current selection so repeated clicks advance.
    const from = ta ? ta.selectionEnd : 0;
    const at = nextIndex(content, find, from, caseSensitive);
    // No content change here, so the DOM value is current — select immediately.
    if (at !== -1) selectMatch(at, at + find.length);
  }

  // Replace the currently selected occurrence if it matches `find`; otherwise
  // jump to (select) the next one so a second click replaces it.
  function replaceCurrent() {
    if (!find) return;
    const ta = textareaRef.current;
    const start = ta ? ta.selectionStart : 0;
    const end = ta ? ta.selectionEnd : 0;
    const selected = content.slice(start, end);
    const isMatch = caseSensitive
      ? selected === find
      : selected.toLowerCase() === find.toLowerCase();
    if (isMatch) {
      const next = content.slice(0, start) + replace + content.slice(end);
      onContentChange(next);
      // Defer selecting the next match until `next` is rendered into the DOM.
      const after = start + replace.length;
      const at = nextIndex(next, find, after, caseSensitive);
      setPending(at !== -1 ? { start: at, end: at + find.length } : { start: after, end: after });
    } else {
      findNext();
    }
  }

  function replaceAll() {
    if (!find || matches === 0) return;
    let out = "";
    const h = caseSensitive ? content : content.toLowerCase();
    const n = caseSensitive ? find : find.toLowerCase();
    let i = 0;
    let at = h.indexOf(n, i);
    while (at !== -1) {
      out += content.slice(i, at) + replace;
      i = at + n.length;
      at = h.indexOf(n, i);
    }
    out += content.slice(i);
    onContentChange(out);
  }

  return (
    <div className="space-y-2 rounded-md border bg-muted/30 p-2">
      <div className="flex flex-wrap items-center gap-2">
        <Label htmlFor="cfg-find" className="sr-only">
          {t("agents.config.find.find")}
        </Label>
        <Input
          id="cfg-find"
          value={find}
          onChange={(e) => setFind(e.target.value)}
          placeholder={t("agents.config.find.find")}
          className="h-8 w-40 text-xs"
        />
        <span className="text-xs text-muted-foreground" data-testid="find-match-count">
          {t("agents.config.find.matches", { n: matches })}
        </span>
        <Button type="button" variant="outline" size="sm" onClick={findNext} disabled={!find}>
          {t("agents.config.find.findNext")}
        </Button>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Label htmlFor="cfg-replace" className="sr-only">
          {t("agents.config.find.replace")}
        </Label>
        <Input
          id="cfg-replace"
          value={replace}
          onChange={(e) => setReplace(e.target.value)}
          placeholder={t("agents.config.find.replace")}
          className="h-8 w-40 text-xs"
        />
        <Button type="button" variant="outline" size="sm" onClick={replaceCurrent} disabled={!find}>
          {t("agents.config.find.replace")}
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={replaceAll} disabled={!find}>
          {t("agents.config.find.replaceAll")}
        </Button>
        <label className="ml-auto flex items-center gap-1.5 text-xs text-muted-foreground">
          <input
            type="checkbox"
            checked={caseSensitive}
            onChange={(e) => setCaseSensitive(e.target.checked)}
            aria-label={t("agents.config.find.caseSensitive")}
          />
          {t("agents.config.find.caseSensitive")}
        </label>
      </div>
    </div>
  );
}
