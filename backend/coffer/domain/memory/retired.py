"""What retirement is, and why it has to be written down (spec memory "Record
retirements so they stick").

A note this layer removes cannot simply be deleted. The material it was built
from still sits in the agent's own memory, so the next aggregation reads it
again and the next distil pass re-opens the note the last one removed. In a
store whose sources live outside it, **an unrecorded deletion is undone**.

So a retirement is a record: what was retired, why, and what replaced it. It
serves three readers at once, which is why one file does the job of three
mechanisms:

* the **next distil pass**, which takes it as an exclusion list and therefore
  does not reinstate the subject from the same unchanged raw entry;
* the **developer**, who opens the partition as a folder and wants to know
  what Coffer decided was no longer true, and on what grounds;
* **delivery and recall**, which must not surface a retired note —
  the previous design marked a fact superseded and then handed it back from
  ``recall`` anyway, so 11 dead facts on the maintainer's live vault were
  still answerable as if current.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetiredNote:
    """One record of something this layer decided not to carry forward.

    Two things are recorded here, because the exclusion list has to account
    for both or the pass that reads it re-imports what the last one removed:

    * **A note that was retired.** ``slug`` names the file it had under
      ``notes/``, ``replaced_by`` names what took its place, and
      ``entry_ids`` carries the raw entries that note was built from — so
      those entries are accounted for the moment the note leaves, rather than
      surfacing as undistilled again on the next pass and having to be
      re-judged.
    * **Entries a pass kept nothing from** (the fourth action of "Distil
      incrementally in two stages"). There is
      no note and no file, so ``slug`` is empty and ``entry_ids`` is the whole
      of what the record excludes. ``.raw/`` may not be pruned to express this
      ("Keep distil out of the raw directory"), so without the record the same
      entry is routed to the model on
      every pass for the rest of the vault's life.

    ``entry_ids`` is what :mod:`coffer.application.memory.distil` matches on
    in both cases; ``slug`` is for the human and for naming a file that
    actually existed.
    """

    #: The retired note's slug — the file name it had under ``notes/``. Empty
    #: when this record accounts for dropped entries rather than for a note.
    slug: str
    #: Its title, so the record reads as prose rather than as identifiers.
    title: str
    #: Why it is no longer true, in Coffer's own words.
    reason: str
    #: The slug of the note that replaced it, when one did. Empty when the
    #: subject was dropped rather than superseded.
    replaced_by: str = ""
    #: When the retirement was recorded.
    retired_at: str = ""
    #: The raw entries this record accounts for, so no later pass offers them
    #: again.
    entry_ids: tuple[str, ...] = ()


__all__ = ["RetiredNote"]
