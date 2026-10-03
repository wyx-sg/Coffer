// src/components/clis/CliActions.tsx — Edit and ⋯ › Remove for a tool that was added by hand, in its detail header (board CliHeader).
//
// A tool only a skill or MCP server requires has neither: it is not Coffer's to
// change. Remove is the only item in the ⋯ menu, in danger text, and
// asks in a 420 confirm: removing a hand-added tool that a skill also requires
// only drops the declaration, and the dialog says so; the entry stays for as
// long as the skill requires it. The dialog closes only once the removal
// succeeded.
import { Pencil } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ActionMenu } from "@/components/ui/menu";
import type { Cli } from "@/lib/api/clis";
import { useRemoveCli } from "@/lib/hooks/useClis";
import { AddCliDialog } from "./AddCliDialog";

interface Props {
  cli: Cli;
  /** The tool left the list (nothing else requires it). */
  onRemoved: () => void;
}

export function CliActions({ cli, onRemoved }: Props) {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const [removing, setRemoving] = useState(false);
  const remove = useRemoveCli();
  const stays = cli.needed_by.length > 0 || cli.needed_by_servers.length > 0;
  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
        <Pencil aria-hidden />
        {t("common.edit")}
      </Button>
      <ActionMenu
        label={t("clis.menu.label", { command: cli.command })}
        actions={[
          {
            key: "remove",
            label: t("clis.remove.action"),
            onSelect: () => setRemoving(true),
            destructive: true,
          },
        ]}
      />
      <AddCliDialog open={editing} onOpenChange={setEditing} existing={cli} />
      <ConfirmDialog
        open={removing}
        onOpenChange={setRemoving}
        title={t("clis.remove.title", { command: cli.command })}
        description={t(stays ? "clis.remove.bodyStays" : "clis.remove.body", {
          command: cli.command,
        })}
        confirmLabel={t("clis.remove.action")}
        pendingLabel={t("clis.remove.pending")}
        errorTitle={t("clis.remove.failed", { command: cli.command })}
        variant="destructive"
        pending={remove.isPending}
        error={remove.error}
        onConfirm={() =>
          remove.mutate(cli.command, {
            onSuccess: () => {
              setRemoving(false);
              if (!stays) onRemoved();
            },
          })
        }
      />
    </>
  );
}
