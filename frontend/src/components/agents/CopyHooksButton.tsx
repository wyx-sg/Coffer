// src/components/agents/CopyHooksButton.tsx — copies Codex's `/hooks` slash command (boards 2.1.51, 2.1.53).
//
// Codex runs a new or changed hook only after the user approves it in its own
// `/hooks` screen; Coffer never approves it for them. The button hands over
// the command to paste into Codex.
import { useTranslation } from "react-i18next";
import { Check, Copy } from "lucide-react";

import { TableActionButton } from "@/components/table/TableActionButton";
import { useCopyText } from "@/lib/hooks/useCopyText";

const HOOKS_COMMAND = "/hooks";

export function CopyHooksButton() {
  const { t } = useTranslation();
  const { copied, copy } = useCopyText();
  return (
    <TableActionButton
      icon={copied ? Check : Copy}
      label={copied ? t("common.copied") : t("agents.hookApproval.copy")}
      onClick={() => copy(HOOKS_COMMAND)}
    />
  );
}
