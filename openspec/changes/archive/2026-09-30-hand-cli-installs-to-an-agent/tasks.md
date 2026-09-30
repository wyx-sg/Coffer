# Tasks

## 1. Backend
- [x] 1.1 `domain/handoff.py` (`Handoff`, `render_handoff`, the standing rules); `infrastructure/platform/host.machine_label()`
- [x] 1.2 `application/skill/cli_handoff.py`: the prompt per status; `CliRequirementService` carries it on every view and loses the installer, the install jobs and the audit
- [x] 1.3 Remove `HomebrewInstaller`, `InstallJob`, both install routes and schemas, the install audit events and error codes, and the `brew:` field of `requires:`
- [x] 1.4 `CliOut.handoff` (`HandoffOut`, shared); `make contracts`
- [x] 1.5 `coffer cli prompt <command> [--json]` in place of `coffer cli install`; `coffer cli show` names it; parity table; `scripts/check_removed_commands.py` lists `coffer cli install`

## 2. Frontend
- [x] 2.1 `components/handoff/AgentHandoff.tsx` (Copy prompt, Ask an agent) and the draft pre-fill through location state (`lib/conversations/handoff.ts`, `useChatController`); `.agents/frontend.md` says when to use it
- [x] 2.2 CLI detail banner, CLIs list row action and the Requires tab use it; the install dialog, output and hooks are removed with their strings

## 3. Tests
- [x] 3.1 Unit: the hand-off renderer, the machine label, the prompt per status
- [x] 3.2 Integration: the prompt on REST and the CLI, no install route or command; `acceptance(skill-manager, …)` for every scenario of this change
- [x] 3.3 Vitest for the component, the pre-fill and the pages; e2e for the CLI page

## 4. Docs
- [x] 4.1 `docs-site/guides/clis.md` and every page that described the Homebrew install; skill-requirements architecture note; skill-manager `data-model.md`; CLI and REST references regenerated
- [x] 4.2 The web-ui requirement "Show every CLI a skill requires on the CLIs page" in change `revise-web-ui-ia` offers the hand-off instead of Install

## 5. Verify and archive
- [x] 5.1 `make verify`, `make verify-visual`
- [x] 5.2 Archive the change
