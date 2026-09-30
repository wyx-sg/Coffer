## Where a prompt travels

- **On the resource's own response** when the chore is a state of that resource (an agent type
  not installed, a server's missing launcher, a channel's missing SDK, a drift entry, an update
  preview, a scan result, a quota row, a local-runtime detect). The page already reads it.
- **In a coded error's `details.handoff`** when the chore is the reason a request was refused
  (`SHIM_NOT_FOUND`, `KNOWLEDGE_UNDO_CONFLICT`, `KNOWLEDGE_HISTORY_UNAVAILABLE`, a Git import
  with no git). The existing `error_details` mechanism carries it, so the error envelope gains no
  field. The frontend reads it with one helper (`lib/api/errorHandoff.ts`), and the CLI's
  `render_http_error` prints it for every command, so no command needs its own handling.
- **On the attention item** when the Overview should offer it. The item carries the same text the
  page offers, and its reason names no command.

## The Overview row

A Needs you row has room for one button, the item's action. The hand-off goes in the row's ⋯
menu (Copy prompt, then Ask an agent while a managed agent is available), through
`useAgentHandoff`, the hook `AgentHandoff` itself is built on. No canvas board shows a hand-off
control yet; this is the smallest change to the designed row.

## Ask an agent when the missing agent is the one that would be asked

`AgentHandoff` offers Ask an agent only while a managed agent is *available*. The agent whose
program is missing is not available, so Ask appears only when the other one is, and the
conversations page with no managed agent offers copy only. No extra prop is needed.

## I merged it

After an agent merges an upstream update into local edits, the pin must move without the files
changing. `POST /skills/{uid}/source/merged {commit}` re-fetches the source, accepts only a
commit that is waiting (the ref's tip or one between the pin and it), moves the pin, records the
pin's content hash as that commit's own content, and audits `skill_update_merged`. Recording the
upstream content rather than the merged folder's keeps the merged folder counted as edited
against its new base, so the next update is a conflict again that lists only the edits carried
over, instead of silently overwriting them.

## Restarting the daemon from a browser

The route spawns a detached successor with the same command and environment plus the
predecessor's pid, answers 202 with the port, then exits through the graceful path. The successor
waits for the old pid to exit before taking the lock and the port; if it never exits, the
successor finds a live daemon and stands down, so two never serve. A successor that cannot be
spawned leaves the daemon serving and the request fails. The launchd login service was not used:
it exists only with Start at login on and restarts only crashed daemons. `coffer daemon restart`
keeps its stop-then-start from outside, because it must work on a daemon that cannot answer.

## Secrets in prompts

Prompts carry names, paths and line numbers, never values: an MCP config summary lists env var
and header names only; a secret-scan prompt names the file, the line and the secret name each key
will become. Every prompt ends with the standing rule to leave any login to the person.
