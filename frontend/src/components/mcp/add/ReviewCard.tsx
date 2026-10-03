// frontend/src/components/mcp/add/ReviewCard.tsx — one server in the review
// step (board Mcp-Import-Review), as one row: include tick, the name it will
// keep (editable until added, flagged over 24 characters), how it runs, and
// what it carries as the shared header / env rows (a value that looks like a
// secret arrives as a new secret, switchable back from its 🔑 menu). A server added
// by an earlier attempt shows a check, its fixed name and "Added".
import { useTranslation } from "react-i18next";
import { Check } from "lucide-react";

import { KeyValueSecretRows } from "@/components/secret/KeyValueSecretRows";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";
import type { NewServer } from "@/lib/mcp/importMcpServers";
import { NameField } from "./NameField";

interface Props {
  index: number;
  server: NewServer;
  include: boolean;
  /** Already registered by an earlier attempt of this dialog: shown, locked. */
  added: boolean;
  taken: ReadonlySet<string>;
  /** Why the last attempt did not add it (not a name clash — that shows under the name). */
  error?: string;
  /** The keys that arrived flagged secret without a value: the person types one. */
  asked: ReadonlySet<string>;
  onInclude: (on: boolean) => void;
  onChange: (server: NewServer) => void;
}

function summary(t: (k: string, o?: Record<string, string>) => string, s: NewServer): string {
  if (s.transportType === "http") return t("mcp.add.summaryHttp");
  const program = s.command.split(/[\\/]/).pop() ?? s.command;
  return t("mcp.add.summaryStdio", { program });
}

export function ReviewCard({
  index,
  server,
  include,
  added,
  taken,
  error,
  asked,
  onInclude,
  onChange,
}: Props) {
  const { t } = useTranslation();
  const http = server.transportType === "http";
  const label = http ? t("mcp.add.headers") : t("mcp.add.env");
  return (
    <div
      className={cn(
        "grid grid-cols-[auto_13rem_8rem_minmax(0,1fr)] items-start gap-x-3 border-t border-border-subtle py-3",
        !include && "opacity-disabled",
      )}
    >
      {added ? (
        <Check aria-hidden className="mt-2 size-4 text-success" />
      ) : (
        <Checkbox
          className="mt-2"
          checked={include}
          aria-label={t("mcp.add.include", { name: server.name })}
          onChange={(e) => onInclude(e.target.checked)}
        />
      )}
      <div className="min-w-0">
        {added ? (
          <p className="pt-1.5 font-mono text-xs font-label text-text">{server.name}</p>
        ) : (
          <NameField
            id={`review-name-${index}`}
            compact
            value={server.name}
            taken={taken}
            onChange={(name) => onChange({ ...server, name })}
          />
        )}
      </div>
      <p className="pt-1.5 text-xs text-text-muted">{summary(t, server)}</p>
      <div className="min-w-0 space-y-1.5 pt-1.5 text-xs text-text-muted">
        {added ? (
          <div className="flex items-center gap-2">
            <Badge variant="secondary">{t("mcp.add.added")}</Badge>
            {t("mcp.add.testingBackground")}
          </div>
        ) : null}
        {server.originalName && server.originalName !== server.name ? (
          <p>{t("mcp.add.renamedFrom", { name: server.originalName })}</p>
        ) : null}
        {added ? null : (
          <>
            <KeyValueSecretRows
              rows={server.env}
              onChange={(env) => onChange({ ...server, env })}
              label={label}
              keyPlaceholder={http ? "Authorization" : "API_KEY"}
              addLabel={http ? t("mcp.env.addHeader") : t("mcp.env.addVariable")}
            />
            {server.env.length === 0 ? <p>{t(http ? "mcp.add.noHeaders" : "mcp.add.noEnv")}</p> : null}
            {server.env
              .filter((e) => e.value.kind === "new")
              .map((e) => (
                <p key={e.key}>{t("mcp.add.secretLine", { key: e.key })}</p>
              ))}
            {server.env
              .filter((e) => asked.has(e.key) && e.value.kind === "plain" && e.value.value === "")
              .map((e) => (
                <p key={e.key}>{t("mcp.add.secretMissing", { key: e.key })}</p>
              ))}
          </>
        )}
        {error && !added ? (
          <p className="text-danger" role="alert">
            {error}
          </p>
        ) : null}
      </div>
    </div>
  );
}
