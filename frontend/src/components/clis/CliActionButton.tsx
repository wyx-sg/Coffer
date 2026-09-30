// src/components/clis/CliActionButton.tsx — the one action a CLI row offers for its problem.
//
// Install… for a missing command and Update… for an outdated one — both only
// when a Homebrew formula is declared, and both only open the confirmation
// (`onInstall`); nothing runs from here. Copy login command for one that is
// not logged in. A ready command, or a problem Coffer cannot act on, offers
// nothing. `table` renders it as a TableActionButton (the list), otherwise as
// a plain outline button (a detail page, a skill's Requires tab).
import { Check, Copy, Download } from "lucide-react";
import { useTranslation } from "react-i18next";

import { TableActionButton } from "@/components/table/TableActionButton";
import { Button } from "@/components/ui/button";
import type { Cli } from "@/lib/api/clis";
import { isInstallable } from "@/lib/clis/format";
import { useCopyText } from "@/lib/hooks/useCopyText";

interface Props {
  cli: Cli;
  onInstall: (cli: Cli) => void;
  table?: boolean;
  /** The copy button's label; defaults to "Copy login command". */
  copyLabel?: string;
}

export function CliActionButton({ cli, onInstall, table = false, copyLabel }: Props) {
  const { t } = useTranslation();
  const { copied, copy } = useCopyText();

  let icon = Download;
  let label: string;
  let onClick: () => void;
  if (isInstallable(cli)) {
    label = t(cli.status === "missing" ? "clis.actions.install" : "clis.actions.update");
    onClick = () => onInstall(cli);
  } else if (cli.status === "logged_out" && cli.login.command) {
    const command = cli.login.command;
    icon = copied ? Check : Copy;
    label = copied ? t("clis.actions.copied") : (copyLabel ?? t("clis.actions.copyLogin"));
    onClick = () => copy(command);
  } else {
    return null;
  }

  if (table) return <TableActionButton icon={icon} label={label} onClick={onClick} />;
  const Icon = icon;
  return (
    <Button type="button" variant="outline" size="sm" onClick={onClick}>
      <Icon aria-hidden />
      {label}
    </Button>
  );
}
