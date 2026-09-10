import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { translateApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/types";
import { CredentialRowEditor, type CredRow } from "./CredentialRowEditor";
import { ServerTimeoutFields } from "./ServerTimeoutFields";
import { timeoutsOf, type Timeouts } from "./serverTimeouts";
import {
  configWithoutOwnControls,
  credentialRefsOf,
  saveMcpServerEdit,
} from "./editMcpServerSave";

type ResourceOut = components["schemas"]["ResourceOut"];

interface Props {
  resource: ResourceOut;
}

/**
 * Edit an MCP server: description, the config as JSON, and credentials.
 * Credentials live in their own section because the encrypted credential
 * store holds the values — the config JSON only ever carries references.
 * On save, new / rotated secrets are written to the credential store and
 * any credential the server no longer references (and that this server
 * owns) is deleted.
 */
export function EditMcpServerDialog({ resource }: Props) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [description, setDescription] = useState("");
  const [configText, setConfigText] = useState("");
  const [creds, setCreds] = useState<CredRow[]>([]);
  const [timeouts, setTimeouts] = useState<Timeouts>(() => timeoutsOf(resource.config));

  function reset() {
    setDescription(resource.description ?? "");
    setConfigText(configWithoutOwnControls(resource.config));
    setTimeouts(timeoutsOf(resource.config));
    setCreds(
      Object.entries(credentialRefsOf(resource.config)).map(([name, ref], i) => ({
        id: i,
        name,
        value: "",
        originalRef: ref,
        originalName: name,
      })),
    );
  }

  const save = useMutation({
    mutationFn: () =>
      saveMcpServerEdit({ resource, description, configText, creds, timeouts, t }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["resources"] });
      setOpen(false);
    },
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (next) reset();
        setOpen(next);
      }}
    >
      <DialogTrigger asChild>
        <Button variant="outline" size="sm">
          <Pencil className="mr-1.5 size-3.5" /> {t("mcp.server.edit")}
        </Button>
      </DialogTrigger>
      <DialogContent className="max-h-[85vh] max-w-lg overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t("mcp.edit.title")}</DialogTitle>
          <DialogDescription>{t("mcp.edit.subtitle")}</DialogDescription>
        </DialogHeader>
        {save.error ? (
          <div
            className="rounded-md border border-destructive/40 bg-destructive/5 px-4 py-3 text-sm text-destructive"
            role="alert"
          >
            {translateApiError(t, save.error)}
          </div>
        ) : null}
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="edit-desc">{t("mcp.edit.description")}</Label>
            <Input
              id="edit-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={t("mcp.edit.descriptionPlaceholder")}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="edit-config">{t("mcp.edit.config")}</Label>
            <textarea
              id="edit-config"
              value={configText}
              onChange={(e) => setConfigText(e.target.value)}
              className="h-56 w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs"
            />
            <p className="text-xs text-muted-foreground">{t("mcp.edit.configHint")}</p>
          </div>

          <ServerTimeoutFields value={timeouts} onChange={setTimeouts} idPrefix="edit-timeout" />

          <CredentialRowEditor
            creds={creds}
            onUpdate={(idx, patch) =>
              setCreds((c) => c.map((r, i) => (i === idx ? { ...r, ...patch } : r)))
            }
            onRemove={(idx) => setCreds((c) => c.filter((_, i) => i !== idx))}
            onAdd={() =>
              setCreds((c) => [
                ...c,
                { id: Date.now(), name: "", value: "", originalRef: null, originalName: null },
              ])
            }
          />

          <div className="flex justify-end gap-2 pt-1">
            <Button variant="ghost" onClick={() => setOpen(false)} disabled={save.isPending}>
              {t("common.cancel")}
            </Button>
            <Button onClick={() => save.mutate()} disabled={save.isPending}>
              {save.isPending ? t("common.saving") : t("common.save")}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
