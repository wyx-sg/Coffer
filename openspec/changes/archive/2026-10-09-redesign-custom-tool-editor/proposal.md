## Why

The custom tool editor was one long column: request, description, headers, body,
arguments and the test stacked in a 640 drawer, two screens of scrolling with the
result at the very bottom. Arguments were a separate table with nothing tying
them to the `{holes}` of the request, so an argument that went nowhere or a hole
with no argument went unnoticed. Adding a tool used a dialog with the same fields
in another order. On the group's page, a group with one environment had its base
URL and headers in Edit group while a group with several had them under
Environments: the same setting in two places.

## What Changes

- One **tool editor** for the drawer and Add a request: tabs General · Request ·
  Arguments · Response on the left, **Try it** on the right, always in view. The
  drawer widens to 1040, and so does the add dialog's request step.
- Request shows the path's query parameters as rows kept in step with the path;
  a GET's body says it sends none.
- Arguments says where the request uses each argument and flags an argument used
  nowhere (Add as query parameter, Remove argument) and a hole with no argument
  (Add argument).
- Response states when a call counts as failed and what the agent gets; it is
  where per-group and per-tool success rules will be edited.
- Try it shows the request it would send (Preview) and, after a run, the Result,
  on two tabs.
- The group's definition no longer names a base URL or headers; every group lists
  its environments, and Edit group edits only the description and timeout.

## Impact

- `web-ui`: "Manage custom tool groups on their own page" and "Preview and test a
  custom tool in one chosen environment" are modified.
- Frontend only; no API change. Canvas 4 (Capabilities) custom-tools boards; the
  docs site's custom tools guide (en and zh).
