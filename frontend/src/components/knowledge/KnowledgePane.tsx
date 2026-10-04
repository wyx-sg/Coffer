// frontend/src/components/knowledge/KnowledgePane.tsx
//
// The right side of the Knowledge page: which view the address names
// (lib/knowledge/routes.ts). One change → its diffs; a collection's Inbox;
// an open document with its Document and History tabs; a collection with no
// document open → its overview; nothing chosen → Recent changes.
import { Book } from "lucide-react";

import { DetailNotFound } from "@/components/DetailNotFound";
import { KnowledgeChangeView } from "@/components/knowledge/KnowledgeChangeView";
import { KnowledgeCollectionView } from "@/components/knowledge/KnowledgeCollectionView";
import { KnowledgeDocumentPane } from "@/components/knowledge/KnowledgeDocumentPane";
import { KnowledgeInboxView } from "@/components/knowledge/KnowledgeInboxView";
import { KnowledgeRecentChanges } from "@/components/knowledge/KnowledgeRecentChanges";
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
  file: string | null;
  modelSet: boolean | undefined;
}

export function KnowledgePane(props: Props) {
  if (props.version) {
    return <KnowledgeChangeView version={props.version} collections={props.collections} />;
  }
  if (!props.uid) {
    return <KnowledgeRecentChanges collections={props.collections} modelSet={props.modelSet} />;
  }
  if (!props.collection) {
    if (props.collectionsLoading) {
      return (
        <div className="space-y-3 p-6" aria-busy>
          <Skeleton className="h-6 w-1/3" />
          <Skeleton className="h-4 w-2/3" />
        </div>
      );
    }
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center p-6">
        <DetailNotFound kind="knowledge" id={props.uid} backTo={KNOWLEDGE_ROOT} icon={Book} />
      </div>
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
      />
    );
  }
  return (
    <KnowledgeCollectionView collection={props.collection} modelSet={props.modelSet} />
  );
}
