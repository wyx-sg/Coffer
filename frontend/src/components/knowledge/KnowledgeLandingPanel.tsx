// frontend/src/components/knowledge/KnowledgeLandingPanel.tsx
// The Knowledge page with collections but none open (the bare /knowledge
// address): the tree on the left lists them, and this says to pick one. There
// is no Recent changes view (spec knowledge "Show a collection as one tree of
// read-only documents in the web UI") — history is git's.
import { Book } from "lucide-react";
import { useTranslation } from "react-i18next";

import { EmptyState } from "@/components/EmptyState";

export function KnowledgeLandingPanel() {
  const { t } = useTranslation();
  return (
    <EmptyState
      icon={Book}
      title={t("knowledge.landing.title")}
      description={t("knowledge.landing.body")}
      className="min-h-full"
    />
  );
}
