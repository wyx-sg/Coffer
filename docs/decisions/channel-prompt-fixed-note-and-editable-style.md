# A Channel's System Prompt Is a Fixed Channel Note Plus a Reply Style the Owner Can Rewrite

**Status**: Accepted
**Date**: 2026-10-12
**Deciders**: Yuxing Wu
**Related**: [A Channel Turn Shows Progress on a Preview Surface Where One Exists, and the Reply Is the Answer Alone](channel-live-surface-strategy.md), [Channels Are Thin Transport Adapters Over One Shared Core](channel-adapter-framework.md), spec channels "Tell a channel-driven agent it is on a chat channel" and "Let the owner rewrite a channel's reply style"

## Context

Every turn that comes from a chat channel carries a system-prompt append that
Coffer writes: where the agent is (SeaTalk group thread, Telegram direct chat),
what Markdown renders there, how to send a file (`MEDIA:/absolute/path`), how
to ask the owner with buttons (`coffer__ask`), that only the text after the
last tool call is sent, that it cannot click dialogs on the computer, and how a
reply should read (outcome first, about 15 lines, no narrated steps, evidence
quoted verbatim). The owner could add instructions of their own, per chat kind,
which were appended after Coffer's text under `Instructions from the channel's
owner:`.

The owner could not see Coffer's text. The Settings tab showed only their own
additions, blank by default, so they did not know what the agent was already
told, and could not change any of it — only pile instructions on top, some of
which contradicted it ("answer in detail" after "at most about 15 lines").

Coffer's text is not one kind of thing. About half of it is a **contract** with
the channel: the agent sends a file only by writing the `MEDIA:` line, a
question reaches the owner as buttons only through `coffer__ask`, a reply
written before the last tool call is never sent. Change those words and a
feature stops working with no error anywhere. It also varies with the running
transport (what renders, whether `## Details` collapses, whether threads can be
read), so it is generated, not a fixed string. The other half is **style**:
how long, what goes first, what to leave out. Changing that is a matter of taste
and breaks nothing.

How comparable products handle a built-in prompt the user may want to change:

- **Hidden built-in, user text appended** — ChatGPT custom instructions, Cursor
  rules, GitHub Copilot custom instructions, Cline. Safe, but the user cannot
  see what the model is already told.
- **Prefilled and editable, the edit replaces it** — n8n's AI Agent system
  message, Dify's prompt template, Open WebUI's per-model system prompt.
  Visible and fully editable; an edited prompt no longer receives the product's
  improvements.
- **Default shown, overridable, with reset** — Roo Code's Prompts view shows
  each mode's role definition prefilled, lets the user edit it, offers "reset
  to default", and separately previews the whole composed system prompt.
  OpenClaw seeds its workspace files (`AGENTS.md`, `SOUL.md`) with defaults the
  user edits in place.

(From what is publicly documented of these products as of 2026-10; not
re-verified line by line.)

The question is two forks: what the owner may edit, and what happens to an
edited prompt when Coffer's own text improves.

## Options Considered

### Option A — Split it: the channel note is shown read-only, the reply style is editable with a default (chosen)

The append becomes two parts. The **channel note** — where the agent is, what
renders, `MEDIA:`, `coffer__ask`, the last-tool-call rule, no clicking dialogs,
the thread tool — is generated per channel and chat kind as before and shown
on the Settings tab read-only. The **reply style** — write like a person
texting, the answer first in one or two sentences, no process or caveat lists,
about 8 lines, a full report only as a file offered first, diagrams as PNG,
evidence verbatim — is a default text Coffer ships. Each chat kind of each channel
either follows the default (stored empty) or holds the owner's rewrite. The
turn carries the note, then `Reply style:` and the style in force.

An edit stores the full rewritten text plus a fingerprint of the default it was
written against. When Coffer later changes the default, a channel that follows
it gets the new text on its next turn; a channel holding a rewrite keeps it,
and the Settings tab says the default has changed since, with **Restore
default** in the edit dialog. Text saved equal to the default is stored empty,
so it goes back to following.

- Pros: the owner sees everything the agent is told and can change everything
  that is theirs to change. The features that depend on exact wording cannot be
  edited away. An untouched channel keeps improving with Coffer; an edited one
  is never silently overwritten, and is told when there is something new.
- Cons: two parts to explain instead of one; a fingerprint to store per chat
  kind; the line between "contract" and "style" is a judgement that has to be
  kept as the text evolves (a new feature instruction belongs in the note).

Wins because it is the only option that is fully visible, safe, and keeps
updates flowing to everyone who has not deliberately diverged.

### Option B — Show the whole built-in text read-only, keep appending the owner's text

The Settings tab shows Coffer's full append for each chat kind; the owner's
prompt stays an addition after it.

- Pros: smallest change; nothing the owner does can break a feature; every
  improvement reaches every channel.
- Cons: the owner still cannot change the style, only contradict it, and the
  agent then receives two conflicting instructions and picks one. The visible
  default reads like a setting they cannot change.

Loses because the point of the request was to be able to change what Coffer
says, not only to read it.

### Option C — Prefill the whole built-in text, and an edit replaces it

The Settings tab shows Coffer's full text in an editable field; saving stores
it, and the stored text replaces Coffer's on every turn.

- Pros: maximum freedom; one field, one concept; the pattern most chat
  front-ends use.
- Cons: deleting or rewording the `MEDIA:` or `coffer__ask` lines silently
  breaks sending files and asking questions, and nothing tells the owner why.
  The note is generated per transport (what renders, details, threads), so a
  saved copy freezes one transport's state and is wrong after a capability
  change. Every improvement to the text stops reaching a channel the moment it
  is edited, with no way to tell.

Loses on safety: it turns a feature contract into free text the owner is
invited to rewrite.

### Option D — Keep the built-in text hidden, the owner's text appended (the design this replaced)

- Pros: simplest; safe; always current.
- Cons: the owner cannot see or change what the agent is told, which is exactly
  the complaint.

Loses: it is the status quo the request rejects.

### Sub-choice — how an edited style learns of a new default

- **Fingerprint and notice (chosen):** store the hash of the default an edit
  was written against; the page compares it with today's default. The owner
  decides whether to adopt the change. No text is merged.
- **Three-way merge of the owner's edit onto the new default:** automatic, but
  prose does not merge reliably, and a wrong merge is worse than a notice.
- **Version number on the default:** works, but a version must be bumped by
  hand whenever the text changes; a hash cannot be forgotten.
- **Always overwrite on upgrade:** loses the owner's work.

## Decision

A channel turn's system-prompt append is the channel note followed by
`Reply style:` and the reply style in force for its chat kind.

- The channel note is generated by Coffer per channel and chat kind
  (`channel_note_text`), shown read-only on the channel's Settings tab, and
  never stored in the channel's config. Anything a feature depends on —
  how to send, how to ask, what is sent, what renders — belongs here.
- The reply style is `direct_reply_style` / `group_reply_style` in the
  channel's config: empty follows Coffer's default (`DEFAULT_REPLY_STYLE`);
  text equal to the default is stored empty; anything else is the owner's
  rewrite, up to 6,000 characters, with `*_reply_style_base` holding the
  fingerprint of the default it was written against.
- A channel stored with the old `direct_system_prompt` / `group_system_prompt`
  migrates on read: an owner prompt becomes a rewrite holding Coffer's default
  style followed by that prompt, so the agent reads the same instructions as
  before.

## Consequences

- The Settings tab shows the agent's full channel instructions; the owner can
  restore the default at any time.
- Adding an instruction a feature depends on means adding it to the channel
  note, not the default style; otherwise channels with a rewrite never get it.
- Changing `DEFAULT_REPLY_STYLE` changes its fingerprint, which flags every
  rewritten style on the Settings tab until its owner saves it again. A reply
  that ignores the style and runs too long is caught after the fact, whatever
  style is in force: see [A Long Channel Reply Is Rewritten Short by the
  Agent](long-channel-reply-is-rewritten-short.md).
- The config keys changed (`*_system_prompt` → `*_reply_style`). Channels are
  machine-local ([Channels Are Machine-Local Resources](channels-are-machine-local-resources.md)),
  so the migration runs on the one machine that holds the channel; REST callers
  still sending the old keys are migrated the same way.
- Enforced in `backend/coffer/domain/chat/channel_prompt.py` (the two parts and
  the default), `backend/coffer/domain/channel/config.py` (storage, settling,
  migration) and `backend/coffer/surfaces/http/channel_prompt_preview.py` (what
  the page shows).
