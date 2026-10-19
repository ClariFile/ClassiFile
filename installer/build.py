"""Build the Windows installer: PyInstaller makes the app folder, Inno Setup wraps it in one setup file.

Usage: .venv\\Scripts\\python -m installer.build [--tessdata FOLDER] [--iscc PATH]

Needs: requirements-build.txt in the venv; Tesseract's English data (eng.traineddata; default: the Tesseract
install in Program Files); Inno Setup 6 (ISCC.exe; without it only the app folder and zip are built). Writes
dist\\ClassiFile-<version>\\ (the app folder), dist\\ClassiFile-<version>-portable.zip (the app folder with
installer\\portable\\, for testing without installing) and dist\\ClassiFile-<version>-setup.exe; it refuses when any
exists, so an earlier build is never overwritten. Network access is not needed.
"""
import argparse
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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tessdata", type=Path, default=TESSDATA)
    ap.add_argument("--iscc", type=Path)
    a = ap.parse_args(argv)
    app, setup = DIST / f"ClassiFile-{__version__}", DIST / f"ClassiFile-{__version__}-setup.exe"
    portable = DIST / f"ClassiFile-{__version__}-portable.zip"
    for p in (app, setup, portable):
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
        print(f"App folder: {app}")
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
