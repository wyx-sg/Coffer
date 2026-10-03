// src/lib/customTools/handoff.ts — the prompts a custom-tool problem hands to an agent (Ask an agent ▾).
// Problems that depend on this machine only: a group whose calls fail, a test that cannot connect or
// times out. The daemon sends no prompt for these, so they are written here from what the page knows.
import type { CustomToolGroup } from "@/lib/api/customTools";
import { hostOf } from "@/lib/customTools/groups";

/** A group whose recent calls fail. */
export function failingGroupPrompt(group: Pick<CustomToolGroup, "name" | "base_url">): string {
  return [
    `Coffer's custom tool group "${group.name}" (base URL ${group.base_url}) is failing: its recent calls got an error.`,
    `Find out why from this machine: check that ${hostOf(group.base_url)} resolves and is reachable (VPN, proxy, DNS), that the API is up, and what its recent calls returned (coffer log mcp).`,
    "Tell me what you find before changing anything.",
  ].join("\n");
}

/** A test run that could not connect or timed out. */
export function testFailurePrompt(args: {
  group: string;
  method: string;
  url: string | null;
  failure: "connect" | "timeout";
  detail: string | null;
  seconds: number;
}): string {
  const what =
    args.failure === "timeout"
      ? `timed out after ${args.seconds} s with no response`
      : `could not connect${args.detail ? ` (${args.detail})` : ""}`;
  return [
    `Testing a request of Coffer's custom tool group "${args.group}" ${what}: ${args.method} ${args.url ?? "(no URL)"}.`,
    "Find out why from this machine: DNS, VPN or proxy, firewall, or the API being down or slow. Tell me what you find before changing anything.",
  ].join("\n");
}
