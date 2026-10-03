// src/lib/hooks/useHistoryNav.ts — whether the app's own history has somewhere to go back or forward to.
//
// React Router stamps every history entry with an `idx` in `window.history.state`.
// The hook reads the current one and remembers the furthest it has reached,
// which a new entry (PUSH) resets: going back past the first entry would leave
// the app, and going forward past the furthest would do nothing, so the title
// bar's arrows grey out there (spec web-ui "Go back and forward from the title bar").
import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate, useNavigationType } from "react-router-dom";

function currentIdx(): number {
  const state = window.history.state as { idx?: unknown } | null;
  return typeof state?.idx === "number" ? state.idx : 0;
}

/** @ui-only where the title bar's arrows can go; never crosses the wire. */
export interface HistoryNav {
  canGoBack: boolean;
  canGoForward: boolean;
  goBack: () => void;
  goForward: () => void;
}

export function useHistoryNav(): HistoryNav {
  const navigate = useNavigate();
  const location = useLocation();
  const type = useNavigationType();
  const [pos, setPos] = useState(() => ({ idx: currentIdx(), max: currentIdx() }));

  useEffect(() => {
    const idx = currentIdx();
    setPos((prev) => ({ idx, max: type === "PUSH" ? idx : Math.max(prev.max, idx) }));
  }, [location, type]);

  const canGoBack = pos.idx > 0;
  const canGoForward = pos.idx < pos.max;
  const goBack = useCallback(() => {
    if (canGoBack) navigate(-1);
  }, [canGoBack, navigate]);
  const goForward = useCallback(() => {
    if (canGoForward) navigate(1);
  }, [canGoForward, navigate]);
  return { canGoBack, canGoForward, goBack, goForward };
}
