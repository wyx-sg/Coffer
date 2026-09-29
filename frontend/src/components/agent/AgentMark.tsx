// src/components/agent/AgentMark.tsx — an agent's official mark, the image inside an AgentBadge tile.
//
// Claude Code is the Claude Spark (Clay on both themes); Codex is the OpenAI
// Blossom, Black on light and White on dark, chosen by CSS against the root's
// `data-theme` so no JS watches the theme. Any other type gets a neutral agent
// glyph in muted ink. The marks are the files as supplied — never recoloured,
// never letters (Foundations-AgentBadge "Official marks").
import sparkUrl from "@/assets/brand/claude-spark-clay.svg";
import blossomBlackUrl from "@/assets/brand/openai-blossom-black.svg";
import blossomWhiteUrl from "@/assets/brand/openai-blossom-white.svg";
import { agentMarkKind } from "./agentMarkKind";

interface Props {
  type: string;
  /** Spark / generic glyph size in px. */
  markSize: number;
  /** The Blossom's box in px — its file carries its own margin, so it is larger. */
  blossomSize: number;
}

export function AgentMark({ type, markSize, blossomSize }: Props) {
  const kind = agentMarkKind(type);
  if (kind === "claude-spark") {
    return (
      <img
        src={sparkUrl}
        alt=""
        aria-hidden
        width={markSize}
        height={markSize}
        className="block shrink-0 object-contain"
        style={{ width: markSize, height: markSize }}
      />
    );
  }
  if (kind === "openai-blossom") {
    const style = { width: blossomSize, height: blossomSize };
    return (
      <>
        <img
          src={blossomBlackUrl}
          alt=""
          aria-hidden
          width={blossomSize}
          height={blossomSize}
          className="block shrink-0 object-contain [[data-theme=dark]_&]:hidden"
          style={style}
        />
        <img
          src={blossomWhiteUrl}
          alt=""
          aria-hidden
          width={blossomSize}
          height={blossomSize}
          className="hidden shrink-0 object-contain [[data-theme=dark]_&]:block"
          style={style}
        />
      </>
    );
  }
  // The board's generic agent glyph: a robot head on the 24 grid, drawn with
  // the nav-icon pen.
  return (
    <svg
      width={markSize}
      height={markSize}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className="block shrink-0 text-text-muted"
    >
      <rect x="4" y="8" width="16" height="12" rx="2" />
      <path d="M12 8V4H8" />
      <path d="M2 14h2M20 14h2M15 13v2M9 13v2" />
    </svg>
  );
}
