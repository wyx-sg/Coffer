// frontend/src/pages/sync/SyncRoundPathList.tsx
//
// One titled list of paths from a converge round — agent-merged paths, paths
// that could not be applied here, credential references this machine cannot
// decrypt. Three lists with the same shape and three different meanings, so
// the tone is a prop rather than three near-identical blocks in the card.
//
// Renders nothing at all when the list is empty: a round with no failures
// should not leave an empty "Could not be applied here" heading behind.
import { useTranslation } from "react-i18next";

import { cn } from "@/lib/utils";

interface Props {
  titleKey: string;
  /** An explanatory line under the title, when the list needs one. */
  hintKey?: string;
  items: string[];
  /** `warn` and `err` use the status tokens; the default is plain body text. */
  tone?: "warn" | "err";
  testId: string;
}

export function SyncRoundPathList({ titleKey, hintKey, items, tone, testId }: Props) {
  const { t } = useTranslation();
  if (items.length === 0) return null;

  return (
    <div className="space-y-1" data-testid={testId}>
      <p
        className={cn(
          "text-sm font-medium",
          tone === "err" && "text-status-err",
          tone === "warn" && "text-status-warn",
        )}
      >
        {t(titleKey)}
      </p>
      {hintKey ? <p className="text-xs text-muted-foreground">{t(hintKey)}</p> : null}
      <ul className="space-y-0.5">
        {items.map((item) => (
          <li key={item} className="font-mono text-xs">
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}
