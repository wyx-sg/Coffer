"""The one template Coffer ships with (spec workflow FR-009).

A vault that has never been touched still has somewhere to start. This is that
somewhere: five tasks that carry one change from a question to a written
result. It is a document like any other template the developer writes, and
from the moment it is seeded it is theirs — editable, renameable, disableable,
deletable (FR-001).

**It names no skill and no agent**, and that is a hard constraint rather than a
stylistic one. A skill and an agent are both registered resources, and
``parse_template`` refuses a task naming one this vault does not have (FR-006,
FR-007). A built-in that assumed either would validate on the machine it was
written on and be refused on everyone else's, which would make the seed fail
exactly where it matters most — a fresh install.

For the same reason no task names a tool. The instructions say what the task
owes and why it owes it; *how* to produce it is the agent's problem, and a
brief that answered it would be wrong for every agent but one.

It lives in the domain because it is a value — a config the domain's own
parser is the authority on — and because a unit test can then hold it against
``parse_template(..., known_skills=(), allowed_agents=())`` and prove the
paragraph above, with no application layer in the way.
"""

from __future__ import annotations

import uuid
from typing import Any

#: The label the seeded row starts with. Not an identity: the developer may
#: rename it the moment it exists, and nothing looks it up by this afterwards.
BUILTIN_TEMPLATE_NAME = "ship-a-change"

BUILTIN_TEMPLATE_DESCRIPTION = (
    "Coffer's starter workflow: understand, plan, implement, verify, report. "
    "Edit it, rename it or delete it — it is yours."
)

#: The built-in's identity, the same on every machine that holds it.
#:
#: Fixed rather than minted, because this row is not "a template this machine
#: made" but "the built-in", and a uid drawn per machine would make two of them
#: in a vault that spans two — each seeding its own, then converging both. It
#: is also what makes the seed's "is it already here?" question survive a
#: rename, which a lookup by name cannot.
#:
#: Derived rather than pasted so the constant carries its own provenance, and
#: so a 32-character hex literal does not sit in the tree looking like a key.
BUILTIN_TEMPLATE_UID = uuid.uuid5(uuid.NAMESPACE_URL, "coffer://workflow/builtin-template").hex


def builtin_template_config() -> dict[str, Any]:
    """A fresh copy of the built-in template's config.

    A function rather than a module constant: the caller hands this straight to
    the resource framework, which is free to keep it, and a shared mutable dict
    would let one write reach every later read of the built-in.
    """
    return {
        "description": (
            "Five tasks that carry one change from a question to a written result. "
            "Each one owes a document, because the task after it opens with what the "
            "run has produced and none of the conversation that produced it."
        ),
        "stages": [
            {
                "key": "understand",
                "name": "Understand",
                "nodes": [
                    {
                        "key": "understand",
                        "name": "Understand what is being asked",
                        "type": "ai",
                        "instructions": (
                            "Read enough of what already exists to state the problem in "
                            "your own words, including the part of it nobody wrote down.\n\n"
                            "You owe understanding.md: what is being asked, how things "
                            "behave today, and the questions you could not answer from "
                            "what you read. Write the open questions down even when they "
                            "are uncomfortable — a plan built on a guess nobody flagged "
                            "is the expensive kind of wrong.\n\n"
                            "The tasks after this one see your artifacts and none of "
                            "your conversation, so anything you worked out and did not "
                            "write down leaves the run when this task closes."
                        ),
                        "artifacts": [{"name": "understanding.md", "required": True}],
                    }
                ],
            },
            {
                "key": "plan",
                "name": "Plan",
                "nodes": [
                    {
                        "key": "plan",
                        "name": "Decide how the work will be done",
                        "type": "ai",
                        "instructions": (
                            "Decide how the change will be made before any of it is "
                            "made, and say what you are deliberately not doing.\n\n"
                            "You owe plan.md: the steps in the order they will happen, "
                            "what each one changes, and how anyone would know it "
                            "worked. A step whose success cannot be checked is a step "
                            "the verify task can only agree with."
                        ),
                        "artifacts": [{"name": "plan.md", "required": True}],
                    }
                ],
            },
            {
                "key": "implement",
                "name": "Implement",
                "nodes": [
                    {
                        "key": "implement",
                        "name": "Make the change",
                        "type": "ai",
                        "instructions": (
                            "Carry out the plan. Where the work shows the plan was "
                            "wrong, depart from it and say so — following a plan you "
                            "no longer believe, without saying that you stopped "
                            "believing it, is worse than either alternative.\n\n"
                            "This task declares no document of its own, because what "
                            "it produces is the change itself. What it owes is an "
                            "account of that change: what you altered, where you left "
                            "the plan and why, and what you knowingly left undone. "
                            "Whoever verifies next has your account and the code, and "
                            "nothing else."
                        ),
                        # Deliberately no `artifacts`: the deliverable is the change,
                        # not a document about it. FR-072 gives a task that declares
                        # none a required `report.md` when the template is read, so the
                        # account the brief asks for is still owed and still checked —
                        # the seed leans on that default rather than restating it.
                    }
                ],
            },
            {
                "key": "verify",
                "name": "Verify",
                "nodes": [
                    {
                        "key": "verify",
                        "name": "Check the work against what was asked",
                        "type": "ai",
                        "instructions": (
                            "Check the change against what was asked, not against what "
                            "was built — the second only proves the work is consistent "
                            "with itself.\n\n"
                            "You owe verification.md: what you exercised, what actually "
                            "happened, and every discrepancy you found, including the "
                            "ones you decided were not worth acting on and why. "
                            "'Looks right' is not a result; name what you ran and what "
                            "it said."
                        ),
                        "artifacts": [{"name": "verification.md", "required": True}],
                    }
                ],
            },
            {
                "key": "report",
                "name": "Report",
                "nodes": [
                    {
                        "key": "report",
                        "name": "Write the run up for whoever comes next",
                        "type": "ai",
                        "instructions": (
                            "Close the run for someone who was not here and will not "
                            "read the earlier artifacts.\n\n"
                            "You owe report.md: what was asked, what was done, what was "
                            "verified, and what is still open. Keep it short enough to "
                            "be read in full, and end on the open items — they are the "
                            "reason anyone opens this file a week from now."
                        ),
                        "artifacts": [{"name": "report.md", "required": True}],
                    }
                ],
            },
        ],
    }


__all__ = [
    "BUILTIN_TEMPLATE_DESCRIPTION",
    "BUILTIN_TEMPLATE_NAME",
    "BUILTIN_TEMPLATE_UID",
    "builtin_template_config",
]
