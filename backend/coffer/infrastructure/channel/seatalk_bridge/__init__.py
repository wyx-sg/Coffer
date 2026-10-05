"""``coffer-seatalk-bridge``: SeaTalk's WebSocket SDK, outside the daemon.

SeaTalk's SDK (``seatalk_oapi_sdk``) is operator-supplied: Coffer cannot ship
it, so it is imported from a directory the person — and therefore any agent
running as the same OS user — can write to. In a signed build the daemon holds
the ``keychain-access-groups`` entitlement and can read the master key, so code
imported into it could decrypt every secret. The SDK therefore runs here, in a
separate executable signed WITHOUT that entitlement, and only events cross back
(spec channels/seatalk "Load the websocket client library from an
operator-supplied directory").

Standard library only, and nothing from the rest of Coffer: this package is
everything the bridge executable runs.

* ``protocol`` — the wire: one JSON config line in on stdin, typed JSON lines out.
* ``session`` — import the SDK and hold one connection, wired as the daemon
  used to wire it in-process.
* ``main`` — the executable: stdout hygiene, and exit on stdin EOF or SIGTERM.
"""
