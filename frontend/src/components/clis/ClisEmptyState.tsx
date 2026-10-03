// src/components/clis/ClisEmptyState.tsx — the CLIs page before any tool is added and before any skill declares `requires:`.
import { ExternalLink, Plus, Terminal } from "lucide-react";
import { useTranslation } from "react-i18next";

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
      description={t("clis.empty.description")}
      action={
        <Button onClick={onAdd}>
          <Plus aria-hidden />
          {t("clis.addTool")}
        </Button>
      }
      secondaryAction={
        <Button variant="outline" asChild>
          <a href={t("clis.empty.docsUrl")} target="_blank" rel="noreferrer">
            <ExternalLink aria-hidden />
            {t("clis.empty.docs")}
          </a>
        </Button>
      }
    />
  );
}
