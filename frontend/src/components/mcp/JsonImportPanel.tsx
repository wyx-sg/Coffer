// frontend/src/components/mcp/JsonImportPanel.tsx
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Lock } from "lucide-react";
import {
  MCP_SERVER_NAME_MAX,
  parseMcpJson,
  serverNameTooLong,
  type ParsedServer,
} from "./jsonImport";

interface Props {
  onImport: (servers: ParsedServer[]) => void;
  importing: boolean;
}

/** The parser's own message for text that is not JSON at all, or `null` when
 * it parses (or is still empty). Checked as the user types, so Continue is
 * only live for text that can be continued with. */
function jsonSyntaxError(text: string): string | null {
  if (!text.trim()) return null;
  try {
    JSON.parse(text);
    return null;
  } catch (e) {
    return e instanceof Error ? e.message : String(e);
  }
}

/**
 * The "Paste JSON" tab: paste MCP server JSON, then a review step where
 * each env var (an http server's headers) is shown with a Secret toggle (pre-set by heuristic) — so
 * the user confirms what goes to the encrypted credential store before importing.
 *
 * The review also shows each server's name as the one it will keep: it is the
 * key in the pasted block, fixed after registration. A name over the 24-character
 * cap is flagged there and the import stays disabled until it is shortened in
 * the pasted block, so no registration is sent for it (spec web-ui "Import MCP
 * servers from pasted JSON").
 */
export function JsonImportPanel({ onImport, importing }: Props) {
  const { t } = useTranslation();
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [servers, setServers] = useState<ParsedServer[] | null>(null);
  const syntaxError = useMemo(() => jsonSyntaxError(text), [text]);

  function handleParse() {
    const result = parseMcpJson(text);
    if (!result.ok) {
      setError(t(`mcp.import.${result.errorKey}`, result.errorParams));
      return;
    }
    setError(null);
    setServers(result.servers);
  }

  function toggleSecret(serverIdx: number, envIdx: number) {
    setServers((prev) =>
      prev === null
        ? prev
        : prev.map((s, si) =>
            si !== serverIdx
              ? s
              : {
                  ...s,
                  env: s.env.map((e, ei) => (ei !== envIdx ? e : { ...e, isSecret: !e.isSecret })),
                },
          ),
    );
  }

  if (servers === null) {
    // A syntax error is shown as the user types; a shape error (valid JSON,
    // but no server in it) only once they ask to continue.
    const shown = syntaxError ? t("mcp.add.invalidJson", { detail: syntaxError }) : error;
    return (
      <div className="space-y-3">
        <Label htmlFor="json-input" required>
          {t("mcp.import.jsonLabel")}
        </Label>
        <Textarea
          id="json-input"
          className="h-56 font-mono text-xs"
          placeholder={t("mcp.import.jsonPlaceholder")}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setError(null);
          }}
          aria-invalid={shown ? true : undefined}
        />
        <p className="text-xs text-muted-foreground">{t("mcp.import.jsonHelp")}</p>
        {shown ? (
          <p className="text-sm text-destructive" role="alert">
            {shown}
          </p>
        ) : null}
        <div className="flex justify-end">
          <Button onClick={handleParse} disabled={!text.trim() || syntaxError !== null}>
            {t("mcp.import.parse")}
          </Button>
        </div>
      </div>
    );
  }

  const tooLong = servers.filter((s) => serverNameTooLong(s.name));

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t("mcp.import.review")}</p>
      <div className="space-y-3">
        {servers.map((srv, si) => (
          <div key={srv.name} className="rounded-lg border border-border p-3">
            <div className="flex items-center gap-1.5 font-mono font-medium">
              <Lock className="size-3.5 text-muted-foreground" aria-hidden />
              {srv.name}
            </div>
            <p className="mt-0.5 text-xs text-muted-foreground">{t("mcp.import.fixedName")}</p>
            {serverNameTooLong(srv.name) ? (
              <p className="mt-1 text-xs text-destructive" role="alert">
                {t("mcp.import.nameTooLong", {
                  name: srv.name,
                  length: srv.name.length,
                  max: MCP_SERVER_NAME_MAX,
                })}
              </p>
            ) : null}
            <div className="mt-0.5 break-all font-mono text-xs text-muted-foreground">
              {srv.transportType === "stdio" ? [srv.command, ...srv.args].join(" ") : srv.url}
            </div>
            {srv.env.length > 0 ? (
              <div className="mt-2 space-y-1.5">
                {srv.env.map((e, ei) => (
                  <div key={e.key} className="flex items-center justify-between gap-2 text-xs">
                    <span className="min-w-0 flex-1 truncate font-mono">
                      <span className="text-foreground">{e.key}</span>
                      <span className="text-muted-foreground">
                        {" = "}
                        {e.isSecret ? "••••••" : e.value}
                      </span>
                    </span>
                    <label className="flex shrink-0 cursor-pointer items-center gap-1.5">
                      <Switch checked={e.isSecret} onCheckedChange={() => toggleSecret(si, ei)} />
                      <span className="text-muted-foreground">{t("mcp.import.secret")}</span>
                    </label>
                  </div>
                ))}
              </div>
            ) : (
              <div className="mt-2 text-xs text-muted-foreground">
                {t(srv.transportType === "http" ? "mcp.import.noHeaders" : "mcp.import.noEnv")}
              </div>
            )}
          </div>
        ))}
      </div>
      <p className="text-xs text-muted-foreground">{t("mcp.import.secretHint")}</p>
      {tooLong.length > 0 ? (
        <p className="text-sm text-destructive" role="status">
          {t("mcp.import.blockedByName", { max: MCP_SERVER_NAME_MAX })}
        </p>
      ) : null}
      <div className="flex justify-between gap-2">
        <Button variant="outline" onClick={() => setServers(null)} disabled={importing}>
          {t("mcp.import.back")}
        </Button>
        <Button onClick={() => onImport(servers)} disabled={importing || tooLong.length > 0}>
          {importing ? t("common.saving") : t("mcp.import.import", { count: servers.length })}
        </Button>
      </div>
    </div>
  );
}
