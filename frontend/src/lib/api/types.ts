// frontend/src/lib/api/types.ts
//
// Every capability's generated types, merged: `components` for the wire
// shapes, `paths` for the shared openapi-fetch client in `client.ts`.
//
// Each `generated/<capability>.ts` comes from that capability's
// `contracts/api.openapi.yaml`, and every contract is cut from the daemon's
// one OpenAPI document (`make contracts`), so a schema name means the same
// shape in every module that carries it and intersecting them is safe.
//
// The contracts spell paths from the host root (`/api/v1/resources`); the
// client's base URL already ends in `/api/v1`, so `paths` is re-keyed
// without that prefix and a call reads `client.GET("/resources")`.
import type {
  components as AgentRegistry,
  paths as AgentRegistryPaths,
} from "./generated/agent-registry";
import type { components as Channels, paths as ChannelsPaths } from "./generated/channels";
import type { components as Chat, paths as ChatPaths } from "./generated/chat";
import type { components as Credentials, paths as CredentialsPaths } from "./generated/credentials";
import type { components as Daemon, paths as DaemonPaths } from "./generated/daemon";
import type {
  components as InternalEngine,
  paths as InternalEnginePaths,
} from "./generated/internal-engine";
import type { components as Knowledge, paths as KnowledgePaths } from "./generated/knowledge";
import type { components as McpGateway, paths as McpGatewayPaths } from "./generated/mcp-gateway";
import type { components as Memory, paths as MemoryPaths } from "./generated/memory";
import type {
  components as ProviderSwitching,
  paths as ProviderSwitchingPaths,
} from "./generated/provider-switching";
import type {
  components as ResourceFramework,
  paths as ResourceFrameworkPaths,
} from "./generated/resource-framework";
import type {
  components as SkillManager,
  paths as SkillManagerPaths,
} from "./generated/skill-manager";
import type { components as VaultSync, paths as VaultSyncPaths } from "./generated/vault-sync";

export type components = AgentRegistry &
  Channels &
  Chat &
  Credentials &
  Daemon &
  InternalEngine &
  Knowledge &
  McpGateway &
  Memory &
  ProviderSwitching &
  ResourceFramework &
  SkillManager &
  VaultSync;

type WithoutApiPrefix<P> = {
  [K in keyof P as K extends `/api/v1${infer Rest}` ? Rest : never]: P[K];
};

export type paths = WithoutApiPrefix<
  AgentRegistryPaths &
    ChannelsPaths &
    ChatPaths &
    CredentialsPaths &
    DaemonPaths &
    InternalEnginePaths &
    KnowledgePaths &
    McpGatewayPaths &
    MemoryPaths &
    ProviderSwitchingPaths &
    ResourceFrameworkPaths &
    SkillManagerPaths &
    VaultSyncPaths
>;
