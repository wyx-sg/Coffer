/** Composition root for frontend kinds.
 *
 * Each kind's UI module is imported here and registered into the kindRegistry.
 * Adding a new kind means: add an import + registerKindUI call. The kind
 * modules themselves are self-contained under src/kinds/<name>/.
 */
import { registerKindUI } from "@/lib/components/kindRegistry";
import { MCP_KIND_UI } from "@/kinds/mcp";

let _registered = false;

export function registerFrontendKinds(): void {
  if (_registered) return;
  registerKindUI(MCP_KIND_UI);
  _registered = true;
}
