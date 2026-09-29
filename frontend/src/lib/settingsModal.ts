// src/lib/settingsModal.ts — open and close the Settings modal over the page underneath.
//
// Settings is a modal addressed by route (`/settings/<tab>`), rendered over a
// background location (spec web-ui "Open Settings as a modal from the sidebar
// footer"). Opening it pushes one history entry whose state carries the page
// the user was on; the shell keeps rendering that page underneath, so it stays
// mounted and unchanged. Switching tab replaces that entry, so browser Back
// always closes the modal rather than stepping through tabs. A fresh load of a
// Settings route has no background, and the shell puts Overview underneath.
import { useCallback } from "react";
import { useLocation, useNavigate, type Location } from "react-router-dom";

import { isSettingsPath, settingsPath, type SettingsTabId } from "@/lib/navigation";

/** What a Settings route's history entry carries. */
interface SettingsLocationState {
  /** The page under the modal; absent on a fresh load of a Settings route. */
  backgroundLocation?: Location;
}

/** Overview — the page under a Settings modal that was loaded directly. */
const OVERVIEW_LOCATION: Location = {
  pathname: "/",
  search: "",
  hash: "",
  state: null,
  key: "overview",
};

function backgroundOf(location: Location): Location | undefined {
  const state = location.state as SettingsLocationState | null | undefined;
  return state?.backgroundLocation;
}

/** The location of the page the user is on — the one under the modal while
 *  Settings is open, the current one otherwise. */
export function usePageLocation(): Location {
  const location = useLocation();
  if (!isSettingsPath(location.pathname)) return location;
  return backgroundOf(location) ?? OVERVIEW_LOCATION;
}

/** Whether the Settings modal is open. */
export function useSettingsOpen(): boolean {
  return isSettingsPath(useLocation().pathname);
}

/** Open the Settings modal on a tab, over the page the user is on. Called while
 *  it is already open, it switches tab in place (one history entry). */
export function useOpenSettings(): (tab?: SettingsTabId) => void {
  const location = useLocation();
  const navigate = useNavigate();
  return useCallback(
    (tab: SettingsTabId = "general") => {
      if (isSettingsPath(location.pathname)) {
        const state: SettingsLocationState = { backgroundLocation: backgroundOf(location) };
        navigate(settingsPath(tab), { replace: true, state });
        return;
      }
      const state: SettingsLocationState = { backgroundLocation: location };
      navigate(settingsPath(tab), { state });
    },
    [location, navigate],
  );
}

/** Close the modal and return to the page underneath at its own route. */
export function useCloseSettings(): () => void {
  const location = useLocation();
  const navigate = useNavigate();
  return useCallback(() => {
    const background = backgroundOf(location);
    if (background) {
      // Opened in-app: one entry was pushed, so stepping back lands on the page
      // exactly as it was, and a later Back does not revisit the modal.
      navigate(-1);
      return;
    }
    navigate("/", { replace: true });
  }, [location, navigate]);
}
