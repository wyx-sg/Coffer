// src/components/clis/CliDetailSections.tsx — the body of a CLI's pane: Command, Login and Needed by, as read-only rows in a two-column grid.
//
// Nothing here acts: Coffer never runs a login, an install or an update (the
// pane's header hands those to an agent). Needed by lists the MCP servers
// started with the command — each opening that server's page — and the skills
// that declare it, each opening that skill's Requires tab. When both kinds
// need it, each row carries its kind. A tool added by hand that nothing needs
// shows "—" there.
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { SectionStack } from "@/components/Section";
import { Badge } from "@/components/ui/badge";
import type { Cli } from "@/lib/api/clis";
import { CliField, CliSection } from "./CliField";

interface Props {
  cli: Cli;
}

function KindBadge({ children }: { children: string }) {
  return (
    <Badge variant="secondary" className="ml-2 align-middle">
      {children}
    </Badge>
  );
}

function NeededBy({ cli }: Props) {
  const { t } = useTranslation();
  const mixed = cli.needed_by_servers.length > 0 && cli.needed_by.length > 0;
  const linkClass = "font-mono text-sm text-accent-text hover:underline";
  return (
    <CliSection title={t("clis.detail.sections.neededBy")}>
      {cli.needed_by.length === 0 && cli.needed_by_servers.length === 0 ? (
        <CliField label={t("clis.detail.addedByYou")}>
          <span className="text-xs text-text-muted">—</span>
        </CliField>
      ) : null}
      {cli.needed_by_servers.map((server) => (
        <CliField
          key={server.server_uid}
          label={
            <>
              <Link
                to={`/mcp-servers/${encodeURIComponent(server.server_name)}`}
                className={linkClass}
              >
                {server.server_name}
              </Link>
              {mixed ? <KindBadge>{t("clis.detail.kind.server")}</KindBadge> : null}
            </>
          }
        >
          <span className="text-xs text-text-muted">
            {t("clis.detail.startsWith", { launcher: server.launcher })}
          </span>
        </CliField>
      ))}
      {cli.needed_by.map((need) => (
        <CliField
          key={need.skill_uid}
          label={
            <>
              <Link
                to={`/skills/${encodeURIComponent(need.skill_name)}/requires`}
                className={linkClass}
              >
                {need.skill_name}
              </Link>
              {mixed ? <KindBadge>{t("clis.detail.kind.skill")}</KindBadge> : null}
            </>
          }
        >
          <span className="text-xs text-text-muted">
            {[need.min_version ? t("clis.needs", { version: need.min_version }) : null, need.why]
              .filter(Boolean)
              .join(" · ") || "—"}
          </span>
        </CliField>
      ))}
    </CliSection>
  );
}

export function CliDetailSections({ cli }: Props) {
  const { t } = useTranslation();
  const versionOk = cli.status !== "missing" && cli.status !== "outdated";
  // A command that was not found could not run its login check — but one
  // that declares none needs no login either way.
  const loginState = cli.login.state ?? (cli.login.check === null ? "not_needed" : null);

  return (
    <SectionStack>
      <CliSection title={t("clis.detail.sections.command")}>
        <CliField label={t("clis.detail.foundAt")}>
          {cli.path ? (
            <span className="font-mono text-xs">{cli.path}</span>
          ) : (
            <span className="text-danger">{t("clis.notOnPath")}</span>
          )}
        </CliField>
        <CliField label={t("clis.detail.version")}>
          <span className="font-mono text-xs">
            {cli.version ?? (cli.path ? t("clis.unknownVersion") : "—")}
          </span>
          {cli.min_version ? (
            <span className="ml-2 text-xs text-text-muted">
              {versionOk && cli.version ? "✓ " : ""}
              {t("clis.needs", { version: cli.min_version })}
            </span>
          ) : null}
        </CliField>
      </CliSection>

      <CliSection title={t("clis.detail.sections.login")}>
        <CliField label={t("clis.detail.state")}>
          {loginState ? t(`clis.login.${loginState}`) : "—"}
        </CliField>
      </CliSection>

      <NeededBy cli={cli} />
    </SectionStack>
  );
}
