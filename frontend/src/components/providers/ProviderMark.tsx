// src/components/providers/ProviderMark.tsx — a provider's official mark on its neutral tile.
//
// The marks are the files as supplied, never recoloured (Foundations "Official
// marks"; brandMarks.ts holds them). A mark with a light and a dark file swaps
// by CSS against the root's `data-theme`, so no JS watches the theme; a
// monochrome one inverts on the dark theme. Ollama's mark is monochrome black
// with no light file: rather than editing it, its TILE turns light (the `knob`
// role) on the dark theme, so the black mark keeps its contrast. A gateway or
// custom endpoint gets Coffer's neutral provider glyph, drawn with the
// nav-icon pen in muted ink.
// OpenAI's mark is the Blossom with the word "OpenAI" beside it (`withWord`);
// a dense list row passes `withWord={false}` and names the vendor in its
// sub-line. Which mark: see markKind.ts.
import { BRAND_MARKS } from "@/lib/providers/brandMarks";
import type { Provider } from "@/lib/api/providers";
import { providerMarkKind } from "@/lib/providers/markKind";
import { cn } from "@/lib/utils";

type Size = "sm" | "md" | "lg";

/** Tile box, and the mark's own box inside it (the Blossom's file carries a margin). */
const SIZE: Record<Size, { tile: string; mark: number; blossom: number }> = {
  sm: { tile: "size-6 rounded-item", mark: 14, blossom: 24 },
  md: { tile: "size-7 rounded-md", mark: 16, blossom: 28 },
  lg: { tile: "size-8 rounded-lg", mark: 18, blossom: 32 },
};

interface Props {
  provider: Pick<Provider, "base_url" | "protocol" | "local_runtime">;
  size?: Size;
  /** OpenAI only: show the word "OpenAI" beside the Blossom (default true). */
  withWord?: boolean;
  className?: string;
}

/** Coffer's neutral provider glyph (the Model providers nav icon). */
function Glyph({ box }: { box: number }) {
  return (
    <svg
      width={box}
      height={box}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className="block shrink-0 text-text-muted"
    >
      <path d="M21 8l-9-5-9 5 9 5 9-5z" />
      <path d="M3 8v8l9 5 9-5V8M12 13v8" />
    </svg>
  );
}

function Img({ src, box, className }: { src: string; box: number; className?: string }) {
  return (
    <img
      src={src}
      alt=""
      aria-hidden
      width={box}
      height={box}
      className={cn("shrink-0 object-contain", className)}
      // The one inline style: the mark's pixel box, which has no class.
      style={{ width: box, height: box }}
    />
  );
}

export function ProviderMark({ provider, size = "md", withWord = true, className }: Props) {
  const kind = providerMarkKind(provider);
  const geo = SIZE[size];
  const box = kind === "openai" ? geo.blossom : geo.mark;
  const tile = (
    <span
      data-provider-mark={kind}
      aria-hidden
      className={cn(
        "inline-flex shrink-0 items-center justify-center overflow-hidden bg-chip",
        kind === "ollama" && "[[data-theme=dark]_&]:bg-knob",
        geo.tile,
        className,
      )}
    >
      {kind === "glyph" ? (
        <Glyph box={box} />
      ) : BRAND_MARKS[kind].dark ? (
        <>
          <Img
            src={BRAND_MARKS[kind].light}
            box={box}
            className="block [[data-theme=dark]_&]:hidden"
          />
          <Img
            src={BRAND_MARKS[kind].dark!}
            box={box}
            className="hidden [[data-theme=dark]_&]:block"
          />
        </>
      ) : (
        <Img
          src={BRAND_MARKS[kind].light}
          box={box}
          className={cn("block", BRAND_MARKS[kind].invert && "[[data-theme=dark]_&]:invert")}
        />
      )}
    </span>
  );
  if (kind !== "openai" || !withWord) return tile;
  // The brand's mark for OpenAI is the Blossom with its name; the word is the
  // vendor's name, not copy, so it is not translated.
  return (
    <span className="inline-flex shrink-0 items-center gap-1.5">
      {tile}
      <span className="text-xs font-label text-text">OpenAI</span>
    </span>
  );
}
