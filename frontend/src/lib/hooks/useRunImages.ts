// frontend/src/lib/hooks/useRunImages.ts — the images a note refers to, as
// object URLs the browser will actually display.
//
// A note is markdown the developer wrote, and a screenshot they pasted into it
// is an ordinary uploaded input the note names. Rendering it is not as simple
// as leaving the `src` alone: the daemon authorises by the `X-Coffer-Token`
// HEADER, and an `<img>` element cannot send one. So each referenced file is
// fetched the way every other request is and handed to the renderer as an
// object URL.
//
// Every URL created here is revoked. An object URL pins its blob for the
// lifetime of the document, so a note page opened and closed twenty times
// while a run goes would otherwise hold twenty copies of every screenshot.
import { useEffect, useState } from "react";

import { workflowApi } from "@/lib/api/workflow";

/** `![alt](src)` and `<img src="...">`, which is what a paste can produce. */
const IMAGE_SRC = /!\[[^\]]*\]\(([^)\s]+)\)|<img[^>]+src=["']([^"']+)["']/g;

/** Left alone: already absolute, already a blob, or a data URI. These are
 *  returned as themselves, so the renderer draws them where they point. */
export function isExternal(src: string): boolean {
  return /^[a-z]+:/i.test(src) || src.startsWith("//");
}

/**
 * The object URL for each image `markdown` refers to, keyed by the `src` it
 * wrote. A source that is already a URL is absent from the map, and the
 * renderer leaves those alone.
 *
 * Paths are resolved under the run's `inputs/` directory, because that is
 * where an upload lands and what its ref names. A `src` that is already
 * relative to the run (`artifacts/...`) is used as it stands.
 */
export function useRunImages(runId: string, markdown: string): Record<string, string> {
  const [urls, setUrls] = useState<Record<string, string>>({});

  useEffect(() => {
    const sources = new Set<string>();
    for (const match of markdown.matchAll(IMAGE_SRC)) {
      const src = match[1] ?? match[2];
      if (src && !isExternal(src)) sources.add(src);
    }
    if (runId.length === 0 || sources.size === 0) {
      setUrls({});
      return;
    }

    let live = true;
    const made: string[] = [];
    void Promise.all(
      [...sources].map(async (src) => {
        const path = src.includes("/") ? src : `inputs/${src}`;
        try {
          const blob = await workflowApi.readFileBytes(runId, path);
          return [src, URL.createObjectURL(blob)] as const;
        } catch {
          // A note can refer to a file that was unmounted since. The renderer
          // shows the broken image, which is the truth.
          return null;
        }
      }),
    ).then((pairs) => {
      const next: Record<string, string> = {};
      for (const pair of pairs) {
        if (pair === null) continue;
        made.push(pair[1]);
        next[pair[0]] = pair[1];
      }
      if (live) setUrls(next);
      else made.forEach((url) => URL.revokeObjectURL(url));
    });

    return () => {
      live = false;
      made.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [runId, markdown]);

  return urls;
}
