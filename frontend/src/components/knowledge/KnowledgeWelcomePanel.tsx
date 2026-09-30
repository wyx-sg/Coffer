// frontend/src/components/knowledge/KnowledgeWelcomePanel.tsx
// First run on /knowledge: nothing is written down yet. Nothing
// auto-provisions a collection (spec knowledge "Create collections only
// deliberately"), so the panel says what knowledge is and offers the one
// deliberate first step — a collection — beside the two ways documents arrive
// once one exists: an upload, and agents filing what they learn.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Library, Plus } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";

export function KnowledgeWelcomePanel({ onCreate }: { onCreate: () => void }) {
  const { t } = useTranslation();
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <EmptyState
        icon={Library}
        title={t("knowledge.welcome.title")}
        description={t("knowledge.welcome.body")}
      />
      <ul className="grid gap-3 sm:grid-cols-3">
        <WelcomeStep
          title={t("knowledge.welcome.collection.title")}
          body={t("knowledge.welcome.collection.body")}
          action={
            <Button size="sm" onClick={onCreate}>
              <Plus aria-hidden /> {t("knowledge.create.title")}
            </Button>
          }
        />
        <WelcomeStep
          title={t("knowledge.welcome.upload.title")}
          body={t("knowledge.welcome.upload.body")}
        />
        <WelcomeStep
          title={t("knowledge.welcome.agents.title")}
          body={t("knowledge.welcome.agents.body")}
          action={
            <span className="rounded-sm bg-chip px-1.5 py-0.5 text-2xs text-text-muted">
              {t("knowledge.welcome.agents.automatic")}
            </span>
          }
        />
      </ul>
    </div>
  );
}

function WelcomeStep({ title, body, action }: { title: string; body: string; action?: ReactNode }) {
  return (
    <li className="flex flex-col gap-2 rounded-xl border border-border-subtle bg-surface-raised p-4">
      <p className="text-sm font-semibold">{title}</p>
      <p className="flex-1 text-xs leading-relaxed text-text-muted">{body}</p>
      {action ? <div>{action}</div> : null}
    </li>
  );
}
