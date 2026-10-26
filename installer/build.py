"""Build the Windows installer: PyInstaller makes the app folder, Inno Setup wraps it in one setup file.

Usage: .venv\\Scripts\\python -m installer.build [--tessdata FOLDER] [--iscc PATH]

Needs: requirements-build.txt in the venv; Tesseract's English data (eng.traineddata; default: the Tesseract
install in Program Files); Inno Setup 6 (ISCC.exe; without it only the app folder and zip are built). Writes
dist\\ClassiFile-<version>\\ (the app folder), dist\\ClassiFile-<version>-portable.zip (the app folder with
installer\\portable\\, for testing without installing) and dist\\ClassiFile-<version>-setup.exe; it refuses when any
exists, so an earlier build is never overwritten. Network access is not needed.
A build is made only from a commit with no uncommitted change to tracked files, and says which: build.json beside
ClassiFile.exe (version, commit, extraction record and reader versions, Python and library versions; About,
Advanced and the problem report show the commit), and dist\\ClassiFile-<version>-hashes.txt (SHA-256 of the setup
file, the portable zip and build.json), so a tested copy can be matched to its source.
"""
import argparse
import hashlib
import json
import importlib.metadata
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from classifile import __version__

ROOT = Path(__file__).resolve().parent.parent
HERE = ROOT / "installer"
DIST = ROOT / "dist"
CRLF = chr(13) + chr(10)          # the launcher and notes as Windows text
TESSDATA = Path(r"C:\Program Files\Tesseract-OCR\tessdata")
ISCC = [Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
        Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"), Path(r"C:\Program Files\Inno Setup 6\ISCC.exe")]


def licenses(folder):
    """Every licence the installed app ships, under the names installer/NOTICE.txt gives them."""
    pymupdf = next(f for f in importlib.metadata.distribution("pymupdf").files if f.name == "COPYING")
    for src, name in ((HERE / "NOTICE.txt", "NOTICE.txt"), (ROOT / "LICENSE", "ClassiFile-AGPL-3.0.txt"),
                      (Path(sys.base_prefix) / "LICENSE.txt", "Python-PSF.txt"),
                      (pymupdf.locate(), "PyMuPDF-COPYING.txt"), *((p, p.name) for p in (HERE / "licenses").iterdir())):
        shutil.copyfile(src, folder / name)


def write_portable(app, out):
    """The app folder under ClassiFile/, with the launcher that keeps its catalog beside it (installer/portable/)."""
    top = out.stem
    with zipfile.ZipFile(out, "x", zipfile.ZIP_DEFLATED) as z:
        for f in sorted((HERE / "portable").iterdir()):
            z.writestr(f"{top}/{f.name}", CRLF.join(f.read_text(encoding="utf-8").splitlines()) + CRLF)
        for f in sorted(app.rglob("*")):
            if f.is_file():
                z.write(f, f"{top}/ClassiFile/{f.relative_to(app).as_posix()}")


def commit():
    """The commit being built; exits when tracked files have changes that are not committed."""
    git = lambda *a: subprocess.run(["git", *a], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()
    if git("status", "--porcelain", "--untracked-files=no"):
        sys.exit("Commit or stash the changes first: a build is made only from a recorded commit.")
    return git("rev-parse", "HEAD")


def build_info(head):
    from classifile.reader import RECORD_VERSION, odt, ooxml, pdf
    versions = {name: importlib.metadata.version(name) for name in ("pymupdf", "pyside6", "pyinstaller")}
    return {"version": __version__, "commit": head, "record_version": RECORD_VERSION,
            "readers": [pdf.READER_VERSION, ooxml.DOCX_READER_VERSION, ooxml.PPTX_READER_VERSION, odt.READER_VERSION],
            "python": sys.version.split()[0], "libraries": versions}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tessdata", type=Path, default=TESSDATA)
    ap.add_argument("--iscc", type=Path)
    a = ap.parse_args(argv)
    app, setup = DIST / f"ClassiFile-{__version__}", DIST / f"ClassiFile-{__version__}-setup.exe"
    portable = DIST / f"ClassiFile-{__version__}-portable.zip"
    hashes = DIST / f"ClassiFile-{__version__}-hashes.txt"
    head = commit()
    for p in (app, setup, portable, hashes):
        if p.exists():
            sys.exit(f"Refusing to overwrite {p}: remove it first.")
    eng = a.tessdata / "eng.traineddata"
    if not eng.is_file():
        sys.exit(f"No eng.traineddata in {a.tessdata}")
    with tempfile.TemporaryDirectory(prefix="classifile-build-") as tmp:
        tmp = Path(tmp)
        subprocess.run([sys.executable, "-m", "PyInstaller", str(HERE / "classifile.spec"), "--noconfirm",
                        "--distpath", str(tmp / "dist"), "--workpath", str(tmp / "work")],
                       check=True, cwd=ROOT, env=os.environ | {"CLASSIFILE_ENG_TRAINEDDATA": str(eng)})
        DIST.mkdir(exist_ok=True)
        shutil.move(tmp / "dist" / "ClassiFile", app)
        with open(app / "build.json", "x", encoding="utf-8") as f:
            json.dump(build_info(head), f, indent=1)
        print(f"App folder: {app} (commit {head[:10]})")
        write_portable(app, portable)
        print(f"Portable zip: {portable}")
        iscc = a.iscc or next((p for p in ISCC if p.is_file()), None)
        if iscc is None:
            sys.exit("Inno Setup 6 (ISCC.exe) not found: the app folder is built, the setup file is not.")
        (tmp / "licenses").mkdir()
        licenses(tmp / "licenses")
        subprocess.run([str(iscc), f"/DAppVersion={__version__}", f"/DSource={app}", f"/DLicenses={tmp / 'licenses'}",
                        f"/DOutputDir={DIST}", f"/DIcon={ROOT / 'assets' / 'icons' / 'classifile' / 'classifile.ico'}",
                        str(HERE / "classifile.iss")], check=True)
    print(f"Setup file: {setup}")
    with open(hashes, "x", encoding="utf-8") as f:
        f.write(f"ClassiFile {__version__}, commit {head}\n")
        f.writelines(f"{sha256(p)}  {p.name}\n" for p in (setup, portable, app / "build.json"))
    print(f"Hashes: {hashes}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
