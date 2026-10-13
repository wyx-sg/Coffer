// frontend/src/components/knowledge/KnowledgeLink.tsx
//
// Every link in an open knowledge file (spec knowledge "Link pages by slug or
// relative path and check every link"):
//
// - a `[[link]]` opens the file the daemon resolved it to (KnowledgeWikiLink);
// - a link by relative path opens the file it names in the Knowledge page,
//   in whichever collection that is; one that names nothing, or climbs out
//   of the knowledge root, is drawn in the danger tone with a tooltip saying
//   which, like a dead `[[link]]`;
// - a web link opens in the browser. In the desktop app the daemon opens it
//   in the default browser (its webview opens no window of its own, which is
//   why such a link once did nothing there); in a browser tab, a new tab.
import type { MouseEvent, ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import { KnowledgeWikiLink } from "@/components/knowledge/KnowledgeWikiLink";
import { useToast } from "@/components/ui/toast";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { fsApi } from "@/lib/api/fs";
import type { LinkRefOut } from "@/lib/api/knowledge";
import { useKnowledgeCollections } from "@/lib/hooks/useKnowledge";
import { isWebLink, pathTargetOf, resolvePathLink } from "@/lib/knowledge/pathLinks";
import { collectionPath } from "@/lib/knowledge/routes";
import { wikiTargetOf } from "@/lib/knowledge/wikiLinks";
import { inDesktopShell } from "@/lib/tauri";

const LINK_CLASS = "text-accent-text underline underline-offset-2";

interface Props {
  href: string | undefined;
  title?: string;
  children: ReactNode;
  /** The open file's knowledge path and its resolved links. */
  documentPath: string;
  links: LinkRefOut[];
  /** The collection the file is in. */
  collectionUid: string;
}

export function WebLink({
  href,
  title,
  children,
}: {
  href: string;
  title?: string;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const { toast } = useToast();
  const onClick = (event: MouseEvent<HTMLAnchorElement>) => {
    if (!inDesktopShell()) return;
    event.preventDefault();
    void fsApi.openUrl(href).catch(() => toast.error(t("knowledge.link.openFailed")));
  };
  return (
    <a
      className={LINK_CLASS}
      href={href}
      title={title}
      target="_blank"
      rel="noreferrer"
      onClick={onClick}
    >
      {children}
    </a>
  );
}

function BrokenLink({
  outside,
  target,
  children,
}: {
  outside: boolean;
  target: string;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          tabIndex={0}
          data-link={outside ? "outside" : "dead"}
          className="cursor-help text-danger underline decoration-dotted underline-offset-2"
        >
          {children}
        </span>
      </TooltipTrigger>
      <TooltipContent>
        {t(outside ? "knowledge.link.outside" : "knowledge.link.deadPath", { target })}
      </TooltipContent>
    </Tooltip>
  );
}

export function KnowledgeLink({
  href,
  title,
  children,
  documentPath,
  links,
  collectionUid,
}: Props) {
  const collections = useKnowledgeCollections();
  const wiki = wikiTargetOf(href);
  if (wiki !== null) {
    return (
      <KnowledgeWikiLink collectionUid={collectionUid} links={links} target={wiki}>
        {children}
      </KnowledgeWikiLink>
    );
  }
  if (href && isWebLink(href)) {
    return (
      <WebLink href={href} title={title}>
        {children}
      </WebLink>
    );
  }
  const target = pathTargetOf(href);
  if (target === null) {
    // An anchor on this page, or a scheme no reader here opens: as written.
    return (
      <a className={LINK_CLASS} href={href} title={title}>
        {children}
      </a>
    );
  }
  const link = resolvePathLink(links, documentPath, target);
  if (link.state !== "file") {
    return (
      <BrokenLink outside={link.state === "outside"} target={target}>
        {children}
      </BrokenLink>
    );
  }
  // A file in another collection opens there, addressed by that collection's uid.
  const name = link.path.split("/")[0];
  const here = documentPath.split("/")[0];
  const uid = name === here ? collectionUid : collections.data?.find((c) => c.name === name)?.uid;
  if (!uid) {
    return (
      <BrokenLink outside target={target}>
        {children}
      </BrokenLink>
    );
  }
  return (
    <Link to={collectionPath(uid, link.path)} className={LINK_CLASS} title={title}>
      {children}
    </Link>
  );
}
