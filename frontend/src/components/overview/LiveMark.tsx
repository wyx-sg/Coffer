// src/components/overview/LiveMark.tsx — the Overview header's "● Live · checked 14:06" mark.
//
// Live while the daemon's event stream is open, so the page will change on
// its own; the time is when the attention list was last read. It sits in a
// <time> element so visual tests can mask it.
import { useTranslation } from "react-i18next";

import { StatusWord } from "@/components/status/StatusWord";
import { formatClock } from "@/lib/overview/time";

interface Props {
  live: boolean;
  /** When the attention list was last fetched (epoch ms); 0 = not yet. */
  checkedAt: number;
}

export function LiveMark({ live, checkedAt }: Props) {
  const { t } = useTranslation();
  const iso = checkedAt > 0 ? new Date(checkedAt).toISOString() : null;
  return (
    <p className="flex items-center gap-1.5 text-xs text-text-muted" data-testid="overview-live">
      <StatusWord tone={live ? "ok" : "off"}>
        {live ? t("overview.live.on") : t("overview.live.off")}
      </StatusWord>
      {iso ? (
        <>
          <span aria-hidden>·</span>
          <span>
            {t("overview.live.checked")} <time dateTime={iso}>{formatClock(iso)}</time>
          </span>
        </>
      ) : null}
    </p>
  );
}
