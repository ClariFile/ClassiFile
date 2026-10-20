"""Previews without other programs: PDF pages are rendered with PyMuPDF; PPTX, DOCX and ODT files show the
thumbnail the saving application stored inside the file, when there is one. Page images only, never text views.
Files are only read, from memory. The window asks for them through serve(), in a worker process (classifile.worker),
so a damaged or slow file can neither freeze nor end the window. Nothing here imports Qt."""
from pathlib import Path

import pymupdf

from classifile.reader.common import open_zip, part

THUMBNAILS = ("docProps/thumbnail.jpeg", "docProps/thumbnail.jpg", "docProps/thumbnail.png", "Thumbnails/thumbnail.png")


class PdfPages:
    """A PDF opened from its bytes for page-by-page previews."""

    def __init__(self, path):
        self.doc = pymupdf.open(stream=Path(path).read_bytes(), filetype="pdf")
        if self.doc.needs_pass:
            self.close()
            raise ValueError("encrypted")

    @property
    def count(self):
        return self.doc.page_count

    def png(self, index, width=900, fmt="png"):
        """The page drawn width pixels wide. fmt "ppm": uncompressed, far quicker to make, for the window."""
        page = self.doc[index]
        zoom = width / max(page.rect.width, 1)
        return page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).tobytes(fmt)

    def close(self):
        self.doc.close()


def thumbnail_png(path):
    """The first-page thumbnail stored in a PPTX, DOCX or ODT file, as PNG bytes, or None."""
    try:
        zf = open_zip(Path(path).read_bytes(), "document")
        for name in THUMBNAILS:
            thumb = part(zf, name, required=False)
            if thumb:
                with pymupdf.open(stream=thumb) as img:  # JPEG/PNG; EMF/WMF thumbnails cannot be drawn
                    return img[0].get_pixmap().tobytes("png")
    except Exception:
        return None
    return None


def first_page_png(path, width=260):
    """PNG bytes of the first page or slide, or None when no preview can be made this way."""
    try:
        if Path(path).suffix.lower() == ".pdf":
            pages = PdfPages(path)
            try:
                return pages.png(0, width)
            finally:
                pages.close()
        return thumbnail_png(path)
    except Exception:
        return None


_open = {}      # in the preview process: the PDF last asked about, kept open for its next pages


def serve(request):
    """The preview process's answer to one request: ("ping",) -> True (started ahead of the first preview);
    ("thumbnail", path) -> PNG bytes, or b"" without a stored picture; ("count", path) -> pages;
    ("page", path, index, width) -> the page drawn width pixels wide, as PPM bytes. A file that cannot be read
    raises; the worker then answers with its failure value."""
    kind = request[0]
    if kind == "ping":
        return True
    path = Path(request[1])
    if kind == "thumbnail":
        return thumbnail_png(path) or b""
    key = (str(path), path.stat().st_mtime_ns)   # a file changed since is opened again
    if key not in _open:
        for pages in _open.values():
            pages.close()
        _open.clear()
        _open[key] = PdfPages(path)
    pages = _open[key]
    if kind == "count":
        return pages.count
    return pages.png(request[2], request[3], "ppm")
