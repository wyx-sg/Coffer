// src/test/blockedStorage.ts — test helper: make window.localStorage throw, then restore it.
//
// `mode: "access"` makes reading `window.localStorage` itself throw (storage
// disabled by the browser); `mode: "methods"` returns a Storage whose every
// method throws (quota / security errors on use).
export function blockLocalStorage(mode: "access" | "methods" = "methods"): () => void {
  const own = Object.getOwnPropertyDescriptor(window, "localStorage");
  const fail = () => {
    throw new DOMException("blocked", "SecurityError");
  };
  const throwing = {
    getItem: fail,
    setItem: fail,
    removeItem: fail,
    clear: fail,
    key: fail,
    get length(): number {
      return fail();
    },
  };
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    get: mode === "access" ? fail : () => throwing,
  });
  return () => {
    if (own) Object.defineProperty(window, "localStorage", own);
    else delete (window as unknown as { localStorage?: unknown }).localStorage;
  };
}
