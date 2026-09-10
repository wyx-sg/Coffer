// frontend/src/kinds/mcp/serverTimeouts.ts — the three per-server timeouts as
// data: bounds, defaults, and the read/merge pair the edit dialog uses.
//
// Separate from the component so the pure helpers can be imported by the save
// path without dragging a React module along.
export interface Timeouts {
  spawn: number;
  request: number;
  idle: number;
}

/** Defaults from `MCPServerConfig`; shown when a server has never set one. */
export const TIMEOUT_DEFAULTS: Timeouts = { spawn: 30, request: 120, idle: 600 };

export const BOUNDS = {
  spawn: { min: 5, max: 120 },
  request: { min: 5, max: 1800 },
  idle: { min: 60, max: 86400 },
} as const;

function readNumber(config: Record<string, unknown>, key: string, fallback: number): number {
  const raw = config[key];
  return typeof raw === "number" && Number.isFinite(raw) ? raw : fallback;
}

/** Pull the three timeouts out of a config object, defaulting each. */
export function timeoutsOf(config: unknown): Timeouts {
  const c = (config ?? {}) as Record<string, unknown>;
  return {
    spawn: readNumber(c, "spawn_timeout_seconds", TIMEOUT_DEFAULTS.spawn),
    request: readNumber(c, "request_timeout_seconds", TIMEOUT_DEFAULTS.request),
    idle: readNumber(c, "idle_timeout_seconds", TIMEOUT_DEFAULTS.idle),
  };
}

/** Merge edited timeouts back into a config object. */
export function withTimeouts(
  config: Record<string, unknown>,
  timeouts: Timeouts,
): Record<string, unknown> {
  return {
    ...config,
    spawn_timeout_seconds: timeouts.spawn,
    request_timeout_seconds: timeouts.request,
    idle_timeout_seconds: timeouts.idle,
  };
}
