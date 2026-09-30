// src/components/mcp/env/TransportInputs.tsx — where the edit dialog's server
// is reached: the URL of an HTTP server, or the command and arguments of a
// stdio one (boards Mcp-Edit / Mcp-EditStdio). The working directory sits
// below the Environment rows and is `WorkingDirInput`.
import { useTranslation } from "react-i18next";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface Props {
  http: boolean;
  url: string;
  command: string;
  argsText: string;
  /** The arguments line does not split (an unclosed quote). */
  argsInvalid: boolean;
  onUrl: (v: string) => void;
  onCommand: (v: string) => void;
  onArgs: (v: string) => void;
}

export function TransportInputs(p: Props) {
  const { t } = useTranslation();
  if (p.http) {
    return (
      <div className="space-y-1.5">
        <Label htmlFor="edit-url" required>
          {t("mcp.add.url")}
        </Label>
        <Input
          id="edit-url"
          className="font-mono"
          spellCheck={false}
          value={p.url}
          onChange={(e) => p.onUrl(e.target.value)}
        />
        <p className="text-xs text-text-muted">{t("mcp.edit.urlHelp")}</p>
      </div>
    );
  }
  return (
    <>
      <div className="space-y-1.5">
        <Label htmlFor="edit-command" required>
          {t("mcp.add.command")}
        </Label>
        <Input
          id="edit-command"
          className="font-mono"
          spellCheck={false}
          value={p.command}
          onChange={(e) => p.onCommand(e.target.value)}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="edit-args">{t("mcp.add.args")}</Label>
        <Input
          id="edit-args"
          className="font-mono"
          spellCheck={false}
          value={p.argsText}
          aria-invalid={p.argsInvalid || undefined}
          onChange={(e) => p.onArgs(e.target.value)}
        />
        {p.argsInvalid ? (
          <p className="text-xs text-danger" role="alert">
            {t("mcp.add.argsQuote")}
          </p>
        ) : null}
      </div>
    </>
  );
}

export function WorkingDirInput({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="space-y-1.5">
      <Label htmlFor="edit-cwd">{t("mcp.edit.cwd")}</Label>
      <Input
        id="edit-cwd"
        className="font-mono"
        spellCheck={false}
        value={value}
        placeholder={t("mcp.edit.cwdPlaceholder")}
        onChange={(e) => onChange(e.target.value)}
      />
      <p className="text-xs text-text-muted">{t("mcp.edit.cwdHelp")}</p>
    </div>
  );
}
