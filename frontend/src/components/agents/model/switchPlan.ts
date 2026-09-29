// src/components/agents/model/switchPlan.ts — what a confirmed switch writes: the target file and the keys Coffer sets or removes, for the Review pane.
//
// There is no server-side preview of a provider switch, so this is a summary of
// the managed keys (spec provider-switching "Project into Claude Code settings
// without clobbering them" / "… Codex config …"), not a diff of the file. The
// user's own values (model, effort, tiers) are shown literally; the wiring
// Coffer derives itself (endpoint route, key helper, model list) is described
// rather than spelled out, because it depends on how this daemon reaches the
// connection.
import type { TFunction } from "i18next";

import type { AgentOut } from "@/lib/api/agents";
import { modelIds } from "@/lib/api/providers";
import { abbreviateHomePath } from "@/lib/agents/display";
import type { ConnectionDraft, Tier } from "@/lib/hooks/useAgentConnectionDraft";
import type { DiffLine } from "@/components/change-preview/changeCounts";

interface SwitchPlan {
  path: string;
  lines: DiffLine[];
}

function hostOf(url: string | null | undefined): string {
  if (!url) return "";
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

const TIER_ENV: Record<Tier, string> = {
  opus: "ANTHROPIC_DEFAULT_OPUS_MODEL",
  sonnet: "ANTHROPIC_DEFAULT_SONNET_MODEL",
  haiku: "ANTHROPIC_DEFAULT_HAIKU_MODEL",
  fable: "ANTHROPIC_DEFAULT_FABLE_MODEL",
};

const add = (text: string): DiffLine => ({ kind: "add", text });
const remove = (text: string): DiffLine => ({ kind: "remove", text });

export function targetPath(agent: AgentOut): string {
  const file = agent.type === "codex" ? "config.toml" : "settings.json";
  return abbreviateHomePath(`${agent.config_dir.replace(/\/$/, "")}/${file}`);
}

export function planSwitch(agent: AgentOut, c: ConnectionDraft, t: TFunction): SwitchPlan {
  const path = targetPath(agent);
  const codex = agent.type === "codex";

  if (c.draftIsBuiltin) {
    const keys = codex
      ? [
          "model_provider",
          "model",
          "model_reasoning_effort",
          "model_catalog_json",
          "[model_providers.coffer]",
        ]
      : [
          "model",
          "effortLevel",
          "apiKeyHelper",
          "env.ANTHROPIC_BASE_URL",
          ...Object.values(TIER_ENV).map((k) => `env.${k}`),
          "modelPicker",
        ];
    return { path, lines: keys.map(remove) };
  }

  const route = t("agents.modelTab.review.route", { host: hostOf(c.draftConnObj?.base_url) });
  const curated = modelIds(c.draftConnObj?.models ?? [], "text").length;
  const list = t("agents.modelTab.review.modelList", { count: curated });
  const effort = c.effortLevels.length > 0 ? c.draftEffort : null;

  if (codex) {
    const lines = [add(`model_provider = "coffer"`), add(`model = "${c.draftModel}"`)];
    if (effort) lines.push(add(`model_reasoning_effort = "${effort}"`));
    if (curated > 0) lines.push(add(`model_catalog_json  ← ${list}`));
    lines.push(add("[model_providers.coffer]"), add(`base_url  ← ${route}`));
    return { path, lines };
  }

  const lines = [add(`"model": "${c.draftModel}"`)];
  if (effort) lines.push(add(`"effortLevel": "${effort}"`));
  lines.push(
    add(`"apiKeyHelper"  ← ${t("agents.modelTab.review.keyHelper")}`),
    add(`"env.ANTHROPIC_BASE_URL"  ← ${route}`),
  );
  for (const tier of c.tiers) {
    const model = c.draftTiers[tier];
    if (c.showTiers && model) lines.push(add(`"env.${TIER_ENV[tier]}": "${model}"`));
  }
  if (curated > 0) lines.push(add(`"modelPicker"  ← ${list}`));
  return { path, lines };
}
