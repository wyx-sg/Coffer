// src/test/cliFixtures.ts — CliOut rows for the CLIs page, detail page and Requires tab tests.
import type { Cli } from "@/lib/api/clis";

const CHECKED = new Date(Date.now() - 2 * 60_000).toISOString();

function need(skill: string, why: string | null = null) {
  return { skill_uid: `sk-${skill}`, skill_name: skill, why, profiles: [] };
}

export function cli(overrides: Partial<Cli> & Pick<Cli, "command">): Cli {
  return {
    title: null,
    description: null,
    added: false,
    status: "ready",
    path: `/opt/homebrew/bin/${overrides.command}`,
    handoff: null,
    needed_by: [need("any-skill")],
    needed_by_servers: [],
    needed_by_coffer: [],
    checked_at: CHECKED,
    ...overrides,
  };
}

/** gh ready and needed by two skills, jq missing (with a hand-off prompt), uv ready. */
export const GH_READY = cli({
  command: "gh",
  title: "GitHub CLI",
  needed_by: [need("gh-triage", "Opens and labels issues."), need("release-notes")],
});

export const JQ_MISSING = cli({
  command: "jq",
  status: "missing",
  path: null,
  handoff: { prompt: "Install jq on this machine." },
  needed_by: [need("gh-triage", "The skill filters issue JSON with it."), need("log-digest")],
});

export const UV_READY = cli({
  command: "uv",
  needed_by: [need("gh-triage")],
});

/** uv missing, needed by the MCP server duckdb (started with uvx) and a skill. */
export const UV_MISSING_FOR_SERVER = cli({
  command: "uv",
  status: "missing",
  path: null,
  handoff: { prompt: "Install uv on this machine so Coffer can start duckdb." },
  needed_by: [need("data-profiling")],
  needed_by_servers: [{ server_uid: "srv-duckdb", server_name: "duckdb", launcher: "uvx" }],
});

/** git missing, needed by Coffer itself (the vault's history and sync) and nothing else. */
export const GIT_MISSING_FOR_COFFER = cli({
  command: "git",
  title: "Git",
  status: "missing",
  path: null,
  handoff: { prompt: "Install git on this machine." },
  needed_by: [],
  needed_by_coffer: ["vault_history", "sync"],
});

/** A tool added by hand, with no skill and no MCP server behind it. */
export const DEMO_ADDED = cli({
  command: "demo",
  title: "Demo tool",
  description: "A tool the person added themselves.",
  added: true,
  needed_by: [],
});
