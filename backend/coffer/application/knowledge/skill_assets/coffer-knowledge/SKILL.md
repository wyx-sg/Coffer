---
name: coffer-knowledge
description: Use when you need a fact about THIS user's working environment that is not in the repository in front of you — what a service or repo is for and who owns it, how their projects fit together, who they work with, a decision they already made, or a trap they have already hit. Coffer holds these as markdown files the user and every agent share, so something learned in one session is here in the next. Read it before asking the user something they may already have written down, and write to it when you learn something durable. NOT for facts you can read out of the current repository, and NOT a place for secrets.
---

# Coffer's knowledge

A directory of markdown files, shared by the user and every agent they run.
There is no index and no search engine: you navigate it the way you navigate a
codebase — look at what is there, then read the file.

## Finding something

1. **`coffer__list`** with no arguments names every collection you may read,
   each with a one-line description and a file count. Collections are the
   user's own filing — `shopee`, `coffer`, whatever they made.
2. **`coffer__list` with a `path`** walks down one level: the folders and files
   directly inside it, each file with its `title` and `description`. Read those
   descriptions and pick. Do not try to list the whole tree at once; descend.
3. **`coffer__read`** with a file's path returns the whole file.
4. **`coffer__grep`** matches literal text or a regex across everything you may
   read, returning file and line. Use it when you know a string — an
   identifier, a path, a name — rather than a topic. It matches bytes, so CJK
   works and nothing is stemmed away.

Descriptions are the retrieval surface. If nothing in a catalogue looks right,
grep for a word the file would have to contain, then read what it hits.

## Writing something down

Use **`coffer__write`** when you learn something durable — a fact about a
service, a convention the user follows, a decision and its reason, a trap and
how to avoid it. Not for what is already in the repository, and not for
anything transient to this session.

- `title` is what a person reads in a file list; make it name the subject.
- `description` is one sentence, and it is what an agent reads to decide
  whether to open the file. A vague one makes the file unfindable.
- `directory` is the collection (or a folder inside it) to file it under; pass
  `path` instead to replace an existing file.

`coffer__delete` removes a file when it has become wrong.

## What this is not

It is not a secret store — no keys, tokens or credentials. It is not a scratch
pad: what goes in is meant to be true in a month. And it is not the
repository — if the answer is in the code in front of you, read the code.
