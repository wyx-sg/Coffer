# Competitive Research — Messaging-Channel Connectivity & Routing for Agents

> English: this file · 中文版: [messaging-channels.zh.md](./messaging-channels.zh.md)
>
> Internal competitive-research report for Coffer's channels feature (spec 009,
> ADR-014). **Date:** 2026-06-16. **Method:** deep-research harness. Angles A/B/C
> covered; some HITL platforms and Rasa/Chatwoot/Voiceflow/Sweep unverified.

## 1. Landscape at a glance

"Connect an agent to messaging apps" is really three adjacent markets:

| Angle                              | What it is                             | Examples                                                   |
| ---------------------------------- | -------------------------------------- | ---------------------------------------------------------- |
| **(A) Omnichannel bot connectors** | One bot/agent ↔ many channels, hosted | Azure Bot Service Channels, Botpress, Twilio Conversations |
| **(B) ChatOps for coding agents**  | Drive a coding agent from chat (team)  | Claude Code Slack, Devin, Cursor, OpenHands                |
| **(C) In-chat human approval**     | Approve agent actions from chat        | HumanLayer, Slack Block Kit, n8n / LangGraph HITL          |

### Key findings

- **Connectors normalize channels into a channel-agnostic core** — Azure's
  "Activity" model, Botpress's Telegraf layer — which is structurally the same
  **N+M** decoupling Coffer uses (a new channel never touches agent code). The
  difference is they are **hosted/team**; Coffer self-hosts a **signed callback
  listener**. Telegram auth is a bot token; Slack needs app credentials via the
  platform's callbacks. [confirmed 3-0 — learn.microsoft.com Azure Bot Service;
  Azure Bot SDK archived Dec 2025, Channels GA]
- **Twilio Conversations is the clearest many-to-many model Coffer lacks:**
  number-pair routing, inbound auto-creation, and a **per-conversation bot**
  bound via webhooks (up to five). Coffer binds **one default agent per
  channel.** [confirmed 3-0 — twilio.com/docs/conversations]
- **Coding ChatOps is the inverse of Coffer's security model.** Claude Code
  (Slack), Devin, Cursor, and OpenHands use **workspace OAuth + per-user
  account linking**, gated by channel-invite + per-user identity — a **team**
  model. Coffer uses a **single owner, one pairing code, strangers silently
  ignored.** Cursor leads on N-to-M routing. [confirmed 3-0 —
  code.claude.com/docs/slack; docs.devin.ai; cursor.com; openhands]
- **Approval + notification are table stakes** (e.g. `ccgram` drives Claude Code
  from Telegram via hooks). But **Coffer's exact combination — a channel that is
  a managed _resource_, stealth pairing, a _shared_ approval gate reused by the
  web console, and an N+M signed listener — has no exact analog.** [medium]
- **The closest single analog to Coffer's pairing/stealth design is Anthropic's
  own official Telegram plugin** (`claude-plugins-official/external_plugins/
telegram`), whose README + ACCESS.md document pairing, an owner allowlist, and
  silent-ignore — validating Coffer's security posture, though it is one plugin,
  not a managed multi-channel framework.

## 2. Capability comparison

| Capability                     | Azure Bot Svc | Twilio Conv. | Claude Code Slack / Devin | Anthropic TG plugin | **Coffer channels**                          |
| ------------------------------ | ------------- | ------------ | ------------------------- | ------------------- | -------------------------------------------- |
| Channel-agnostic core (N+M)    | ✅ Activity   | ✅           | ✅                        | —                   | **✅**                                       |
| Channels supported             | many          | SMS/WA/chat  | Slack (+GitHub)           | Telegram            | **Telegram, SeaTalk**                        |
| Hosting                        | cloud         | cloud        | cloud/SaaS                | self-host           | **self-host (signed listener + tunnel)**     |
| Access model                   | app/org       | per number   | **team OAuth + per-user** | owner allowlist     | **single-owner pairing, stealth**            |
| Channel = managed resource     | ❌ config     | ❌           | ❌                        | ❌                  | **✅ resource (lifecycle/audit/cred-probe)** |
| Per-conversation agent binding | partial       | **✅**       | ✅                        | ❌                  | **❌ one default agent/channel**             |
| In-chat approval               | via Block Kit | —            | ✅                        | ✅                  | **✅ shared gate w/ web console**            |
| Notifications push             | ✅            | ✅           | ✅                        | ✅                  | **✅**                                       |
| Single-user local-first        | ❌            | ❌           | ❌                        | ✅                  | **✅**                                       |

## 3. How Coffer compares

**Where Coffer is distinctive.**

1. **Channel as a first-class managed resource.** Connectors treat a channel as
   config; Coffer makes it a `channel:<name>` resource with lifecycle, audit, and
   credential-probing — consistent with every other Coffer asset.
2. **Single-owner stealth pairing is a security posture the team tools don't
   have.** Omnichannel/ChatOps tools assume a trusted org (workspace OAuth);
   Coffer fails closed for a personal vault — a pairing code, and the bot never
   reveals it is alive to strangers. Only Anthropic's own Telegram plugin matches
   this, which validates the design.
3. **Shared approval gate.** In-chat approval runs over the _same_ seams as the
   web console (one approval path, two surfaces). HumanLayer does in-chat
   approval but as a separate SaaS; Coffer folds it into the vault.
4. **Self-hosted signed listener** behind a user-run tunnel — local-first, vs
   hosted connectors.

**Where Coffer lags.**

1. **Only Telegram + SeaTalk.** No Slack/WhatsApp/Teams/Discord — and Slack is
   exactly where coding-agent ChatOps lives.
2. **One default agent per channel; no per-conversation binding.** Twilio's
   per-conversation bot is the model to copy: a single channel routing different
   conversations to different agents.
3. **Single owner, no team routing** — a deliberate choice, but it cedes the
   whole team segment.
4. **No rich interactive UI** (Slack Block Kit buttons) beyond approval.

## 4. Key takeaways for Coffer

1. **The channel-as-resource + stealth-pairing + shared-approval combo is
   genuinely differentiated** — Anthropic's own Telegram plugin is the only close
   analog, which is validation, not competition. Lead with it.
2. **Borrow per-conversation agent binding** (Twilio model) so one channel can
   route different conversations to different agents — the clearest functional
   gap.
3. **Add a Slack adapter next.** ChatOps gravity is on Slack; your N+M
   architecture makes a new channel an adapter, not a rewrite.
4. **Keep single-owner as a conscious scope decision** — team routing is a
   different product; don't drift into it by accident.
5. **Consider per-platform interactive controls** (buttons) for approvals where
   the platform supports them (Slack Block Kit, Telegram inline keyboards).

## 5. Sources

Primary:

- learn.microsoft.com/azure/bot-service — manage-channels, connect-telegram, connect-slack
- twilio.com/docs/conversations — inbound-autocreation, conversations-webhooks
- botpress.com/integrations/telegram
- code.claude.com/docs/en/slack · docs.devin.ai/integrations/slack · cursor.com/docs/integrations/slack · docs.openhands.dev (slack)
- github.com/anthropics/claude-plugins-official — external_plugins/telegram (README, ACCESS.md)
- github.com/jsayubi/ccgram · dev.to (control Claude Code from Telegram/Discord/Slack)
- docs.slack.dev/interactivity · docs.n8n.io/advanced-ai/human-in-the-loop-tools · docs.langchain.com (deepagents HITL) · github.com/humanlayer/humanlayer

## Verification update (2026-06-19)

> Re-verification pass. The two-part local claim is now partly stale:
> channel-as-managed-resource and single-owner stealth pairing hold, but the
> "shared approval gate reused by the web console" was removed by commit
> `165f0e6` (PR #101, merged 2026-06-18) — two days after this report's
> 2026-06-16 date — which deleted the entire tool-approval system. All three
> web claims (Anthropic Telegram plugin, Twilio "up to five" webhooks, Azure
> Bot SDK archived) confirmed against primary sources.

### ✅ Confirmed

- **Channel = managed resource.** ADR-014 §Decision item 1 makes a channel a
  resource kind (`channel:<name>`, ADR-007) on the generic
  lifecycle/audit/credential-ref machinery; `kind.py` probes `*_ref` credential
  fields at registration. (`repo:docs/decisions/ADR-014-channel-adapter-framework.md`,
  `repo:backend/coffer/application/channel/kind.py`)
- **Single-owner stealth pairing.** `pairing.py` implements one pending pairing
  code per channel (8 chars, 1-hour TTL, bounded attempts, fail-closed,
  memory-only); `inbound.py` is an owner-gated bridge that silently ignores
  wrong-member/stranger messages (lines 165–202); spec.md User Story 2 codifies
  "the bot never reveals it is alive to strangers."
  (`repo:backend/coffer/application/channel/pairing.py`,
  `repo:backend/coffer/application/channel/inbound.py`)
- **Anthropic's official Telegram plugin** matches Coffer's pairing/stealth
  posture: DM the bot for a 6-char pairing code; default `pairing` policy then
  switch to `allowlist` so "strangers don't get pairing-code replies"; access
  state in `~/.claude/channels/telegram/access.json`. One self-host plugin, not
  a managed multi-channel framework — as the report states.
  (https://github.com/anthropics/claude-plugins-official/blob/main/external_plugins/telegram/README.md)
- **Twilio Conversations "up to five" per-conversation webhooks** is exact: each
  Conversation can have as many as five conversation-scoped webhooks; a sixth is
  rejected with error 50361 "Too many conversation webhooks." Scoped webhooks
  are the documented mechanism for a per-conversation bot.
  (https://www.twilio.com/docs/conversations/api/conversation-scoped-webhook-resource,
  https://www.twilio.com/docs/api/errors/50361)
- **Azure Bot SDK archived Dec 2025, channels still GA.** Microsoft Learn states
  the Bot Framework SDK is planned to be archived no later than end of December
  2025, with new work directed to the Microsoft 365 Agents SDK, while channel
  infrastructure (V3) stays compatible with no EOL/disruption plan.
  (https://learn.microsoft.com/en-us/azure/bot-service/what-is-new?view=azure-bot-service-4.0)

### ✏️ Corrected

- **"Shared approval gate reused by the web console" — removed, no longer
  exists.** OLD (report 2026-06-16): in-chat approval runs over the same seams
  as the web console (one approval path, two surfaces), listed as a distinctive
  feature — key-findings bullet, capability table row "In-chat approval — shared
  gate w/ web console," §3 item 3, §4 takeaway 1. CORRECTED (current tree, post
  `165f0e6` / PR #101 merged 2026-06-18 16:48 +0800): the entire tool-approval
  system was deleted — `ApprovalGate`/`ApprovalChannel`/`ApprovalRequest`/
  `ApprovalDecision`, the channel `send`/`resolve_approval_prompt` +
  `on_approval_click` relay, the web `ApprovalCard` + approval seat, the
  `/conversations/{id}/approvals` route, and the `CHANNEL_APPROVAL_RESOLVED`
  audit event; `backend/coffer/application/chat/approvals.py` is gone; no
  `ApprovalGate`/"approval gate" symbols remain under `backend/coffer/` or
  `specs/009-channels/`; agents now run with full permissions. The commit's
  rationale is the report's own framing turned against it: the relay was
  "redundant with owner-pairing (only the paired owner can drive a channel, and
  the web console is the owner too)." The other two legs of local claim #1
  (channel = resource; single-owner stealth pairing) remain the load-bearing
  differentiators; the approval-gate leg should be struck or rewritten as
  historical. (git commit `165f0e6`)
- **"Azure Bot SDK"** — precise product name is the **Bot Framework SDK** (the
  SDK behind Azure Bot Service). (same Microsoft Learn source above)

### ➕ Coverage added

- **Rasa** — closest open-source structural analog to Coffer's N+M decoupling.
  Separates `InputChannel` (receives) from `OutputChannel` (sends); a custom
  connector subclasses `rasa.core.channels.channel.InputChannel`. Built-in
  connectors (Slack, Messenger, Telegram, Twilio, web chat) and any number of
  channels with no change to the dialogue model — same "new channel never
  touches agent code" property. Difference: server/team-hosted, no single-owner
  stealth-pairing posture; access control left to the deployment.
  (https://rasa.com/docs/reference/channels/custom-connectors/,
  https://rasa.com/docs/reference/channels/messaging-and-voice-channels/)
- **Chatwoot** — open-source omnichannel support desk (~22k stars) unifying live
  chat, email, WhatsApp, Instagram, Messenger, Telegram into one inbox. Channel
  binding is per-inbox: an AgentBot connects to an inbox, with auto-assignment
  routing by availability/language/region plus SLA escalation; built-in AI agent
  "Captain." Team/CX omnichannel model — the opposite of Coffer's single-owner
  personal-vault posture. (https://www.chatwoot.com/features/channels,
  https://github.com/chatwoot/chatwoot/wiki/Connecting-Agent-Bot-to-an-Inbox)
- **Voiceflow** — no-code platform to build/deploy chat and voice agents "across
  any channel": web widgets, phone (Twilio voice), mobile (API), WhatsApp
  natively, Instagram/Messenger/Telegram via connectors. One agent, many
  channels via connectors — but fully hosted SaaS, no self-host signed-listener
  or owner-pairing model; oriented at customer-facing bots, not a personal
  vault. (https://www.voiceflow.com/integrations/whatsapp,
  https://docs.voiceflow.com/docs/welcome)
- **HumanLayer (+ n8n) HITL approval** — tool-layer human-in-the-loop approval
  as a separate plane. HumanLayer's `@hl.require_approval()` decorator blocks a
  call until a human approves over Slack/Email/Discord, framework-agnostic; n8n
  offers the same shape as a "Send a message and wait for response" workflow node
  (Slack/Telegram/Teams/etc.), enforced per-tool. Both are EXTERNAL approval
  planes layered onto an agent — contrast with Coffer's old in-vault gate (now
  removed in PR #101); these HITL tools remain the live exemplars of in-chat
  approval. (https://pypi.org/project/humanlayer/,
  https://docs.n8n.io/advanced-ai/human-in-the-loop-tools/)
