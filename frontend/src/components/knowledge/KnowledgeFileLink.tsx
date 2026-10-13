// frontend/src/components/knowledge/KnowledgeFileLink.tsx
//
// A standard relative link in a knowledge file's rendered body
// (lib/knowledge/fileLinks.ts). One the daemon resolved to a file opens it in
// the reader, in its own collection; one that leaves the knowledge folder, or
// names no file, is plain text with a tooltip saying which — a relative path
// is never handed to the browser to open.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import type { LinkRefOut } from "@/lib/api/knowledge";
import { resolveFileLink } from "@/lib/knowledge/fileLinks";
import { collectionPath } from "@/lib/knowledge/routes";
import { useKnowledgeCollections } from "@/lib/hooks/useKnowledge";

interface Props {
  /** The collection the open file is in, and its directory name. */
  collectionUid: string;
  collectionName: string;
  links: LinkRefOut[];
  href: string;
  children: ReactNode;
}

export function KnowledgeFileLink({ collectionUid, collectionName, links, href, children }: Props) {
  const { t } = useTranslation();
  const collections = useKnowledgeCollections();
  const link = resolveFileLink(links, href);
  const path = link && !link.outside ? link.path : null;
  const directory = path?.split("/")[0];
  const uid =
    directory === collectionName
      ? collectionUid
      : collections.data?.find((c) => c.name === directory)?.uid;
  if (path && uid && path.includes("/")) {
    return (
      <Link
        to={collectionPath(uid, path)}
        data-link="file"
        className="text-accent-text underline underline-offset-2"
      >
        {children}
      </Link>
    );
  }
  return (
    <span
      data-link={link?.outside ? "outside" : "unresolved"}
      title={t(link?.outside ? "knowledge.link.outside" : "knowledge.link.noFile", {
        target: href,
      })}
      className="underline decoration-dotted underline-offset-2"
    >
      {children}
    </span>
  );
}
