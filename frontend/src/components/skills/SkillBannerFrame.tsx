// frontend/src/components/skills/SkillBannerFrame.tsx
// One banner above the open skill's tab content: a tinted strip with an icon,
// a title, a body and the actions that fix the problem it states (a fix button
// lives in the banner that names the problem). Used by the dependency and
// master-folder banners (SkillDependencyBanners, SkillMasterBanner).
import type { ReactNode } from "react";
import { AlertCircle, AlertTriangle } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

interface Props {
  tone: "warning" | "error";
  title: string;
  children: ReactNode;
  /** Buttons on the right: the fix, then (for a machine problem) the hand-off. */
  actions?: ReactNode;
  testId: string;
}

export function SkillBannerFrame({ tone, title, children, actions, testId }: Props) {
  const Icon = tone === "error" ? AlertCircle : AlertTriangle;
  return (
    <Alert variant={tone} data-testid={testId}>
      <Icon aria-hidden />
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <AlertTitle>{title}</AlertTitle>
          <AlertDescription>{children}</AlertDescription>
        </div>
        {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
      </div>
    </Alert>
  );
}
