// src/test/pointerEvent.ts — test helper: a minimal PointerEvent for jsdom, which has none.
//
// Without it `fireEvent.pointerDown(el, { clientX, pointerId, button })` builds
// a bare `Event` and drops every coordinate, so a drag cannot be exercised.
// Importing this module installs the polyfill once (a no-op where the
// environment already has PointerEvent).
if (typeof window !== "undefined" && typeof window.PointerEvent === "undefined") {
  class PointerEventPolyfill extends MouseEvent {
    readonly pointerId: number;
    readonly pointerType: string;
    constructor(type: string, init: PointerEventInit = {}) {
      super(type, init);
      this.pointerId = init.pointerId ?? 0;
      this.pointerType = init.pointerType ?? "mouse";
    }
  }
  Object.defineProperty(window, "PointerEvent", {
    configurable: true,
    writable: true,
    value: PointerEventPolyfill,
  });
}

export {};
