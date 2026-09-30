import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { Search, X } from "lucide-react";
import { Input } from "@/components/ui/input";
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
  /** A key that focuses the field from anywhere on the page (not while
   *  typing elsewhere), hinted at the right edge while the field is empty. */
  shortcut?: string;
}

/**
 * A search field with a leading magnifier and a trailing clear (×) button
 * that appears once there is text. Shared by the MCP server list and the
 * audit log search.
 */
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
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (!shortcut) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== shortcut || e.metaKey || e.ctrlKey || e.altKey) return;
      const target = e.target as HTMLElement | null;
      if (target?.closest("input, textarea, select, [contenteditable='true']")) return;
      e.preventDefault();
      input.current?.focus();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [shortcut]);
  return (
    <div className={cn("relative", className)}>
      <Search
        className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
        aria-hidden
      />
      <Input
        ref={input}
        id={id}
        aria-label={ariaLabel}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={
          onSearch
            ? (e) => {
                if (e.key === "Enter" && value.trim()) onSearch();
              }
            : undefined
        }
        className={cn("pl-9", value && "pr-9")}
      />
      {value ? (
        <button
          type="button"
          onClick={() => onChange("")}
          aria-label={t("common.clear")}
          className="absolute right-1.5 top-1/2 grid size-7 -translate-y-1/2 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-surface-hover hover:text-text"
        >
          <X className="size-4" />
        </button>
      ) : shortcut ? (
        <kbd
          aria-hidden
          className="pointer-events-none absolute right-2 top-1/2 inline-flex h-[18px] -translate-y-1/2 items-center rounded-xs border border-border px-1 font-sans text-2xs text-text-subtle"
        >
          {shortcut}
        </kbd>
      ) : null}
    </div>
  );
}
