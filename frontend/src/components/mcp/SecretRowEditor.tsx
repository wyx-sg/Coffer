// frontend/src/components/mcp/SecretRowEditor.tsx
//
// The secrets section of EditMcpServerDialog (board Mcp-Edit): every stored
// secret as its key, "Stored" and a Replace button — the value is never shown,
// and replacing writes a new one through the same ref — plus rows for new
// secrets (key + value) and an "Add secret" button.
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PasswordInput } from "@/components/ui/password-input";

export interface CredRow {
  id: number;
  name: string;
  /** New value to write; "" = keep the existing one. */
  value: string;
  /** Existing secret store ref, or null for a freshly added row. */
  originalRef: string | null;
  /** The env-var name this row loaded with, or null for a new row. Used to
   *  detect a rename that needs the secret re-entered. */
  originalName: string | null;
}

interface Props {
  creds: CredRow[];
  onUpdate: (idx: number, patch: Partial<CredRow>) => void;
  onRemove: (idx: number) => void;
  onAdd: () => void;
  /** Open the first stored secret for replacing, focused — the dialog was
   *  opened from a "secret missing" notice. */
  focusFirst?: boolean;
}

export function SecretRowEditor({ creds, onUpdate, onRemove, onAdd, focusFirst }: Props) {
  const { t } = useTranslation();
  const firstStored = creds.find((r) => r.originalRef)?.id;
  const [replacing, setReplacing] = useState<Set<number>>(() => new Set());

  return (
    <div className="space-y-2">
      <Label>{t("mcp.edit.secrets")}</Label>
      {creds.length === 0 ? (
        <p className="text-xs text-text-muted">{t("mcp.edit.noSecrets")}</p>
      ) : null}
      {creds.map((row, idx) => {
        const stored = row.originalRef !== null;
        const focused = focusFirst === true && row.id === firstStored;
        const open = !stored || focused || replacing.has(row.id);
        return (
          <div key={row.id} className="flex items-center gap-2">
            {stored ? (
              <span className="flex min-w-0 flex-1 items-center gap-2 text-xs">
                <span className="truncate font-mono text-text">{row.name}</span>
                <span className="text-text-muted">{t("mcp.edit.stored")}</span>
              </span>
            ) : (
              <Input
                value={row.name}
                aria-label={t("mcp.edit.secretKey")}
                onChange={(e) => onUpdate(idx, { name: e.target.value })}
                placeholder="GITHUB_TOKEN"
                className="flex-1 font-mono text-xs"
              />
            )}
            {open ? (
              <PasswordInput
                containerClassName="flex-1"
                aria-label={t("mcp.edit.secretValue", { name: row.name })}
                autoFocus={focused}
                value={row.value}
                onChange={(e) => onUpdate(idx, { value: e.target.value })}
                placeholder={stored ? t("common.secretKeepBlank") : t("mcp.edit.secretNew")}
              />
            ) : (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setReplacing((prev) => new Set(prev).add(row.id))}
              >
                {t("mcp.edit.replace")}
              </Button>
            )}
            <Button
              type="button"
              variant="ghost"
              size="icon-sm"
              onClick={() => onRemove(idx)}
              aria-label={t("mcp.edit.removeSecret")}
            >
              <Trash2 />
            </Button>
          </div>
        );
      })}
      <Button type="button" variant="outline" size="sm" onClick={onAdd}>
        <Plus /> {t("mcp.edit.addSecret")}
      </Button>
      <p className="text-xs text-text-muted">{t("mcp.edit.secretHint")}</p>
    </div>
  );
}
