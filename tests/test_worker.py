import hashlib
import shutil

from worker_helpers import misbehave
from classifile.worker import Worker
from conftest import EXPECT, SAMPLE  # noqa: E402


def test_timeouts_crashes_and_errors_are_operational_failures(samples, tmp_path):
    src = samples / SAMPLE["S2"]
    paths = {}
    for kind in ("hang", "crash", "raise", "fine"):
        paths[kind] = tmp_path / f"{kind}.pdf"
        shutil.copyfile(src, paths[kind])
    digest = hashlib.sha256(src.read_bytes()).hexdigest()
    w = Worker(misbehave, timeout=5)
    try:
        for kind, reason in (("hang", "reading timed out"), ("crash", "reader process stopped unexpectedly"),
                             ("raise", "internal error (ValueError)")):
            result, analysis, summary = w.run(paths[kind])
            assert (result.status, result.reason, analysis, summary) == ("failed", reason, None, None), kind
            assert result.sha256 == digest  # still recordable as a failed snapshot
        w.timeout = 300  # the short limit is for the hang: a fresh child on a busy machine may need longer
        result, analysis, summary = w.run(paths["fine"])  # a fresh child after the failures
        assert result.status == "ok" and analysis.suggestions and summary["summary_version"]
    finally:
        w.stop()
