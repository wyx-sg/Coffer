"""Provider-switching domain (spec 011).

A *provider profile* is a config resource (Kind ``provider``) describing one
upstream endpoint for one wire format. Switching = projecting the active profile
into the matching agent's native config. Pure domain code only — no I/O.
"""
