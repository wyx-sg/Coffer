# Hand CLI installs to an agent

## Why

The CLIs page installed a missing command by running `brew install <formula>`
after a confirmation. That reaches only people who use Homebrew and only
skills that declare a formula, and keeping an installer correct across
machines is a maintenance load that grows with every package manager. Coffer
is AI-native: the person already has an agent that can look at this machine
and pick the right way to install a tool. What Coffer knows — which command,
which skills need it, the minimum version, the OS and architecture — is what
that agent needs, written up as a prompt.

## What Changes

- **Coffer installs nothing.** The Homebrew installer, its install job and
  streamed output, `POST` and `GET /api/v1/clis/{command}/install`,
  `coffer cli install`, the install confirmation dialog, the
  `cli_install_started` / `cli_install_finished` audit events, their five error
  codes and the `brew:` field of a skill's `requires:` entry are removed.
  Detection — `PATH`, version, login state — is unchanged.
- **A hand-off prompt instead.** Each required command that is missing or too
  old carries a short prompt asking the person's agent to install or update it
  the right way for this machine: it names the command, the skills that need it
  with their minimum versions, the OS and architecture, asks the agent to check
  with the person before anything that needs `sudo` or changes system settings,
  to confirm with `<command> --version`, and to leave any login to the person.
  A command that is installed but not logged in carries a prompt that asks only
  for help logging in. The prompt is built by the daemon and served on the
  command's REST response (`handoff.prompt`) and by `coffer cli prompt
  <command>`, so every surface hands over the same words.
- **A reusable hand-off block.** The prompt is written by one kind-agnostic
  builder (`domain/handoff.py`) that each feature feeds its facts, and shown by
  one web component with **Copy prompt** and **Ask an agent**, which opens a
  new conversation with a Coffer-managed agent with the prompt in the composer
  for the person to send. The CLI detail page, the CLIs list and a skill's
  Requires tab use it.

Capabilities whose requirements change: `skill-manager` (the declaration, the
check, the hand-off, the surfaces). The web UI's CLIs page requirement, still
in flight in change `revise-web-ui-ia`, is updated there.
