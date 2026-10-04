// src/components/clis/CliPane.tsx — the CLIs page's detail pane: one command-line tool, on one page.
//
// Spec web-ui "Show every CLI a skill requires on the CLIs page". The header
// names the command (CliHeader), the problem banner carries the fix (Check
// again, then the hand-off to an agent), then "On this machine" and "Needed
// by", stacked — no tab strip. A command not in the list (a deep link the list
// has not caught up with) is read on its own.
import { Terminal } from "lucide-react";
import { useTranslation } from "react-i18next";

import { DetailNotFound } from "@/components/DetailNotFound";
import { EmptyState } from "@/components/EmptyState";
import { PageFallback } from "@/components/PageFallback";
import type { Cli } from "@/lib/api/clis";
import { ApiError, translateApiError } from "@/lib/api/errors";
import { useCli } from "@/lib/hooks/useClis";
import { CliHeader } from "./CliHeader";
import { CliMachineSection } from "./CliMachineSection";
import { CliNeededBySection } from "./CliNeededBySection";
import { CliProblemBanner } from "./CliProblemBanner";

interface Props {
  command: string;
  /** The command's row from the list, when the list has it. */
  listed: Cli | undefined;
  /** A tool added by hand was removed and nothing else requires it. */
  onRemoved: () => void;
}

export function CliPane({ command, listed, onRemoved }: Props) {
  const { t } = useTranslation();
  const lookup = useCli(listed ? "" : command);
  const cli = listed ?? lookup.data;

  if (cli) {
    return (
      <div className="space-y-[18px]">
        <CliHeader cli={cli} onRemoved={onRemoved} />
        <CliProblemBanner cli={cli} />
        <div className="space-y-3.5">
          <CliMachineSection cli={cli} />
          <CliNeededBySection cli={cli} />
        </div>
      </div>
    );
  }
  if (lookup.isPending) return <PageFallback />;
  // A command the daemon does not know is gone; any other failure keeps its own message.
  if (lookup.error instanceof ApiError && lookup.error.code.endsWith("NOT_FOUND")) {
    return <DetailNotFound kind="clis" id={command} backTo="/clis" icon={Terminal} />;
  }
  return (
    <EmptyState
      icon={Terminal}
      tone="error"
      title={t("clis.detail.notFound")}
      description={lookup.error ? translateApiError(t, lookup.error) : undefined}
    />
  );
}
