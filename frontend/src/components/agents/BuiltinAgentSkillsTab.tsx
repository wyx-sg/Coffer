// frontend/src/components/agents/BuiltinAgentSkillsTab.tsx — spec 008.
// READ-ONLY list of the skills the built-in agent can use through Coffer's MCP
// gateway. Built-in agents don't BIND skills (they reach them via the gateway),
// so there are no per-agent toggles here — just the catalogue with a note. When
// the agent's gateway is off, tools/skills are disabled, so we say so instead.
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { DataTable, type Column } from "@/components/DataTable";
import { translateApiError } from "@/lib/api/errors";
import type { SkillOut } from "@/lib/api/skills";
import { useSkills } from "@/lib/hooks/useSkills";

export function BuiltinAgentSkillsTab({
  agentName,
  useGateway,
}: {
  agentName: string;
  useGateway: boolean;
}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const skills = useSkills();

  if (!useGateway) {
    return <p className="text-sm text-muted-foreground">{t("builtinAgents.detail.gatewayOff")}</p>;
  }

  const columns: Column<SkillOut>[] = [
    {
      key: "name",
      header: t("skills.name"),
      className: "whitespace-nowrap",
      cell: (r) => <span className="font-medium">{r.name}</span>,
    },
    {
      key: "description",
      header: t("skills.description"),
      cell: (r) =>
        r.description ? (
          <span className="line-clamp-1 max-w-md text-muted-foreground">{r.description}</span>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
  ];

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">{t("builtinAgents.detail.skillsNote")}</p>

      {skills.isPending ? (
        <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
      ) : skills.error ? (
        <p className="text-sm text-destructive">{translateApiError(t, skills.error)}</p>
      ) : (
        <DataTable
          rows={skills.data ?? []}
          columns={columns}
          rowKey={(r) => r.name}
          search={{
            accessor: (r) => `${r.name} ${r.description}`,
            placeholder: t("skills.searchPlaceholder"),
          }}
          onRowClick={(r) =>
            navigate(`/skills/${r.name}`, {
              state: { backTo: `/agents/builtin/${agentName}`, backLabel: agentName },
            })
          }
          emptyMessage={t("builtinAgents.detail.skillsEmpty")}
        />
      )}
    </div>
  );
}
