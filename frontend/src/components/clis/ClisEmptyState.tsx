// src/components/clis/ClisEmptyState.tsx — the CLIs page before any tool is added and before any skill declares `requires:` (board 4.4.02).
import { ExternalLink, Plus, Terminal } from "lucide-react";
import { Trans, useTranslation } from "react-i18next";

import { EmptyState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";

interface Props {
  onAdd: () => void;
}

export function ClisEmptyState({ onAdd }: Props) {
  const { t } = useTranslation();
  return (
    <EmptyState
      icon={Terminal}
      title={t("clis.empty.title")}
      description={
        <Trans
          i18nKey="clis.empty.description"
          components={{ code: <code className="font-mono text-xs" /> }}
        />
      }
      action={
        <Button onClick={onAdd}>
          <Plus aria-hidden />
          {t("clis.addTool")}
        </Button>
      }
      secondaryAction={
        <a
          href={t("clis.empty.docsUrl")}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 text-xs font-label text-accent-text hover:underline"
        >
          {t("clis.empty.docs")}
          <ExternalLink className="size-3" aria-hidden />
        </a>
      }
    />
  );
}
