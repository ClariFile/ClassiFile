"""ClassiFile: an offline document categorizer, part of the ClariFile suite."""
import json
import sys
from pathlib import Path

__version__ = "1.0.0-rc.9"   # pilot release candidate; 1.0.0 after the pilot (docs/LAUNCH.md)


def build():
    """The commit an installed or portable copy was built from (build.json beside ClassiFile.exe, written by
    installer.build), shortened; "" when run from source or when it can't be read."""
    if not getattr(sys, "frozen", False):
        return ""
    try:
        return json.loads((Path(sys.executable).parent / "build.json").read_text(encoding="utf-8"))["commit"][:10]
    except (OSError, ValueError, KeyError, TypeError):
        return ""


def version_text():
    """ "1.0.0-rc.9 (build 0123abcdef)", or the version alone when run from source."""
    return f"{__version__} (build {build()})" if build() else __version__
