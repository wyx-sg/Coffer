// src/components/secret/ApprovalsOffNote.tsx — the one line that says secret approvals are off
// because of the build, not because anyone turned them off (spec secret "Default the approval
// protection by the build"). An unsigned build cannot protect its master key, so approvals default
// off there; the reason is one hover away in the help tip.
//
// Shown only while the requirement is off AND the build defaults it off: a signed build where a
// person turned it off already says so on Overview, and where it is on there is nothing to say.
import { useTranslation } from "react-i18next";

import { HelpTip } from "@/components/HelpTip";
import { useSecretBoundarySettings } from "@/lib/hooks/useApprovals";

export function ApprovalsOffNote() {
  const { t } = useTranslation();
  const { data } = useSecretBoundarySettings();
  if (!data || data.require_approval || data.default_on) return null;
  return (
    <p
      data-testid="approvals-off-by-build"
      className="flex items-center gap-1.5 text-xs text-text-muted"
    >
      {t("secrets.approvalsOffByBuild.line")}
      <HelpTip>{t("secrets.approvalsOffByBuild.help")}</HelpTip>
    </p>
  );
}
