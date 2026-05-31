// frontend/src/components/chat/NewConversationDialog.tsx
//
// New-conversation flow: pick a target (a built-in agent or a managed agent),
// create the conversation, and hand the new id back to the caller to navigate.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle, Bot, Terminal } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { translateApiError } from "@/lib/api/errors";
import { useCreateConversation } from "@/lib/hooks/useChat";
import { useChatTargets, type ChatTarget } from "@/lib/hooks/useChatTargets";
import { cn } from "@/lib/utils";

export function NewConversationDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (conversationId: string) => void;
}) {
  const { t } = useTranslation();
  const { data: targets, isPending, error } = useChatTargets();
  const create = useCreateConversation();
  const [selected, setSelected] = useState<string | null>(null);

  // Default to the first target (built-in agent) each time the dialog opens.
  useEffect(() => {
    if (open) setSelected((prev) => prev ?? targets?.[0]?.ref ?? null);
    if (!open) setSelected(null);
  }, [open, targets]);

  const submit = () => {
    if (!selected) return;
    create.mutate(
      { target_ref: selected },
      {
        onSuccess: (conv) => {
          onOpenChange(false);
          onCreated(conv.id);
        },
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("chat.new.title")}</DialogTitle>
          <DialogDescription>{t("chat.new.subtitle")}</DialogDescription>
        </DialogHeader>

        {isPending ? (
          <p className="py-4 text-center text-sm text-muted-foreground">{t("common.loading")}</p>
        ) : error ? (
          <div className="flex items-start gap-2 text-sm text-destructive" role="alert">
            <AlertCircle className="mt-0.5 size-4 shrink-0" />
            <span>{translateApiError(t, error)}</span>
          </div>
        ) : (targets ?? []).length === 0 ? (
          <p className="py-4 text-center text-sm text-muted-foreground">{t("chat.new.empty")}</p>
        ) : (
          <ul className="flex max-h-72 flex-col gap-2 overflow-y-auto">
            {(targets ?? []).map((target) => (
              <TargetRow
                key={target.ref}
                target={target}
                selected={selected === target.ref}
                onSelect={() => setSelected(target.ref)}
              />
            ))}
          </ul>
        )}

        {create.error ? (
          <div className="flex items-start gap-2 text-sm text-destructive" role="alert">
            <AlertCircle className="mt-0.5 size-4 shrink-0" />
            <span>{translateApiError(t, create.error)}</span>
          </div>
        ) : null}

        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button onClick={submit} disabled={!selected || create.isPending}>
            {create.isPending ? t("chat.new.starting") : t("chat.new.start")}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function TargetRow({
  target,
  selected,
  onSelect,
}: {
  target: ChatTarget;
  selected: boolean;
  onSelect: () => void;
}) {
  const { t } = useTranslation();
  const Icon = target.kind === "builtin_agent" ? Terminal : Bot;
  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        aria-pressed={selected}
        className={cn(
          "flex w-full items-start gap-3 rounded-md border px-3 py-2.5 text-left transition-colors",
          selected
            ? "border-primary bg-primary/5"
            : "border-border hover:border-input hover:bg-secondary",
        )}
      >
        <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-md bg-primary/10 text-primary">
          <Icon className="size-4" strokeWidth={1.75} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-2">
            <span className="truncate text-sm font-medium text-foreground">{target.name}</span>
            <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
              {target.kind === "builtin_agent" ? t("chat.new.builtin") : t("chat.new.managed")}
            </span>
          </span>
          {target.description ? (
            <span className="mt-0.5 block truncate text-xs text-muted-foreground">
              {target.description}
            </span>
          ) : null}
        </span>
      </button>
    </li>
  );
}
