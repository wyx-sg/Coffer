// frontend/src/lib/api/memory.ts
//
// Request helpers for memory (`/api/v1/memory`, spec memory "Show and edit
// memory on the Memory page"): the page's state, a project's topics, one
// file's text, and a person's edit or delete of a file. A tidy is started and
// finished by the agent the Tidy prompt is handed to, never by the page.
//
// Transport via the typed client (.agents/frontend.md §4); wire types in
// `memoryTypes.ts`, aliases of the generated contract.
import { getApiClient, unwrap, unwrapVoid } from "@/lib/api/client";
import type { MemoryFile, MemoryState, MemoryTopic } from "./memoryTypes";

export * from "./memoryTypes";

export function getMemoryState(): Promise<MemoryState> {
  return unwrap(getApiClient().GET("/memory"));
}

export async function listTopics(project: string): Promise<MemoryTopic[]> {
  const out = await unwrap(
    getApiClient().GET("/memory/projects/{project}", { params: { path: { project } } }),
  );
  return out.topics;
}

export function getMemoryFile(project: string, name: string): Promise<MemoryFile> {
  return unwrap(
    getApiClient().GET("/memory/projects/{project}/{name}", {
      params: { path: { project, name } },
    }),
  );
}

/** Replace a file's text; 409 `MEMORY_FILE_STALE` when it changed since `expected` was read. */
export function saveMemoryFile(
  project: string,
  name: string,
  text: string,
  expected: string,
): Promise<MemoryFile> {
  return unwrap(
    getApiClient().PUT("/memory/projects/{project}/{name}", {
      params: { path: { project, name } },
      body: { text, expected },
    }),
  );
}

export function deleteMemoryFile(project: string, name: string, expected: string): Promise<void> {
  return unwrapVoid(
    getApiClient().DELETE("/memory/projects/{project}/{name}", {
      params: { path: { project, name }, query: { expected } },
    }),
  );
}
