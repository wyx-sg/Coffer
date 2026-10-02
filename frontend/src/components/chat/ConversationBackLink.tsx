// src/components/chat/ConversationBackLink.tsx — the way back out of an open
// conversation (or the draft), which fills the page: "← Conversations" to the
// list with its filters, or — when the page was opened from elsewhere (Overview,
// an agent's page) — "← Back to {that page}" (lib/origin).
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { ArrowLeft } from "lucide-react";

import { InTitleBar } from "@/components/shell/titleBarSlot";
import { useOrigin } from "@/lib/origin";

interface Props {
  /** The Conversations list, carrying the filters it was last shown with. */
  listPath: string;
}

export function ConversationBackLink({ listPath }: Props) {
  const { t } = useTranslation();
  const origin = useOrigin();
  return (
    <InTitleBar>
      <Link
        to={origin?.to ?? listPath}
        className="inline-flex shrink-0 items-center gap-1 text-xs text-text-subtle transition-colors duration-fast hover:text-text"
      >
        <ArrowLeft className="size-3.5" aria-hidden />
        {origin ? t("common.backTo", { label: origin.label }) : t("conversations.title")}
      </Link>
    </InTitleBar>
  );
}
