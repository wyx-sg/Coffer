// src/lib/hooks/useWindowFullscreen.ts — whether the desktop window is full screen.
//
// macOS hides the traffic lights in full screen, so the title strip moves its
// controls to the left edge (board 1.1.02). Always false in a browser.
import { useEffect, useState } from "react";

import { watchWindowFullscreen } from "@/lib/windowFullscreen";

export function useWindowFullscreen(): boolean {
  const [fullscreen, setFullscreen] = useState(false);
  useEffect(() => watchWindowFullscreen(setFullscreen), []);
  return fullscreen;
}
