## Why

A skill's `requires:` names the commands it drives, and Coffer checks each one
where the agent runs. Many skills also need a secret — an API key or token the
person keeps in Coffer's secret store and the skill's commands receive through
`coffer run --secret`. Nothing said which secret a skill needs, so a skill
whose secret was never set failed at run time with nothing in Coffer pointing
at the cause.

## What Changes

- skill-manager: the mapping form of `requires:` also takes `secrets:`, a list
  of Coffer secret names. Only the mapping form carries it; the list form stays
  commands only. A mapping key other than `commands` and `secrets` is refused:
  it is reported as a warning and nothing under it is read.
- skill-manager: the skill read model carries `requires_secrets`, each secret's
  name and whether the secret store holds it (`is_set`), answered by presence
  alone — no value is read.
- skill-manager: a skill with a declared secret that is not set raises one
  "needs you" item (`skill_missing_secret`) naming each such secret, whose
  action opens the Secrets page. Setting a secret is the person's task, so the
  item carries no agent hand-off.
- web-ui: the Skills page's Requires tab lists the declared secrets with their
  state, a missing one reading "secret <name> is not set" and opening Secrets;
  the library row and the skill's banner say the same.
- Docs: the skills and skill-library guides describe `requires.secrets`.
