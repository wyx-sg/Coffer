// frontend/src/components/knowledge/KnowledgeWelcomePanel.tsx
// First run on /knowledge (board 5.1.20): nothing is written down yet. Nothing
// auto-provisions a collection (spec knowledge "Create collections only
// deliberately"), so the panel says what knowledge is and lists, as one card of
// rows, the deliberate first step — a collection — beside the two ways
// documents arrive: an upload, and agents filing what they learn. An upload
// needs a collection to land in, so with none yet its button starts one first.
import type { ReactNode } from "react";
import { Trans, useTranslation } from "react-i18next";
import { Bot, FolderPlus, Library, Upload } from "lucide-react";

import { Button } from "@/components/ui/button";

interface Props {
  onCreate: () => void;
  onUpload: () => void;
}

export function KnowledgeWelcomePanel({ onCreate, onUpload }: Props) {
  const { t } = useTranslation();
  return (
    <div className="mx-auto flex w-full max-w-[560px] flex-col gap-1 px-4 py-7">
      <div className="flex min-h-[220px] flex-col items-center justify-center gap-3 text-center">
        <span className="inline-flex size-10 items-center justify-center rounded-lg border border-border-subtle bg-surface-sunken text-text-muted">
          <Library className="size-5" aria-hidden />
        </span>
        <div className="flex max-w-[360px] flex-col gap-1">
          <p className="text-[15px] font-semibold">{t("knowledge.welcome.title")}</p>
          <p className="text-sm leading-normal text-text-muted">{t("knowledge.welcome.body")}</p>
        </div>
      </div>
      <ul className="divide-y divide-border-subtle overflow-hidden rounded-lg border border-border bg-surface-raised">
        <WelcomeStep
          icon={<FolderPlus className="size-4" aria-hidden />}
          title={t("knowledge.welcome.collection.title")}
          body={t("knowledge.welcome.collection.body")}
          action={
            <Button size="sm" onClick={onCreate}>
              {t("knowledge.create.title")}
            </Button>
          }
        />
        <WelcomeStep
          icon={<Upload className="size-4" aria-hidden />}
          title={t("knowledge.welcome.upload.title")}
          body={t("knowledge.welcome.upload.body")}
          action={
            <Button size="sm" variant="outline" onClick={onUpload}>
              {t("knowledge.upload.button")}
            </Button>
          }
        />
        <WelcomeStep
          icon={<Bot className="size-4" aria-hidden />}
          title={t("knowledge.welcome.agents.title")}
          body={
            <Trans
              i18nKey="knowledge.welcome.agents.body"
              components={{
                code: (
                  <code className="rounded-xs bg-chip px-1 py-px font-mono text-xs text-text" />
                ),
              }}
            />
          }
          action={
            <span className="text-xs text-text-muted">
              {t("knowledge.welcome.agents.automatic")}
            </span>
          }
        />
      </ul>
    </div>
  );
}

function WelcomeStep({
  icon,
  title,
  body,
  action,
}: {
  icon: ReactNode;
  title: string;
  body: ReactNode;
  action: ReactNode;
}) {
  return (
    <li className="flex min-h-[60px] items-center gap-3 px-3.5 py-2">
      <span className="inline-flex size-7 shrink-0 items-center justify-center rounded-lg border border-border-subtle bg-surface-sunken text-text-muted">
        {icon}
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="text-sm">{title}</span>
        <span className="text-xs text-text-muted">{body}</span>
      </div>
      <span className="ml-auto flex shrink-0 items-center gap-2">{action}</span>
    </li>
  );
}
