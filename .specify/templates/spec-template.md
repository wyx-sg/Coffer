# Feature Specification: [FEATURE NAME]

**Spec**: `[short-name]` (the folder name under `specs/`, named for the feature — never numbered)
**Status**: Draft
**Input**: User description: "$ARGUMENTS"

<!--
  A spec seeded from this template must keep three things intact or it will
  fail `make verify`:

  1. The top-level `## Acceptance Scenarios` section, with one
     `### Scenario: <title>` per scenario. `scripts/audit_acceptance.py`
     parses exactly that shape and FAILS a spec.md with zero scenarios.
     Do NOT nest scenarios under a user story — the gate does not see them
     there.
  2. A named folder, not a numbered one. `scripts/check_doc_numbering.py`
     rejects numbered spec directories and any `spec <NNN>` token in prose.
  3. No date or time annotation in the header or body (see
     `agents/sdd.md` "Markdown Style for spec.md"). Chronology lives in git
     and in `.specify/memory/roadmap.md`, not in the spec.

  A spec may nest: a parent spec owns the requirements its children share,
  and a child spec lives in a subfolder of the parent's
  (`specs/<parent>/<child>/spec.md`) and owns only what is specific to it.
  A child's spec id is its path — `channels/telegram`, not `telegram`.
-->

## User Scenarios *(mandatory)*

<!--
  User stories are PRIORITIZED user journeys, ordered by importance. Each one
  must be INDEPENDENTLY TESTABLE: if you implement just ONE of them, the
  result is still a viable slice that delivers value on its own — developable,
  testable, deployable and demonstrable without the others.

  Assign priorities (P1, P2, P3, …), P1 being the most critical.

  Scenarios themselves do NOT go here. Each story names the outcomes it needs
  and they are written up as `### Scenario:` entries in the
  `## Acceptance Scenarios` section below, which is the section the gate reads.
-->

### User Story 1 - [Brief Title] (Priority: P1)

[Describe this user journey in plain language]

**Why this priority**: [The value it delivers and why it ranks here]

**Independent Test**: [How this can be tested on its own — e.g. "fully tested by [action], delivering [value]"]

**Covered by**: [the `### Scenario:` titles below that prove this story works]

---

### User Story 2 - [Brief Title] (Priority: P2)

[Describe this user journey in plain language]

**Why this priority**: [The value it delivers and why it ranks here]

**Independent Test**: [How this can be tested on its own]

**Covered by**: [scenario titles from below]

---

[Add more user stories as needed, each with an assigned priority]

### Edge Cases

<!-- ACTION REQUIRED: replace these placeholders with the real edge cases. -->

- What happens when [boundary condition]?
- How does the system handle [error scenario]?

## Requirements *(mandatory)*

<!--
  ACTION REQUIRED: replace these placeholders with the real functional
  requirements.

  FR ids are numbered **per spec, from FR-001**, and are never reused: a
  requirement that is removed leaves its number retired rather than letting
  the next one inherit it. A child spec numbers its own requirements from
  FR-001 too — an id is only unique within the spec that carries it, so cite
  one as `<spec-id> FR-00N` when referring to it from elsewhere.

  Requirements shared by several sibling specs belong in the parent spec;
  a child carries only what is specific to it.
-->

### Functional Requirements

- **FR-001**: System MUST [specific capability, e.g. "allow users to create accounts"]
- **FR-002**: System MUST [specific capability, e.g. "validate email addresses"]
- **FR-003**: Users MUST be able to [key interaction, e.g. "reset their password"]
- **FR-004**: System MUST [data requirement, e.g. "persist user preferences"]
- **FR-005**: System MUST [behavior, e.g. "log all security events"]

*Example of marking an unclear requirement:*

- **FR-006**: System MUST authenticate users via [NEEDS CLARIFICATION: auth method not specified — email/password, SSO, OAuth?]

### Key Entities *(include if the feature involves data)*

- **[Entity 1]**: [What it represents, key attributes, no implementation detail]
- **[Entity 2]**: [What it represents, relationships to other entities]

## Acceptance Scenarios

<!--
  ACTION REQUIRED: replace these placeholders with the real scenarios.

  This section is the contract the test suite is audited against. One
  `### Scenario: <title>` per independently testable outcome. Each title must
  be matched by at least one test carrying the acceptance marker:

      @pytest.mark.acceptance(spec="<spec-id>", scenario="<title>")   # Python
      acceptance("<spec-id>", "<title>", …)                            # TS

  `scripts/audit_acceptance.py` (part of `make verify`) fails on a scenario
  with no covering test, on a marker naming a scenario or spec that does not
  exist, and on a marker whose test is unconditionally skipped. Titles are
  matched verbatim, so edit a title and its marker in the same change.

  Keep the Given/When/Then detail in the body under each heading — the
  heading itself is the identifier, so keep it short and stable.
-->

### Scenario: [short, stable title of the outcome]

**Given** [initial state], **When** [action], **Then** [expected outcome].

### Scenario: [short, stable title of the outcome]

**Given** [initial state], **When** [action], **Then** [expected outcome].

## Success Criteria *(mandatory)*

<!-- ACTION REQUIRED: measurable and technology-agnostic. -->

### Measurable Outcomes

- **SC-001**: [Measurable metric, e.g. "a user completes account creation in under 2 minutes"]
- **SC-002**: [Measurable metric]
- **SC-003**: [User-facing metric]

## Assumptions

<!--
  ACTION REQUIRED: the reasonable defaults chosen where the feature
  description left something unspecified.
-->

- [Assumption about the user, e.g. "the user is the single owner of this vault"]
- [Assumption about scope boundaries, e.g. "X is out of scope for the first cut"]
- [Assumption about data or environment]
- [Dependency on an existing module or service]

## Out of Scope

<!--
  What this spec deliberately does not do, so a reader does not infer it.
-->

- [Thing deliberately excluded, and why]
