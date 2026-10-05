## MODIFIED Requirements

### Requirement: Hand a partition's tidying to the agent
Reading one partition (`GET /api/v1/memory/partitions/{uid}`) MUST carry `tidy_handoff`: a prompt, produced by the domain's hand-off text, that names the partition, its absolute directory and the `coffer-guide` section to follow (see "Teach tidying in the coffer-guide's memory section"). The partition's page MUST offer a **Tidy** button. With a managed agent available, **Tidy** MUST start the hand-off agent in the person's preferred terminal with the `tidy_handoff` prompt sent at once ([web-ui](../web-ui/spec.md) "Hand a machine-dependent problem to an agent with one split button") and leave the page where it is; with none available, the page MUST offer **Copy prompt** only. The Memory page MUST also offer **Tidy all** in its header, backed by `GET /api/v1/memory/tidy-handoff`: a prompt that names the memory root and every partition with its absolute notes directory and note count, and asks the agent to tidy them one at a time by the same section; it behaves as **Tidy** does. Nothing MUST tidy a partition unattended: a partition is tidied only when a person chooses Tidy or asks an agent to.

#### Scenario: Tidy sends the prompt to the default managed agent
- **GIVEN** a partition's page and a managed agent
- **WHEN** the person chooses **Tidy**
- **THEN** the hand-off agent starts in the preferred terminal with the partition's `tidy_handoff` prompt already sent, and the page stays where it is
- **AND** the prompt names the partition, its absolute directory and the coffer-guide section to follow

#### Scenario: Tidy all hands every partition to the agent in one conversation
- **GIVEN** the Memory page with two partitions and a managed agent
- **WHEN** the person chooses **Tidy all**
- **THEN** one session of the hand-off agent starts in the preferred terminal with the `GET /api/v1/memory/tidy-handoff` prompt already sent
- **AND** the prompt names the memory root and both partitions with their notes directories and note counts

#### Scenario: with no managed agent the page offers Copy prompt only
- **GIVEN** a partition's page and no managed agent
- **WHEN** the person opens Tidy
- **THEN** the page offers **Copy prompt**, which copies the `tidy_handoff` prompt, and starts no terminal

#### Scenario: nothing tidies a partition unattended
- **GIVEN** a partition holding near-duplicate notes, with the aggregate and distil switches on
- **WHEN** the workers run through several intervals and no person chooses Tidy
- **THEN** every note is as the distil pass wrote it, and no terminal or agent session was started
