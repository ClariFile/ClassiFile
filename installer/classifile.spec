# PyInstaller spec for ClassiFile: one folder with ClassiFile.exe, Python, PyMuPDF, PySide6, the icons and
# Tesseract's English language data. Run through installer/build.py, which passes the language data's path.
import os
from pathlib import Path

ROOT = Path(SPECPATH).parent
ENG = os.environ["CLASSIFILE_ENG_TRAINEDDATA"]

a = Analysis(
    [str(ROOT / "installer" / "launcher.py")],
    pathex=[str(ROOT)],
    datas=[(str(ROOT / "assets" / "icons" / "classifile"), "assets/icons/classifile"), (ENG, "tessdata")],
    excludes=["tkinter", "pytest", "tools", "tests"],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="ClassiFile", console=False,
          icon=str(ROOT / "assets" / "icons" / "classifile" / "classifile.ico"))
coll = COLLECT(exe, a.binaries, a.datas, name="ClassiFile")
