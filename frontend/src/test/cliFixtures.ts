// src/test/cliFixtures.ts — CliOut rows for the CLIs page, detail page and Requires tab tests.
import type { Cli } from "@/lib/api/clis";

const CHECKED = new Date(Date.now() - 2 * 60_000).toISOString();

function need(skill: string, min: string | null = null, why: string | null = null) {
  return { skill_uid: `sk-${skill}`, skill_name: skill, min_version: min, why, profiles: [] };
}

export function cli(overrides: Partial<Cli> & Pick<Cli, "command">): Cli {
  return {
    title: null,
    description: null,
    added: false,
    status: "ready",
    path: `/opt/homebrew/bin/${overrides.command}`,
    version: "1.0.0",
    min_version: null,
    login: { state: "not_needed", check: null, command: null },
    handoff: null,
    needed_by: [need("any-skill")],
    needed_by_servers: [],
    needed_by_coffer: [],
    checked_at: CHECKED,
    ...overrides,
  };
}

/** gh too old, gcloud not logged in, jq missing (each with a hand-off prompt), uv ready. */
export const GH_OUTDATED = cli({
  command: "gh",
  title: "GitHub CLI",
  status: "outdated",
  version: "2.30.0",
  min_version: "2.40",
  handoff: { prompt: "Update gh to 2.40 or newer on this machine." },
  needed_by: [need("gh-triage", "2.40", "Opens and labels issues."), need("release-notes")],
});

export const GCLOUD_LOGGED_OUT = cli({
  command: "gcloud",
  title: "Google Cloud CLI",
  status: "logged_out",
  version: "480.0.0",
  login: {
    state: "logged_out",
    check: ["gcloud", "auth", "print-access-token"],
    command: "gcloud auth login",
  },
  handoff: { prompt: "Help me log gcloud in on this machine." },
  needed_by: [need("gh-triage")],
});

export const JQ_MISSING = cli({
  command: "jq",
  status: "missing",
  path: null,
  version: null,
  min_version: "1.6",
  login: { state: null, check: null, command: null },
  handoff: { prompt: "Install jq 1.6 or newer on this machine." },
  needed_by: [
    need("gh-triage", "1.6", "The skill filters issue JSON with it."),
    need("log-digest", "1.6"),
  ],
});

export const UV_READY = cli({
  command: "uv",
  version: "0.4.18",
  min_version: "0.4",
  needed_by: [need("gh-triage", "0.4")],
});

/** uv missing, needed by the MCP server duckdb (started with uvx) and a skill. */
export const UV_MISSING_FOR_SERVER = cli({
  command: "uv",
  status: "missing",
  path: null,
  version: null,
  min_version: "0.4",
  login: { state: null, check: null, command: null },
  handoff: { prompt: "Install uv on this machine so Coffer can start duckdb." },
  needed_by: [need("data-profiling", "0.4")],
  needed_by_servers: [{ server_uid: "srv-duckdb", server_name: "duckdb", launcher: "uvx" }],
});

/** git missing, needed by Coffer itself (the vault's history and sync) and nothing else. */
export const GIT_MISSING_FOR_COFFER = cli({
  command: "git",
  title: "Git",
  status: "missing",
  path: null,
  version: null,
  login: { state: null, check: null, command: null },
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
  version: "3.0.0",
  needed_by: [],
});
