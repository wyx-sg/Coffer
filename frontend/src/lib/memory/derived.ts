// frontend/src/lib/memory/derived.ts
//
// One question, asked in two places: is this path inside a partition's `.raw/`?
//
// A partition holds two kinds of file and the difference matters more than any
// other thing the browser could say about them. `MEMORY.md`, `notes/` and
// `RETIRED.md` are COFFER'S OWN WRITING, distilled from what the agents know.
// `.raw/` is the INPUT to that distillation: the agents' own words, copied
// verbatim and kept only so a note's claim can be checked against the source it
// came from (spec memory, "Raw entry"). Reading a `.raw/` file as if it were
// Coffer's answer is exactly the mistake the surface has to prevent, so the
// tree marks the folder and the viewer says so over the file.
const RAW_DIR = ".raw";

/** True for the `.raw` directory itself and for everything under it. */
export function isDerivedInput(path: string): boolean {
  return path === RAW_DIR || path.startsWith(`${RAW_DIR}/`);
}
