// frontend/src/lib/workflow/contextRows.ts
// One row model over the two things a run's page used to show in two tabs:
// what it READS (mounted inputs) and what it WROTE (artifacts).
//
// They were separate tabs because they arrive from separate routes, which is a
// fact about the API and not about the work. To the developer they are one
// question — what is this delivery made of — so they are one table, and what
// distinguishes a row is its ORIGIN: a thing you mounted, or a thing a task
// produced. Only the first can be unmounted, which is the one behavioural
// difference the table has to carry.
import type { Artifact, RunInput, RunInputKind } from "@/lib/api/workflow";

/** An artifact's kind, alongside the four an input can have. */
export type ContextKind = RunInputKind | "artifact";

/** Mounted by the developer, or produced by a task. The one difference the
 *  table has to act on: only the first can be unmounted. */
type ContextOrigin = "mounted" | "produced";

/**
 * What clicking a row does, which is a property of the KIND and not of the
 * table: a collection is a page in this vault, a link is somewhere else
 * entirely, a file is bytes only the daemon can reach, and a repository is a
 * directory on this machine that belongs in a file manager rather than in a
 * dialog. A row that did the same thing for all four would be a row that did
 * the wrong thing for three.
 */
type ContextOpen =
  /** Show the contents. `path` is relative to the run's own directory. */
  | { how: "preview"; path: string }
  /** Open the developer's own note, where it can also be rewritten. */
  | { how: "note"; ref: string }
  /** Go to the knowledge collection's own page. */
  | { how: "collection"; name: string }
  /** Leave the app. */
  | { how: "url"; href: string }
  /** Show an absolute path on this machine in the OS file manager. */
  | { how: "reveal"; path: string };

export interface ContextRow {
  id: string;
  kind: ContextKind;
  origin: ContextOrigin;
  /** What this is, in the developer's words when they gave any. */
  name: string;
  /** Where it actually is: a collection name, a URL, or a path. Null when
   *  that would only repeat `name` — an unlabelled link IS its URL, and
   *  printing it twice in one row is noise, not information. */
  where: string | null;
  /** Bytes, when anything knows them — a link and a collection do not. */
  size: number | null;
  /** The input this row is, so the table can unmount it. Null for artifacts. */
  input: RunInput | null;
  /** Which task wrote it, and when. Null for a mounted input. */
  produced: { nodeKey: string; attempt: number; at: string } | null;
  /** What clicking it does, or null when there is nothing to open. */
  open: ContextOpen | null;
  /** For a link: what the daemon recognised it as — `confluence`, `jira`,
   *  `google_docs` … — or null when nothing is known beyond the address.
   *  Never computed here: the daemon derives it, tells the NODE the
   *  same thing, and a second table in this language would drift from it. */
  provider: string | null;
}

/** Where an input's row leads. A repository with no checkout recorded leads
 *  nowhere: there is no directory to reveal yet. */
function openFor(input: RunInput): ContextOpen | null {
  switch (input.kind) {
    case "knowledge":
      return { how: "collection", name: input.ref };
    case "link":
      return { how: "url", href: input.ref };
    case "file":
      // The upload landed under the run's own `inputs/`, and its ref is the
      // name the store chose there.
      return { how: "preview", path: `inputs/${input.ref}` };
    case "note":
      // Not a preview: a note is the developer's own writing and stays theirs
      // to change, so its row leads to the page that can also write it.
      return { how: "note", ref: input.ref };
    case "repo":
      return input.path ? { how: "reveal", path: input.path } : null;
  }
}

function fromInput(input: RunInput): ContextRow {
  return {
    // Kind AND ref: a collection and an uploaded file may share a name, and a
    // row that changes identity when another is removed loses its React state.
    id: `input:${input.kind}:${input.ref}`,
    kind: input.kind,
    origin: "mounted",
    name: input.label ?? input.ref,
    // A repository's `ref` is where it came FROM; `path` is the checkout the
    // run was given. The checkout is what a task opens, so that is "where".
    where:
      input.label === null || input.label === undefined
        ? (input.path ?? null)
        : (input.path ?? input.ref),
    size: input.size ?? null,
    input,
    produced: null,
    open: openFor(input),
    provider: input.provider ?? null,
  };
}

function fromArtifact(artifact: Artifact): ContextRow {
  return {
    id: `artifact:${artifact.node_key}:${artifact.attempt}:${artifact.path}`,
    kind: "artifact",
    origin: "produced",
    name: artifact.name,
    where: artifact.path,
    size: artifact.size,
    input: null,
    produced: {
      nodeKey: artifact.node_key,
      attempt: artifact.attempt,
      at: artifact.modified_at,
    },
    // `ArtifactOut.path` is relative to the ARTIFACT root, and the preview
    // route reads relative to the run — hence the one prefix.
    open: { how: "preview", path: `artifacts/${artifact.path}` },
    provider: null,
  };
}

/**
 * Inputs first, then artifacts.
 *
 * Not sorted by name or time: the inputs are what the run was pointed at and
 * the artifacts are what came out of it, so reading the table top to bottom is
 * reading the delivery in the direction it ran. Within each half the server's
 * own order is kept — the artifact catalogue is generated from disk,
 * and re-sorting it here would be this table inventing an order the context
 * the agents actually receive does not have.
 */
export function buildContextRows(inputs: RunInput[], artifacts: Artifact[]): ContextRow[] {
  return [...inputs.map(fromInput), ...artifacts.map(fromArtifact)];
}
