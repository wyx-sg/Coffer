// frontend/src/components/knowledge/KnowledgeCollectionSelect.tsx
// The collection picker of the Upload dialog; its value
// is the collection's NAME, which is what an upload is sent to
// — and what it shows, since a collection has no title.
import { useTranslation } from "react-i18next";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { CollectionOut } from "@/lib/api/knowledge";

interface Props {
  id: string;
  collections: CollectionOut[];
  value: string;
  onChange: (name: string) => void;
}

export function KnowledgeCollectionSelect({ id, collections, value, onChange }: Props) {
  const { t } = useTranslation();
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger id={id} aria-label={t("knowledge.upload.into")} className="font-mono text-xs">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {collections.map((c) => (
          <SelectItem key={c.uid} value={c.name} className="font-mono text-xs">
            {c.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
