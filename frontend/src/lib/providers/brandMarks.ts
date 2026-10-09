// src/lib/providers/brandMarks.ts — the official mark of each vendor and runtime, shared by the vendor grid and the provider tile.
//
// Files as supplied, never recoloured (Foundations "Official marks"; sources in
// assets/brand/providers/README.md). A mark with a dark file swaps by CSS
// against the root's `data-theme`. A monochrome file drawn in `currentColor`
// renders black in an `<img>`, so `invert` turns it white on the dark theme.
// Ollama's black mark keeps its tile light instead (see ProviderMark).
import anthropicIvoryUrl from "@/assets/brand/providers/anthropic-symbol-ivory.svg";
import anthropicSlateUrl from "@/assets/brand/providers/anthropic-symbol-slate.svg";
import deepseekUrl from "@/assets/brand/providers/deepseek.svg";
import fireworksUrl from "@/assets/brand/providers/fireworks.svg";
import geminiUrl from "@/assets/brand/providers/gemini.svg";
import groqUrl from "@/assets/brand/providers/groq.svg";
import hunyuanUrl from "@/assets/brand/providers/hunyuan.svg";
import kimiUrl from "@/assets/brand/providers/kimi.svg";
import llamaCppUrl from "@/assets/brand/providers/llama-cpp.svg";
import lmstudioUrl from "@/assets/brand/providers/lmstudio.svg";
import minimaxUrl from "@/assets/brand/providers/minimax.svg";
import mistralUrl from "@/assets/brand/providers/mistral.svg";
import ollamaUrl from "@/assets/brand/providers/ollama-logo.svg";
import openrouterCloudUrl from "@/assets/brand/providers/openrouter-cloud.svg";
import openrouterInkUrl from "@/assets/brand/providers/openrouter-ink.svg";
import qianfanUrl from "@/assets/brand/providers/qianfan.svg";
import qwenUrl from "@/assets/brand/providers/qwen.svg";
import siliconflowUrl from "@/assets/brand/providers/siliconflow.svg";
import stepfunUrl from "@/assets/brand/providers/stepfun.svg";
import togetherUrl from "@/assets/brand/providers/together.svg";
import vllmUrl from "@/assets/brand/providers/vllm-logo.svg";
import xaiUrl from "@/assets/brand/providers/xai.svg";
import zhipuUrl from "@/assets/brand/providers/zhipu.svg";
import blossomBlackUrl from "@/assets/brand/openai-blossom-black.svg";
import blossomWhiteUrl from "@/assets/brand/openai-blossom-white.svg";
import type { PresetId } from "./presets";

/** Every vendor or runtime with a mark: the presets but Custom, plus the runtimes detection finds. */
export type BrandId = Exclude<PresetId, "custom"> | "vllm" | "llama-cpp";

export interface BrandMark {
  light: string;
  dark?: string;
  /** Monochrome `currentColor` file: invert it on the dark theme. */
  invert?: boolean;
}

export const BRAND_MARKS: Record<BrandId, BrandMark> = {
  anthropic: { light: anthropicSlateUrl, dark: anthropicIvoryUrl },
  openai: { light: blossomBlackUrl, dark: blossomWhiteUrl },
  gemini: { light: geminiUrl },
  deepseek: { light: deepseekUrl },
  openrouter: { light: openrouterInkUrl, dark: openrouterCloudUrl },
  xai: { light: xaiUrl, invert: true },
  mistral: { light: mistralUrl },
  groq: { light: groqUrl, invert: true },
  together: { light: togetherUrl },
  fireworks: { light: fireworksUrl },
  kimi: { light: kimiUrl },
  zhipu: { light: zhipuUrl },
  minimax: { light: minimaxUrl },
  qwen: { light: qwenUrl },
  siliconflow: { light: siliconflowUrl },
  qianfan: { light: qianfanUrl },
  hunyuan: { light: hunyuanUrl },
  stepfun: { light: stepfunUrl },
  ollama: { light: ollamaUrl },
  lmstudio: { light: lmstudioUrl, invert: true },
  vllm: { light: vllmUrl },
  "llama-cpp": { light: llamaCppUrl },
};
