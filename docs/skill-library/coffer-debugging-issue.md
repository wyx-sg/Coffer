# Design: `coffer-debugging-issue`

A read-only, provider-independent skill that takes a problem report and
returns an evidenced root cause, a fix proposal when the cause is in code,
and two reports: a short one for the person who raised it and a detailed one
for internal review. It is an orchestrator domain in the sense of
[Writing skill libraries](../../docs-site/guides/writing-skill-libraries.md):
it owns the method, and every layer it inspects is handed to an existing
carrier domain named by the profile.

Status: design approved in conversation on 2026-09-28; this document is the
written spec awaiting review.

## Why

The log-search domain answers one question well — what do the logs say — but
real problems cross layers. A typical report (a test account that cannot log
in) needed the knowledge base for how the login service works, the logs for
the failure, and a local check that a password hash matched a known value.
Left to improvise that sequence, an agent:

- answered with a conclusion and no evidence, so the user had to ask a second
  time for the log lines;
- told the user a spreadsheet was unreachable without ever calling the skill
  that reads it, because an unrelated, unauthorised connector was listed.

Both failures come from the absence of a method, not of capability. This
domain supplies the method.

## Decisions

| Question | Decision |
|---|---|
| Where does an investigation end? | At an evidenced root cause, plus a fix proposal (file, line, diff draft) when the cause is in code. Code is never changed. Filing a ticket is a follow-up offered at the end, handled by the ticket-filing domain. |
| Mutations | None. Every layer is used through its read-only operations only. Anything that would write is listed for the user to decide; this domain never performs it. |
| Portability | Generic. The method names no platform; an environment file names the carriers. |
| Reports | Two versions: a brief one for the reporter, a detailed one for internal review. |
| Where the detailed report goes | Into the chat, and archived in a dedicated `incidents` knowledge collection. |
| How code is reached | Local checkouts under profile-named roots first; otherwise the profile's code-platform carrier, read remotely. No cloning. Code is read at the version that is actually deployed. |
| Autonomy | Fully automatic within a budget. It stops when every hypothesis is resolved, the evidence budget is spent, or it is genuinely blocked, and then reports — a partial report when not converged. |
| Shape | Ordered phases in `functions/`, with a hypothesis ⇄ evidence loop in the middle. Past incidents act as learned playbooks; no hand-written per-symptom playbooks. |

## Phases

All live in `functions/`, run in order. They are steps of one flow, not
things a user asks for alone.

| # | Phase | Does | Produces |
|---|---|---|---|
| 1 | Intake | Normalise the report (a forwarded chat, a ticket, a screenshot) into a symptom card: what is observed, who or what is affected, environment and region, time, clues (trace IDs, error codes, paths, account or order identifiers), and the reporter's language. Missing essentials are asked for **once, together**. | Symptom card |
| 2 | Recall | Search the `incidents` collection for similar cases, then the service knowledge, then any external knowledge carriers the profile names. | Similar cases, known facts |
| 3 | Scope | Locate the services involved and the call chain (entry → owning service → downstreams), the environment, and the deployed version. | Services, chain, version |
| 4 | Hypothesise ⇄ gather | The loop below. | Hypothesis table with evidence |
| 5 | Locate in code | Only when the root cause is in code: read the deployed version, pin `file:line@version`, draft the fix as a diff. | Location, diff draft |
| 6 | Report | Brief and detailed reports, via the shared base skill. | Two reports |
| 7 | Archive | File the detailed report in `incidents`. | Knowledge entry |

## The hypothesis loop

### The table

| Field | Meaning |
|---|---|
| `H#` | Identifier |
| Statement | One sentence, e.g. "the stored password is out of date" |
| Category | user side · data · configuration · release/change · downstream dependency · capacity/timeout · code defect |
| Likelihood, cost | high / medium / low each |
| Confirms if / refutes if | The observation that would confirm or refute it — **written before gathering** |
| Layer | Which profile layer can produce that observation |
| Status | open → confirmed · refuted · inferred · blocked |
| Evidence | `E#` references |

### Seeding

Similar incidents from Recall come first, with their root causes as leading
hypotheses. Then walk the seven categories against the symptom and write at
least one hypothesis for every category that could plausibly produce it, so
the investigation does not anchor on the first guess.

### Ordering

Prefer the evidence that **discriminates between several hypotheses at once**
(one login log search separates "account banned", "wrong password" and
"system fault"). Then order by likelihood × cheapness.

### One iteration

1. Pick the next evidence action and call the layer's carrier, read-only.
2. Record the result as `E#`: layer, the exact query run, a verbatim excerpt
   (trimmed, secrets masked), and its timestamp.
3. Update statuses against the pre-written confirm/refute conditions. Add a
   hypothesis when evidence surprises.
4. Increment the evidence counter.

### Status rules

- **Confirmed** needs direct evidence. A conclusion reached by reasoning is
  **inferred**, and the report keeps the two apart.
- **Blocked** is only allowed after the layer's carrier has actually been
  called; the entry quotes the carrier's own error. Never mark a layer
  unreachable without trying it.

### Convergence

All three must hold:

1. one root-cause hypothesis is confirmed;
2. every link from root cause to symptom is backed by an `E#`;
3. at least one competing hypothesis is explicitly refuted.

Otherwise the loop continues until the budget is spent or it is blocked, and
Phase 6 produces a partial report whose open items say what is needed to go
on.

## Profile

`profiles/default.md` sets every layer to `none`: reaching one, the domain
names it and asks which tool serves that layer, never guessing. An
environment file (one per environment, no inheritance) fills them in.

```yaml
layers:            # each value is a carrier domain, used read-only
  logs: none
  container: none
  api: none        # replaying read-only requests only
  db: none         # SELECT only
  config: none     # reading configuration only
  data: none       # warehouse read-only queries only
  jobs: none       # job execution history only
  deploy: none     # confirming the deployed version only
code:
  local_roots: []
  remote: none     # code-platform carrier for remote read and search
recall:
  collection: incidents
  external: []     # extra knowledge carriers
intake:
  ticket_source: none
budget:
  evidence_calls: 25
report:
  timezone: local
```

- An environment file may add layers (a message queue, say); Phase 4 can
  then use them without a body change.
- `references/read-only-rules.md` lists, per layer, which operations of the
  carrier are allowed. Before implementation each environment file's
  carrier is checked for a real read-only operation; a layer whose carrier
  has none is set to `none` rather than named on hope.
- `recall.collection` never varies by environment; it is declared for
  discoverability.

## Reports and the shared base skill

The evidence rules and both report templates are shared with the log-search
and change-testing domains, so they live in a small base skill,
`coffer-reporting-evidence`, loaded by name through the agent's skill
mechanism at report time. No domain
references another skill's files by path. Each domain that loads it declares
`metadata.requires: [coffer-reporting-evidence]`; if loading fails it says so
by name instead of improvising a format.

The base skill holds:

- **Evidence rules** — quote, never paraphrase; trim with `…`; mask secrets as
  `***`; every line carries its timestamp, severity and trace or request ID.
- **Try-first rule** — no "cannot access" without calling the named carrier
  and quoting its error.
- **Brief report** — in the reporter's language; no internal code paths or
  diffs. Conclusion (one or two sentences) · impact and what you need to do ·
  key evidence, 1–3 verbatim lines keeping trace IDs · status (located, or
  still open and what is missing). About fifteen lines.
- **Detailed report** — symptom card · scope (services, environment, region,
  time, deployed version) · conclusion · causal chain root → symptom with
  `E#` per link · the full hypothesis table including refuted ones · code
  location `file:line@version` and diff draft · next steps and owners ·
  how to reproduce (link or query parameters) · evidence budget used ·
  open items · evidence appendix (`E#`: layer, query, verbatim excerpt).

Delivery: in a terminal both are printed in order. In a phone chat the brief
report is the reply body and the detailed report is sent as a `.md`
attachment through the channel's file sentinel (`MEDIA:/path`), so the phone
gets a short reply and the evidence is still delivered.

## Archive

One document per investigation in `incidents`, named
`YYYY-MM-DD-<service>-<slug>.md`, with frontmatter: date, services,
environment, region, symptom keywords, root-cause category, status (located or
partial), related tickets. The body is the detailed report, re-checked for
secrets before filing. Recall greps these fields.

**To verify first.** `coffer knowledge write` and `upload` both feed
curation, which merges and rewrites material; neither keeps a document as
written. A file written directly into the collection is also noticed by
curation. The first implementation step creates `incidents`, writes one report
file into it, runs a curation pass, and compares. If the file survives
unchanged, the archive writes files directly. If not, Coffer needs a
per-collection "do not curate" switch, which is a Coffer product change
(an OpenSpec change of its own) and blocks Phase 7 until it lands.

## Changes to sibling skills in the same effort

From the review of `coffer-testing-change`, only what the new domain shares:

- `coffer-testing-change` and `coffer-investigating-logs` load
  `coffer-reporting-evidence` for their reports and declare the dependency;
  the report sections that duplicated it are removed.
- `coffer-testing-change` adopts the try-first rule in preflight.
- `coffer-testing-change`'s archive phase stops calling the removed
  `coffer knowledge ingest` and follows whatever the archive experiment above
  settles.

The rest of that review (a read-only database query path, the test-plan
schema and validator drift, stop conditions per case, irreversible teardown)
is a separate effort.

## Verification

- `scripts/` tests for the portability lint (including the standard Profile
  paragraph).
- A dry run against the login incident above, from its original forwarded
  report: it must reach the same root cause, cite verbatim evidence in the
  first reply, refute at least one competing hypothesis, and stay within
  budget.
- A blocked-layer run: a layer set to `none`, and a layer whose carrier
  errors — the report must name the layer and quote the error.
- A phone-channel run: brief report as the reply, detailed report delivered
  as an attachment.

## Out of scope

- Changing code, configuration, data or jobs.
- Filing tickets or replying to the reporter on the user's behalf.
- Hand-written per-symptom playbooks.
- Coffer product support for skill dependencies beyond the script check.
