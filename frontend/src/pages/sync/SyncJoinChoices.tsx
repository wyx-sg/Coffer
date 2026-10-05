// frontend/src/pages/sync/SyncJoinChoices.tsx — first join, differing files (6.4.23).
//
// The files a join found different here and on the remote. A join never
// overwrites either side on its own: each file stays exactly as it is here,
// and is not pushed, until a person keeps this Mac's version, takes the other
// Mac's, or merges the two. The files are not listed here: Choose versions
// opens the Resolve page in join mode, where each one's versions are read
// before choosing, and Ask an agent hands every file an agent may merge over
// in one prompt.
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { AgentHandoff } from "@/components/handoff/AgentHandoff";
import { Button } from "@/components/ui/button";
import { useHandoffRequest, useJoinChoices } from "@/lib/hooks/useSyncStop";

const RESOLVE = "/sync/conflicts?mode=join";

export function SyncJoinChoices() {
  const { t } = useTranslation();
  const { data } = useJoinChoices(true);
  const handoff = useHandoffRequest({ join: true });
  const files = data?.files ?? [];
  if (files.length === 0) return null;
  const mergeable = files.some((f) => f.agent_mergeable);

  return (
    <section
      className="flex flex-col gap-2.5"
      data-testid="sync-join-choices"
      aria-label={t("sync.joinChoices.title")}
    >
      <div className="flex items-end gap-2">
        <div className="flex flex-col gap-0.5">
          <h2 className="text-md font-semibold text-text">{t("sync.joinChoices.title")}</h2>
          <p className="text-xs text-text-muted">
            {t("sync.joinChoices.body", { count: files.length })}
          </p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <Button asChild variant="outline" size="sm">
            <Link to={RESOLVE}>{t("sync.joinChoices.choose")}</Link>
          </Button>
          {mergeable ? <AgentHandoff size="sm" prompt={({ agent }) => handoff({ agent })} /> : null}
        </div>
      </div>
    </section>
  );
}
