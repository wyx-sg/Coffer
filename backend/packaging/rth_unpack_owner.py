# PyInstaller runtime hook for Coffer's one-file binaries: write this process's
# pid into the directory the bootloader unpacked it into, before any Coffer
# code runs.
#
# The bootloader deletes that directory when the program exits, but not when
# the process is killed outright. The daemon deletes a marked directory whose
# pid no longer runs (coffer/infrastructure/daemon/unpack_keepalive.py, which
# names the same marker file); an unmarked one may belong to another
# PyInstaller program and is never touched.
import os
import sys

_meipass = getattr(sys, "_MEIPASS", None)
if _meipass:
    try:
        with open(os.path.join(_meipass, ".coffer-pid"), "w") as _marker:
            _marker.write(str(os.getpid()))
    except OSError:
        pass
