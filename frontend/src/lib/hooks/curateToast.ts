/** The i18n key for the message a finished curation pass leaves.
 *
 *  One key per `status`, except a `truncated` pass that gave up on its item
 *  (spec knowledge "Bound a pass to eight writes"): that pass settled the item,
 *  so the plain `truncated` message — which promises another try — would be
 *  wrong. */
export function curateToastKey(result: { status: string; gave_up: boolean }): string {
  const base = "knowledge.detail.curateStatus";
  if (result.status === "truncated" && result.gave_up) return `${base}.truncatedGaveUp`;
  return `${base}.${result.status}`;
}
