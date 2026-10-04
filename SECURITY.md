# Security Policy

## Supported Versions

Only the **latest release** is supported. Fixes land on `main` and ship in the next release; older releases receive no security backports.

## Threat Model in Brief

Coffer is a single-user tool that runs as you, beside coding agents that also run as you. The adversary it is designed against is a **prompt-injected agent running as the user** — one that read a hostile page, issue or tool result and now follows an attacker's instructions with the user's shell — and, second, **a web page in the user's browser** reaching the loopback daemon. Agents may still read and change Coffer's configuration; the boundary is the **secret**:

- **No route, command or MCP tool returns a secret's plaintext or the master key.** Revealing or copying a secret and writing a master key backup happen only in the Coffer desktop app, each behind its own Touch ID or login-password check with no reuse window, proven to the daemon by a one-time grant bound to that operation and signed with a key derived from the master key.
- **A secret goes to a new destination only after a person approves it in the desktop app** — an MCP server's environment variable or header, a channel's secret, the sync remote's push token, or a changed command line or URL for one of those. Switching the protection off waits for the same approval. Where a secret is placed (the header or variable it rides in, the protocol that presents a provider key) is part of what is approved, and a redirect to another origin is never sent it. Writing a secret's value, new or replacing, is open to every surface: whoever supplies a value already has it.
- **Every listener refuses a foreign `Host` and a foreign `Origin`**, and every management call needs the per-start token.
- **Agents get capabilities, not keys**: the gateway injects an HTTP upstream's headers itself.

What stays exposed, by design:

- **Group chats are not content-filtered.** In a group turn the agent can still read your memory, knowledge and files, and a SeaTalk group reply cannot be recalled by the platform. Coffer does not scan replies for secrets or personal data. Your safeguard is deleting a reply (`/del`, the 🗑 button); an agent tricked by a group member can still say something private. Do not pair the bot with a group that contains people you do not trust.

- A stdio MCP server's environment, including its secrets, is readable by any same-user process (`ps eww`), even from inside an agent's sandbox.
- A secret `coffer run` hands to a command is readable by the agent that ran the command; `coffer run` guards against accidents, not against that agent.
- An agent with Accessibility or screen control can click an approval.
- The signed `coffer` CLI shares the master key's Keychain access group; no CLI path returns the key or plaintext.
- Agents in bypass modes (`bypassPermissions`, `--yolo`, `danger-full-access`) have no sandbox of their own.
- **Development builds.** Until Coffer ships Developer-ID-signed binaries, the master key is the file `~/.coffer/master.key`, readable by any same-user process, so a presence grant can be forged and **the boundary does not hold**. It holds only in a signed release. For the same reason approvals are **off by default in a development build** (they would stop only accidents) and on by default in a signed release; a person can turn them on in either, and turning them off in a signed release still needs the desktop app.

The full model is in [`docs-site/architecture/security.md`](docs-site/architecture/security.md). A way to read a secret's plaintext or the master key, or to make Coffer send a secret to an unapproved target, without a present human in a signed build is a vulnerability — please report it as below.

## Reporting a Vulnerability

**Do not open a public GitHub issue for security findings.**

Two private channels:

1. **GitHub Private Vulnerability Reporting** (preferred): open a report at <https://github.com/wyx-sg/Coffer/security/advisories/new>. Authenticated users see a "Report a vulnerability" button on the Security tab.
2. **Email**: <hutwyx@gmail.com>. Encrypt with the maintainer's public PGP key if you have it; otherwise plain text is acceptable for non-critical findings.

## What to Include

- Affected commit or version.
- Reproduction steps (minimal repo, log excerpt).
- Impact assessment.
- Suggested mitigation, if any.

## Response

- **Acknowledgement**: within 72 hours.
- **Triage / first response**: within 7 days.
- **Fix / disclosure timeline**: agreed case-by-case; typical 30–90 days.

Coffer has a single maintainer, so response time is best-effort, not SLA-guaranteed.
