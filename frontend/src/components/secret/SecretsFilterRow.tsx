// src/components/secret/SecretsFilterRow.tsx — the list's filters: search, status (with counts), owner type, view, and Delete unused.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { SearchInput } from "@/components/SearchInput";
import { Segmented } from "@/components/ui/segmented";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  OWNER_KINDS,
  STATUSES,
  type SecretListState,
  type SecretStatus,
  type SecretView,
} from "@/lib/secrets/listState";
import { useOwnerLabel } from "./useOwnerLabel";

interface Props {
  state: SecretListState;
  counts: Record<SecretStatus, number>;
  onChange: (patch: Partial<SecretListState>) => void;
  /** The bulk "Delete unused…" action, shown when anything unused can go. */
  trailing?: ReactNode;
}

export function SecretsFilterRow({ state, counts, onChange, trailing }: Props) {
  const { t } = useTranslation();
  const { kindLabel } = useOwnerLabel();
  return (
    <div className="flex flex-wrap items-center gap-2">
      <SearchInput
        value={state.q}
        onChange={(q) => onChange({ q })}
        ariaLabel={t("secrets.search")}
        placeholder={t("secrets.search")}
        className="w-[220px]"
      />
      <Segmented<SecretStatus>
        label={t("secrets.filters.status.label")}
        value={state.status}
        onChange={(status) => onChange({ status })}
        options={STATUSES.map((s) => ({
          value: s,
          label: `${t(`secrets.filters.status.${s}`)} ${counts[s]}`,
        }))}
      />
      <Select
        value={state.kind}
        onValueChange={(kind) => onChange({ kind: kind as SecretListState["kind"] })}
      >
        <SelectTrigger
          aria-label={t("secrets.filters.kind.label")}
          className="h-control-sm w-auto text-xs"
        >
          <SelectValue>
            {`${t("secrets.filters.kind.label")}: ${
              state.kind === "all" ? t("secrets.filters.kind.all") : kindLabel(state.kind)
            }`}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">{t("secrets.filters.kind.all")}</SelectItem>
          {OWNER_KINDS.map((k) => (
            <SelectItem key={k} value={k}>
              {kindLabel(k)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <div className="ml-auto flex items-center gap-2">
        {trailing}
        <Segmented<SecretView>
          label={t("secrets.filters.view.label")}
          value={state.view}
          onChange={(view) => onChange({ view })}
          options={[
            { value: "list", label: t("secrets.filters.view.list") },
            { value: "owner", label: t("secrets.filters.view.byOwner") },
          ]}
        />
      </div>
    </div>
  );
}
