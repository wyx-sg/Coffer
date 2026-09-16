// frontend/src/lib/api/types.ts
//
// The mcp-gateway contract's generated types, re-exported under the path every
// existing `from "@/lib/api/types"` import already uses: `components` for the
// wire shapes, and `paths` for the one typed openapi-fetch client in
// `client.ts`. `npm run codegen` writes one module per contract into
// `./generated/` (see `scripts/codegen.mjs`); import a sibling contract's
// schemas from there directly, e.g.
// `import type { components } from "@/lib/api/generated/channels"`.
export type { components, paths } from "./generated/mcp-gateway";
