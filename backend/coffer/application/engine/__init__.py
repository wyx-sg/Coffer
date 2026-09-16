"""Coffer's own LLM engine, above every kind.

The engine is what Coffer runs on its OWN behalf — knowledge's tidy, memory's
organise, vault-sync's conflict resolver, chat's voice transcription — so it
belongs to none of them and may import none of them.

Deliberately import-free: this package sits in the kind-agnostic source list of
the "Kind-agnostic core does not import kind-specific code" contract, and that
contract forbids INDIRECT imports too. A convenience re-export here would put
whatever a submodule ever imports on the package's own import chain, and every
consumer of the engine would inherit it.
"""
