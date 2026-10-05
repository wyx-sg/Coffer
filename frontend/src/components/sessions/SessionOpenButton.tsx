// src/components/sessions/SessionOpenButton.tsx — a session row's split button
// (spec chat "Open a conversation in the terminal"): the main part opens the
// session in the preferred terminal, named on it ("Open in iTerm"); the ▾ menu
// holds Open in <other terminal> for each other terminal on this machine, then
// Copy command — the same shape as Hand off to <Agent>. A row with no session
// yet shows it disabled, with the reason in a tooltip, and no menu.
import { useTranslation } from "react-i18next";
import { Copy, SquareTerminal } from "lucide-react";

import type { MenuAction } from "@/components/ui/menu";
import { SplitButton } from "@/components/ui/split-button";
import type { TerminalChoice } from "@/lib/hooks/useTerminals";
import type { SessionRowData } from "@/lib/sessions/rows";

interface Props {
  row: SessionRowData;
  openable: boolean;
  /** The preferred terminal's name; without it the button reads "Open in terminal". */
  terminalLabel?: string;
  otherTerminals: readonly TerminalChoice[];
  /** Opens the row — in `terminal` when one is picked from the menu. */
  onOpen: (row: SessionRowData, terminal?: string) => void;
  onCopyCommand?: (row: SessionRowData) => void;
}

export function SessionOpenButton({
  row,
  openable,
  terminalLabel,
  otherTerminals,
  onOpen,
  onCopyCommand,
}: Props) {
  const { t } = useTranslation();
  const actions: MenuAction[] = otherTerminals.map((other) => ({
    key: `terminal:${other.value}`,
    label: t("sessions.row.openIn", { terminal: other.label }),
    icon: SquareTerminal,
    onSelect: () => onOpen(row, other.value),
  }));
  if (onCopyCommand) {
    actions.push({
      key: "copy-command",
      label: t("sessions.row.copyCommand"),
      icon: Copy,
      separated: actions.length > 0,
      onSelect: () => onCopyCommand(row),
    });
  }
  return (
    <SplitButton
      size="sm"
      icon={<SquareTerminal aria-hidden />}
      label={
        terminalLabel
          ? t("sessions.row.openIn", { terminal: terminalLabel })
          : t("sessions.row.open")
      }
      disabled={!openable}
      tooltip={openable ? undefined : t("sessions.row.noSession")}
      onClick={() => onOpen(row)}
      menuLabel={t("sessions.row.openOptions", { title: row.title })}
      actions={openable ? actions : []}
    />
  );
}
