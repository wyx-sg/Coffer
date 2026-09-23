// frontend/src/lib/workflow/templateErrors.ts
// A refused template, read back as the ONE field that is wrong.
//
// The daemon refuses a template config naming the JSON path of the offending
// field — `stages[1].nodes[0].skill`, not "a node". The editor's job
// is to put the message against that field rather than in a banner over a form
// with forty inputs in it, so this module turns whatever the envelope carried
// into `{path, message}` and the components ask it whether THEIR path is the
// one that was named.
//
// The path arrives one of two ways, because the write goes through the
// kind-agnostic resource endpoint and the refusal can be raised at either of
// two depths:
//
//   • `details.path` — a refusal that kept the field structured.
//   • the message — `stages[1].nodes[0].skill: no registered skill named 'x'`,
//     possibly wrapped in a Pydantic validation report. The path is the first
//     thing in it that LOOKS like a template path, which is why the pattern is
//     anchored on the four field names the template's top level actually has.
import { ApiError } from "@/lib/api/errors";

/** A refusal reduced to the field it names and what it said about it. */
export interface TemplateRefusal {
  /** JSON path of the offending field, e.g. `stages[1].nodes[0].skill`. */
  path: string;
  /** The reason, with the leading `<path>: ` stripped. */
  message: string;
}

// `stages`, optionally indexed and followed by dotted (optionally indexed)
// segments. There are no template-level scalar fields left to name: the
// attempt ceiling is a task's own, so it arrives inside this path like every
// other field.
const PATH_PATTERN = /stages(?:\[\d+\])?(?:\.[a-z_]+(?:\[\d+\])?)*/;

/**
 * The field a refusal names, or `null` when it names none — a transport
 * failure, a 409, a message that carries no path. A caller that gets `null`
 * shows the error the way it shows any other: whole-surface, because there is
 * no field to put it on.
 */
export function templateRefusal(error: unknown): TemplateRefusal | null {
  if (!(error instanceof ApiError)) return null;
  const details = error.details as { path?: unknown; reason?: unknown } | undefined;
  const raw = error.envelopeMessage ?? "";
  const path =
    typeof details?.path === "string" ? details.path : (PATH_PATTERN.exec(raw)?.[0] ?? null);
  if (path === null) return null;
  const reason = typeof details?.reason === "string" ? details.reason : null;
  return { path, message: stripPath(reason ?? raw, path) };
}

/** `stages[0].key: duplicate stage key 'x'` → `duplicate stage key 'x'`. */
function stripPath(message: string, path: string): string {
  const marker = `${path}: `;
  const at = message.indexOf(marker);
  if (at === -1) return message.trim();
  // Pydantic wraps the reason in a report; everything after the path up to the
  // bracketed type annotation it appends is the part a human wrote.
  const rest = message.slice(at + marker.length);
  return rest.split(" [type=")[0].trim();
}

/** The message to render at `path`, or undefined when this field is not the
 *  one that was refused. */
export function messageFor(refusal: TemplateRefusal | null, path: string): string | undefined {
  return refusal?.path === path ? refusal.message : undefined;
}

/** DOM id of a field's error line, so the control can point at it with
 *  `aria-describedby` and a screen reader reads the refusal with the field. */
export function errorId(path: string): string {
  return `template-error-${path}`;
}

/** `aria-describedby` / `aria-invalid` for the control at `path`, so a control
 *  and its error line are wired together the same way everywhere. */
export function fieldErrorProps(
  refusal: TemplateRefusal | null,
  path: string,
): { "aria-invalid"?: true; "aria-describedby"?: string } {
  if (messageFor(refusal, path) === undefined) return {};
  return { "aria-invalid": true, "aria-describedby": errorId(path) };
}
