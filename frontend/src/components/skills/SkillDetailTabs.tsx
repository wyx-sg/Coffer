// frontend/src/components/skills/SkillDetailTabs.tsx
// Overview tab body for SkillDetailPage (extracted to keep the page file under
// the size limit). Overview is a read-only metadata view, opening with the
// skill's description — long-form copy belongs here, not in the page header.
// Per-agent skill binding lives on the agent page, not here.
import { useTranslation } from "react-i18next";

import { Card, CardContent } from "@/components/ui/card";
import type { SkillOut } from "@/lib/api/skills";
import { formatDateTime } from "@/lib/utils";

export function SkillOverview({ skill }: { skill: SkillOut }) {
  const { t } = useTranslation();
  return (
    <Card>
      <CardContent className="space-y-4 py-6">
        {skill.description ? (
          <p className="max-w-prose text-sm text-muted-foreground">{skill.description}</p>
        ) : null}
        <dl className="grid gap-y-3 text-sm sm:grid-cols-[12rem_1fr]">
          <dt className="text-muted-foreground">{t("skills.source")}</dt>
          <dd className="font-mono text-xs">{skill.source.original_path}</dd>

          <dt className="text-muted-foreground">{t("skills.detail.versionHash")}</dt>
          <dd className="font-mono text-xs">{skill.version_hash.slice(0, 12)}</dd>

          <dt className="text-muted-foreground">{t("skills.detail.masterPath")}</dt>
          <dd className="font-mono text-xs">{skill.master_path}</dd>

          <dt className="text-muted-foreground">{t("skills.detail.lastSynced")}</dt>
          <dd>
            {skill.last_synced_from_source_at
              ? formatDateTime(skill.last_synced_from_source_at)
              : "—"}
          </dd>

          <dt className="text-muted-foreground">{t("skills.detail.created")}</dt>
          <dd>{formatDateTime(skill.created_at)}</dd>

          <dt className="text-muted-foreground">{t("skills.detail.updated")}</dt>
          <dd>{formatDateTime(skill.updated_at)}</dd>
        </dl>
      </CardContent>
    </Card>
  );
}
