// frontend/src/kinds/memory/MemoryFactList.tsx
//
// Facts list section: a "Clear all" action plus the fact rows with their
// name / actor / type badges, optional description, inline edit textarea, and
// delete. All state and mutations live in the page; this component renders.
import { useTranslation } from "react-i18next";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { type FactListOut, type FactOut } from "./api";

interface Props {
  store: string;
  facts: FactListOut | undefined;
  editingId: string | null;
  editText: string;
  isClearPending: boolean;
  isUpdatePending: boolean;
  isDeletePending: boolean;
  onClearAll: () => void;
  onStartEdit: (fact: FactOut) => void;
  onDelete: (id: string) => void;
  onEditTextChange: (value: string) => void;
  onSaveEdit: (id: string) => void;
  onCancelEdit: () => void;
}

export function MemoryFactList({
  store,
  facts,
  editingId,
  editText,
  isClearPending,
  isUpdatePending,
  isDeletePending,
  onClearAll,
  onStartEdit,
  onDelete,
  onEditTextChange,
  onSaveEdit,
  onCancelEdit,
}: Props) {
  const { t } = useTranslation();
  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-medium">{t("memory.detail.facts")}</h2>
        <Button
          variant="destructive"
          size="sm"
          onClick={() => {
            if (window.confirm(t("memory.detail.clearConfirm", { store }))) {
              onClearAll();
            }
          }}
          disabled={isClearPending}
        >
          {t("memory.detail.clearAll")}
        </Button>
      </div>
      {facts ? (
        <ul className="divide-y rounded border">
          {facts.facts.map((f: FactOut) => (
            <li key={f.id} className="flex items-start justify-between gap-2 p-3">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium">{f.name}</span>
                  <Badge variant="secondary">{f.actor}</Badge>
                  {f.type ? <Badge variant="outline">{f.type}</Badge> : null}
                </div>
                {f.description ? (
                  <div className="text-xs text-muted-foreground">{f.description}</div>
                ) : null}
                {editingId === f.id ? (
                  <div className="mt-2 space-y-2">
                    <textarea
                      aria-label={t("memory.detail.editAria", { name: f.name })}
                      className="min-h-20 w-full rounded-md border border-input bg-background p-2 text-sm"
                      value={editText}
                      onChange={(e) => onEditTextChange(e.target.value)}
                    />
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        onClick={() => onSaveEdit(f.id)}
                        disabled={!editText.trim() || isUpdatePending}
                      >
                        {isUpdatePending ? t("common.saving") : t("common.save")}
                      </Button>
                      <Button size="sm" variant="ghost" onClick={onCancelEdit}>
                        {t("common.cancel")}
                      </Button>
                    </div>
                  </div>
                ) : (
                  <div className="mt-1 break-words text-sm">{f.text}</div>
                )}
              </div>
              {editingId === f.id ? null : (
                <div className="flex shrink-0 gap-1">
                  <Button size="sm" variant="ghost" onClick={() => onStartEdit(f)}>
                    {t("common.edit")}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      if (window.confirm(t("memory.detail.deleteConfirm", { name: f.name }))) {
                        onDelete(f.id);
                      }
                    }}
                    disabled={isDeletePending}
                  >
                    {t("common.delete")}
                  </Button>
                </div>
              )}
            </li>
          ))}
          {facts.facts.length === 0 ? (
            <li className="p-3 text-sm text-muted-foreground">{t("memory.detail.empty")}</li>
          ) : null}
        </ul>
      ) : null}
    </section>
  );
}
