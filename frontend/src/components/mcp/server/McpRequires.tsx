// src/components/mcp/server/McpRequires.tsx — the Overview's "Requires": what the server needs from this Mac, worked out from its command and settings (design 4.1.05).
//
// One row per thing: the launcher (a CLI, found or not, with its version) and
// each secret its environment or headers cite (set, missing here, or waiting
// for approval), each with a link to the page that owns it. A Streamable HTTP
// server has no launcher row. Nothing to show when it needs nothing.
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { Section } from "@/components/Section";
import type { McpStatusDetail } from "@/lib/hooks/useMcpServerStatus";
import { toneTextClass } from "@/lib/statusColors";
import { cn } from "@/lib/utils";

type Requirement = McpStatusDetail["requires"][number];

const OK: ReadonlySet<Requirement["status"]> = new Set(["found", "set"]);

export function McpRequires({ requires }: { requires: readonly Requirement[] }) {
  const { t } = useTranslation();
  if (requires.length === 0) return null;
  return (
    <Section title={t("mcp.page.requires.title")} gap="snug" labelled compact>
      <p className="-mt-1 text-xs text-text-muted">{t("mcp.page.requires.sub")}</p>
      <ul className="flex flex-col border-b border-border-subtle">
        {requires.map((r) => (
          <li
            key={`${r.kind}:${r.name}`}
            className="grid min-h-9 grid-cols-[160px_72px_minmax(0,1fr)_128px] items-center gap-3 border-t border-border-subtle"
          >
            <span className="truncate font-mono text-xs font-label text-text">{r.name}</span>
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
            <span className="text-right">
              <Link
                to={r.kind === "cli" ? `/clis/${encodeURIComponent(r.name)}` : "/secrets"}
                className="text-xs font-label text-accent-text hover:underline"
              >
                {t(
                  r.kind === "cli" ? "mcp.page.requires.viewClis" : "mcp.page.requires.viewSecrets",
                )}
              </Link>
            </span>
          </li>
        ))}
      </ul>
    </Section>
  );
}
