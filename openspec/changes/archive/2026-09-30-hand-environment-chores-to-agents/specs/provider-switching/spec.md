## MODIFIED Requirements

### Requirement: Detect a local model runtime without changing it
`POST /api/v1/providers/detect-local` and `coffer provider detect-local [--base-url <url>]` MUST
report which runtime answers at a loopback URL — or, with none given, at each runtime's default port
(Ollama 11434, LM Studio 1234, llama-server 8080; vLLM's default 8000 is the daemon's own port, so
vLLM is found only on a URL the user gives) — by fingerprint rather than port, with its version, the
wires it serves at that version and, per model, the context window it serves and whether it can
call tools, where the runtime says. Detection MUST be read-only — nothing is pulled, loaded or
downloaded — and MUST refuse a non-loopback URL as 422. A runtime below the minimum version for a
wire (Ollama 0.14.0 for Messages and 0.13.4 for Responses, LM Studio 0.4.1 and 0.3.29, vLLM 0.11.1
and 0.10.0) is not reported as serving it. When nothing answers, the response MUST carry
`handoff`, a prompt the daemon writes (see [skill-manager](../skill-manager/spec.md) "Hand a
required command to an agent with a prompt" for the shape every hand-off takes) asking the
person's agent to set a runtime up on this machine — naming the machine's OS, architecture and,
where it is known, its memory; the runtimes detection probes with their default ports; the
versions from which Ollama and LM Studio serve both wires; that an agent needs a tool-calling
model with a window of at least 64k tokens — preferring Ollama or LM Studio, pulling one
tool-calling chat model that fits, confirming it answers on its default port, and then telling
the person to press Detect; it MUST name no installer or command, and it MUST be `null` once a
runtime answers. `coffer provider detect-local` MUST print the same prompt when it finds nothing.
The Add provider dialog's local path MUST offer that prompt beside its note that nothing
answered, and keep typing the address of a runtime that is already running.

#### Scenario: detection reads the runtime, version and served windows
- **GIVEN** an Ollama runtime 0.14.2 on a loopback port serving `qwen3-coder` with a 65536-token window and tool support
- **WHEN** the user runs detection against that URL
- **THEN** it reports `ollama` 0.14.2 serving both wires, and `qwen3-coder` with a 65536-token window and tools

#### Scenario: a runtime below the minimum version serves no wire it lacks
- **GIVEN** an Ollama runtime 0.13.5 on a loopback port
- **WHEN** detection runs
- **THEN** it reports Responses and not Messages

#### Scenario: detection refuses a non-loopback address
- **GIVEN** the daemon is running
- **WHEN** detection is asked to probe `http://example.com:11434`
- **THEN** it is refused as 422 and no request leaves the machine

#### Scenario: nothing found hands setting up a runtime to an agent
- **GIVEN** a loopback port nothing answers on
- **WHEN** detection probes it, and the Add provider dialog shows the result
- **THEN** the response finds nothing and carries a prompt naming this machine, Ollama on 11434, LM Studio on 1234 and llama-server on 8080, preferring Ollama or LM Studio, ending with pressing Detect and the standing rules every hand-off ends with, and naming no install command
- **AND** the dialog says nothing answered, keeps typing a running runtime's address as the other way, and offers Copy prompt with that prompt

### Requirement: Offer an opt-in statusline wrapper
`coffer usage statusline -- <the user's own statusLine command>` MUST forward the `rate_limits`
object of the statusline JSON Claude Code writes to its stdin to
`POST /api/v1/usage/quota/statusline`, with a timeout of at most one second and never starting a
daemon, then run the user's own command with the same stdin and print its output and exit code —
even when the daemon is down. Coffer never installs it: the user opts in by setting it as their
`statusLine` command, which covers the Claude Code sessions they run in their own terminal.
Because that is an edit to a setting of Claude Code's that differs per person, it is handed to
the person's agent: while Claude Code has no quota value, its row in `GET /api/v1/usage/quota`
(and in the refresh answer) MUST carry `handoff`, a prompt the daemon writes asking the agent to
wrap the current `statusLine.command` in the registered Claude Code agent's `settings.json` (the
standard `~/.claude` when none is registered) as `coffer usage statusline -- '<it>'`, kept as one
argument, or to add a `statusLine` that runs `coffer usage statusline` alone when there is none;
to keep every other setting; and to show the diff before saving. The prompt MUST NOT ask for a
credential, an OAuth token or a quota endpoint. Every other row's `handoff` is `null`, and Claude
Code's is `null` once a value is seen. `coffer usage quota --prompt` MUST print the same prompt,
and the Usage page MUST offer it on Claude Code's row with no reading, and no switch that turns
the wrapper on.

#### Scenario: the user's statusline command still runs with the daemon down
- **GIVEN** no daemon running
- **WHEN** Claude Code runs the wrapper with the user's own statusline command
- **THEN** the user's command runs with the same stdin and its output is printed

#### Scenario: the quota page hands the statusline opt-in to an agent
- **GIVEN** a Claude Code agent registered with its own config dir, and no quota value for it yet
- **WHEN** the quota is read and the Usage page shows it
- **THEN** Claude Code's row carries a prompt naming that config dir's `settings.json`, the wrapper's form, the no-`statusLine` case and showing the diff first, and naming no token; Codex's row carries none
- **AND** the page offers Copy prompt on Claude Code's row only, with no switch
- **AND** once a value is seen the row carries no prompt
