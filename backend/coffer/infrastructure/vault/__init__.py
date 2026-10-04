"""The vault's files and repository (spec vault-storage).

``home`` names the five class directories; ``git`` runs one git process over
the vault repository; ``repository`` reads it (history, trees, blobs, status);
``writer`` is the one way anything is written into it — lock, compare-and-swap,
validation, one commit per operation naming its writer; ``json_store`` is the
atomic JSON file ``local/`` state is kept in.
"""
