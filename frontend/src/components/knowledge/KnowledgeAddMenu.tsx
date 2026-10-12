// frontend/src/components/knowledge/KnowledgeAddMenu.tsx
//
// The Knowledge page's one Add menu (spec knowledge "Add documents and
// collections from one Add menu"). Each item says what Coffer keeps: an upload
// becomes a source Coffer keeps and syncs; a new collection is a folder Coffer
// keeps; an external folder stays where it is and is only shared with the
// agents, never copied into Coffer. Upload needs a collection Coffer keeps.
import { useTranslation } from "react-i18next";
import { ChevronDown, FolderPlus, FolderSymlink, Plus, Upload } from "lucide-react";

import type { KnowledgeDialog } from "@/components/knowledge/KnowledgeDialogs";
import { Button } from "@/components/ui/button";
import { ActionMenu } from "@/components/ui/menu";

interface Props {
  onSelect: (dialog: Exclude<KnowledgeDialog, null>) => void;
  /** Whether a collection Coffer keeps exists for an upload to land in. */
  canUpload: boolean;
}

export function KnowledgeAddMenu({ onSelect, canUpload }: Props) {
  const { t } = useTranslation();
  return (
    <ActionMenu
      label={t("knowledge.add.button")}
      trigger={
        <Button aria-haspopup="menu">
          <Plus aria-hidden /> {t("knowledge.add.button")}
          <ChevronDown aria-hidden />
        </Button>
      }
      actions={[
        {
          key: "upload",
          icon: Upload,
          label: t("knowledge.add.upload"),
          description: t("knowledge.add.uploadHint"),
          onSelect: () => onSelect("upload"),
          disabled: !canUpload,
        },
        {
          key: "create",
          icon: FolderPlus,
          label: t("knowledge.add.create"),
          description: t("knowledge.add.createHint"),
          onSelect: () => onSelect("create"),
        },
        {
          key: "link",
          icon: FolderSymlink,
          label: t("knowledge.add.link"),
          description: t("knowledge.add.linkHint"),
          onSelect: () => onSelect("link"),
          separated: true,
        },
      ]}
    />
  );
}
