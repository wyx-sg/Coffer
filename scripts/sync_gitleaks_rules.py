#!/usr/bin/env python3
"""Import gitleaks' default rules as Coffer's bundled plaintext-secret rules.

Spec secret "Detect plaintext secrets with the bundled rules". Run by hand
before a release (``make refresh-secret-rules``); the files it writes ship in
every build and are reviewed as a diff.

What it does:

1. resolves the commit of the pinned gitleaks release (``--version`` to read
   another one);
2. downloads ``config/gitleaks.toml`` and ``LICENSE`` at that commit;
3. translates every Go RE2 pattern into Python ``re`` syntax (``translate``);
4. writes ``backend/coffer/infrastructure/secret/rules/gitleaks.toml`` with a
   header naming the source, release, commit and licence, and the licence
   beside it (MIT: the notice travels with the rules).

A pattern that cannot be translated is never dropped silently: it is listed
in the file's ``[source].untranslated`` and the script exits 1 without
writing, so the shipped rules stay at the release they were.

Usage::

    python scripts/sync_gitleaks_rules.py            # write the files
    python scripts/sync_gitleaks_rules.py --check    # exit 1 if they would change
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
import urllib.request
import warnings
from pathlib import Path
from typing import Any

REPO = "gitleaks/gitleaks"
#: The gitleaks release the bundled rules come from. Moving to a newer one is
#: this line plus the regenerated file.
VERSION = "v8.30.1"
ROOT = Path(__file__).resolve().parents[1]
RULES_DIR = ROOT / "backend" / "coffer" / "infrastructure" / "secret" / "rules"
RULES_FILE = RULES_DIR / "gitleaks.toml"
LICENSE_FILE = RULES_DIR / "gitleaks.LICENSE"

#: POSIX classes RE2 accepts inside a bracket expression.
POSIX = {
    "alnum": "a-zA-Z0-9",
    "alpha": "a-zA-Z",
    "ascii": r"\x00-\x7f",
    "blank": r" \t",
    "cntrl": r"\x00-\x1f\x7f",
    "digit": "0-9",
    "graph": r"!-~",
    "lower": "a-z",
    "print": r" -~",
    "punct": r"!-/:-@\[-`{-~",
    "space": r" \t\n\r\f\v",
    "upper": "A-Z",
    "word": r"\w",
    "xdigit": "0-9A-Fa-f",
}
_POSIX_RE = re.compile(r"\[:(\^?)([a-z]+):\]")
_FLAGS_RE = re.compile(r"\(\?([a-zA-Z]*(?:-[a-zA-Z]+)?)\)")
_NAMED_RE = re.compile(r"\(\?P?<(\w+)>")


class UntranslatableError(ValueError):
    """An RE2 construct Python ``re`` has no equivalent for."""


def _bracket(p: str, i: int) -> tuple[str, int]:
    """The bracket expression starting at ``p[i] == "["``, translated, and
    the index after it."""
    j, out = i + 1, ["["]
    if j < len(p) and p[j] == "^":
        out.append("^")
        j += 1
    if j < len(p) and p[j] == "]":
        out.append(r"\]")
        j += 1
    while j < len(p) and p[j] != "]":
        c = p[j]
        if c == "\\":
            if p[j + 1 : j + 2] in ("p", "P", "Q", "C"):
                raise UntranslatableError(f"\\{p[j + 1]}")
            out.append(p[j : j + 2])
            j += 2
            continue
        m = _POSIX_RE.match(p, j)
        if m:
            if m.group(1) or m.group(2) not in POSIX:
                raise UntranslatableError(m.group(0))
            out.append(POSIX[m.group(2)])
            j = m.end()
            continue
        # Python warns about (and will one day parse) nested sets and set
        # operations; RE2 reads these characters literally.
        if c == "[" or (c in "&~|-" and p[j + 1 : j + 2] == c):
            out.append("\\" + c)
            j += 1
            continue
        out.append(c)
        j += 1
    if j >= len(p):
        raise UntranslatableError("unterminated bracket expression")
    out.append("]")
    return "".join(out), j + 1


def translate(pattern: str) -> str:
    """``pattern`` (Go RE2) in Python ``re`` syntax, compiled with ``re.ASCII``.

    * A flag group past the start (``a(?i)b``) applies in RE2 to the rest of
      its enclosing group, across ``|``; Python only accepts it first. It
      becomes a scoped group, reopened after each ``|``:
      ``(?:a(?i)b|c)`` -> ``(?:a(?i:b)|(?i:c))``.
    * ``\\z`` and ``$`` (RE2 without ``m``: end of text) become ``\\Z``;
      Python's ``$`` would also match before a final newline.
    * ``[[:alnum:]]`` and the other POSIX classes become ranges.
    * ``\\p{…}``, ``\\Q…\\E``, ``\\C`` and the ``m`` flag are untranslatable.
    """
    out: list[str] = []
    #: Per open group, the flag groups opened in it that must close with it.
    stack: list[list[str]] = [[]]
    i, n = 0, len(pattern)
    while i < n:
        c = pattern[i]
        if c == "\\":
            nxt = pattern[i + 1 : i + 2]
            if nxt in ("p", "P", "Q", "C") or not nxt:
                raise UntranslatableError(f"\\{nxt}")
            out.append(r"\Z" if nxt == "z" else pattern[i : i + 2])
            i += 2
        elif c == "[":
            text, i = _bracket(pattern, i)
            out.append(text)
        elif c == "(":
            m = _FLAGS_RE.match(pattern, i)
            if m:
                if "m" in m.group(1):
                    raise UntranslatableError("(?m)")
                if not out:
                    out.append(m.group(0))
                else:
                    out.append(f"(?{m.group(1)}:")
                    stack[-1].append(m.group(1))
                i = m.end()
                continue
            if re.match(r"\(\?[a-zA-Z]*m[a-zA-Z]*(?:-[a-zA-Z]+)?:", pattern[i:]):
                raise UntranslatableError("(?m:)")
            m = _NAMED_RE.match(pattern, i)
            if m:
                out.append(f"(?P<{m.group(1)}>")
                i = m.end()
            else:
                out.append("(")
                i += 1
            stack.append([])
        elif c == "|":
            opened = stack[-1]
            out.append(")" * len(opened) + "|" + "".join(f"(?{f}:" for f in opened))
            i += 1
        elif c == ")":
            if len(stack) == 1:
                raise UntranslatableError("unbalanced )")
            out.append(")" * len(stack.pop()) + ")")
            i += 1
        elif c == "$":
            out.append(r"\Z")
            i += 1
        else:
            out.append(c)
            i += 1
    if len(stack) != 1:
        raise UntranslatableError("unbalanced (")
    out.append(")" * len(stack[0]))
    translated = "".join(out)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            re.compile(translated, re.ASCII)
    except (re.error, FutureWarning) as e:
        raise UntranslatableError(f"Python rejects the translation: {e}") from e
    return translated


def _pattern_keys(table: dict[str, Any]) -> None:
    """Translate the pattern fields of a rule or an allowlist in place."""
    for key in ("regex", "path"):
        if key in table:
            table[key] = translate(table[key])
    for key in ("regexes", "paths"):
        if key in table:
            table[key] = [translate(p) for p in table[key]]


def convert(config: dict[str, Any]) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    """The rule set with every pattern translated, and the rules (``id``,
    reason) left out because a pattern of theirs could not be."""
    allowlist = dict(config.get("allowlist") or {})
    _pattern_keys(allowlist)
    rules: list[dict[str, Any]] = []
    untranslated: list[tuple[str, str]] = []
    for raw in config.get("rules", []):
        rule = json.loads(json.dumps(raw))
        try:
            _pattern_keys(rule)
            for al in rule.get("allowlists", []):
                _pattern_keys(al)
        except UntranslatableError as e:
            untranslated.append((str(raw.get("id")), str(e)))
            continue
        rules.append(rule)
    return {"allowlist": allowlist, "rules": rules}, untranslated


def _toml_str(value: str) -> str:
    if "'''" not in value and "\n" not in value and not value.endswith("'"):
        return f"'''{value}'''"
    return json.dumps(value)


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return _toml_str(value)
    if isinstance(value, list):
        if len(value) <= 3 and all(isinstance(v, str) and len(v) < 40 for v in value):
            return "[" + ", ".join(_toml_value(v) for v in value) + "]"
        return "[\n" + "".join(f"    {_toml_value(v)},\n" for v in value) + "]"
    raise TypeError(type(value))


def _table(name: str, table: dict[str, Any]) -> str:
    lines = [name]
    lines += [f"{k} = {_toml_value(v)}" for k, v in table.items() if not isinstance(v, list)]
    lines += [f"{k} = {_toml_value(v)}" for k, v in table.items() if isinstance(v, list)]
    return "\n".join(lines) + "\n"


def render(
    converted: dict[str, Any], version: str, commit: str, untranslated: list[tuple[str, str]]
) -> str:
    """The rule file Coffer ships, deterministic for one release."""
    head = [
        "# Coffer's bundled plaintext-secret rules (spec secret \"Detect plaintext",
        '# secrets with the bundled rules"). Generated by scripts/sync_gitleaks_rules.py',
        "# from gitleaks' default config; do not edit by hand.",
        "#",
        f"# Source:  https://github.com/{REPO} {version} ({commit})",
        "# Licence: MIT, Copyright (c) 2019 Zachary Rice — see gitleaks.LICENSE beside",
        "#          this file. Patterns are translated from Go RE2 to Python re.",
        "",
    ]
    source = {
        "repository": f"https://github.com/{REPO}",
        "version": version,
        "commit": commit,
        "license": "MIT",
        "rules": len(converted["rules"]),
        "untranslated": [f"{rid}: {why}" for rid, why in untranslated],
    }
    parts = [
        "\n".join(head),
        _table("[source]", source),
        _table("[allowlist]", converted["allowlist"]),
    ]
    for rule in converted["rules"]:
        allowlists = rule.pop("allowlists", [])
        parts.append(_table("[[rules]]", rule))
        parts += [_table("[[rules.allowlists]]", al) for al in allowlists]
    return "\n".join(parts)


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "coffer-release"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return bytes(response.read())


def _commit(version: str) -> str:
    data = json.loads(_get(f"https://api.github.com/repos/{REPO}/commits/{version}"))
    return str(data["sha"])


def build(version: str) -> tuple[str, str, list[tuple[str, str]]]:
    commit = _commit(version)
    raw = _get(f"https://raw.githubusercontent.com/{REPO}/{commit}/config/gitleaks.toml")
    licence = _get(f"https://raw.githubusercontent.com/{REPO}/{commit}/LICENSE").decode("utf-8")
    converted, untranslated = convert(tomllib.loads(raw.decode("utf-8")))
    return render(converted, version, commit, untranslated), licence, untranslated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--version", default=VERSION, help=f"gitleaks release (default {VERSION})")
    parser.add_argument("--check", action="store_true", help="report drift, write nothing")
    args = parser.parse_args(argv)
    rules, licence, untranslated = build(args.version)
    for rid, why in untranslated:
        print(f"untranslatable: {rid}: {why}", file=sys.stderr)
    current = RULES_FILE.read_text("utf-8") if RULES_FILE.exists() else ""
    if args.check:
        if current == rules:
            print(f"bundled secret rules are at gitleaks {args.version} (current)")
            return 0
        print(f"bundled secret rules differ from gitleaks {args.version}")
        return 1
    if untranslated:
        print("nothing written: translate or drop the rules above first", file=sys.stderr)
        return 1
    RULES_DIR.mkdir(parents=True, exist_ok=True)
    RULES_FILE.write_text(rules, "utf-8")
    LICENSE_FILE.write_text(licence, "utf-8")
    print(f"wrote {RULES_FILE.relative_to(ROOT)} from gitleaks {args.version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
