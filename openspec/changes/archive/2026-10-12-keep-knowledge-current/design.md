## Context

The decisions and their alternatives are argued in ADR
`knowledge-stays-current-through-flags-coffer-computes`; this file records
only the shape of the implementation.

## Decisions

**Derived on every read, stored nowhere.** Both findings come out of the one
`WikiGraph` that `wiki.build` makes from the files on every read, as the other
findings do. `build` also reads the README's `verify_after_days` and takes an
optional `today`, so a test can fix the date.

**A replacement chain, not one hop.** `WikiGraph.successors` walks
`superseded_by` from a source to the end of its chain, stopping where it
repeats, so a loop cannot hang a read. A page is flagged only when it cites
none of the later sources; the finding's `others` names the last one, which
is the source a tidy should recheck the page against. A `superseded_by` that
resolves to two sources counts as no replacement.

**Lenient interval.** `verify_days` accepts an integer or a numeric string;
anything else, a boolean or a negative number falls back to 90 rather than
failing the read, because a typo in a README should not hide every finding.
`parse_day` reads a full timestamp by its date.

**The description stops at the rules.** `readme_description` and
`write_description` treat the first `##` heading as the end of the
description, so the default README's rules are never read as a description,
and an edit inserts the description above them when there is none.
`write_description` on a collection without a README writes the full default.

**One read module for files.** `describe` moved from `wiki.py` to
`wiki_reads.py` so `wiki.py` stays under the file-size limit; it adds a
page's `stale` and a source's resolved `superseded_by` and `summary`.

**Catalogue.** At full detail the sources part lists every source with its
mark and summary; at the no-descriptions level it keeps the old "waiting"
list, with the superseded mark where it applies, so the budget is unchanged.

## Risks / Trade-offs

- The first read after the upgrade flags every page without `verified`. The
  first tidy clears them; until then To do is long.
- A summary or a `superseded_by` is only as good as the agent that wrote it.
  The history and the next tidy are the check.
