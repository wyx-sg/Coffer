// src/components/agents/list/AgentConfigDirDialog.tsx — spec agent-registry "Offer a folder picker for a custom config directory".
//
// Reached from a row's menu, Use a different config directory…: the default
// directory is found on its own, so another one is the exception. The folder
// comes from the native dialog (the in-app browser only on a host without
// one), then the daemon validates it — an added agent's directory moves
// (PATCH), a not-added one is registered there without connecting. The
// daemon's refusal (already registered, not a valid directory) shows inline.
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Loader2 } from "lucide-react";

import { FolderPickerField } from "@/components/FolderPickerField";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { connectionFiles } from "@/lib/agents/connectionPlan";
import { abbreviateHomePath, agentTypeLabel } from "@/lib/agents/display";
import type { AgentTypeOut, CofferConnection } from "@/lib/api/agents";
import { translateApiError } from "@/lib/api/errors";
import { useAgentConnection, usePatchAgent, useRegisterAgent } from "@/lib/hooks/useAgents";
import { AgentConfigDirReview } from "./AgentConfigDirReview";
import { keptEntries, useFolderListing } from "./useFolderListing";

interface Props {
  row: AgentTypeOut;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const LABEL = "text-2xs font-semibold uppercase tracking-[.04em] text-text-subtle";

function FoundThere({ row, path }: { row: AgentTypeOut; path: string }) {
  const { t } = useTranslation();
  const listing = useFolderListing(path);
  if (listing.isPending) {
    return <Loader2 className="size-4 animate-spin text-text-subtle" aria-hidden />;
  }
  if (listing.missing) {
    return <p className="text-xs text-warning">{t("agents.configDirDialog.notAFolder")}</p>;
  }
  const mcpFile = abbreviateHomePath(connectionFiles({ ...row, config_dir: path }).mcp);
  return (
    <ul className="divide-y divide-border-subtle rounded-md border border-border-subtle">
      {keptEntries(row.type).map((entry) => {
        const found = entry.folder ? listing.folders.has(entry.name) : undefined;
        const role =
          entry.name === ".claude.json"
            ? t("agents.configDirDialog.role.mcpAt", { path: mcpFile })
            : entry.folder && found && listing.skillFolders !== undefined
              ? t("agents.configDirDialog.skillFolders", { count: listing.skillFolders })
              : t(entry.role);
        return (
          <li
            key={entry.name}
            className="grid grid-cols-[140px_minmax(0,1fr)_auto] items-center gap-3 px-3 py-2"
          >
            <span className="font-mono text-xs text-text">
              {entry.folder ? `${entry.name}/` : entry.name}
            </span>
            <span className="break-all text-xs text-text-muted">{role}</span>
            <span className="text-xs text-text-subtle">
              {found === undefined
                ? t("agents.configDirDialog.fileUnchecked")
                : found
                  ? t("agents.configDirDialog.found")
                  : t("agents.configDirDialog.notHere")}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

export function AgentConfigDirDialog({ row, open, onOpenChange }: Props) {
  const { t } = useTranslation();
  const patch = usePatchAgent();
  const register = useRegisterAgent();
  const [path, setPath] = useState<string | null>(row.config_dir);
  // The review of a move; it keeps the parts Coffer had written when it opened,
  // because the connection read changes under the steps it runs.
  const [reviewing, setReviewing] = useState<{
    parts: CofferConnection["parts"];
    dir: string;
  } | null>(null);
  const connection = useAgentConnection(row.uid ?? "").data;
  // Coffer's lines are in the agent's folder: moving it is a change to review.
  const parts = connection?.parts ?? [];
  const carriesCoffer = !!row.uid && parts.some((p) => p.installed);
  const mutation = row.uid ? patch : register;

  const { reset: resetPatch } = patch;
  const { reset: resetRegister } = register;
  useEffect(() => {
    if (!open) return;
    setPath(row.config_dir);
    resetPatch();
    resetRegister();
  }, [open, row.config_dir, resetPatch, resetRegister]);

  // A fresh opening starts at the form, not in the review.
  useEffect(() => {
    if (open) setReviewing(null);
  }, [open]);

  const chosen = path?.trim() || null;
  const apply = async () => {
    if (!chosen) return;
    try {
      if (row.uid) await patch.mutateAsync({ uid: row.uid, body: { config_dir: chosen } });
      else await register.mutateAsync({ type: row.type, config_dir: chosen });
      onOpenChange(false);
    } catch {
      // Shown inline from the mutation's error.
    }
  };

  return (
    <>
      <Dialog
        open={open && !reviewing}
        onOpenChange={(next) => !mutation.isPending && onOpenChange(next)}
      >
        <DialogContent className="max-w-[480px]">
          <DialogHeader>
            <DialogTitle>{t("agents.configDirDialog.title")}</DialogTitle>
            <DialogDescription>
              {t("agents.configDirDialog.subtitle", {
                name: agentTypeLabel(row.type),
                standard: abbreviateHomePath(row.standard_config_dir),
              })}
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="agent-config-dir" className="text-xs font-label text-text">
                {t("agents.configDirDialog.field")}
              </label>
              <FolderPickerField
                inputId="agent-config-dir"
                value={path}
                onChange={setPath}
                typeable
              />
              <p className="text-xs text-text-muted">{t("agents.configDirDialog.hint")}</p>
            </div>
            {chosen ? (
              <div className="flex flex-col gap-2">
                <span className={LABEL}>{t("agents.configDirDialog.foundThere")}</span>
                <FoundThere row={row} path={chosen} />
              </div>
            ) : null}
            {mutation.error ? (
              <p role="alert" className="text-xs text-danger">
                {translateApiError(t, mutation.error)}
              </p>
            ) : null}
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => onOpenChange(false)}>
              {t("common.cancel")}
            </Button>
            <Button
              onClick={() =>
                carriesCoffer && chosen ? setReviewing({ parts, dir: chosen }) : void apply()
              }
              disabled={!chosen || chosen === row.config_dir || mutation.isPending}
            >
              {t(carriesCoffer ? "agents.configDirDialog.review" : "agents.configDirDialog.apply")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      {reviewing && row.uid ? (
        <AgentConfigDirReview
          row={row}
          uid={row.uid}
          parts={reviewing.parts}
          newDir={reviewing.dir}
          open={open}
          onOpenChange={(next) => {
            if (!next) {
              setReviewing(null);
              onOpenChange(false);
            }
          }}
        />
      ) : null}
    </>
  );
}
