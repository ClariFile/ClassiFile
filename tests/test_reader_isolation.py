import ast
from pathlib import Path

READER = Path(__file__).resolve().parent.parent / "classifile" / "reader"


def _imports(path, root=READER):
    pkg = ["classifile", "reader", *path.relative_to(root).parent.parts]
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            yield from (a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = pkg[: len(pkg) - node.level + 1] if node.level else []
            yield ".".join(base + ([node.module] if node.module else []))


def _violations(root):
    return [
        f"{p.name}: {m}"
        for p in root.rglob("*.py")
        for m in _imports(p, root)
        if m.split(".")[0] == "classifile" and m.split(".")[:2] != ["classifile", "reader"]
    ]


def test_reader_imports_nothing_from_other_classifile_packages():
    assert not _violations(READER)


def test_checker_catches_violations(tmp_path):
    (tmp_path / "x.py").write_text("from ..catalog import db\nimport classifile.copies\nfrom . import ok\nimport os\n")
    assert sorted(_violations(tmp_path)) == ["x.py: classifile.catalog", "x.py: classifile.copies"]
