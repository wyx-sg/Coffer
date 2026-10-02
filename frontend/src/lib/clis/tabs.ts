// src/lib/clis/tabs.ts — a CLI's detail tabs: Overview (the default, at the bare `/clis/<command>`) and Commands (`/clis/<command>/commands`).
export const CLI_TABS = ["overview", "commands"] as const;
export type CliTab = (typeof CLI_TABS)[number];
export const DEFAULT_CLI_TAB: CliTab = "overview";
