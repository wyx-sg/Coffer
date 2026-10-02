// src/components/chat/FilesChangedCard.tsx — "Files changed" under an
// agent's reply: each file its tool calls wrote, with the lines added and
// removed (lib/conversations/filesChanged). Nothing renders for a reply that
// changed no file.
import { useTranslation } from "react-i18next";
import { FileText } from "lucide-react";

import { Section } from "@/components/Section";
import { LineCounts } from "@/components/change-preview/LineCounts";
import type { FileChange } from "@/lib/conversations/filesChanged";

export function FilesChangedCard({ files }: { files: FileChange[] }) {
  const { t } = useTranslation();
  if (files.length === 0) return null;
  return (
    <Section
      title={t("conversations.files.title")}
      gap="tight"
      labelled
      className="overflow-hidden rounded-lg border border-border-subtle bg-surface-raised text-xs [&>div:first-child]:border-b [&>div:first-child]:border-border-subtle [&>div:first-child]:px-3"
    >
      <ul>
        {files.map((f) => (
          <li
            key={f.path}
            className="flex h-8 items-center gap-2 border-b border-border-subtle px-3 last:border-b-0"
          >
            <FileText className="size-3.5 shrink-0 text-text-subtle" aria-hidden />
            <span className="min-w-0 flex-1 truncate font-mono text-text">{f.path}</span>
            <LineCounts added={f.added} removed={f.removed} />
          </li>
        ))}
      </ul>
    </Section>
  );
}
