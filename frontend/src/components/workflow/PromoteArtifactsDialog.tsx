// frontend/src/components/workflow/PromoteArtifactsDialog.tsx
// Keep what a run produced: copy its files into a knowledge collection
// (FR-043), so one delivery's output becomes the next delivery's input.
//
// Two ways, because both are real: a delivery that stands on its own gets a
// NEW collection, and one of a series — the third service migrated the same
// way — is ADDED to the collection the others are in. The old dialog had a
// bare text box that did both depending on whether what you typed happened to
// exist already, which is the kind of field that creates a near-duplicate
// collection out of a typo.
//
// It is a COPY. The run's own directory is left exactly as it was, and the
// dialog says so rather than leaving the developer to guess whether saving
// moves the files out from under a run that may still be going.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Combobox } from "@/components/ui/combobox";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useKnowledgeCollections } from "@/lib/hooks/useKnowledge";
import { usePromoteArtifacts } from "@/lib/hooks/useWorkflowRun";
import { cn } from "@/lib/utils";

type Mode = "new" | "existing";

interface Props {
  runId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function PromoteArtifactsDialog({ runId, open, onOpenChange }: Props) {
  const { t } = useTranslation();
  const promote = usePromoteArtifacts(runId);
  const collections = useKnowledgeCollections();
  const [mode, setMode] = useState<Mode>("new");
  const [created, setCreated] = useState("");
  const [existing, setExisting] = useState<string | null>(null);

  const known = collections.data ?? [];
  const collection = mode === "new" ? created.trim() : (existing ?? "");

  const reset = () => {
    setMode("new");
    setCreated("");
    setExisting(null);
  };

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={(next) => {
        if (!next) reset();
        onOpenChange(next);
      }}
      title={t("workflow.artifacts.promoteTitle")}
      description={t("workflow.artifacts.promoteDescription")}
      confirmLabel={t("workflow.artifacts.promote")}
      variant="default"
      pending={promote.isPending || collection.length === 0}
      onConfirm={() => promote.mutateAsync(collection)}
    >
      <div className="space-y-3">
        <div className="flex gap-2" role="radiogroup" aria-label={t("workflow.artifacts.whereTo")}>
          {(["new", "existing"] as const).map((option) => (
            <button
              key={option}
              type="button"
              role="radio"
              aria-checked={mode === option}
              // Nothing to add to is not a choice — it is the reason the other
              // one is the only one.
              disabled={option === "existing" && known.length === 0}
              onClick={() => setMode(option)}
              className={cn(
                "flex-1 rounded-md border px-3 py-2 text-sm transition-colors disabled:cursor-not-allowed disabled:opacity-50",
                mode === option
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-border hover:bg-secondary",
              )}
            >
              {t(`workflow.artifacts.mode.${option}`)}
            </button>
          ))}
        </div>

        {mode === "new" ? (
          <div className="space-y-2">
            <Label htmlFor="promote-collection">{t("workflow.artifacts.newLabel")}</Label>
            <Input
              id="promote-collection"
              value={created}
              onChange={(e) => setCreated(e.target.value)}
              placeholder={t("workflow.artifacts.newPlaceholder")}
            />
          </div>
        ) : (
          <div className="space-y-2">
            <Label htmlFor="promote-existing">{t("workflow.artifacts.existingLabel")}</Label>
            <Combobox
              id="promote-existing"
              value={existing}
              options={known.map((c) => ({
                value: c.name,
                label: c.name,
                hint: c.description || undefined,
              }))}
              onChange={setExisting}
              placeholder={t("workflow.artifacts.existingPlaceholder")}
              emptyMessage={t("workflow.inputs.noCollectionMatches")}
            />
            <p className="text-xs text-muted-foreground">{t("workflow.artifacts.existingHint")}</p>
          </div>
        )}
      </div>
    </ConfirmDialog>
  );
}
