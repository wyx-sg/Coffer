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
import { getApiClient } from "@/lib/api/client";
import { translateApiError, throwApiError } from "@/lib/api/errors";
import type { components } from "@/lib/api/types";
import { CredentialRowEditor, type CredRow } from "./CredentialRowEditor";

type ResourceOut = components["schemas"]["ResourceOut"];

function credentialRefsOf(config: unknown): Record<string, string> {
  const transport = (config as Record<string, unknown> | null)?.transport;
  const refs = (transport as Record<string, unknown> | undefined)?.credential_refs;
  const out: Record<string, string> = {};
  if (refs && typeof refs === "object") {
    for (const [k, v] of Object.entries(refs)) {
      if (typeof v === "string") out[k] = v;
    }
  }
  return out;
}

/** The config JSON minus credential_refs — credentials are edited separately. */
function configWithoutCreds(config: unknown): string {
  const clone = JSON.parse(JSON.stringify(config ?? {})) as Record<string, unknown>;
  const transport = clone.transport as Record<string, unknown> | undefined;
  if (transport) delete transport.credential_refs;
  return JSON.stringify(clone, null, 2);
}

interface Props {
  resource: ResourceOut;
}

/**
 * Edit an MCP server: description, the config as JSON, and credentials.
 * Credentials live in their own section because the keychain holds the
 * values — the config JSON only ever carries references. On save, new /
 * rotated secrets are written to the keychain and any credential the
 * server no longer references (and that this server owns) is deleted.
 */
export function EditMcpServerDialog({ resource }: Props) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [description, setDescription] = useState("");
  const [configText, setConfigText] = useState("");
  const [creds, setCreds] = useState<CredRow[]>([]);

  function reset() {
    setDescription(resource.description ?? "");
    setConfigText(configWithoutCreds(resource.config));
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
    mutationFn: async () => {
      let config: Record<string, unknown>;
      try {
        config = JSON.parse(configText) as Record<string, unknown>;
      } catch {
        throw new Error(t("mcp.import.errInvalidJson"));
      }
      const client = getApiClient();

      // Pre-validate before any keychain write: a row renamed without a new
      // value can't be moved in the keychain blind (we don't hold the
      // plaintext), so require the secret to be re-entered under the new
      // name rather than silently leaving the ref pointing at the old name.
      for (const row of creds) {
        const name = row.name.trim();
        if (name === "" || row.value !== "" || !row.originalRef) continue;
        if (row.originalName !== null && name !== row.originalName) {
          throw new Error(t("mcp.edit.errRenameNeedsValue", { name }));
        }
      }

      // Build credential_refs; write new / rotated secret values first.
      // Track keychain refs we create that are BRAND NEW (not a rotation of
      // an existing ref) so we can clean them up if the PATCH below fails —
      // otherwise a config the backend rejects would orphan the secret.
      const originalRefSet = new Set(Object.values(credentialRefsOf(resource.config)));
      const credentialRefs: Record<string, string> = {};
      const newlyWrittenRefs: string[] = [];
      for (const row of creds) {
        const name = row.name.trim();
        if (name === "") continue;
        if (row.value !== "") {
          const ref = `${resource.name}.${name}`;
          const { error: e } = await client.POST("/keychain", {
            body: { ref, value: row.value },
          });
          if (e) throwApiError(e, "INTERNAL_ERROR", "keychain write failed");
          credentialRefs[name] = ref;
          if (!originalRefSet.has(ref)) newlyWrittenRefs.push(ref);
        } else if (row.originalRef) {
          // Unchanged name → keep the existing secret under its ref.
          credentialRefs[name] = row.originalRef;
        }
      }

      const transport = {
        ...((config.transport as Record<string, unknown>) ?? {}),
        credential_refs: credentialRefs,
      };
      const { error: pe } = await client.PATCH("/resources/{kind}/{name}", {
        params: { path: { kind: "mcp_server", name: resource.name } },
        body: {
          description: description.trim() || null,
          config: { ...config, transport },
        },
      });
      if (pe) {
        // PATCH rejected the config — delete the brand-new keychain entries
        // we just wrote so they don't dangle (best-effort; rotations of
        // existing refs are left, since the unchanged config still uses them).
        for (const ref of newlyWrittenRefs) {
          try {
            await client.DELETE("/keychain/{ref}", { params: { path: { ref } } });
          } catch {
            // best-effort cleanup; the PATCH error below is what matters
          }
        }
        throwApiError(pe, "INTERNAL_ERROR", "update failed");
      }

      // Clean up keychain entries this server no longer references — but
      // only ones it owns (`<name>.` prefix); never a shared/manual ref.
      // A failed cleanup must not roll back the successful PATCH above;
      // we log a warning and let the user re-trigger if needed.
      const newRefs = new Set(Object.values(credentialRefs));
      const prefix = `${resource.name}.`;
      const orphanWarnings: string[] = [];
      for (const ref of Object.values(credentialRefsOf(resource.config))) {
        if (!newRefs.has(ref) && ref.startsWith(prefix)) {
          const { error: de } = await client.DELETE("/keychain/{ref}", {
            params: { path: { ref } },
          });
          if (de) {
            const msg = de.error?.message ?? "keychain delete failed";
            console.warn(`[EditMcpServerDialog] orphan cleanup failed for ${ref}:`, msg);
            orphanWarnings.push(ref);
          }
        }
      }
      return { orphanWarnings };
    },
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
