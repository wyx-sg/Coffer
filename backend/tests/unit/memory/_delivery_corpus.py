"""A note corpus and a fake memory port for the delivery tests (spec memory
"Retrieve the notes a prompt names").

The BM25 relevance floor is calibrated on a real store of one to two hundred
notes; over two or three notes every term's IDF is tiny and nothing clears it.
So every retrieval test ranks its target notes inside :func:`filler_notes` —
two dozen notes on unrelated subjects with vocabulary of their own — which is
the smallest corpus in which the floor means what it means in production.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from coffer.domain.memory.note import TYPE_FEEDBACK, TYPE_PROJECT, Note
from coffer.domain.memory.partition import GLOBAL_PARTITION

_WORDS = [
    "apple",
    "banana",
    "cherry",
    "dolphin",
    "eagle",
    "falcon",
    "garnet",
    "harbor",
    "iceberg",
    "jasmine",
    "kettle",
    "lantern",
    "meadow",
    "nectar",
    "orchid",
    "pebble",
    "quartz",
    "raven",
    "saffron",
    "tundra",
    "umber",
    "velvet",
    "walnut",
    "xenon",
    "yarrow",
    "zephyr",
    "anchor",
    "beacon",
    "canyon",
    "dune",
    "ember",
    "fjord",
    "glacier",
    "hollow",
    "island",
    "jungle",
    "kelp",
    "lagoon",
    "marsh",
    "nebula",
    "oasis",
    "prairie",
    "quarry",
    "reef",
    "savanna",
    "tide",
    "upland",
    "valley",
    "willow",
    "yonder",
    "zenith",
    "amber",
    "bronze",
    "copper",
    "denim",
    "ebony",
    "fuchsia",
    "gold",
    "hazel",
    "indigo",
    "jade",
    "khaki",
    "lilac",
    "maroon",
    "navy",
    "olive",
    "peach",
    "ruby",
    "sepia",
    "teal",
    "ultramarine",
    "vermilion",
    "wheat",
    "almond",
    "basil",
    "cumin",
    "dill",
    "fennel",
    "ginger",
    "hyssop",
    "juniper",
    "kale",
    "lemongrass",
    "mint",
    "nutmeg",
    "oregano",
    "paprika",
    "rosemary",
    "sage",
    "thyme",
]

FILLER_COUNT = 24


def filler_notes(partition: str, count: int = FILLER_COUNT, *, offset: int = 0) -> list[Note]:
    """``count`` notes whose words appear nowhere else in the corpus."""
    out: list[Note] = []
    for i in range(count):
        j = (i + offset) % (len(_WORDS) // 3)
        a, b, c = _WORDS[j * 3 : j * 3 + 3]
        out.append(
            Note(
                slug=f"filler-{partition}-{i}",
                title=f"{a.title()} {b} handling",
                description=f"{a} {b} {c} are kept together",
                type=TYPE_PROJECT,
                body=f"The {a} and the {b} go beside the {c}; {a} first.\n",
                partition=partition,
            )
        )
    return out


def note(
    slug: str,
    title: str,
    description: str,
    *,
    partition: str,
    body: str = "",
    type: str = TYPE_PROJECT,
    search_terms: Sequence[str] = (),
) -> Note:
    return Note(
        slug=slug,
        title=title,
        description=description,
        type=type,
        body=body or f"{description}\n",
        partition=partition,
        search_terms=tuple(search_terms),
    )


def node20_note(partition: str) -> Note:
    """The note the spec's retrieval and guard scenarios are about."""
    return note(
        "node-20-for-make-verify",
        "Run make verify under Node 20",
        "make verify fails with undici AbortSignal under Node 22 and 24; switch to Node 20",
        partition=partition,
        type=TYPE_FEEDBACK,
        body=(
            "Put Node 20 first on PATH before make verify; newer Node throws undici AbortSignal.\n"
        ),
        search_terms=("nvm", "vitest"),
    )


@dataclass(frozen=True)
class PartitionRow:
    """What ``resolve_cwd_partition`` reads off a partition."""

    name: str
    repository_path: str = ""
    repository_key: str = ""


@dataclass
class FakeMemory:
    """A ``MemoryPort``: partitions by name, the notes each holds, and the
    repository each is keyed on."""

    notes: dict[str, list[Note]] = field(default_factory=dict)
    repositories: dict[str, str] = field(default_factory=dict)
    list_calls: int = 0

    def add(self, *notes: Note) -> None:
        for n in notes:
            self.notes.setdefault(n.partition, []).append(n)

    def partition(self, name: str, repository: str = "") -> None:
        self.notes.setdefault(name, [])
        if repository:
            self.repositories[name] = repository

    async def served_partitions(self) -> Sequence[str]:
        return list(self.notes)

    async def list_notes(self, partition: str) -> Sequence[Note]:
        self.list_calls += 1
        return list(self.notes.get(partition, []))

    async def placements(self) -> Sequence[PartitionRow]:
        return [PartitionRow(n, self.repositories.get(n, "")) for n in self.notes]


def corpus(repository: str, *, project: str = "coffer") -> FakeMemory:
    """A repository partition and ``global``, each padded with filler notes."""
    memory = FakeMemory()
    memory.partition(project, repository)
    memory.partition(GLOBAL_PARTITION)
    memory.add(*filler_notes(project))
    memory.add(*filler_notes(GLOBAL_PARTITION, offset=FILLER_COUNT // 2))
    return memory


__all__ = [
    "FILLER_COUNT",
    "FakeMemory",
    "PartitionRow",
    "corpus",
    "filler_notes",
    "node20_note",
    "note",
]
