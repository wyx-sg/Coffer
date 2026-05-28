// frontend/src/kinds/mcp/CredentialRowEditor.tsx
//
// Renders the credential-editing section of EditMcpServerDialog: a list of
// name/value row editors plus an "Add credential" button.
import { useTranslation } from "react-i18next";
import { Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export interface CredRow {
  id: number;
  name: string;
  /** New value to write; "" = keep the existing one. */
  value: string;
  /** Existing keychain ref, or null for a freshly added row. */
  originalRef: string | null;
}

interface Props {
  creds: CredRow[];
  onUpdate: (idx: number, patch: Partial<CredRow>) => void;
  onRemove: (idx: number) => void;
  onAdd: () => void;
}

export function CredentialRowEditor({ creds, onUpdate, onRemove, onAdd }: Props) {
  const { t } = useTranslation();

  return (
    <div className="space-y-2">
      <Label>{t("mcp.edit.credentials")}</Label>
      {creds.length === 0 ? (
        <p className="text-xs text-muted-foreground">{t("mcp.edit.noCredentials")}</p>
      ) : (
        creds.map((row, idx) => (
          <div key={row.id} className="flex items-center gap-2">
            <Input
              value={row.name}
              onChange={(e) => onUpdate(idx, { name: e.target.value })}
              placeholder="GITHUB_TOKEN"
              className="font-mono text-xs"
            />
            <Input
              type="password"
              value={row.value}
              onChange={(e) => onUpdate(idx, { value: e.target.value })}
              placeholder={
                row.originalRef ? t("mcp.edit.credentialKeep") : t("mcp.edit.credentialNew")
              }
            />
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="size-9 shrink-0"
              onClick={() => onRemove(idx)}
              aria-label={t("mcp.edit.removeCredential")}
            >
              <Trash2 className="size-4" />
            </Button>
          </div>
        ))
      )}
      <Button type="button" variant="outline" size="sm" onClick={onAdd}>
        <Plus className="mr-1 size-4" /> {t("mcp.edit.addCredential")}
      </Button>
      <p className="text-xs text-muted-foreground">{t("mcp.edit.credentialHint")}</p>
    </div>
  );
}
