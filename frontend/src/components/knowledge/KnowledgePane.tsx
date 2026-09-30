// frontend/src/components/knowledge/KnowledgePane.tsx
//
// The right side of the Knowledge page: which view the address names
// (lib/knowledge/routes.ts). One change → its diffs; a collection's Inbox;
// an open document with its Document and History tabs; a collection with no
// document open → its overview; nothing chosen → Recent changes.
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Library } from "lucide-react";

import { EmptyState } from "@/components/EmptyState";
import { KnowledgeChangeView } from "@/components/knowledge/KnowledgeChangeView";
import { KnowledgeCollectionView } from "@/components/knowledge/KnowledgeCollectionView";
import { KnowledgeDocumentPane } from "@/components/knowledge/KnowledgeDocumentPane";
import { KnowledgeInboxView } from "@/components/knowledge/KnowledgeInboxView";
import { KnowledgeRecentChanges } from "@/components/knowledge/KnowledgeRecentChanges";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { CollectionOut } from "@/lib/api/knowledge";
import { KNOWLEDGE_ROOT, type KnowledgeTab } from "@/lib/knowledge/routes";

interface Props {
  uid: string | null;
  version: string | null;
  /** The collection `uid` names, once the list has it. */
  collection: CollectionOut | null;
  collections: CollectionOut[];
  collectionsLoading: boolean;
  tab: KnowledgeTab;
  setTab: (tab: string) => void;
  file: string | null;
  modelSet: boolean | undefined;
  onAdd: () => void;
  onUpload: () => void;
}

export function KnowledgePane(props: Props) {
  const { t } = useTranslation();

  if (props.version) {
    return <KnowledgeChangeView version={props.version} collections={props.collections} />;
  }
  if (!props.uid) {
    return <KnowledgeRecentChanges collections={props.collections} modelSet={props.modelSet} />;
  }
  if (!props.collection) {
    if (props.collectionsLoading) {
      return (
        <div className="space-y-3" aria-busy>
          <Skeleton className="h-6 w-1/3" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      );
    }
    return (
      <EmptyState
        icon={Library}
        title={t("knowledge.notFound.title")}
        description={t("knowledge.notFound.body")}
        action={
          <Button asChild variant="outline">
            <Link to={KNOWLEDGE_ROOT}>{t("knowledge.recent.title")}</Link>
          </Button>
        }
      />
    );
  }
  if (props.tab === "inbox") {
    return (
      <KnowledgeInboxView
        collection={props.collection}
        file={props.file}
        modelSet={props.modelSet}
      />
    );
  }
  if (props.file) {
    return (
      <KnowledgeDocumentPane
        collection={props.collection}
        path={props.file}
        tab={props.tab === "history" ? "history" : "document"}
        setTab={props.setTab}
      />
    );
  }
  return (
    <KnowledgeCollectionView
      collection={props.collection}
      modelSet={props.modelSet}
      onAdd={props.onAdd}
      onUpload={props.onUpload}
    />
  );
}
