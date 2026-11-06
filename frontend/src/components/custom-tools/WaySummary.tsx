// src/components/custom-tools/WaySummary.tsx — the first step's choice (a request by hand, into which group),
// restated at the top of the request form, with Change to go back to it.
import { useTranslation } from "react-i18next";
import { List } from "lucide-react";

interface Props {
  /** The group the way ends in, named after the title: "· into deploy-api". */
  into?: string;
  /** Written after the title as "· new group" when there is no group yet. */
  newGroup?: boolean;
  /** The line under the way's title. */
  sub: string;
  onChange: () => void;
}

export function WaySummary({ into, newGroup = false, sub, onChange }: Props) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-3 rounded-lg bg-surface-sunken px-3 py-2.5">
      <span className="inline-flex size-8 shrink-0 items-center justify-center rounded-lg border border-border-subtle bg-surface-raised text-text-muted">
        <List className="size-4" aria-hidden />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-label text-text">
          {t("customTools.ways.handTitle")}
          {into ? ` · ${t("customTools.add.into", { group: into })}` : null}
          {newGroup ? ` · ${t("customTools.add.newGroupTag")}` : null}
        </span>
        <span className="block text-xs text-text-muted">{sub}</span>
      </span>
      <button
        type="button"
        className="text-xs font-label text-accent-text hover:underline"
        onClick={onChange}
      >
        {t("customTools.add.change")}
      </button>
    </div>
  );
}
