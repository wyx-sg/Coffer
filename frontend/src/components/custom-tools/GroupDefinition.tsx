// src/components/custom-tools/GroupDefinition.tsx — a group's definition as read-only rows: the name agents
// see, its reach, base URL, the auth header and the secret it is bound to, and the spec it came from.
import { useTranslation } from "react-i18next";

import { ScopeControl } from "@/components/ScopeControl";
import { Badge } from "@/components/ui/badge";
import type { CustomToolGroup } from "@/lib/api/customTools";
import { agentPrefix, groupScope } from "@/lib/customTools/groups";
import { formatDateTime } from "@/lib/utils";
import { AuthLine } from "./AuthLine";
import { DefinitionRow } from "./DefinitionRow";

interface Props {
  group: CustomToolGroup;
  onReimport: () => void;
}

export function GroupDefinition({ group, onReimport }: Props) {
  const { t } = useTranslation();
  const auth = group.auth;
  const secretBadge =
    group.secret_state === "missing" ? (
      <Badge variant="warning">{t("customTools.definition.missing")}</Badge>
    ) : group.secret_state === "pending_approval" ? (
      <Badge variant="warning">{t("customTools.definition.waiting")}</Badge>
    ) : null;

  return (
    <section aria-labelledby="ct-definition" className="space-y-1">
      <h2 id="ct-definition" className="text-sm font-semibold">
        {t("customTools.definition.title")}
      </h2>
      <div>
        <DefinitionRow
          label={t("customTools.definition.agentsSee")}
          value={agentPrefix(group.name)}
          mono
          copyable={false}
        />
        <div className="flex min-h-row items-center gap-3 border-b border-border-subtle">
          <span className="w-32 shrink-0 text-xs text-text-muted">
            {t("customTools.fields.availableTo")}
          </span>
          <ScopeControl
            kind="mcp_server"
            uid={group.uid}
            enabled={group.enabled}
            scope={groupScope(group)}
          />
        </div>
        <DefinitionRow label={t("customTools.fields.baseUrl")} value={group.base_url} mono />
        <DefinitionRow
          label={t("customTools.definition.auth")}
          value={auth?.secret ?? t("customTools.definition.noAuth")}
          copyable={false}
        >
          {auth?.secret ? (
            <AuthLine
              header={auth.header}
              prefix={auth.prefix}
              secret={auth.secret}
              trailing={secretBadge}
            />
          ) : (
            t("customTools.definition.noAuth")
          )}
        </DefinitionRow>
        {group.source ? (
          <DefinitionRow
            label={t("customTools.definition.spec")}
            value={group.source.location}
            mono
            trailing={
              <>
                <span className="shrink-0 text-xs text-text-muted">
                  {t("customTools.definition.fetched", {
                    date: formatDateTime(group.source.fetched_at),
                  })}
                </span>
                <button
                  type="button"
                  className="shrink-0 text-xs font-label text-accent-text hover:underline"
                  onClick={onReimport}
                >
                  {t("customTools.reimport.action")}
                </button>
              </>
            }
          />
        ) : null}
      </div>
    </section>
  );
}
