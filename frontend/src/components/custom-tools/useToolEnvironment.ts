// src/components/custom-tools/useToolEnvironment.ts — the environment a saved group's tool form previews and tests
// in. One state for the whole form: the request help, the headers, the secret, the timeout and the run all read it.
// Picking one changes nothing saved. It starts at the first environment that is on and never moves by itself: an
// environment switched off or deleted while the form is open stays chosen, reported as such, until one is picked.
import { useEffect, useState } from "react";

import type { CustomToolEnvironment, CustomToolGroup } from "@/lib/api/customTools";
import {
  chooseEnvironment,
  firstEnabled,
  type EnvironmentChoice,
} from "@/lib/customTools/environmentContext";

export interface ToolEnvironment {
  name: string;
  setName: (name: string) => void;
  choice: EnvironmentChoice;
  /** The chosen environment when it can run, else null. */
  env: CustomToolEnvironment | null;
  /** The environment the form's fields describe: the chosen one, even switched off; null once deleted. */
  shown: CustomToolEnvironment | null;
}

/** `restart` changes when the form starts over (the drawer reopens, another tool opens). */
export function useToolEnvironment(
  group: CustomToolGroup | null,
  restart?: unknown,
): ToolEnvironment {
  const [name, setName] = useState(() => (group ? firstEnabled(group) : ""));
  useEffect(() => {
    if (group) setName(firstEnabled(group));
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only when the form starts over
  }, [restart]);
  const choice: EnvironmentChoice = group ? chooseEnvironment(group, name) : { state: "none" };
  return {
    name,
    setName,
    choice,
    env: choice.state === "ok" ? choice.environment : null,
    shown: choice.state === "ok" || choice.state === "disabled" ? choice.environment : null,
  };
}
