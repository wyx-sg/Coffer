// src/components/SearchInput.tsx — the search field: a leading magnifier, a clear (×) once typed, an optional key to reach it.
//
// Foundations-Inputs "Search with shortcut": the 30px text field, padding 10,
// a 14px text-subtle icon 8 before the text, and — for the one search a list
// page leads with — a key cap on the right ("/") that focuses the field from
// anywhere on the page. The cap hides while the field is focused or holds
// text, where the clear button takes its place. Esc in such a field clears it,
// and a second Esc leaves it (Foundations-Focus "Shortcuts").
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Search, X } from "lucide-react";

import { Input } from "@/components/ui/input";
import { Kbd } from "@/components/ui/kbd";
import { cn } from "@/lib/utils";

interface Props {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  /** Form id — set when a separate <Label htmlFor> labels the field. */
  id?: string;
  /** Accessible name — set when there is no visible label. */
  ariaLabel?: string;
  /** Extra classes for the wrapper (e.g. width). */
  className?: string;
  /** Fired on Enter when the (trimmed) value is non-empty — for inputs that
   *  trigger an explicit action (e.g. a server search) rather than live-filter. */
  onSearch?: () => void;
  /** A single key (e.g. "/") that focuses this field from anywhere on the page
   *  while nothing editable has focus; shown as a key cap in the empty field.
   *  Give it to the one search a page leads with. */
  shortcut?: string;
}

/** True when a key press belongs to a field the user is typing in. */
function typingIn(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return (
    target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName.toUpperCase())
  );
}

export function SearchInput({
  value,
  onChange,
  placeholder,
  id,
  ariaLabel,
  className,
  onSearch,
  shortcut,
}: Props) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    if (!shortcut) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== shortcut || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.defaultPrevented || typingIn(e.target)) return;
      e.preventDefault();
      inputRef.current?.focus();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [shortcut]);

  const showKey = Boolean(shortcut) && !value && !focused;

  return (
    <div className={cn("relative", className)}>
      <Search
        className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-text-subtle"
        aria-hidden
      />
      <Input
        ref={inputRef}
        id={id}
        aria-label={ariaLabel}
        aria-keyshortcuts={shortcut}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && onSearch && value.trim()) onSearch();
          if (e.key === "Escape" && shortcut) {
            if (value) onChange("");
            else e.currentTarget.blur();
          }
        }}
        className={cn("pl-8", (value || showKey) && "pr-8")}
      />
      {value ? (
        <button
          type="button"
          onClick={() => onChange("")}
          aria-label={t("common.clear")}
          className="absolute right-1 top-1/2 grid size-control-sm -translate-y-1/2 place-items-center rounded-item text-text-subtle transition-colors duration-fast hover:bg-surface-hover hover:text-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring"
        >
          <X className="size-3.5" aria-hidden />
        </button>
      ) : null}
      {showKey ? (
        <Kbd aria-hidden className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2">
          {shortcut}
        </Kbd>
      ) : null}
    </div>
  );
}
