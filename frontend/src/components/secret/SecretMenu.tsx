// src/components/secret/SecretMenu.tsx — the one secret menu (Foundations 0.2.05):
// filter · stored secrets by name (with their description and "used by N") · New secret… · Change value… ·
// (rows only) Type a plain value · (optional fields) None. Wraps its trigger, and owns the New secret
// and Replace value dialogs it opens.
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Check, KeyRound, Search } from "lucide-react";

import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useSecretChoices } from "./useSecretChoices";
import { cn } from "@/lib/utils";
import { LABEL_MAX } from "./secretRows";
import { NewSecretDialog } from "./NewSecretDialog";
import { ReplaceSecretDialog } from "./ReplaceSecretDialog";

interface Props {
  /** The trigger; rendered as the popover's anchor (`asChild`). */
  children: ReactNode;
  /** The secret now chosen (stored id, or a pending new one's id). */
  selected: string | null;
  onSelectStored: (name: string) => void;
  /** Label the New secret dialog opens with. */
  defaultNewLabel: string;
  /** Rows only: back to a plain value. Omit in a whole-value secret field. */
  onPlain?: () => void;
  /** An optional secret field: the item that empties it ("None"). */
  clear?: { label: string; onClear: () => void };
  /** A pending new secret: its label, editable until the form is saved. */
  pendingLabel?: { value: string; onChange: (label: string) => void };
  disabled?: boolean;
}

const ITEM =
  "flex h-[30px] w-full items-center gap-2 rounded-md px-2 text-left text-xs hover:bg-surface-hover focus-visible:bg-surface-hover focus-visible:outline-none";

export function SecretMenu(props: Props) {
  const { children, selected, onSelectStored, defaultNewLabel, onPlain, pendingLabel, clear } =
    props;
  const { t } = useTranslation();
  const { options, rowOf, displayOf } = useSecretChoices();
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("");
  const [creating, setCreating] = useState(false);
  const [changing, setChanging] = useState(false);

  const needle = filter.trim().toLowerCase();
  const shown = options.filter((o) =>
    [o.display, o.name, o.description].some((v) => v?.toLowerCase().includes(needle)),
  );
  const changeRow = selected ? (rowOf(selected) ?? null) : null;
  const close = () => {
    setOpen(false);
    setFilter("");
  };

  return (
    <>
      <Popover open={open} onOpenChange={(next) => (next ? setOpen(true) : close())}>
        <PopoverTrigger asChild disabled={props.disabled}>
          {children}
        </PopoverTrigger>
        <PopoverContent
          collisionPadding={8}
          className="flex max-h-[min(420px,var(--radix-popover-content-available-height))] w-[var(--radix-popover-trigger-width)] min-w-[240px] flex-col p-1.5 text-text"
          aria-label={t("secretField.menu")}
        >
          {pendingLabel ? (
            <div className="mb-1 flex shrink-0 flex-col gap-1 border-b border-border-subtle px-1 pb-2">
              <label htmlFor="secret-menu-label" className="text-xs text-text-muted">
                {t("secretField.pendingLabel")}
              </label>
              <Input
                id="secret-menu-label"
                value={pendingLabel.value}
                className="text-xs"
                maxLength={LABEL_MAX}
                onChange={(e) => pendingLabel.onChange(e.target.value)}
              />
            </div>
          ) : null}
          <div className="mb-0.5 flex shrink-0 items-center gap-2 border-b border-border-subtle px-2">
            <Search className="size-3.5 shrink-0 text-text-subtle" aria-hidden />
            <input
              autoFocus
              value={filter}
              placeholder={t("secretField.filter")}
              aria-label={t("secretField.filter")}
              onChange={(e) => setFilter(e.target.value)}
              className="h-8 w-full bg-transparent text-xs text-text caret-accent outline-none placeholder:text-text-subtle"
            />
          </div>
          <div
            role="listbox"
            aria-label={t("secretField.list")}
            className="flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto"
          >
            {shown.map((o) => (
              <button
                key={o.name}
                type="button"
                role="option"
                aria-selected={o.name === selected}
                className={cn(ITEM, "shrink-0", o.name === selected && "bg-surface-selected")}
                onClick={() => {
                  onSelectStored(o.name);
                  close();
                }}
              >
                <KeyRound className="size-3.5 shrink-0 text-text-muted" aria-hidden />
                <span className="min-w-0 truncate">{o.display}</span>
                {o.description ? (
                  <span className="min-w-0 flex-1 truncate font-sans text-text-subtle">
                    {o.description}
                  </span>
                ) : null}
                {o.name === selected ? (
                  <Check className="size-3.5 text-accent" aria-hidden />
                ) : null}
                <span className="ml-auto shrink-0 font-sans text-text-subtle">
                  {t("secretField.usedBy", { count: o.usedBy })}
                </span>
              </button>
            ))}
            {shown.length === 0 ? (
              <p className="px-2 py-1.5 text-xs text-text-subtle">{t("secretField.noMatch")}</p>
            ) : null}
          </div>
          <div className="mt-1 flex shrink-0 flex-col gap-0.5 border-t border-border-subtle pt-1">
            <button
              type="button"
              className={ITEM}
              onClick={() => {
                close();
                setCreating(true);
              }}
            >
              {t("secretField.newSecret")}
            </button>
            {changeRow ? (
              <button
                type="button"
                className={ITEM}
                onClick={() => {
                  close();
                  setChanging(true);
                }}
              >
                {t("secretField.changeValue", { name: displayOf(selected ?? "") })}
              </button>
            ) : null}
            {clear && selected ? (
              <button
                type="button"
                className={ITEM}
                onClick={() => {
                  clear.onClear();
                  close();
                }}
              >
                {clear.label}
              </button>
            ) : null}
            {onPlain ? (
              <button
                type="button"
                className={ITEM}
                onClick={() => {
                  onPlain();
                  close();
                }}
              >
                {t("secretField.plain")}
              </button>
            ) : null}
          </div>
        </PopoverContent>
      </Popover>
      <NewSecretDialog
        open={creating}
        onOpenChange={setCreating}
        defaultLabel={defaultNewLabel}
        onCreated={onSelectStored}
      />
      <ReplaceSecretDialog row={changing ? changeRow : null} onOpenChange={setChanging} />
    </>
  );
}
