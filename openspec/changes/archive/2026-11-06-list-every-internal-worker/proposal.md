# List every internal worker

## Why

The Coffer internal section showed nine workers and folded the rest under
**Show all**. The owner wants it to read like the page's other lists, which
show every row: the fold hid workers for no gain.

## What Changes

- Coffer internal lists every worker the daemon reports: the ones a person
  recognises first, in their fixed order, then the rest by name. No **Show
  all** button.

## Impact

- Spec `daemon`: "Show Coffer's own background work beside the owner's tasks".
- Web UI: the Scheduled tasks page's list pane; docs en/zh; Run canvas.
