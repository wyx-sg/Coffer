// frontend/src/components/mcp/add/ReviewCard.tsx — one server in the review
// step (board Mcp-Import-Review), as one row: include tick, the name it will
// keep (editable until added, flagged over 24 characters), how it runs, and
// what it carries — a Secret toggle per environment / header key. A server added
// by an earlier attempt shows a check, its fixed name and "Added".
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Check } from "lucide-react";

import { Badge } from "@/components/ui/badge";
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
  /** A name for a new secret made from `key`, unique across the whole batch. */
  nameSecret: (key: string) => string;
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
  nameSecret,
  onInclude,
  onChange,
}: Props) {
  const { t } = useTranslation();
  // The keys that arrived without a value (a `bearer_token_env_var` header):
  // their box stays while the value is typed.
  const [asked] = useState(
    () =>
      new Set(
        server.env.filter((e) => e.value.kind === "new" && e.value.value === "").map((e) => e.key),
      ),
  );
  const setValue = (i: number, value: NewServer["env"][number]["value"]) =>
    onChange({ ...server, env: server.env.map((e, j) => (j === i ? { ...e, value } : e)) });
  /** The Secret switch: plain ↔ a new secret holding the same text. */
  const toggle = (i: number, on: boolean) => {
    const e = server.env[i];
    const text = e.value.kind === "plain" || e.value.kind === "new" ? e.value.value : "";
    setValue(
      i,
      on
        ? { kind: "new", name: nameSecret(e.key), value: text }
        : { kind: "plain", value: text },
    );
  };
  const http = server.transportType === "http";
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
        {added ? null : server.env.length === 0 ? <p>{t(http ? "mcp.add.noHeaders" : "mcp.add.noEnv")}</p> : null}
        {(added ? [] : server.env).map((e, i) => (
          <div key={e.key} className="space-y-1">
            <div className="flex items-start gap-2">
              <span className="min-w-0 flex-1">
                {e.value.kind !== "plain" ? (
                  t("mcp.add.secretLine", { key: e.key })
                ) : (
                  <span className="font-mono text-text">{e.key}</span>
                )}
              </span>
              <label className="flex shrink-0 cursor-pointer items-center gap-1.5">
                <Switch
                  checked={e.value.kind !== "plain"}
                  aria-label={t("mcp.add.secretFor", { key: e.key })}
                  onCheckedChange={(on) => toggle(i, on)}
                />
                {t("mcp.add.secret")}
              </label>
            </div>
            {e.value.kind === "new" && (e.value.value === "" || asked.has(e.key)) ? (
              <PasswordInput
                aria-label={t("mcp.add.rowValue", { key: e.key })}
                placeholder={t("mcp.add.secretMissing", { key: e.key })}
                value={e.value.value}
                onChange={(ev) =>
                  setValue(i, { ...(e.value as { kind: "new"; name: string }), value: ev.target.value })
                }
              />
            ) : null}
          </div>
        ))}
        {error && !added ? (
          <p className="text-danger" role="alert">
            {error}
          </p>
        ) : null}
      </div>
    </div>
  );
}
