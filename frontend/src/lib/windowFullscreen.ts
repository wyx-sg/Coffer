// src/lib/windowFullscreen.ts — whether the window is full screen, watched.
//
// macOS hides the traffic lights in full screen, which moves the title strip's
// controls (board 1.1.02). A full-screen window covers the whole display; a
// zoomed one still leaves the menu bar, so comparing the viewport with the
// screen tells them apart without asking the shell. Entering or leaving full
// screen resizes the window, so every resize asks again.

function isFullscreen(): boolean {
  return window.innerWidth >= window.screen.width && window.innerHeight >= window.screen.height;
}

/** Call `callback` with whether the window is full screen — now, and after each
 *  resize. Returns the unsubscribe. */
export function watchWindowFullscreen(callback: (fullscreen: boolean) => void): () => void {
  const report = () => callback(isFullscreen());
  report();
  window.addEventListener("resize", report);
  return () => window.removeEventListener("resize", report);
}
