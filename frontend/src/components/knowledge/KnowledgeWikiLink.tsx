// frontend/src/components/knowledge/KnowledgeWikiLink.tsx
//
// The link element of a knowledge page's rendered body (spec knowledge "Show a
// collection as one tree of read-only documents in the web UI"). A `[[link]]`
// (lib/knowledge/wikiLinks.ts) opens the file the daemon resolved it to, in
// the same pane; one that names nothing, or more than one file, is drawn in
// the danger tone with a tooltip saying which. Any other link is the
// renderer's ordinary link, opening in a new window.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { LinkRefOut } from "@/lib/api/knowledge";
import { collectionPath } from "@/lib/knowledge/routes";
import { resolveWikiLink } from "@/lib/knowledge/wikiLinks";

const WIKI_LINK_CLASS = "text-accent-text underline underline-offset-2";

interface Props {
  collectionUid: string;
  links: LinkRefOut[];
  target: string;
  children: ReactNode;
}

export function KnowledgeWikiLink({ collectionUid, links, target, children }: Props) {
  const { t } = useTranslation();
  const link = resolveWikiLink(links, target);
  if (link?.path && !link.ambiguous) {
    return (
      <Link to={collectionPath(collectionUid, link.path)} className={WIKI_LINK_CLASS}>
        {children}
      </Link>
    );
  }
  const ambiguous = Boolean(link?.ambiguous);
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          tabIndex={0}
          data-link={ambiguous ? "ambiguous" : "dead"}
          className="cursor-help text-danger underline decoration-dotted underline-offset-2"
        >
          {children}
        </span>
      </TooltipTrigger>
      <TooltipContent>
        {t(ambiguous ? "knowledge.link.ambiguous" : "knowledge.link.dead", { target })}
      </TooltipContent>
    </Tooltip>
  );
}
