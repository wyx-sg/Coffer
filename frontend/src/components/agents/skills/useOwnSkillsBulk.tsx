// src/components/agents/skills/useOwnSkillsBulk.tsx — bulk Adopt and Delete over the agent's own skill folders.
//
// Spec agent-registry "Act on several of an agent's own items at once". The bar
// offers Adopt (unmanaged folders only: an invalid folder, a foreign link or a
// duplicate cannot be adopted, and the dialog says how many are skipped) and
// Delete… (every ticked folder). Each is the single-folder request, sent one
// after another; a name Coffer already has fails that folder alone.
import { useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Trash2 } from "lucide-react";

import { BulkFailures } from "@/components/agents/bulk/BulkFailures";
import { useBulkDialog } from "@/components/agents/bulk/useBulkDialog";
import type { OwnSkillRow } from "@/components/agents/skills/skillRows";
import { ReachControl } from "@/components/reach/ReachControl";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useToast } from "@/components/ui/toast";
import { agentsApi } from "@/lib/api/agents";
import { agentKey, agentUnmanagedSkillsKey, skillsKey } from "@/lib/api/queryKeys";
import { joinNames } from "@/lib/skills/names";
import { EVERY_AGENT, toWire, type SkillReachDraft } from "@/lib/skills/reach";

type Kind = "adopt" | "delete";

export function useOwnSkillsBulk(agentUid: string) {
  const { t, i18n } = useTranslation();
  const { toast } = useToast();
  const invalidate = useMemo(
    () => [agentUnmanagedSkillsKey(agentUid), skillsKey, agentKey(agentUid)],
    [agentUid],
  );
  const dialog = useBulkDialog<OwnSkillRow>(invalidate);
  const [kind, setKind] = useState<Kind>("adopt");
  const [skipped, setSkipped] = useState(0);
  const [reach, setReach] = useState<SkillReachDraft>(EVERY_AGENT);

  const open = (next: Kind, rows: OwnSkillRow[], clear: () => void) => {
    const applicable = next === "adopt" ? rows.filter((r) => r.state === "unmanaged") : rows;
    setKind(next);
    setSkipped(rows.length - applicable.length);
    setReach(EVERY_AGENT);
    dialog.start(applicable, clear);
  };

  const actions = (rows: OwnSkillRow[], clear: () => void): ReactNode => {
    const adoptable = rows.filter((r) => r.state === "unmanaged").length;
    return (
      <>
        <Button
          variant="outline"
          size="sm"
          disabled={adoptable === 0}
          title={adoptable === 0 ? t("agents.skillsTab.bulk.adoptDisabled") : undefined}
          onClick={() => open("adopt", rows, clear)}
        >
          {t("agents.skillsTab.adopt")}
        </Button>
        <Button variant="outline" size="sm" onClick={() => open("delete", rows, clear)}>
          <Trash2 aria-hidden /> {t("agents.skillsTab.bulk.delete")}
        </Button>
      </>
    );
  };

  const items = dialog.items ?? [];
  const total = items.length;
  const failed = dialog.failures.length;
  const targets = failed > 0 ? failed : total;
  const names = joinNames(
    items.map((r) => r.name),
    i18n.language,
  );
  const adopt = kind === "adopt";

  const confirm = () =>
    void dialog.confirm(
      (row) =>
        adopt
          ? agentsApi.adoptUnmanagedSkill(agentUid, row.name, row.item.location, {
              reach: toWire(reach),
            })
          : agentsApi.deleteUnmanagedSkill(agentUid, row.name, row.item.location),
      (count) =>
        toast.success(
          t(adopt ? "agents.skillsTab.bulk.adopted" : "agents.skillsTab.bulk.deleted", { count }),
        ),
    );

  const dialogs = (
    <ConfirmDialog
      open={dialog.items !== null}
      onOpenChange={(next) => {
        if (!next) dialog.close();
      }}
      title={t(adopt ? "agents.skillsTab.bulk.adoptTitle" : "agents.skillsTab.bulk.deleteTitle", {
        count: total,
      })}
      description={
        adopt
          ? t("agents.skillsTab.bulk.adoptBody", { count: total, names })
          : t("agents.skillsTab.bulk.deleteBody", { count: total, names })
      }
      variant={adopt ? "default" : "destructive"}
      confirmLabel={
        failed > 0
          ? t("agents.skillsTab.bulk.retry", { count: targets })
          : t(
              adopt ? "agents.skillsTab.bulk.adoptConfirm" : "agents.skillsTab.bulk.deleteConfirm",
              {
                count: total,
              },
            )
      }
      pendingLabel={t(adopt ? "agents.skillsTab.bulk.adopting" : "common.deleting")}
      pending={dialog.isPending}
      onConfirm={confirm}
    >
      {skipped > 0 ? (
        <p className="text-xs text-text-muted">
          {t("agents.skillsTab.bulk.skipped", { count: skipped })}
        </p>
      ) : null}
      {adopt && failed === 0 ? (
        <div className="flex flex-col gap-1.5">
          <span className="text-sm font-label text-text">
            {t("agents.skillsTab.adoptDialog.reach")}
          </span>
          <div>
            <ReachControl
              mode={reach.mode}
              initialScope={reach.scope}
              ariaLabel={t("agents.skillsTab.adoptDialog.reach")}
              testId="bulk-adopt-skill-reach"
              onDisabled={() => setReach({ mode: "disabled", scope: reach.scope })}
              onEverywhere={() => setReach(EVERY_AGENT)}
              onRestricted={(scope) => setReach({ mode: "restricted", scope })}
            />
          </div>
          <p className="text-xs text-text-muted">{t("agents.skillsTab.bulk.reachHint")}</p>
        </div>
      ) : null}
      {failed > 0 ? (
        <BulkFailures
          title={t(
            adopt ? "agents.skillsTab.bulk.adoptPartial" : "agents.skillsTab.bulk.deletePartial",
            {
              ok: total - failed,
              total,
            },
          )}
          failures={dialog.failures}
          nameOf={(row) => row.name}
        />
      ) : null}
    </ConfirmDialog>
  );

  return { actions, dialogs };
}
