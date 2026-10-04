/** The i18n key for the message a finished curation pass leaves.
 *
 *  One key per `status`, except a `truncated` pass that gave up on its item
 *  (spec knowledge "Bound a pass to eight writes"): that pass settled the item,
 *  so the plain `truncated` message — which promises another try — would be
 *  wrong. */
export function curateToastKey(result: { status: string; gave_up: boolean }): string {
  const base = "knowledge.curate.status";
  if (result.status === "truncated" && result.gave_up) return `${base}.truncatedGaveUp`;
  return `${base}.${result.status}`;
}

/** The one toast a finished Curate now leaves, from every pass it ran (across
 *  however many collections): a summary ("Curated 3 items into 2 documents"),
 *  or — when any pass failed — an error that points at Activity. How a single
 *  item ended (too large, cut off) is written on its Recent changes row, not
 *  announced here. `documents` counts what the passes wrote. */
export function curateOutcome(
  passes: {
    status: string;
    gave_up: boolean;
    written: number;
    promoted: string[];
  }[],
):
  | { kind: "error"; key: string; vars: Record<string, number> }
  | { kind: "success"; key: string; vars: Record<string, number> } {
  const last = passes[passes.length - 1];
  if (passes.some((p) => p.status === "failed")) {
    return { kind: "error", key: `${KEY_BASE}.failed`, vars: {} };
  }
  const ok = passes.filter((p) => p.status === "ok");
  if (ok.length > 0) {
    const documents = ok.reduce((sum, p) => sum + p.written, 0);
    return {
      kind: "success",
      key: documents > 0 ? "knowledge.curate.summary" : `${KEY_BASE}.ok`,
      vars: { count: ok.length, documents },
    };
  }
  const promoted = passes.reduce((sum, p) => sum + p.promoted.length, 0);
  return {
    kind: "success",
    key: last ? curateToastKey(last) : `${KEY_BASE}.up_to_date`,
    vars: { count: promoted },
  };
}

const KEY_BASE = "knowledge.curate.status";
