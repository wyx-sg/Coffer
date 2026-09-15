import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { parseMcpJson, type ParsedServer } from "./jsonImport";

interface Props {
  onImport: (servers: ParsedServer[]) => void;
  importing: boolean;
}

/**
 * The "Paste JSON" tab: paste MCP server JSON, then a review step where
 * each env var is shown with a Secret toggle (pre-set by heuristic) — so
 * the user confirms what goes to the encrypted credential store before importing.
 */
export function JsonImportPanel({ onImport, importing }: Props) {
  const { t } = useTranslation();
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [servers, setServers] = useState<ParsedServer[] | null>(null);

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
    return (
      <div className="space-y-3">
        <Label htmlFor="json-input">{t("mcp.import.jsonLabel")}</Label>
        <textarea
          id="json-input"
          className="h-56 w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs"
          placeholder={t("mcp.import.jsonPlaceholder")}
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <p className="text-xs text-muted-foreground">{t("mcp.import.jsonHelp")}</p>
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
        <div className="flex justify-end">
          <Button onClick={handleParse} disabled={!text.trim()}>
            {t("mcp.import.parse")}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">{t("mcp.import.review")}</p>
      <div className="space-y-3">
        {servers.map((srv, si) => (
          <div key={srv.name} className="rounded-lg border border-border p-3">
            <div className="font-medium">{srv.name}</div>
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
              <div className="mt-2 text-xs text-muted-foreground">{t("mcp.import.noEnv")}</div>
            )}
          </div>
        ))}
      </div>
      <p className="text-xs text-muted-foreground">{t("mcp.import.secretHint")}</p>
      <div className="flex justify-between gap-2">
        <Button variant="outline" onClick={() => setServers(null)} disabled={importing}>
          {t("mcp.import.back")}
        </Button>
        <Button onClick={() => onImport(servers)} disabled={importing}>
          {importing ? t("common.saving") : t("mcp.import.import", { count: servers.length })}
        </Button>
      </div>
    </div>
  );
}
