// frontend/src/components/skills/SkillFirstRun.tsx
// The Skills page's reading pane while the library holds nothing of the
// user's own — no skill at all, or only Coffer's built-in guide. One button per
// source the Add skill dialog offers, each opening it on that source, and a
// pointer to where the agents' own (unmanaged) skills live: each agent's
// Skills tab. It lists nothing from there.
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Archive, Folder, GitBranch, Sparkles } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import type { SkillAddSource } from "@/components/skills/SkillAddDialog";
import { Button } from "@/components/ui/button";

interface Props {
  /** True when the built-in guide is already there, so the copy says "so far". */
  hasBuiltin: boolean;
  onAdd: (source: SkillAddSource) => void;
}

export function SkillFirstRun({ hasBuiltin, onAdd }: Props) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col items-center gap-4">
      <EmptyState
        icon={Sparkles}
        title={hasBuiltin ? t("skills.firstRun.titleBuiltinOnly") : t("skills.firstRun.title")}
        description={t("skills.firstRun.body")}
        action={
          <div className="flex flex-wrap items-center justify-center gap-2">
            <Button onClick={() => onAdd("folder")}>
              <Folder aria-hidden /> {t("skills.firstRun.fromFolder")}
            </Button>
            <Button variant="outline" onClick={() => onAdd("archive")}>
              <Archive aria-hidden /> {t("skills.firstRun.fromArchive")}
            </Button>
            <Button variant="outline" onClick={() => onAdd("git")}>
              <GitBranch aria-hidden /> {t("skills.firstRun.fromGit")}
            </Button>
          </div>
        }
      />
      <p className="flex flex-wrap items-center justify-center gap-2 text-xs text-text-muted">
        {t("skills.firstRun.agentsHint")}
        <Link to="/agents" className="font-label text-accent-text hover:underline">
          {t("skills.firstRun.openAgents")}
        </Link>
      </p>
    </div>
  );
}
