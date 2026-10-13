// frontend/src/lib/knowledge/lastLocation.ts
//
// Where the person was on the Knowledge page — the collection and open
// document — so the sidebar's Knowledge entry brings them back there after a
// visit to another page, instead of to the bare landing (spec knowledge "Show
// a collection as one tree of read-only documents in the web UI"). Display
// state for this window only: it lives in memory and is gone on reload, when
// the tree itself still comes back from lib/knowledge/treeState.ts.
import { KNOWLEDGE_ROOT } from "@/lib/knowledge/routes";

let last: string = KNOWLEDGE_ROOT;

/** Remember the address of a Knowledge page the person is on. */
export function rememberKnowledgeLocation(pathname: string, search: string): void {
  last = `${pathname}${search}`;
}

/** Forget it, e.g. when its collection no longer exists. */
export function forgetKnowledgeLocation(): void {
  last = KNOWLEDGE_ROOT;
}

/** The address the sidebar's Knowledge entry goes to. */
export function knowledgeLocation(): string {
  return last;
}
