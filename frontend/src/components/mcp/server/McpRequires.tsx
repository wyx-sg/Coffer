// src/components/mcp/server/McpRequires.tsx — the Overview's "Requires": what the server needs from this Mac, worked out from its command and settings (design 4.1.05).
//
// One row per thing: the launcher (a CLI, found or not, with its version) and
// each secret its environment or headers cite (set, missing here, or waiting
// for approval). A CLI row links to its CLIs page; a secret row names the env
// var or header, then the secret by its Secrets-page name (a link to its page)
// with Replace key… beside it. A Streamable HTTP server has no launcher row.
// Nothing to show when it needs nothing.
import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { KeyRound } from "lucide-react";

import { Section } from "@/components/Section";
import { ReplaceSecretRefDialog } from "@/components/secret/ReplaceSecretRefDialog";
import { SecretRefControl } from "@/components/secret/SecretRefControl";
import { Button } from "@/components/ui/button";
import type { McpStatusDetail } from "@/lib/hooks/useMcpServerStatus";
import { toneTextClass } from "@/lib/statusColors";
import { cn } from "@/lib/utils";

type Requirement = McpStatusDetail["requires"][number];

const OK: ReadonlySet<Requirement["status"]> = new Set(["found", "set"]);

const refOf = (id: string) => (id.startsWith("secret/") ? id : `secret/${id}`);

interface Props {
  requires: readonly Requirement[];
  /** Saves the owner pointing `requirement` (an env var or header) at the secret `ref`; omitted, no Replace key button. */
  onRebind?: (requirement: Requirement, ref: string) => Promise<unknown>;
}

export function McpRequires({ requires, onRebind }: Props) {
  const { t } = useTranslation();
  const [replacing, setReplacing] = useState<Requirement | null>(null);
  if (requires.length === 0) return null;
  return (
    <Section title={t("mcp.page.requires.title")} gap="snug" labelled compact>
      <p className="-mt-1 text-xs text-text-muted">{t("mcp.page.requires.sub")}</p>
      <ul className="flex flex-col border-b border-border-subtle">
        {requires.map((r) => {
          // A secret row names the env var or header the server reads, then the secret that
          // fills it by its readable name (a link to its page) with Replace key… beside it.
          const secret = r.kind === "secret" ? (r.secret ?? r.name) : null;
          const replace = secret !== null && onRebind ? () => setReplacing(r) : undefined;
          return (
            <li
              key={`${r.kind}:${r.name}`}
              className="grid min-h-9 grid-cols-[160px_72px_minmax(0,1fr)_auto] items-center gap-3 border-t border-border-subtle py-1"
            >
              <span className="truncate font-mono text-xs font-label text-text" title={r.name}>
                {r.name}
              </span>
              <span className="text-xs text-text-muted">
                {t(r.kind === "cli" ? "mcp.page.requires.cli" : "mcp.page.requires.secret")}
              </span>
              <span
                className={cn(
                  "text-xs",
                  OK.has(r.status) ? "text-text-muted" : toneTextClass("warn"),
                )}
              >
                {r.status === "found" && r.version
                  ? t("mcp.page.requires.foundVersion", { version: r.version })
                  : t(`mcp.page.requires.status.${r.status}`)}
              </span>
              <span className="flex justify-end">
                {secret === null ? (
                  <Link
                    to={`/clis/${encodeURIComponent(r.name)}`}
                    className="text-xs font-label text-accent-text hover:underline"
                  >
                    {t("mcp.page.requires.viewClis")}
                  </Link>
                ) : r.status === "missing" ? (
                  replace ? (
                    <Button variant="outline" size="sm" onClick={replace}>
                      <KeyRound aria-hidden /> {t("secretRef.replaceOpen")}
                    </Button>
                  ) : null
                ) : (
                  <SecretRefControl secretRef={refOf(secret)} onReplace={replace} />
                )}
              </span>
            </li>
          );
        })}
      </ul>
      {onRebind ? (
        <ReplaceSecretRefDialog
          secretRef={replacing?.secret ? refOf(replacing.secret) : null}
          field={replacing?.name ?? ""}
          onClose={() => setReplacing(null)}
          onRebind={(ref) => onRebind(replacing as Requirement, ref)}
        />
      ) : null}
    </Section>
  );
}
