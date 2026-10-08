import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QSize  # noqa: E402
from PySide6.QtGui import QIcon, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from classifile.app import ICON_DIR, ICON_SIZES, app_icon, icon_files, set_app_user_model_id  # noqa: E402
from conftest import ROOT  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def test_icon_files_exist_and_load(app):
    for size, path in zip(ICON_SIZES, icon_files()):
        pix = QPixmap(str(path))
        assert not pix.isNull() and (pix.width(), pix.height()) == (size, size), path.name
    assert not QIcon(str(ICON_DIR / "classifile.ico")).isNull()  # kept for packaging
    readme_icon = ROOT / "assets" / "icons" / "clarifile" / "png" / "clarifile-128.png"
    assert not QPixmap(str(readme_icon)).isNull()


def test_application_icon_covers_every_size_and_windows_inherit_it(app):
    icon = app_icon()
    assert sorted(s.width() for s in icon.availableSizes()) == list(ICON_SIZES)
    app.setWindowIcon(icon)
    w = QWidget()
    assert w.windowIcon().cacheKey() == app.windowIcon().cacheKey()
    w.close()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows taskbar identity")
def test_app_user_model_id():
    import ctypes
    from ctypes import wintypes

    set_app_user_model_id()
    out = wintypes.LPWSTR()
    assert ctypes.windll.shell32.GetCurrentProcessExplicitAppUserModelID(ctypes.byref(out)) == 0
    try:
        assert out.value == "ClariFile.ClassiFile"
    finally:
        ctypes.windll.ole32.CoTaskMemFree(out)


def test_no_summarease_icons_in_this_repository():
    assert not [p for p in (ROOT / "assets").rglob("*") if "summarease" in p.name.casefold()]
