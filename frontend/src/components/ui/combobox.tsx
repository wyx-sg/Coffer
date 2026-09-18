// src/components/ui/combobox.tsx — a select you can type into.
//
// `Select` is the right control for a handful of fixed options; this is for
// the ones that come from the vault and can run to dozens — knowledge
// collections, skills, agents. Same trigger, plus a filter box, so picking one
// out of forty does not mean scrolling forty.
//
// Choices only: what the developer types filters, it never becomes the value.
// A field where a typo silently becomes a new entity is a field that creates
// entities by accident, and the two callers that need "create one" say so with
// their own control.
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, ChevronsUpDown, Search } from "lucide-react";

import { cn } from "@/lib/utils";

export interface ComboboxOption {
  value: string;
  label: string;
  /** A second line under the label — what this option is, when the name alone
   *  does not say. */
  hint?: string;
}

interface Props {
  id?: string;
  value: string | null;
  options: ComboboxOption[];
  onChange: (value: string) => void;
  placeholder: string;
  /** Shown in the list when the filter matches nothing, and when there are no
   *  options at all — "no collections yet" is a different answer from "none
   *  match", and the caller knows which it has. */
  emptyMessage: string;
  disabled?: boolean;
  "aria-invalid"?: true;
  "aria-describedby"?: string;
}

export function Combobox({
  id,
  value,
  options,
  onChange,
  placeholder,
  emptyMessage,
  disabled = false,
  ...aria
}: Props) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("");

  const shown = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    if (needle.length === 0) return options;
    return options.filter(
      (option) =>
        option.label.toLowerCase().includes(needle) ||
        (option.hint ?? "").toLowerCase().includes(needle),
    );
  }, [filter, options]);

  const selected = options.find((option) => option.value === value);
  const root = useRef<HTMLDivElement>(null);

  // Plain element rather than a Popover: this list lives inside dialogs, which
  // are already portalled and already trap focus, and nesting a second
  // portalled layer inside one buys nothing but the ways the two can disagree
  // about which is on top.
  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  const dismiss = () => {
    setOpen(false);
    setFilter("");
  };

  return (
    <div className="relative" ref={root} onKeyDown={(e) => e.key === "Escape" && dismiss()}>
      <button
        id={id}
        type="button"
        role="combobox"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => setOpen((current) => !current)}
        {...aria}
        className={cn(
          "flex h-9 w-full items-center justify-between rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm",
          "focus:outline-none focus:ring-1 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
          "aria-[invalid=true]:border-destructive",
        )}
      >
        <span className={cn("truncate", selected === undefined && "text-muted-foreground")}>
          {selected?.label ?? placeholder}
        </span>
        <ChevronsUpDown className="ml-2 size-4 shrink-0 opacity-50" aria-hidden />
      </button>

      {open ? (
        <div className="absolute z-50 mt-1 w-full rounded-md border border-border bg-popover shadow-md">
          <div className="flex items-center gap-2 border-b border-border px-3">
            <Search className="size-4 shrink-0 text-muted-foreground" aria-hidden />
            <input
              autoFocus
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder={t("common.search")}
              aria-label={t("common.search")}
              className="h-9 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
            />
          </div>
          <div role="listbox" className="max-h-60 overflow-y-auto p-1">
            {shown.length === 0 ? (
              <p className="px-2 py-3 text-center text-sm text-muted-foreground">{emptyMessage}</p>
            ) : (
              shown.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  role="option"
                  aria-selected={option.value === value}
                  onClick={() => {
                    onChange(option.value);
                    dismiss();
                  }}
                  className="flex w-full items-start gap-2 rounded-sm px-2 py-1.5 text-left text-sm hover:bg-secondary focus-visible:bg-secondary focus-visible:outline-none"
                >
                  <Check
                    className={cn(
                      "mt-0.5 size-4 shrink-0",
                      option.value === value ? "opacity-100" : "opacity-0",
                    )}
                    aria-hidden
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate">{option.label}</span>
                    {option.hint ? (
                      <span className="block truncate text-xs text-muted-foreground">
                        {option.hint}
                      </span>
                    ) : null}
                  </span>
                </button>
              ))
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
