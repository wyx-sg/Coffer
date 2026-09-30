// src/components/credentials/SecretsGroups.tsx — the list, in two groups: in use, and not used by anything.
//
// A secret nothing references (spec secret "List every stored and cited
// secret with what uses it", `unreferenced`) is listed apart, marked safe to
// delete. The page's search filters both groups.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import type { CredentialRef } from "@/lib/api/credentials";
import type { SecretRowAction } from "./SecretRowMenu";
import { SecretsTable } from "./SecretsTable";
import { groupRows } from "./secretRows";

interface Props {
  rows: CredentialRef[];
  /** Refs whose new value, or whose adding, waits for approval. */
  waiting: ReadonlySet<string>;
  query: string;
  isLoading: boolean;
  onAction: (action: SecretRowAction, row: CredentialRef) => void;
}

function Group({
  id,
  title,
  count,
  hint,
  children,
}: {
  id: string;
  title: string;
  count?: number;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <section aria-labelledby={id} className="space-y-1.5">
      <div className="flex min-h-control-md items-center gap-2">
        <h2 id={id} className="text-sm font-semibold text-text">
          {title}
        </h2>
        {count !== undefined ? <span className="text-xs text-text-muted">{count}</span> : null}
        {hint ? <span className="text-xs text-text-muted">· {hint}</span> : null}
      </div>
      {children}
    </section>
  );
}

export function SecretsGroups({ rows, waiting, query, isLoading, onAction }: Props) {
  const { t } = useTranslation();
  const { inUse, unused } = groupRows(rows, query);
  const noMatch = t("secrets.noMatch");
  return (
    <div className="space-y-6">
      <Group
        id="secrets-in-use"
        title={t("secrets.groups.inUse")}
        count={isLoading ? undefined : inUse.length}
      >
        <SecretsTable
          rows={inUse}
          waiting={waiting}
          isLoading={isLoading}
          emptyMessage={query ? noMatch : t("secrets.groups.inUseEmpty")}
          onAction={onAction}
        />
      </Group>
      {!isLoading && unused.length > 0 ? (
        <Group
          id="secrets-unused"
          title={t("secrets.groups.unused")}
          count={unused.length}
          hint={t("secrets.groups.unusedHint")}
        >
          <SecretsTable
            rows={unused}
            waiting={waiting}
            emptyMessage={noMatch}
            onAction={onAction}
          />
        </Group>
      ) : null}
    </div>
  );
}
