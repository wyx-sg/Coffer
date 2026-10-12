// frontend/src/lib/knowledge/assets.ts
//
// Where a picture a document links lives (spec knowledge "Keep the pictures of
// an upload beside its source"): a relative `src` resolved against the
// document's own folder, as any Markdown reader would, to the knowledge path
// the asset route takes. A link off the page (`https:`, `data:`) or one that
// climbs out of the collection resolves to nothing.

const IMAGE = /\.(png|jpe?g|gif|webp|svg)$/i;

/** Whether a knowledge path names a picture. */
export function isImagePath(path: string): boolean {
  return IMAGE.test(path);
}

/** The knowledge path `src` names, read from the document at `documentPath`. */
export function resolveAsset(documentPath: string, src: string | undefined): string | null {
  if (!src || /^[a-z][a-z0-9+.-]*:/i.test(src) || src.startsWith("/") || src.startsWith("#")) {
    return null;
  }
  const clean = decodeURI(src.split(/[?#]/)[0]);
  const parts = documentPath.split("/").slice(0, -1);
  const collection = parts[0];
  for (const segment of clean.split("/")) {
    if (segment === "" || segment === ".") continue;
    if (segment === "..") {
      if (parts.length <= 1) return null;
      parts.pop();
    } else {
      parts.push(segment);
    }
  }
  return parts[0] === collection && parts.length > 1 ? parts.join("/") : null;
}
