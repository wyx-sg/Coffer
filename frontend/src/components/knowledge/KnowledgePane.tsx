// frontend/src/components/knowledge/KnowledgePane.tsx
//
// The right side of the Knowledge page: which view the address names
// (lib/knowledge/routes.ts). An open file, read-only, with its history drawer
// when the address names it; a collection with no file open → its overview;
// nothing chosen → a line saying to pick one.
import { Book } from "lucide-react";

import { DetailNotFound } from "@/components/DetailNotFound";
import { KnowledgeCollectionView } from "@/components/knowledge/KnowledgeCollectionView";
import { KnowledgeDocumentPane } from "@/components/knowledge/KnowledgeDocumentPane";
import { KnowledgeLandingPanel } from "@/components/knowledge/KnowledgeLandingPanel";
import { Skeleton } from "@/components/ui/skeleton";
import type { CollectionOut } from "@/lib/api/knowledge";
import { KNOWLEDGE_ROOT } from "@/lib/knowledge/routes";

interface Props {
  uid: string | null;
  /** The collection `uid` names, once the list has it. */
  collection: CollectionOut | null;
  collectionsLoading: boolean;
  file: string | null;
}

export function KnowledgePane(props: Props) {
  if (!props.uid) {
    return <KnowledgeLandingPanel />;
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
  if (props.file) {
    return <KnowledgeDocumentPane collection={props.collection} path={props.file} />;
  }
  return <KnowledgeCollectionView collection={props.collection} />;
}
