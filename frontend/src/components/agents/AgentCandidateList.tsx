// frontend/src/components/agents/AgentCandidateList.tsx — spec agent-registry
// two-signal detection, in the Add dialog's "Detected agents" checklist.
//
// Discovery reports every config directory with either signal — the program on
// PATH, or the directory itself — including one CLAUDE_CONFIG_DIR / CODEX_HOME
// names, so one type can appear more than once. Rows are keyed by `config_dir`.
// Only an `installed_active` candidate (program + directory) can be ticked; one
// that is installed but never run says so, and a directory without its program
// reads "Not installed". The version rides beside the name when known.
import { useTranslation } from "react-i18next";

import { Checkbox } from "@/components/ui/checkbox";
import type { AgentCandidate } from "@/lib/api/agents";
import { isAddableCandidate } from "@/lib/agents/display";

interface Props {
  candidates: AgentCandidate[];
  /** Ticked candidates, by `config_dir`. */
  selected: Set<string>;
  onToggle: (configDir: string) => void;
}

function CandidateLabel({ c }: { c: AgentCandidate }) {
  const { t } = useTranslation();
  return (
    <span className="min-w-0 flex-1">
      <span className="flex flex-wrap items-baseline gap-x-2">
        <span className="font-medium">{c.display_name}</span>
        {c.version ? (
          <span className="font-mono text-xs text-muted-foreground">{c.version}</span>
        ) : null}
      </span>
      <span className="block truncate font-mono text-xs text-muted-foreground">{c.config_dir}</span>
      {c.state === "installed_never_run" ? (
        <span className="block text-xs text-muted-foreground">
          {t("agents.detection.neverRunHint")}
        </span>
      ) : null}
    </span>
  );
}

export function AgentCandidateList({ candidates, selected, onToggle }: Props) {
  const { t } = useTranslation();
  return (
    <ul className="space-y-1">
      {candidates.map((c) =>
        isAddableCandidate(c) ? (
          <li key={c.config_dir}>
            <label className="flex cursor-pointer items-center gap-3 rounded-md border bg-card/60 px-3 py-2 text-sm">
              <Checkbox
                checked={selected.has(c.config_dir)}
                onChange={() => onToggle(c.config_dir)}
              />
              <CandidateLabel c={c} />
            </label>
          </li>
        ) : (
          <li
            key={c.config_dir}
            className="flex items-center gap-3 rounded-md border bg-card/60 px-3 py-2 text-sm text-muted-foreground"
          >
            <CandidateLabel c={c} />
            {c.state === "config_only" ? (
              <span className="shrink-0 text-xs">{t("agents.detection.notInstalled")}</span>
            ) : null}
          </li>
        ),
      )}
    </ul>
  );
}
