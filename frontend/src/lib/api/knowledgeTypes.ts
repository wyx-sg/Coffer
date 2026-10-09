// frontend/src/lib/api/knowledgeTypes.ts
//
// Wire types for the `knowledge` kind. A collection is a top-level folder under
// the knowledge root holding ONE tree of Markdown documents that people and
// agents write together (`shopee/account-gateway.md`, `shopee/apis/login.md`).
//
// Every `path` here is RELATIVE to the knowledge root. The two ABSOLUTE paths —
// `file_path` and `folder_path` on a read — exist only so the viewer can hand
// them to the OS file actions (see "Return absolute paths on reads").
//
// These are the knowledge contract's generated schemas
// (`openspec/specs/knowledge/contracts/api.openapi.yaml` → `generated/knowledge.ts`)
// under the names the hooks and pages already import.
//
// There is no search or grep type in this file because the layer exposes no
// retrieval at all (see "Expose exactly one knowledge tool"): an agent reads the files with its own
// tools at the paths its delivered skill carries, and a person reads them
// through the collection's tree.
import type { components } from "@/lib/api/generated/knowledge";

type Schemas = components["schemas"];

/** One file's frontmatter + body, plus the absolute paths for file actions. */
export type FileOut = Schemas["FileOut"];

/** One collection: a top-level folder, described by its own `README.md`. It
 *  has no title — it is shown by its folder name. It carries its page, source,
 *  waiting-source and finding counts; `tidy_handoff` and `check_handoff` are
 *  the prompts that hand its tidying and its check to an agent. */
export type CollectionOut = Schemas["CollectionOut"];

export type CollectionListOut = Schemas["CollectionListOut"];

/** One file in a tree level: its kind, and for a source whether it waits. */
export type FileSummaryOut = Schemas["FileSummaryOut"];

/** One level of a collection's tree — it descends a level per request. */
export type TreeOut = Schemas["TreeOut"];

/** What one successful `POST /knowledge/upload` produced: the document it became. */
export type IngestedDocumentOut = Schemas["IngestedDocumentOut"];

/** A chore for the person's agent: the prompt, written by the daemon. */
export type HandoffOut = Schemas["HandoffOut"];

/** One change to knowledge: one commit in the vault's history, naming its
 *  writer (see "Commit every knowledge write naming its writer"). */
export type ChangeOut = Schemas["ChangeOut"];

/** The changes feed, newest first. */
export type ChangesOut = Schemas["ChangesOut"];

/** A page's resolved `[[link]]`: the path it names, or null when dead. */
export type LinkRefOut = Schemas["LinkRefOut"];

/** One mechanical finding of a collection's check. */
export type FindingOut = Schemas["FindingOut"];

/** A collection's check: the collection and its findings. */
export type CheckOut = Schemas["CheckOut"];
