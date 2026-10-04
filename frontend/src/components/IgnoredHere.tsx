// src/components/IgnoredHere.tsx — under a page's header: what was ignored on Overview for this page.
//
// One muted line per ignored item that belongs to the page, with a small
// "Show it again" button that puts it back on Overview. A reason is a full
// sentence, so its closing period is dropped before the dash follows it.
import { useTranslation } from "react-i18next";

import { useUnignoreAttention } from "@/lib/hooks/useAttentionIgnore";
import { useIgnoredHere } from "@/lib/overview/useIgnoredHere";

export function IgnoredHere() {
  const { t } = useTranslation();
  const ignored = useIgnoredHere();
  const unignore = useUnignoreAttention();
  if (ignored.length === 0) return null;
  return (
    <div className="flex flex-col gap-0.5">
      {ignored.map((item) => (
        <p key={item.key} className="text-xs text-text-subtle">
          {t("overview.needsYou.ignoredHere", { reason: item.reason.replace(/\.$/, "") })}{" "}
          <button
            type="button"
            className="font-label text-text-muted underline-offset-2 hover:underline disabled:opacity-50"
            disabled={unignore.isPending}
            onClick={() => unignore.mutate(item.key)}
          >
            {t("overview.needsYou.showAgain")}
          </button>
        </p>
      ))}
    </div>
  );
}
