"""The functional gate's offline run (decision record Part E; docs/LAUNCH.md section 0): ClassiFile used from start
to finish while any attempt to reach the network is refused and recorded.

Usage: python -m tools.offline_check [FOLDER]     (default: the six sample PDFs)

Copies the folder's supported files to a temporary folder (the originals are only read), then runs, in a separate
Python process whose every process (the reader's worker processes too) refuses network access through a
temporary sitecustomize module:
  the window, offscreen, with a fresh catalog: the files are imported as by a drop, read by the worker processes
  (with OCR); then filed by the user into two categories, matching learned, automatic filing tried on the last
  document, every copy checked against its hash; then the catalog reopened as after a restart.
Any attempt to reach another computer (an address that is not this computer's own) is refused, recorded and
fails the check. Nothing outside the temporary folder is written.
For the gate, run it once more with the laptop's networking switched off (airplane mode): then nothing outside
Python could reach the network either. Prints counts only, never document text.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "document-organizer-claude-handoff" / "claude-handoff" / "samples"
WAIT = 900          # seconds: only stops a hung run; OCR of the six samples takes about a minute

# Loaded by every Python process of the run (PYTHONPATH): network calls are refused and recorded; this computer's
# own addresses (used by nothing in ClassiFile, but harmless) are allowed.
GUARD = '''
import os, socket
_LOG = os.environ["CLASSIFILE_OFFLINE_LOG"]
_LOCAL = ("127.", "::1", "localhost")


def _host(args):
    a = args[0] if args else None
    return str(a[0] if isinstance(a, tuple) else a)


def _guard(name, real):
    def blocked(*args, **kw):
        host = _host(args[1:] if name.startswith("socket.") else args)
        if host.startswith(_LOCAL):          # this computer's own addresses only
            return real(*args, **kw)
        with open(_LOG, "a", encoding="utf-8") as f:
            f.write(name + "\\n")
        raise OSError("network access refused by the offline check")
    return blocked


for _n in ("connect", "connect_ex", "sendto"):
    setattr(socket.socket, _n, _guard("socket." + _n, getattr(socket.socket, _n)))
for _n in ("create_connection", "getaddrinfo", "gethostbyname"):
    setattr(socket, _n, _guard(_n, getattr(socket, _n)))
'''


def inner(folder):
    """The run itself, inside the guarded process (CLASSIFILE_DATA_DIR points to a fresh data folder)."""
    import socket
    from PySide6.QtWidgets import QApplication
    from classifile.app import make_app
    from classifile.app.main import MainWindow
    from classifile.catalog.db import Catalog, default_data_dir
    from classifile.organizer import Organizer
    from classifile.reader import sha256_file

    if socket.create_connection.__name__ != "blocked":
        print("FAIL: the network guard is not active")
        return 1
    refused = False
    try:
        socket.create_connection(("192.0.2.1", 9), timeout=1)     # a documentation address: never routed anyway
    except OSError as e:
        refused = "refused by the offline check" in str(e)
    if not refused:
        print("FAIL: the network guard let a connection through")
        return 1
    open(os.environ["CLASSIFILE_OFFLINE_LOG"], "w").close()         # the guard's own test is not an attempt
    paths = sorted(str(p) for p in Path(folder).iterdir() if p.is_file())
    app = QApplication.instance() or make_app(sys.argv[:1])
    data = default_data_dir()
    org = Organizer(Catalog(data / "catalog.sqlite3"))
    (data.parent / "out").mkdir(exist_ok=True)
    org.set_output_root(data.parent / "out")
    w = MainWindow(org, ask_output_root=False)
    w.ask_close = lambda n: ("close", False)
    w.show()
    w.import_paths(paths)
    end = time.monotonic() + WAIT
    while (w.inflight or w.read_results) and time.monotonic() < end:
        app.processEvents()
        time.sleep(0.05)
    docs = org.catalog.all_documents()
    read = [d for d in docs if d["status"] == "needs_decision"]
    print(f"Imported {len(paths)} files: {len(read)} read and waiting, {len(docs) - len(read)} other "
          f"({', '.join(sorted({d['status'] for d in docs} - {'needs_decision'})) or 'none'})")
    if len(read) < 3:
        print("FAIL: too few documents were read to file and match")
        return 1
    cats = [org.create_category("Offline check A"), org.create_category("Offline check B")]
    for i, d in enumerate(read[:-1]):
        org.file(d["id"], cats[i % 2])
    result = org.update_matching()
    auto = org.file_automatically(read[-1]["id"])
    if auto is None:
        org.file(read[-1]["id"], cats[0])
    print(f"Filed {len(read) - 1} by the user in 2 categories; matching: {result['outcome']} (version "
          f"{result['version']}); the last document {'filed by itself' if auto else 'waited and was filed by the user'}")
    w.close()
    app.processEvents()
    org.catalog.close()

    cat = Catalog(data / "catalog.sqlite3")                     # as after a restart
    try:
        org = Organizer(cat)
        org.startup()
        copies = cat.all("SELECT path, snapshot_sha256 FROM copies WHERE status = 'published'")
        good = sum(Path(c["path"]).is_file() and sha256_file(c["path"]) == c["snapshot_sha256"] for c in copies)
        filed = sum(d["status"] == "filed" for d in cat.all_documents())
    finally:
        cat.close()
    print(f"After a restart: {filed} documents filed; {good} of {len(copies)} copies match their hash")
    return 0 if filed == len(read) and good == len(copies) == filed else 1


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["--inner"]:
        return inner(argv[1])
    folder = Path(argv[0]) if argv else SAMPLES
    if not folder.is_dir():
        sys.exit(f"No folder at {folder}")
    if "final-eval" in folder.resolve().parts or "validation" in folder.resolve().parts:
        sys.exit("Refusing a held-out folder: use development files")
    from classifile.reader import READERS
    files = [p for p in sorted(folder.iterdir()) if p.is_file() and p.suffix.lower() in READERS]
    with tempfile.TemporaryDirectory(prefix="classifile-offline-") as tmp:
        tmp = Path(tmp)
        (tmp / "site").mkdir()
        (tmp / "site" / "sitecustomize.py").write_text(GUARD, encoding="utf-8")
        (tmp / "src").mkdir()
        for p in files:
            shutil.copy(p, tmp / "src" / p.name)
        log = tmp / "attempts.log"
        log.touch()
        env = os.environ | {"PYTHONPATH": os.pathsep.join([str(tmp / "site"), str(ROOT)]),
                            "CLASSIFILE_DATA_DIR": str(tmp / "data"), "CLASSIFILE_OFFLINE_LOG": str(log),
                            "QT_QPA_PLATFORM": "offscreen"}
        env.pop("CLASSIFILE_OCR", None)                         # the real reader, OCR included
        print(f"Offline check on {len(files)} files (copies), every Python process refusing network access")
        code = subprocess.run([sys.executable, "-m", "tools.offline_check", "--inner", str(tmp / "src")],
                              env=env, cwd=ROOT).returncode
        attempts = log.read_text(encoding="utf-8").split()
    print(f"Network attempts: {len(attempts)}" + (f" ({', '.join(sorted(set(attempts)))})" if attempts else ""))
    ok = code == 0 and not attempts
    print("PASS" if ok else "FAIL")
    print("For the functional gate, also run it with networking switched off (airplane mode).")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
