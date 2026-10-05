// frontend/src/components/agents/UnmanagedSkillOverview.tsx — spec skill-manager
// "Preview an unmanaged skill read-only".
// The Overview tab of an unmanaged skill's detail page (board 2.1.57): one
// quiet line saying Coffer reads the folder but does not manage it, then
// property rows — description, folder, where it was found, and its file count
// with a link to the Files tab (the tree lives there, not in a paragraph).
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { abbreviateHomePath } from "@/lib/agents/display";
import type { UnmanagedSkillDetailOut } from "@/lib/api/agents-workspace";

function PropertyRow({
  label,
  mono,
  children,
}: {
  label: string;
  mono?: boolean;
  children: ReactNode;
}) {
  return (
    <div className="grid min-h-[39px] grid-cols-[156px_minmax(0,1fr)] items-center gap-4 border-t border-border-subtle py-2 first:border-t-0">
      <dt className="text-xs text-text-muted">{label}</dt>
      <dd
        className={mono ? "break-all font-mono text-xs text-text" : "break-words text-sm text-text"}
      >
        {children}
      </dd>
    </div>
  );
}

export function UnmanagedSkillOverview({
  skill,
  agentName,
  fileCount,
  onShowFiles,
}: {
  skill: UnmanagedSkillDetailOut;
  agentName: string;
  /** How many files the folder holds; 0 until the listing has loaded. */
  fileCount: number;
  /** Switch to the Files tab. */
  onShowFiles: () => void;
}) {
  const { t } = useTranslation();
  return (
    <>
      <p className="mb-3 text-xs text-text-muted">
        {t("agents.skillsTab.unmanagedDetail.readOnlyHint")}
      </p>
      <dl className="max-w-[760px]">
        {skill.description ? (
          <PropertyRow label={t("agents.skillsTab.unmanagedDetail.description")}>
            {skill.description}
          </PropertyRow>
        ) : null}
        <PropertyRow label={t("agents.skillsTab.unmanagedDetail.folder")} mono>
          {abbreviateHomePath(skill.path)}
        </PropertyRow>
        <PropertyRow label={t("agents.skillsTab.unmanagedDetail.foundIn")}>
          {skill.location === "agents_dir"
            ? t("agents.skillsTab.unmanagedDetail.foundInAgentsDir")
            : t("agents.skillsTab.unmanagedDetail.foundInSkills", { agent: agentName })}
        </PropertyRow>
        {fileCount > 0 ? (
          <PropertyRow label={t("agents.skillsTab.unmanagedDetail.filesLabel")}>
            <span>{t("agents.skillsTab.unmanagedDetail.files", { count: fileCount })}</span>
            <Button variant="link" size="sm" className="ml-2 h-auto p-0" onClick={onShowFiles}>
              {t("agents.skillsTab.unmanagedDetail.viewFiles")}
            </Button>
          </PropertyRow>
        ) : null}
      </dl>
    </>
  );
}
