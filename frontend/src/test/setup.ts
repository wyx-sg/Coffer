import "@testing-library/jest-dom";
// Initialise i18next with the real locale bundles so components that call
// useTranslation() work in jsdom without needing React.Suspense wrappers.
import "@/i18n";

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
