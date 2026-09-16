// frontend/src/lib/api/types.ts
//
// The generated types for the contracts the shared openapi-fetch client in
// `client.ts` speaks, re-exported under the path every existing
// `from "@/lib/api/types"` import already uses: `components` for the wire
// shapes, `paths` for the client.
//
// These four contracts are merged rather than re-exported one at a time
// because one client talks to all of them: the resource framework owns
// `/resources`, `/audit`, `/retention/*` and `/upkeep/runs`; credentials owns
// `/credentials*` and `/settings/credentials`; the daemon owns `/daemon/*` and
// `/fs/*`; and mcp-gateway keeps the MCP server's own capability, invocation
// and status routes. They were one contract before the specs were split, so
// merging here keeps `components["schemas"][…]` resolving for every consumer
// that predates the split.
//
// Intersecting is safe because the four schema sets are disjoint apart from
// `ErrorResponse`, which is the same shape in all four. A future contract that
// collides on a name with a *different* shape must not simply be added below —
// give it its own import instead.
//
// `npm run codegen` writes one module per contract into `./generated/` (see
// `scripts/codegen.mjs`); import any other contract's schemas from there
// directly, e.g.
// `import type { components } from "@/lib/api/generated/channels"`.
import type { components as Credentials, paths as CredentialsPaths } from "./generated/credentials";
import type { components as Daemon, paths as DaemonPaths } from "./generated/daemon";
import type { components as McpGateway, paths as McpGatewayPaths } from "./generated/mcp-gateway";
import type {
  components as ResourceFramework,
  paths as ResourceFrameworkPaths,
} from "./generated/resource-framework";

export type components = McpGateway & ResourceFramework & Credentials & Daemon;

export type paths = McpGatewayPaths & ResourceFrameworkPaths & CredentialsPaths & DaemonPaths;
