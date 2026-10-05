// frontend/src/components/knowledge/knowledgeTestData.ts — wire fixtures shared by the Knowledge page tests.
//
// Test-only data (imported by `*.test.tsx` files, never by the app): one
// collection holding a document at its root and one inside a folder, plus a
// person's change in the other collection, in the generated wire shapes. The collection's uid and name are deliberately unlike each
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

/** A person's edit, in the other collection. */
export const EDIT = change({
  version: "e5f6a7b8",
  collections: [OTHER.name],
  documents: [{ path: `${OTHER.name}/on-call.md`, status: "modified", added: 1, removed: 1 }],
});
