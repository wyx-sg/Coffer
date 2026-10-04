// e2e/web/specs/shell_settings_security.spec.ts
//
// Settings › Security and the Speech-to-text section of Settings › General
// against a real daemon (change revise-web-ui-ia). Security: the access token
// is masked until Show, Copy puts it on the clipboard, and a rotation installs
// the new token so the page keeps loading data with no reload; in a browser
// the master-key export names the desktop app instead of offering a control.
// General: an unset speech-to-text pair reads as not set, a seeded
// connection's curated speech models fill the model picker, and Test against a
// dead loopback endpoint reads as failing inline.
//
// These are plain tests: the component tests (SecuritySettings.test.tsx,
// EngineSettings.test.tsx) carry the scenarios' acceptance markers.
//
// The rotation changes the e2e daemon's token for every later spec. Each spec
// reads the token from daemon.json per request (readDaemonToken), which the
// daemon rewrites on rotation, and a page the daemon serves is handed the
// current token in its index.html — so later specs see the new one.

import { expect, test } from "@playwright/test";
import {
  beforeEachInjectToken,
  generateUniqueName,
  readDaemonToken,
} from "./_helpers";

beforeEachInjectToken();

async function api<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const { token, port } = readDaemonToken();
  const r = await fetch(`http://127.0.0.1:${port}/api/v1${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-Coffer-Token": token,
      "X-Coffer-Actor": "e2e",
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  if (!r.ok)
    throw new Error(`${method} ${path}: ${r.status} ${await r.text()}`);
  return (r.status === 204 ? undefined : await r.json()) as T;
}

type Provider = {
  uid: string;
  name: string;
  transcribe_default: boolean;
};

test("settings security masks, shows, copies and rotates the daemon token", async ({
  page,
  context,
}) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  const before = readDaemonToken().token;

  await page.goto("/settings/security");
  const modal = page.getByTestId("settings-modal");
  const box = modal.getByTestId("daemon-token");
  await expect(box).toHaveText(new RegExp(`^•+${before.slice(-4)}$`));

  await modal.getByRole("button", { name: /^Show$/ }).click();
  await expect(box).toHaveText(before);
  await modal.getByRole("button", { name: /^Hide$/ }).click();
  await expect(box).not.toHaveText(before);

  await modal.getByRole("button", { name: /^Copy$/ }).click();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(
    before,
  );

  // In a browser the key export is the app's job, never a working control.
  await expect(modal.getByText("Open in Coffer app")).toBeVisible();
  await expect(
    modal.getByRole("button", { name: /export master key/i }),
  ).toHaveCount(0);

  await modal.getByRole("button", { name: /^Rotate…$/ }).click();
  const dialog = page.getByRole("dialog", { name: /rotate the daemon token/i });
  await expect(dialog).toContainText("~/.coffer/daemon.json");
  await dialog.getByRole("button", { name: /^Rotate token$/ }).click();
  await expect(dialog).toHaveCount(0);

  const after = readDaemonToken().token;
  expect(after).not.toBe(before);
  await modal.getByRole("button", { name: /^Show$/ }).click();
  await expect(box).toHaveText(after);

  // No reload: switching tab in the modal loads data with the new token.
  await modal.getByRole("link", { name: /^General$/ }).click();
  await expect(page).toHaveURL(/\/settings\/general$/);
  await expect(
    modal.getByRole("combobox", { name: /^Transcription provider$/ }),
  ).toBeVisible();
});

test("settings general picks the speech-to-text model from a provider's curated list and tests it", async ({
  page,
}) => {
  const config = await api<{ transcribe_model: string | null }>(
    "GET",
    "/internal-engine-config",
  );
  const { providers } = await api<{ providers: Provider[] }>(
    "GET",
    "/providers",
  );
  const priorDefault = providers.find((p) => p.transcribe_default) ?? null;

  const name = generateUniqueName("e2emodel");
  // Nothing listens on the discard port, so every call fails at once — no
  // live endpoint is needed, and the curated list stands in for a probe.
  const created = await api<Provider>("POST", "/providers", {
    name,
    protocol: "ollama",
    base_url: "http://127.0.0.1:9",
    models: [
      { id: "e2e-chat-a", modality: "text" },
      { id: "e2e-whisper-a", modality: "audio" },
      { id: "e2e-whisper-b", modality: "audio" },
    ],
  });

  try {
    await page.goto("/settings/general");
    const section = page.getByTestId("speech-to-text-section");
    const state = section.getByTestId("model-state");
    if (priorDefault === null || !config.transcribe_model) {
      // A fresh daemon: nothing is transcribed, and the agent gets the file.
      await expect(state).toContainText(/Not set/);
      await expect(state).toContainText(/reach the agent as audio files/i);
    }

    await section
      .getByRole("combobox", { name: /^Transcription provider$/ })
      .click();
    await page.getByRole("option", { name }).click();

    await section
      .getByRole("combobox", { name: /^Transcription model$/ })
      .click();
    await expect(
      page.getByRole("option", { name: "e2e-whisper-a" }),
    ).toBeVisible();
    await expect(
      page.getByRole("option", { name: "e2e-whisper-b" }),
    ).toBeVisible();
    await expect(page.getByRole("option", { name: "e2e-chat-a" })).toHaveCount(
      0,
    );
    await page.getByRole("option", { name: "e2e-whisper-a" }).click();
    await expect(
      section.getByRole("combobox", { name: /^Transcription model$/ }),
    ).toHaveText(/e2e-whisper-a/);

    await section.getByRole("button", { name: /Test speech to text/i }).click();
    await expect(state).toContainText(/Failing/, { timeout: 15_000 });
    // The failed test changed nothing.
    const saved = await api<{ transcribe_model: string | null }>(
      "GET",
      "/internal-engine-config",
    );
    expect(saved.transcribe_model).toBe("e2e-whisper-a");
  } finally {
    // Put speech to text back the way the run found it.
    await api("PUT", "/internal-engine-config/transcribe-model", {
      model: config.transcribe_model,
    }).catch(() => undefined);
    if (priorDefault)
      await api(
        "POST",
        `/providers/${priorDefault.uid}/transcribe-default`,
      ).catch(() => undefined);
    await api("DELETE", `/providers/${created.uid}`).catch(() => undefined);
  }
});
