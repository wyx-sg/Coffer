// frontend/src/lib/api/memoryTypes.ts
//
// Wire types of memory (`/api/v1/memory`), every one an alias of the generated
// contract (`generated/memory.ts`, from `openspec/specs/memory`'s
// `api.openapi.yaml`). Memory is one Markdown file per topic under
// `vault/memory/projects/<project>/`, which agents write themselves; the page
// reads them, and a person edits or deletes one.
import type { components as MemoryWire } from "@/lib/api/generated/memory";

type Schemas = MemoryWire["schemas"];

/** What the Memory page reads: the projects, whether a tidy is open, and the Tidy prompt. */
export type MemoryState = Schemas["MemoryStateOut"];
/** One project folder: how many topic files, how many break the format, the newest `updated`. */
export type MemoryProject = Schemas["MemoryProjectOut"];
/** One topic file as the list shows it. */
export type MemoryTopic = Schemas["MemoryTopicOut"];
/** One topic file with its raw text and the digest an edit quotes. */
export type MemoryFile = Schemas["MemoryFileOut"];
