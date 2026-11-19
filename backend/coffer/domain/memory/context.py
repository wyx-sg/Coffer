"""What a session is handed at start: its project's memories (spec memory
"Hand a session its project's memories at start").

The text has three parts, all bounded together by :data:`CAP` bytes:

1. **Where memory lives and how to write it** — two sentences naming the
   project's folder and the coffer-guide skill's "Memory" section. They are
   always there, even for a project with no memories yet, because they are
   how an agent learns to write any.
2. **The memories**, topic by topic in full: what the person is like and how
   they want to work first, then the project's state; within a type, the most
   recently updated first.
3. **What did not fit**, one line per file with its path and title, so the
   agent can read it when it is relevant.

Pure: the caller reads the files and says where they are.
"""

from __future__ import annotations

from collections.abc import Sequence

from coffer.domain.memory.hub import TYPE_FEEDBACK, TYPE_PROJECT, TYPE_USER, Topic

#: The most a session is handed, in UTF-8 bytes.
CAP = 4096

_ORDER = {TYPE_USER: 0, TYPE_FEEDBACK: 1, TYPE_PROJECT: 2}


def _size(text: str) -> int:
    return len(text.encode("utf-8"))


def _sorted(topics: Sequence[Topic]) -> list[Topic]:
    by_date = sorted(topics, key=lambda t: (t.updated, t.name), reverse=True)
    return sorted(by_date, key=lambda t: _ORDER.get(t.type, len(_ORDER)))


def _block(topic: Topic) -> str:
    meta = ", ".join(p for p in (topic.type, topic.updated and f"updated {topic.updated}") if p)
    head = f"## {topic.title}" + (f" ({meta})" if meta else "")
    return f"{head}\n{topic.body}\n"


def render_context(*, project: str, folder: str, topics: Sequence[Topic], cap: int = CAP) -> str:
    """The text handed to a session started in ``project``.

    ``folder`` is the project's memory folder as the agent should write it
    (``~/.coffer/vault/memory/projects/<project>``).
    """
    open_tag = f'<coffer-memory project="{project}">\n'
    close_tag = "</coffer-memory>\n"
    intro = (
        f"Your memories of this project, kept by Coffer in {folder}/ for every agent "
        "the developer uses. When you learn something worth remembering about the "
        "developer or this project, write it there yourself, as the coffer-guide "
        'skill\'s "Memory" section says.\n'
    )
    parts = [open_tag, intro]
    used = _size(open_tag) + _size(intro) + _size(close_tag)
    left_out: list[Topic] = []
    for topic in _sorted(topics):
        block = "\n" + _block(topic)
        if not left_out and used + _size(block) <= cap:
            parts.append(block)
            used += _size(block)
        else:
            left_out.append(topic)
    if left_out:
        head = "\nNot shown here; read a file when it is relevant:\n"
        tail_parts = [head]
        tail_used = _size(head)
        for topic in left_out:
            line = f"- {folder}/{topic.name}: {topic.title}\n"
            if used + tail_used + _size(line) > cap:
                more = f"- … and {len(left_out) - (len(tail_parts) - 1)} more in {folder}/\n"
                tail_parts.append(more)
                break
            tail_parts.append(line)
            tail_used += _size(line)
        parts.extend(tail_parts)
    parts.append(close_tag)
    return "".join(parts)


__all__ = ["CAP", "render_context"]
