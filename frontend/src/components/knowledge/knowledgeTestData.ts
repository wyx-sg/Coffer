// frontend/src/components/knowledge/knowledgeTestData.ts — wire fixtures shared by the Knowledge page tests.
//
// Test-only data (imported by `*.test.tsx` files, never by the app): one
// collection laid out as a wiki — a page in `pages/`, a page in a folder under
// it, and a waiting source in `sources/` — plus a person's change in the other
// collection, in the generated wire shapes. The collection's uid and name are
// deliberately unlike each other: the URL carries the uid, every path is built
// from the name.
import type {
  ChangeOut,
  CollectionOut,
  FileOut,
  FileSummaryOut,
  TreeOut,
} from "@/lib/api/knowledge";

export const UID = "kn-8c1f";
export const NAME = "shopee";

export const COLLECTION: CollectionOut = {
  uid: UID,
  name: NAME,
  description: "How the shop is built.",
  page_count: 2,
  source_count: 1,
  waiting_source_count: 1,
  finding_count: 1,
  folder_path: `/home/u/.coffer/knowledge/${NAME}`,
  updated_at: "2026-09-30T13:30:00Z",
  tidy_handoff: { prompt: `Tidy the ${NAME} collection.` },
  check_handoff: { prompt: `Check the ${NAME} collection.` },
};

export const OTHER: CollectionOut = {
  uid: "kn-77aa",
  name: "runbooks",
  description: "On-call runbooks.",
  page_count: 0,
  source_count: 0,
  waiting_source_count: 0,
  finding_count: 0,
  folder_path: "/home/u/.coffer/knowledge/runbooks",
  updated_at: null,
  tidy_handoff: { prompt: "Tidy the runbooks collection." },
  check_handoff: { prompt: "Check the runbooks collection." },
};

export function file(path: string, over: Partial<FileOut> = {}): FileOut {
  return {
    path,
    kind: "page",
    title: path.split("/").pop() ?? path,
    description: "a page",
    page_type: "concept",
    aliases: [],
    sources: [],
    links: [],
    cited_by: [],
    waiting: false,
    actor: "user",
    created_at: "2026-09-12T00:00:00Z",
    updated_at: "2026-09-20T00:00:00Z",
    body: `Body of ${path}.`,
    file_path: `/Users/dev/.coffer/knowledge/${path}`,
    folder_path: `/Users/dev/.coffer/knowledge/${path.split("/").slice(0, -1).join("/")}`,
    ...over,
  };
}

export const GATEWAY = file(`${NAME}/pages/gateway.md`, {
  title: "Account Gateway",
  description: "where account decisions are made",
  body: "# Account Gateway\n\nThe orchestration layer.",
});

export const SESSION = file(`${NAME}/pages/account/session.md`, {
  title: "Session ownership",
  body: "Login state is owned by account.session.",
});

/** A source no page cites yet. */
export const RELEASE = file(`${NAME}/sources/release-notes.md`, {
  kind: "source",
  title: "Release notes",
  page_type: "",
  waiting: true,
  body: "Release notes, converted.",
});

export const FILES: Record<string, FileOut> = {
  [GATEWAY.path]: GATEWAY,
  [SESSION.path]: SESSION,
  [RELEASE.path]: RELEASE,
};

function summary(f: FileOut): FileSummaryOut {
  return {
    path: f.path,
    kind: f.kind,
    title: f.title,
    description: f.description,
    page_type: f.page_type,
    waiting: f.waiting,
    actor: f.actor,
    updated_at: f.updated_at,
  };
}

export const TREES: Record<string, TreeOut> = {
  // Listed sources-first by the daemon: the tree puts Pages first itself.
  [NAME]: {
    path: NAME,
    directories: [
      { path: `${NAME}/sources`, name: "sources", file_count: 1 },
      { path: `${NAME}/pages`, name: "pages", file_count: 2 },
    ],
    files: [],
  },
  [`${NAME}/pages`]: {
    path: `${NAME}/pages`,
    directories: [{ path: `${NAME}/pages/account`, name: "account", file_count: 1 }],
    files: [summary(GATEWAY)],
  },
  [`${NAME}/pages/account`]: {
    path: `${NAME}/pages/account`,
    directories: [],
    files: [summary(SESSION)],
  },
  [`${NAME}/sources`]: {
    path: `${NAME}/sources`,
    directories: [],
    files: [summary(RELEASE)],
  },
  [OTHER.name]: { path: OTHER.name, directories: [], files: [] },
};

export function change(over: Partial<ChangeOut>): ChangeOut {
  return {
    version: "v0",
    time: new Date().toISOString(),
    writer: "user",
    operation: "save",
    summary: "Edit",
    actor: "user",
    agent: null,
    collections: [NAME],
    item: null,
    status: null,
    restored_from: null,
    undoes: null,
    documents: [],
    ...over,
  };
}

/** A person's edit, in the other collection. */
export const EDIT = change({
  version: "e5f6a7b8",
  collections: [OTHER.name],
  documents: [{ path: `${OTHER.name}/on-call.md`, status: "modified", added: 1, removed: 1 }],
});
