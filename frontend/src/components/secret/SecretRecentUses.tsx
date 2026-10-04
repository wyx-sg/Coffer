// src/components/secret/SecretRecentUses.tsx — the Usage tab: where this Mac last handed the value out.
//
// The list is fetched from the audit log when the tab opens. One line per use, newest first: the kind's icon, the resource's name (opening its page when the
// kind has one and it is open) or `coffer run <command>` with its directory, the slot it went to,
// and when (spec web-ui "Manage stored secrets on the Secrets page").
import { Terminal } from "lucide-react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

import { RelativeTime } from "@/components/RelativeTime";
import type { SecretUse } from "@/lib/api/secret";
import { useSecretUses } from "@/lib/hooks/useSecrets";
import { useKindPageOpen } from "@/lib/hooks/useFeatures";
import { kindMeta } from "@/lib/overview/kinds";
import { cn } from "@/lib/utils";
import { citerHref } from "./secretRows";
import { useKindLabel } from "./useKindLabel";

const LINE = "flex h-8 items-center gap-2 rounded-md px-2";

function UseLine({ use }: { use: SecretUse }) {
  const { t } = useTranslation();
  const kindLabel = useKindLabel();
  const pageOpen = useKindPageOpen();
  const kind = use.destination_kind;
  const run = kind === "run";
  const Icon = run ? Terminal : kindMeta(kind).icon;
  const href = run ? null : citerHref(kind, use.destination_name, use.destination_uid ?? "");
  const name = run
    ? t("secrets.detail.runCommand", { command: use.argv0 ?? use.destination_name })
    : use.destination_name;
  const body = (
    <>
      <Icon className="size-3.5 shrink-0 text-text-subtle" aria-hidden />
      <span className="min-w-0 truncate text-sm text-text">{name}</span>
      {run && use.cwd ? (
        <span className="min-w-0 flex-1 truncate font-mono text-xs text-text-subtle">
          {use.cwd}
        </span>
      ) : (
        <span className="min-w-0 flex-1 truncate text-xs text-text-subtle">
          {use.slot ?? (run ? "" : kindLabel(kind))}
        </span>
      )}
      <RelativeTime iso={use.at} className="shrink-0 text-xs text-text-muted" />
    </>
  );
  if (!href || !pageOpen(kind)) return <li className={LINE}>{body}</li>;
  return (
    <li>
      <Link
        to={href}
        className={cn(
          LINE,
          "hover:bg-surface-hover focus-visible:bg-surface-hover focus-visible:outline-none",
        )}
      >
        {body}
      </Link>
    </li>
  );
}

export function SecretRecentUses({ secretRef }: { secretRef: string }) {
  const { t } = useTranslation();
  const uses = useSecretUses(secretRef);
  const list = uses.data ?? [];
  return (
    <section className="space-y-2" aria-label={t("secrets.tabs.usage")}>
      {uses.isPending ? null : list.length === 0 ? (
        <p className="text-xs text-text-muted">{t("secrets.detail.notUsedHere")}</p>
      ) : (
        <ul>
          {list.map((u, i) => (
            <UseLine key={`${u.at}:${i}`} use={u} />
          ))}
        </ul>
      )}
      <Link
        to={`/activity?tab=changes&q=${encodeURIComponent(secretRef)}`}
        className="inline-block text-xs text-accent-text hover:underline"
      >
        {t("secrets.detail.viewAllActivity")}
      </Link>
    </section>
  );
}
