## Why

The secret detail page had a Usage tab fed by `GET /api/v1/secrets/uses`, and
nothing else read that route. The same rows are already on the Activity page,
so the tab duplicated it, and the detail was a tabbed page for one tab's worth
of content. The Secrets list also used its own controls rather than the other
library lists'. And skills could not cite a secret in the form the citation
index sees when they ran it, because `coffer run --secret` took only names.

## What Changes

- The secret detail shows the overview directly, with no tabs; the address is
  `/secrets/<id>`. `GET /api/v1/secrets/uses` and its schema are removed. Each
  use is still audited as `secret_resolved` and read in Activity.
- The list has a filter box, a Status chip (All / In use / Not used) and the
  secrets grouped under In use and Not used, like the other library lists.
  A row without a label reads as the first citer's name and slot.
- `coffer run --secret` accepts `ENV=coffer://secret/<id>` and a bare
  `coffer://secret/<id>`, so a skill cites a secret in the URI form and the
  secret's Used by lists the skill.

## Impact

- Backend: the uses route and `SecretUseOut` deleted; `coffer run` parses URIs.
- Frontend: tabs and Usage tab removed, list controls changed (another change set).
- Specs: secret, web-ui. Docs: guides/secrets (en + zh), CLI reference.
