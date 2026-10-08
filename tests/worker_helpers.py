"""Worker targets for tests; importable in the spawned child (tests/ is on sys.path)."""
import os
import time

from classifile.organizer import read_and_analyze


def misbehave(path):
    """Hang, crash or raise depending on the file name; otherwise read normally."""
    name = os.path.basename(path)
    if "hang" in name:
        time.sleep(600)
    if "crash" in name:
        os._exit(3)
    if "raise" in name:
        raise ValueError("Secret body text")
    return read_and_analyze(path)
