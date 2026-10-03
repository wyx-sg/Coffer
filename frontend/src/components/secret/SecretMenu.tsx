// src/components/secret/SecretMenu.tsx — the one secret menu (Foundations 0.2.05):
// filter · stored secrets with "used by N" · New secret… · Change value… ·
// (rows only) Type a plain value. Wraps its trigger, and owns the New secret
// and Replace value dialogs it opens.
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Check, KeyRound } from "lucide-react";

import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useSecretChoices } from "./useSecretChoices";
import { cn } from "@/lib/utils";
import { NewSecretDialog } from "./NewSecretDialog";
import { ReplaceSecretDialog } from "./ReplaceSecretDialog";

interface Props {
  /** The trigger; rendered as the popover's anchor (`asChild`). */
  children: ReactNode;
  /** The secret now chosen (stored name, or a pending new one's name). */
  selected: string | null;
  onSelectStored: (name: string) => void;
  /** Name the New secret dialog opens with. */
  defaultNewName: string;
  /** Rows only: back to a plain value. Omit in a whole-value secret field. */
  onPlain?: () => void;
  /** A pending new secret: renaming it before the form is saved. */
  pendingName?: { value: string; onChange: (name: string) => void };
  disabled?: boolean;
}

const ITEM =
  "flex h-[30px] w-full items-center gap-2 rounded-md px-2 text-left text-xs hover:bg-surface-hover focus-visible:bg-surface-hover focus-visible:outline-none";

export function SecretMenu(props: Props) {
  const { children, selected, onSelectStored, defaultNewName, onPlain, pendingName } = props;
  const { t } = useTranslation();
  const { options, rowOf } = useSecretChoices();
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("");
  const [creating, setCreating] = useState(false);
  const [changing, setChanging] = useState(false);

  const needle = filter.trim().toLowerCase();
  const shown = options.filter((o) => o.name.toLowerCase().includes(needle));
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
          className="w-[var(--radix-popover-trigger-width)] min-w-[240px] p-1.5 text-text"
          aria-label={t("secretField.menu")}
        >
          {pendingName ? (
            <div className="mb-1 flex flex-col gap-1 border-b border-border-subtle px-1 pb-2">
              <label htmlFor="secret-menu-rename" className="text-xs text-text-muted">
                {t("secretField.rename")}
              </label>
              <Input
                id="secret-menu-rename"
                value={pendingName.value}
                className="font-mono text-xs"
                spellCheck={false}
                onChange={(e) => pendingName.onChange(e.target.value)}
              />
            </div>
          ) : null}
          <input
            autoFocus
            value={filter}
            placeholder={t("secretField.filter")}
            aria-label={t("secretField.filter")}
            onChange={(e) => setFilter(e.target.value)}
            className="mb-0.5 h-7 w-full border-b border-border-subtle bg-transparent px-2 text-xs text-text caret-accent outline-none placeholder:text-text-subtle"
          />
          <div role="listbox" aria-label={t("secretField.list")} className="flex flex-col gap-0.5">
            {shown.map((o) => (
              <button
                key={o.name}
                type="button"
                role="option"
                aria-selected={o.name === selected}
                className={cn(ITEM, "font-mono", o.name === selected && "bg-surface-selected")}
                onClick={() => {
                  onSelectStored(o.name);
                  close();
                }}
              >
                <KeyRound className="size-3.5 shrink-0 text-text-muted" aria-hidden />
                <span className="truncate">{o.name}</span>
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
          <div className="mt-1 flex flex-col gap-0.5 border-t border-border-subtle pt-1">
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
                {t("secretField.changeValue", { name: selected })}
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
        defaultName={defaultNewName}
        onCreated={onSelectStored}
      />
      <ReplaceSecretDialog row={changing ? changeRow : null} onOpenChange={setChanging} />
    </>
  );
}
