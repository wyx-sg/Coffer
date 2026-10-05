"""``python -m coffer.infrastructure.channel.seatalk_bridge`` — and the frozen
``coffer-seatalk-bridge`` executable's entry script.

An absolute import, because PyInstaller runs this file as a plain script.
"""

from coffer.infrastructure.channel.seatalk_bridge.main import run

if __name__ == "__main__":
    run()
