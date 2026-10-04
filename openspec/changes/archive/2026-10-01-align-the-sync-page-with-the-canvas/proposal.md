## Why

The Sync page and Settings › Data › Vault were built before the final design, so their layout does not
match the boards in canvas ⑥ (6.5.x and 6.2.07–6.2.10). The page split what a person opens Sync for
across Runs and Setup tabs, kept the master key there after it moved to Settings › Security, and the
Vault block showed rows the design dropped. Some sync chores also cannot be done by Coffer at all:
merging two edits of one file, a remote that refuses a push or a sign-in, a machine without git.
Principle IV (AI-Native) says those go to the person's agent as a prompt, and no sync surface offered
one.

## What Changes

- The Sync page has three tabs, as drawn: **Status** (the landing tab), **Machines** and **Remote**.
  - The header carries the status in one word ("In sync", "2 changes to push", "Stopped: 2 conflicts",
    "Push failed", "Paused" …), Sync now / Try again, and the remote URL with a copy button.
  - Status shows a banner, the four area counts, what waits to push, a card for a stopped round or a
    join's differing files, and the Rounds table. A round opens in a drawer and rolls back from it.
  - Conflicts are resolved on their own view (`/sync/conflicts`). Each file has two choices, Open in
    editor, and the diff each choice makes.
  - Held deletions are reviewed on their own view (`/sync/deletions`).
  - Remote is the settings of the one remote: URL, branch, secret, user name, when rounds run
    ("Only when I press Sync now" pauses it), encrypted secrets, the vault's folder, Stop syncing.
  - Machines lists every machine. The one that curates knowledge is tagged "Runs curation".
  - Set-up and joining replace the tabs until this machine has joined.
  - The master key card leaves Sync; its import and export are in Settings › Security.
- **Merge with an agent.** A round stopped on files both machines edited carries a hand-off prompt
  (`StoppedRoundOut.handoff`, and the attention item's `handoff`). The prompt names:
  - the vault;
  - each file, with both sides' commits;
  - how to see each side's diff with `git -C <vault>`;
  - the marked-up copy to edit, which Coffer writes under `derived/sync-conflicts/`;
  - the rule to edit only those copies and let Coffer commit;
  - how the person finishes.

  The person records the agent's merge with **I merged it**: `POST /api/v1/sync/stop/merged` or
  `coffer sync resolve --merged`. It is refused while a copy still has a conflict marker. Continue
  round finishes the round as before. `coffer sync conflicts --prompt` prints the prompt.
- **An encrypted secret in conflict** (`secret/*.enc`) offers only the two choices. It has no editor
  copy and no agent merge (`SYNC_SECRET_NOT_EDITABLE`). The prompt counts such files and never
  carries their contents.
- **A remote's failure is handed to an agent.** A rejected push, a refused sign-in and an unreachable
  remote carry a hand-off on the status's `problem` and on the attention item. The prompt holds:
  - the remote URL without credentials;
  - the branch;
  - the name of the secret, never its value;
  - git's message with tokens scrubbed;
  - what to check.

  A new attention item, `sync_push_failed`, carries it. `coffer sync status --prompt` prints it.
  Retry stays Coffer's own button.
- **git missing.** The status's problem is `git_missing`, with the shared install hand-off. The
  `GIT_MISSING` error carries it in `details.handoff` and names no installer.
- **Settings › Data › Vault** shows size, versions, location and Open folder, as drawn. The storage
  summary drops `latest_time`, `latest_writer` and `sync_configured`, which nothing shows any more.

## Capabilities

### Modified Capabilities

- `vault-sync`: the Sync page's tabs and views, merging with an agent, the refused-remote and
  git-missing hand-offs, the new route and the CLI options.
- `web-ui`: the shared-table and sidebar requirements name Sync's new tabs. The rounds table has
  no search or filter, and a round opens in a drawer.

## Impact

- Backend:
  - new `domain/sync/handoffs.py`;
  - `application/sync/service_status.py`, `round_answers.py`, `attention.py`;
  - `surfaces/http/sync_*` (new `POST /sync/stop/merged`, new fields);
  - `surfaces/cli/sync_cmd.py` and `sync_stop_cmd.py`;
  - `infrastructure/vault/git.py` (`GitMissing` details);
  - `infrastructure/storage_usage.py`.
- Frontend: `pages/sync/*`, `router.tsx`, `pages/settings/DataSettings.tsx`, en/zh strings.
- Docs: `guides/vault-sync.md` (with a GitLab example), `guides/web-ui.md`, `guides/troubleshooting.md`,
  the coffer-guide skill, and the generated references.
