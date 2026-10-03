// frontend/src/components/skills/SkillBulkDelete.tsx
// Delete every selected skill behind one confirmation (420 wide) — the
// selection bar's Delete. One call (POST /skills/bulk-delete) answers per
// skill, so a refused delete never stops the others. When some were refused
// (an agent's copy that is no longer Coffer's link, canvas 4.3.39) the dialog
// stays open on an error block — "Deleted 1 of 2", who was deleted, which
// folder blocked the rest — and the primary button becomes "Delete pdf, keep
// Codex's folder", which sends only the refused ones again leaving those
// folders alone. All deleted is a toast and the selection clears.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Trash2 } from "lucide-react";

import { NotOursNotice } from "@/components/skills/SkillNotOursNotice";
import { Button } from "@/components/ui/button";
import { ConfirmDialog, DialogErrorBanner } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast";
import type { SkillBulkDeleteResult, SkillOut } from "@/lib/api/skills";
import { useAgents } from "@/lib/hooks/useAgents";
import { useBulkDeleteSkills } from "@/lib/hooks/useSkills";
import { joinNames } from "@/lib/skills/names";
import { notOursDetails } from "@/lib/skills/notOurs";

interface Props {
  skills: SkillOut[];
  onDone: () => void;
  /** The trigger's label ("Delete" in the bar). */
  label: string;
}

/** What is left after an attempt: the names that went, and the results that did not. */
interface Outcome {
  total: number;
  deleted: string[];
  failed: SkillBulkDeleteResult[];
}

const NOT_OURS = "SKILL_COPY_NOT_OURS";

export function SkillBulkDelete({ skills, onDone, label }: Props) {
  const { t, i18n } = useTranslation();
  const { toast } = useToast();
  const { data: agents = [] } = useAgents();
  const [open, setOpen] = useState(false);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const bulk = useBulkDeleteSkills();
  const agentLabel = (name: string) => agents.find((a) => a.name === name)?.display_name ?? name;

  const refused = outcome?.failed.filter((f) => f.error_code === NOT_OURS) ?? [];
  const others = outcome?.failed.filter((f) => f.error_code !== NOT_OURS) ?? [];
  const first = refused[0] ? notOursDetails(refused[0].error_details) : null;
  const firstAgent = first ? agentLabel(first.agentName) : "";

  const close = (next: boolean) => {
    setOpen(next);
    if (!next) {
      setOutcome(null);
      bulk.reset();
    }
  };

  const run = async () => {
    // After a partial result only the refused ones go again, keeping the
    // folders that are not Coffer's; a first press sends everything.
    const todo = outcome ? outcome.failed.map((f) => f.uid) : skills.map((s) => s.uid);
    const keep = outcome !== null && others.length === 0;
    const out = await bulk.mutateAsync({ uids: todo, keepForeignCopies: keep });
    const failed = out.results.filter((r) => !r.deleted);
    const deleted = [
      ...(outcome?.deleted ?? []),
      ...out.results.filter((r) => r.deleted).map((r) => r.name),
    ];
    if (failed.length === 0) {
      toast.success(t("skills.bulk.done", { count: deleted.length }));
      close(false);
      onDone();
      return;
    }
    setOutcome({ total: outcome?.total ?? skills.length, deleted, failed });
  };

  const total = outcome?.total ?? skills.length;
  const confirmLabel = !outcome
    ? t("skills.bulk.deleteConfirm", { count: skills.length })
    : others.length > 0
      ? t("common.tryAgain")
      : refused.length === 1
        ? t("skills.bulk.keepOne", { name: refused[0]?.name, agent: firstAgent })
        : t("skills.bulk.keepMany", { count: refused.length });

  return (
    <>
      <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
        <Trash2 aria-hidden /> {label}
      </Button>
      <ConfirmDialog
        open={open}
        onOpenChange={close}
        title={t("skills.bulk.deleteTitle", { count: total })}
        description={t("skills.bulk.deleteBody", {
          names: joinNames(
            outcome
              ? [...outcome.deleted, ...outcome.failed.map((f) => f.name)]
              : skills.map((s) => s.name),
            i18n.language,
          ),
        })}
        confirmLabel={confirmLabel}
        pendingLabel={t("common.deleting")}
        errorTitle={t("common.couldntDeleteSelected")}
        pending={bulk.isPending}
        error={bulk.error ?? undefined}
        // Not returned: the dialog stays open on a partial result (see run).
        onConfirm={() => void run().catch(() => undefined)}
      >
        {outcome && refused.length > 0 && first ? (
          <NotOursNotice
            title={t("skills.bulk.partialTitle", {
              ok: outcome.deleted.length,
              total: outcome.total,
            })}
            lead={
              outcome.deleted.length > 0
                ? t("skills.bulk.partialLead", {
                    count: outcome.deleted.length,
                    deleted: joinNames(outcome.deleted, i18n.language),
                    name: refused[0]?.name,
                  })
                : undefined
            }
            path={first.path}
            tail={t("skills.bulk.partialTail", {
              name: refused[0]?.name,
              agent: firstAgent,
              count: refused.length,
            })}
          />
        ) : null}
        {others.map((f) => (
          <DialogErrorBanner
            key={f.uid}
            title={t("common.couldntDelete", { name: f.name })}
            message={f.error_message ?? ""}
          />
        ))}
      </ConfirmDialog>
    </>
  );
}
