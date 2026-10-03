// src/components/providers/VendorIcon.tsx — the 16px mark on an Add-dialog vendor button.
//
// Anthropic, OpenAI, OpenRouter and Ollama use the official files under
// assets/brand (never recoloured; light/dark files swap by the root's
// `data-theme`). Google Gemini, DeepSeek and LM Studio have no official file in
// the repo yet, so they get a neutral letter tile rather than a drawn imitation
// — to be replaced by the vendors' own marks. Custom is a plain cube outline.
import { Box } from "lucide-react";

import anthropicIvoryUrl from "@/assets/brand/providers/anthropic-symbol-ivory.svg";
import anthropicSlateUrl from "@/assets/brand/providers/anthropic-symbol-slate.svg";
import ollamaUrl from "@/assets/brand/providers/ollama-logo.svg";
import openrouterCloudUrl from "@/assets/brand/providers/openrouter-cloud.svg";
import openrouterInkUrl from "@/assets/brand/providers/openrouter-ink.svg";
import blossomBlackUrl from "@/assets/brand/openai-blossom-black.svg";
import blossomWhiteUrl from "@/assets/brand/openai-blossom-white.svg";
import type { PresetId } from "@/lib/providers/presets";

const FILES: Partial<Record<PresetId, { light: string; dark?: string }>> = {
  anthropic: { light: anthropicSlateUrl, dark: anthropicIvoryUrl },
  openai: { light: blossomBlackUrl, dark: blossomWhiteUrl },
  openrouter: { light: openrouterInkUrl, dark: openrouterCloudUrl },
  ollama: { light: ollamaUrl },
};

/** No official mark on file: a neutral tile with the vendor's initials. */
const LETTERS: Partial<Record<PresetId, string>> = { gemini: "G", deepseek: "DS", lmstudio: "LM" };

function Img({ src, className }: { src: string; className?: string }) {
  return (
    <img
      src={src}
      alt=""
      aria-hidden
      width={16}
      height={16}
      className={`size-4 shrink-0 object-contain ${className ?? ""}`}
    />
  );
}

export function VendorIcon({ id }: { id: PresetId }) {
  const files = FILES[id];
  if (files) {
    return files.dark ? (
      <>
        <Img src={files.light} className="block [[data-theme=dark]_&]:hidden" />
        <Img src={files.dark} className="hidden [[data-theme=dark]_&]:block" />
      </>
    ) : (
      <Img src={files.light} className={id === "ollama" ? "[[data-theme=dark]_&]:invert" : ""} />
    );
  }
  const letters = LETTERS[id];
  if (letters) {
    return (
      <span
        aria-hidden
        className="inline-flex size-4 shrink-0 items-center justify-center rounded-[4px] bg-chip text-[8px] font-heavy leading-none text-text-muted"
      >
        {letters}
      </span>
    );
  }
  return <Box className="size-4 shrink-0 text-text-muted" aria-hidden />;
}
