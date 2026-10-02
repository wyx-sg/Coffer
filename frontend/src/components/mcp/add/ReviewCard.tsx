// frontend/src/components/mcp/add/ReviewCard.tsx — one server in the review
// step (board Mcp-Import-Review), as one row: include tick, the name it will
// keep (editable until added, flagged over 24 characters), how it runs, and
// what it carries — a Secret toggle per environment / header key.
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Checkbox } from "@/components/ui/checkbox";
import { PasswordInput } from "@/components/ui/password-input";
import { Switch } from "@/components/ui/switch";
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
  onInclude,
  onChange,
}: Props) {
  const { t } = useTranslation();
  // The keys that arrived without a value (a `bearer_token_env_var` header):
  // their box stays while the value is typed.
  const [asked] = useState(
    () => new Set(server.env.filter((e) => e.value === "").map((e) => e.key)),
  );
  const setEnv = (i: number, patch: Partial<NewServer["env"][number]>) =>
    onChange({ ...server, env: server.env.map((e, j) => (j === i ? { ...e, ...patch } : e)) });
  const http = server.transportType === "http";
  return (
    <div
      className={cn(
        "grid grid-cols-[auto_13rem_8rem_minmax(0,1fr)] items-start gap-x-3 border-t border-border-subtle py-3",
        !include && "opacity-disabled",
      )}
    >
      <Checkbox
        className="mt-2"
        checked={include}
        disabled={added}
        aria-label={t("mcp.add.include", { name: server.name })}
        onChange={(e) => onInclude(e.target.checked)}
      />
      <div className="min-w-0">
        {added ? (
          <p className="pt-1.5 font-mono text-sm font-label">
            {server.name}{" "}
            <span className="font-sans text-xs text-success">{t("mcp.add.added")}</span>
          </p>
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
        {server.originalName && server.originalName !== server.name ? (
          <p>{t("mcp.add.renamedFrom", { name: server.originalName })}</p>
        ) : null}
        {server.env.length === 0 ? <p>{t(http ? "mcp.add.noHeaders" : "mcp.add.noEnv")}</p> : null}
        {server.env.map((e, i) => (
          <div key={e.key} className="space-y-1">
            <div className="flex items-start gap-2">
              <span className="min-w-0 flex-1">
                {e.isSecret ? (
                  t("mcp.add.secretLine", { key: e.key })
                ) : (
                  <span className="font-mono text-text">{e.key}</span>
                )}
              </span>
              <label className="flex shrink-0 cursor-pointer items-center gap-1.5">
                <Switch
                  checked={e.isSecret}
                  disabled={added}
                  aria-label={t("mcp.add.secretFor", { key: e.key })}
                  onCheckedChange={(on) => setEnv(i, { isSecret: on })}
                />
                {t("mcp.add.secret")}
              </label>
            </div>
            {e.isSecret && (e.value === "" || asked.has(e.key)) && !added ? (
              <PasswordInput
                aria-label={t("mcp.add.rowValue", { key: e.key })}
                placeholder={t("mcp.add.secretMissing", { key: e.key })}
                value={e.value}
                onChange={(ev) => setEnv(i, { value: ev.target.value })}
              />
            ) : null}
          </div>
        ))}
        {error ? (
          <p className="text-danger" role="alert">
            {error}
          </p>
        ) : null}
      </div>
    </div>
  );
}
