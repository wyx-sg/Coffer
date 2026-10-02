// src/components/clis/CliActions.tsx — Edit and Remove for a tool that was added by hand, in its detail header.
//
// A tool only a skill or MCP server requires has neither: it is not Coffer's to
// change. Removing a hand-added tool that a skill also requires only drops the
// declaration, and the dialog says so; the entry stays for as long as the skill
// requires it. The dialog closes only once the removal succeeded.
import { Pencil, Trash2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
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
      <Button variant="outline" onClick={() => setEditing(true)}>
        <Pencil aria-hidden />
        {t("common.edit")}
      </Button>
      <Button variant="outline" onClick={() => setRemoving(true)}>
        <Trash2 aria-hidden />
        {t("clis.remove.action")}
      </Button>
      <AddCliDialog open={editing} onOpenChange={setEditing} existing={cli} />
      <ConfirmDialog
        open={removing}
        onOpenChange={setRemoving}
        title={t("clis.remove.title", { command: cli.command })}
        description={t(stays ? "clis.remove.bodyStays" : "clis.remove.body")}
        confirmLabel={t("clis.remove.action")}
        pendingLabel={t("clis.remove.pending")}
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
