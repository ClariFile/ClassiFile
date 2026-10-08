from pathlib import Path

from .common import RECORD_VERSION, DocumentRecord, ReadResult, UnitRecord, sha256_file
from .odt import read_odt
from .ooxml import read_docx, read_pptx
from .pdf import read_pdf

READERS = {".pdf": read_pdf, ".pptx": read_pptx, ".docx": read_docx, ".odt": read_odt}


def read_document(path, **kw):
    """Dispatch on the file extension; callers check it is in READERS first."""
    return READERS[Path(path).suffix.lower()](path, **kw)


__all__ = ["READERS", "RECORD_VERSION", "DocumentRecord", "ReadResult", "UnitRecord", "read_document", "read_docx",
           "read_odt", "read_pdf", "read_pptx", "sha256_file"]
