"""Workflow-layer domain errors (spec workflow).

Every one of these is raised by pure domain code and mapped by the HTTP surface
to the envelope codes named in ``openspec/specs/workflow/contracts/api.openapi.yaml``:
the four conflict codes are exactly the ones that document's ``Conflict``
response lists, so a code here and a code there are the same string, not two
strings that happen to agree today.
"""

from __future__ import annotations

from coffer.domain.error_base import CofferError


class WorkflowError(CofferError):
    """Root of the workflow layer's errors, so a caller can quarantine the
    whole layer with one ``except`` without catching every domain error."""

    code = "WORKFLOW_ERROR"


class TemplateInvalid(WorkflowError):  # noqa: N818
    """A template config failed validation (spec workflow "Refuse an invalid
    template naming the offending path").

    ``path`` is the JSON path of the offending field —
    ``stages[1].nodes[0].skill``, not "a node". The refusal is only useful if
    it says which field, because a template is hand-written JSON and the
    developer has to find the typo.
    """

    code = "WORKFLOW_TEMPLATE_INVALID"

    def __init__(self, path: str, message: str) -> None:
        super().__init__(f"{path}: {message}")
        self.path = path
        self.reason = message


class WorkflowVersionConflict(WorkflowError):  # noqa: N818
    """A mutating command carried a stale observed version (spec workflow
    "Refuse a command carrying a stale version").

    Carries the run's *current* position as well as its version, because the
    client's next move is to re-read and decide, and the refusal can hand it
    everything it needs to do that without a second round trip.
    """

    code = "WORKFLOW_VERSION_CONFLICT"

    def __init__(
        self,
        run_id: str,
        expected: int,
        current: int,
        *,
        status: str | None = None,
        stage_key: str | None = None,
        node_key: str | None = None,
    ) -> None:
        super().__init__(
            f"run {run_id} is at version {current}, command carried {expected}; "
            "re-read the run and retry"
        )
        self.run_id = run_id
        self.expected = expected
        self.current = current
        self.status = status
        self.stage_key = stage_key
        self.node_key = node_key


class IllegalTransition(WorkflowError):  # noqa: N818
    """A signal or action the current status does not allow.

    ``allowed`` is the set that *was* allowed, sorted, so the message tells the
    caller what to do instead of only what it may not do.
    """

    code = "WORKFLOW_ILLEGAL_TRANSITION"

    def __init__(self, subject: str, status: str, attempted: str, allowed: tuple[str, ...]) -> None:
        offer = ", ".join(allowed) if allowed else "nothing"
        super().__init__(
            f"{subject} in status {status!r} cannot take {attempted!r}; allowed: {offer}"
        )
        self.subject = subject
        self.status = status
        self.attempted = attempted
        self.allowed = allowed


class NotThisMachine(WorkflowError):  # noqa: N818
    """A mutating command reached the machine that does not own the run (spec
    workflow "Advance a run only on the machine that owns it").

    Says which machine does own it: the run is visible everywhere, so the
    developer looking at it here needs to know where to go to advance it.
    """

    code = "WORKFLOW_NOT_THIS_MACHINE"

    def __init__(self, run_id: str, owner_machine_id: str, this_machine_id: str) -> None:
        super().__init__(
            f"run {run_id} is advanced by machine {owner_machine_id!r}, not {this_machine_id!r}; "
            "it is read-only here"
        )
        self.run_id = run_id
        self.owner_machine_id = owner_machine_id
        self.this_machine_id = this_machine_id


class RunTerminal(WorkflowError):  # noqa: N818
    """A mutating command reached a completed or aborted run (spec workflow
    "Keep a run to six statuses", "Accept the run signals start, pause, resume
    and abort").

    Distinct from ``IllegalTransition`` because it is a different answer: not
    "not from here", but "never again".
    """

    code = "WORKFLOW_RUN_TERMINAL"

    def __init__(self, run_id: str, status: str, attempted: str) -> None:
        super().__init__(
            f"run {run_id} is {status}; it refuses every mutating command, including {attempted!r}"
        )
        self.run_id = run_id
        self.status = status
        self.attempted = attempted


class TemplateDisabled(WorkflowError):  # noqa: N818
    """A run was asked for from a workflow that is switched off (spec workflow
    "Refuse new runs from a disabled workflow at the daemon").

    Enabled is what decides whether a workflow may start new runs, so it is
    refused HERE rather than filtered in one client: a rule that lives only in
    the web UI's dropdown is not a rule, it is a courtesy that the CLI and
    every other caller does not extend.

    It says nothing about runs already going. They froze their own snapshot at
    creation ("Freeze the template when a run is created") and keep running —
    switching a workflow off retires it from the menu, it does not stop work
    that is already under way.
    """

    code = "WORKFLOW_TEMPLATE_DISABLED"

    def __init__(self, template: str) -> None:
        super().__init__(
            f"workflow {template!r} is disabled; it starts no new runs. "
            "Runs already created from it are unaffected."
        )
        self.template = template


class UnknownWorkflowAgent(WorkflowError):  # noqa: N818
    """A task was assigned an agent this machine does not have (spec workflow
    "Choose a task's agent, model and effort before it starts").

    Refused when the choice is MADE. Left to the moment the task starts, a
    typed agent key becomes a failed attempt with an agent error hours later,
    attributed to the work rather than to the typo.
    """

    code = "WORKFLOW_UNKNOWN_AGENT"

    def __init__(self, agent: str, known: tuple[str, ...]) -> None:
        super().__init__(f"no agent named {agent!r}; this machine has: {', '.join(known)}")
        self.agent = agent
        self.known = known


class RunLabelInvalid(WorkflowError):  # noqa: N818
    """A run was asked to be called nothing at all (spec workflow "Edit a run's
    title and description as labels").

    A title is what tells one delivery from another in a list, so a blank one
    is refused rather than stored — an empty row in that list is worse than
    the wrong words in it.
    """

    code = "WORKFLOW_RUN_LABEL_INVALID"


class AttemptCeilingReached(WorkflowError):  # noqa: N818
    """A node would open an attempt past the template's ceiling (spec workflow
    "Bound each task's attempts by its own ceiling").

    Raised where the loop would otherwise close — the application turns it into
    a ``run.failed`` event whose reason is ``attempt_ceiling``, which is the
    whole point: a testing-to-coding feedback loop stops instead of spending a
    budget overnight.
    """

    code = "WORKFLOW_ATTEMPT_CEILING"

    def __init__(self, node_key: str, ceiling: int) -> None:
        super().__init__(
            f"node {node_key!r} has used its {ceiling} attempt(s); "
            "the run fails rather than opening another"
        )
        self.node_key = node_key
        self.ceiling = ceiling
