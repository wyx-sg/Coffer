// src/components/mcp/env/TransportInputs.tsx — where the form's server
// is reached (the Add form and the Edit dialog): the URL of an HTTP server, or the command and arguments of a
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
  /** Prefix of the field ids, so two forms never share one. */
  idPrefix?: string;
  /** The URL field's help line. */
  urlHelp?: string;
}

export function TransportInputs(p: Props) {
  const { t } = useTranslation();
  const id = p.idPrefix ?? "edit";
  if (p.http) {
    return (
      <div className="space-y-1.5">
        <Label htmlFor={`${id}-url`} required>
          {t("mcp.add.url")}
        </Label>
        <Input
          id={`${id}-url`}
          className="font-mono"
          spellCheck={false}
          value={p.url}
          onChange={(e) => p.onUrl(e.target.value)}
        />
        <p className="text-xs text-text-muted">{p.urlHelp ?? t("mcp.edit.urlHelp")}</p>
      </div>
    );
  }
  return (
    <>
      <div className="space-y-1.5">
        <Label htmlFor={`${id}-command`} required>
          {t("mcp.add.command")}
        </Label>
        <Input
          id={`${id}-command`}
          className="font-mono"
          spellCheck={false}
          value={p.command}
          onChange={(e) => p.onCommand(e.target.value)}
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor={`${id}-args`}>{t("mcp.add.args")}</Label>
        <Input
          id={`${id}-args`}
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
  idPrefix = "edit",
}: {
  value: string;
  onChange: (v: string) => void;
  idPrefix?: string;
}) {
  const { t } = useTranslation();
  return (
    <div className="space-y-1.5">
      <Label htmlFor={`${idPrefix}-cwd`}>{t("mcp.edit.cwd")}</Label>
      <Input
        id={`${idPrefix}-cwd`}
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
