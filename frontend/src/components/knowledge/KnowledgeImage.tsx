// frontend/src/components/knowledge/KnowledgeImage.tsx
//
// A picture in a knowledge document, or a picture file opened from the tree
// (spec knowledge "Keep the pictures of an upload beside its source"). The
// asset route needs the session token, so the picture is fetched and shown
// from a data URL; until then its place is held, and a picture that is gone
// leaves its alt text, muted.
import { useKnowledgeAsset } from "@/lib/hooks/useKnowledge";

interface Props {
  /** The knowledge path of the picture. */
  path: string;
  alt?: string;
}

export function KnowledgeImage({ path, alt }: Props) {
  const { data, isPending } = useKnowledgeAsset(path);
  if (isPending) {
    return (
      <span
        data-testid="knowledge-image-loading"
        className="my-2 block h-24 w-full max-w-[320px] animate-pulse rounded-md bg-surface-sunken"
      />
    );
  }
  if (!data) {
    return <span className="italic text-text-subtle">{alt || path.split("/").pop()}</span>;
  }
  return (
    <img
      src={data}
      alt={alt ?? ""}
      className="my-2 inline-block max-w-full rounded-md border border-border"
    />
  );
}
