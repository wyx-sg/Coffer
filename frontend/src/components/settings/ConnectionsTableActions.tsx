// frontend/src/components/settings/ConnectionsTableActions.tsx
// Row + bulk actions for ConnectionsTable, kept out of that file so it stays
// within its size budget (mirrors SkillsTableActions). Per row: the connection's
// reach — the same three-state ScopeControl every other kind's row carries,
// replacing the plain enable Switch, which could not say "offer this endpoint
// to exactly these agents" (there is still NO per-row "activate": which model an
// agent runs on is chosen on the Agent detail → Overview tab) + Delete (the
// styled confirm is hoisted to the table). Bulk: that same reach control over
// the selection + delete, fanned out with useBulkMutate so one failure never
// aborts the rest.
import { useTranslation } from "react-i18next";

import { BulkReachActions } from "@/components/reach/BulkReachActions";
import { ScopeControl } from "@/components/ScopeControl";
import { BulkDeleteButton } from "@/components/table/BulkDeleteButton";
import { RowDeleteButton } from "@/components/table/RowDeleteButton";
import { providersApi, type Provider } from "@/lib/api/providers";
import { useBulkMutate } from "@/lib/hooks/useBulkMutate";
import type { ResourceReach } from "@/lib/hooks/useResources";

export const PROVIDER_KIND = "provider";

/** Per-row reach control; stops propagation so neither a segment click nor a
 *  checkbox inside the popover (a React portal still bubbles through the React
 *  tree) triggers the row's navigate-to-detail click.
 *
 *  `scope` is not on the /providers payload — it is a generic Resource field —
 *  so the table merges it in from one `GET /resources?kind=provider` and passes
 *  it here, keeping the control's own per-resource GET switched off. */
export function ConnectionStatusCell({
  provider,
  reach,
}: {
  provider: Provider;
  reach: ResourceReach | undefined;
}) {
  return (
    <div className="flex justify-end" onClick={(e) => e.stopPropagation()}>
      <ScopeControl
        kind={PROVIDER_KIND}
        name={provider.name}
        enabled={provider.enabled}
        scope={reach?.scope ?? null}
      />
    </div>
  );
}

/** The per-row action: Delete (confirm). The dialog it opens is rendered at the
 *  table level so closing it can't fall through to the row's navigation. */
export function ConnectionRowActions({
  provider,
  onDelete,
  deleteDisabled,
}: {
  provider: Provider;
  onDelete: () => void;
  deleteDisabled: boolean;
}) {
  const { t } = useTranslation();

  return (
    <div className="flex items-center justify-end gap-2">
      <RowDeleteButton
        ariaLabel={`${t("common.delete")}: ${provider.name}`}
        disabled={deleteDisabled}
        onDelete={onDelete}
      />
    </div>
  );
}

/** Selection-bar actions: the selection's reach + Delete the selected. */
export function ConnectionsBulkActions({
  providers,
  onDone,
}: {
  providers: Provider[];
  onDone: () => void;
}) {
  const { t } = useTranslation();
  const bulk = useBulkMutate({ invalidate: [["providers"]] });

  return (
    <>
      <BulkReachActions
        rows={providers.map((p) => ({ kind: PROVIDER_KIND, name: p.name }))}
        invalidate={[["providers"]]}
        onDone={onDone}
      />
      <BulkDeleteButton
        title={t("settings.connections.deleteTitle")}
        description={t("settings.connections.bulkDeleteConfirm", { count: providers.length })}
        pending={bulk.isPending}
        onConfirm={async () => {
          await bulk.run(providers, (p) => providersApi.remove(p.name));
          onDone();
        }}
      />
    </>
  );
}
