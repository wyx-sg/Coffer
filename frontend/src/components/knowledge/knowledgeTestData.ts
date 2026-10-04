// frontend/src/components/knowledge/knowledgeTestData.ts — wire fixtures shared by the Knowledge page tests.
//
// Test-only data (imported by `*.test.tsx` files, never by the app): one
// collection holding a document at its root and one inside a folder, plus a
// change an earlier curation pass made and a person's edit, in the generated
// wire shapes. The collection's uid and name are deliberately unlike each
// other: the URL carries the uid, every path is built from the name.
import type { ChangeOut, CollectionOut, FileOut, TreeOut } from "@/lib/api/knowledge";

export const UID = "kn-8c1f";
export const NAME = "shopee";

export const COLLECTION: CollectionOut = {
  uid: UID,
  name: NAME,
  description: "How the shop is built.",
  document_count: 2,
  folder_path: `/home/u/.coffer/knowledge/${NAME}`,
  updated_at: "2026-09-30T13:30:00Z",
  tidy_handoff: { prompt: `Tidy the ${NAME} collection.` },
};

export const OTHER: CollectionOut = {
  uid: "kn-77aa",
  name: "runbooks",
  description: "On-call runbooks.",
  document_count: 0,
  folder_path: "/home/u/.coffer/knowledge/runbooks",
  updated_at: null,
  tidy_handoff: { prompt: "Tidy the runbooks collection." },
};

function file(path: string, over: Partial<FileOut> = {}): FileOut {
  return {
    path,
    title: path.split("/").pop() ?? path,
    description: "a document",
    actor: "user",
    created_at: "2026-09-12T00:00:00Z",
    updated_at: "2026-09-20T00:00:00Z",
    body: `Body of ${path}.`,
    file_path: `/Users/dev/.coffer/knowledge/${path}`,
    folder_path: `/Users/dev/.coffer/knowledge/${path.split("/").slice(0, -1).join("/")}`,
    fingerprint: `fp-${path}`,
    ...over,
  };
}

export const GATEWAY = file(`${NAME}/gateway.md`, {
  title: "Account Gateway",
  description: "where account decisions are made",
  body: "# Account Gateway\n\nThe orchestration layer.",
});

export const SESSION = file(`${NAME}/account/session.md`, {
  title: "Session ownership",
  body: "Login state is owned by account.session.",
});

export const FILES: Record<string, FileOut> = {
  [GATEWAY.path]: GATEWAY,
  [SESSION.path]: SESSION,
};

export const TREES: Record<string, TreeOut> = {
  [NAME]: {
    path: NAME,
    directories: [{ path: `${NAME}/account`, name: "account", file_count: 1 }],
    files: [
      {
        path: GATEWAY.path,
        title: GATEWAY.title,
        description: GATEWAY.description,
        actor: "user",
        updated_at: GATEWAY.updated_at,
      },
    ],
  },
  [`${NAME}/account`]: {
    path: `${NAME}/account`,
    directories: [],
    files: [
      {
        path: SESSION.path,
        title: SESSION.title,
        description: SESSION.description,
        actor: "agent",
        updated_at: SESSION.updated_at,
      },
    ],
  },
  [OTHER.name]: { path: OTHER.name, directories: [], files: [] },
};

function change(over: Partial<ChangeOut>): ChangeOut {
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

/** A change an earlier curation pass made: it keeps its curation label in the history. */
export const PASS = change({
  version: "a1b2c3d4",
  time: new Date(Date.now() - 2 * 3_600_000).toISOString(),
  writer: "curation",
  operation: "pass",
  summary: "Curate 20260928-login-retry.md",
  agent: "codex",
  item: "20260928-login-retry.md",
  status: "ok",
  documents: [
    { path: GATEWAY.path, status: "modified", added: 3, removed: 1 },
    { path: SESSION.path, status: "added", added: 5, removed: 0 },
  ],
});

/** A person's edit, in the other collection. */
export const EDIT = change({
  version: "e5f6a7b8",
  collections: [OTHER.name],
  documents: [{ path: `${OTHER.name}/on-call.md`, status: "modified", added: 1, removed: 1 }],
});

export const DIFF =
  "diff --git a/x b/x\nindex 1..2 100644\n--- a/x\n+++ b/x\n@@ -1,2 +1,2 @@\n # Account Gateway\n-The old layer.\n+The orchestration layer.\n";
