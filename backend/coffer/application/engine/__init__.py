"""Coffer's own settings and speech-to-text resolution, above every kind.

Chat's voice transcription is the one thing Coffer runs a model for on its own
behalf, so the engine belongs to no kind and may import none of them.

Deliberately import-free: this package sits in the kind-agnostic source list of
the "Kind-agnostic core does not import kind-specific code" contract, and that
contract forbids INDIRECT imports too. A convenience re-export here would put
whatever a submodule ever imports on the package's own import chain, and every
consumer of the engine would inherit it.
"""
