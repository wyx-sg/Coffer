import "@testing-library/jest-dom";
// Initialise i18next with the real locale bundles so components that call
// useTranslation() work in jsdom without needing React.Suspense wrappers.
import "@/i18n";

// Node 22+ ships an experimental built-in Web Storage that, under vitest's
// jsdom environment, leaves both `window.localStorage` and the bare
// `localStorage` global `undefined` (it's only populated with
// `--localstorage-file`). Any component reading `localStorage` (e.g.
// FileActions → preferred editor) then throws "Cannot read properties of
// undefined". Install a minimal in-memory Storage on both `window` and
// `globalThis` so tests get a real, isolated store.
if (typeof window !== "undefined" && !window.localStorage) {
  class MemoryStorage implements Storage {
    private store = new Map<string, string>();
    get length(): number {
      return this.store.size;
    }
    clear(): void {
      this.store.clear();
    }
    getItem(key: string): string | null {
      return this.store.has(key) ? (this.store.get(key) as string) : null;
    }
    key(index: number): string | null {
      return Array.from(this.store.keys())[index] ?? null;
    }
    removeItem(key: string): void {
      this.store.delete(key);
    }
    setItem(key: string, value: string): void {
      this.store.set(key, String(value));
    }
  }
  const storage = new MemoryStorage();
  Object.defineProperty(window, "localStorage", { configurable: true, value: storage });
  Object.defineProperty(globalThis, "localStorage", { configurable: true, value: storage });
}

// Radix UI's Select (and some other primitives) use ResizeObserver.
// jsdom doesn't implement it, so we stub it out for tests.
if (typeof global.ResizeObserver === "undefined") {
  global.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

// Radix Select uses scrollIntoView when focusing items.
if (typeof window !== "undefined" && !window.HTMLElement.prototype.scrollIntoView) {
  window.HTMLElement.prototype.scrollIntoView = function () {};
}

// Radix Select uses hasPointerCapture / setPointerCapture / releasePointerCapture.
if (typeof window !== "undefined" && !window.HTMLElement.prototype.hasPointerCapture) {
  window.HTMLElement.prototype.hasPointerCapture = function () {
    return false;
  };
}
if (typeof window !== "undefined" && !window.HTMLElement.prototype.setPointerCapture) {
  window.HTMLElement.prototype.setPointerCapture = function () {};
}
if (typeof window !== "undefined" && !window.HTMLElement.prototype.releasePointerCapture) {
  window.HTMLElement.prototype.releasePointerCapture = function () {};
}

// CodeMirror (the <CodeView> preview) measures ranges via Range.getClientRects,
// which jsdom does not implement — stub it so read-only previews mount quietly
// in tests. Real layout/scroll-to-match is verified by Playwright e2e.
if (typeof Range !== "undefined" && typeof Range.prototype.getClientRects !== "function") {
  const emptyRectList = {
    length: 0,
    item: () => null,
    [Symbol.iterator]: function* () {},
  } as unknown as DOMRectList;
  Range.prototype.getClientRects = () => emptyRectList;
  Range.prototype.getBoundingClientRect = () =>
    ({ x: 0, y: 0, top: 0, left: 0, right: 0, bottom: 0, width: 0, height: 0 }) as DOMRect;
}
