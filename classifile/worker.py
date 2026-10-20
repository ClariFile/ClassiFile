"""Reader worker processes with per-file timeouts (decision record B7).

Reading, analysis and the internal summary run in child processes, so a parser crash or hang cannot take the
app down. A crash or timeout is an operational failure ("failed" with a fixed reason), never semantic evidence.
"""
import multiprocessing as mp
import os
import queue

from classifile.reader import ReadResult, sha256_file

DEFAULT_TIMEOUT = 300  # seconds per file. ponytail: one fixed value; scale with expected OCR work after E8.


def _serve(conn, target):
    """Child loop: one path in, one result out, until the pipe closes."""
    while True:
        try:
            path = conn.recv()
        except (EOFError, OSError):
            return
        try:
            out = target(path)
        except Exception as e:  # reason carries no document text
            out = RuntimeError(f"internal error ({type(e).__name__})")
        conn.send(out)


def failure(path, reason):
    """A failed read the catalog can still record: hash and size come from the parent, which reads only bytes."""
    try:
        sha, size = sha256_file(path), os.stat(path).st_size
    except OSError:
        sha, size = None, None
    return ReadResult("failed", reason, sha, size), None, None


class Worker:
    """One child process that handles one file at a time; replaced after a crash or a timeout."""

    def __init__(self, target, timeout=DEFAULT_TIMEOUT, on_failure=failure):
        """on_failure(request, reason): the answer after a crash, a timeout or an error in the child."""
        self.target, self.timeout, self.on_failure = target, timeout, on_failure
        self.proc = self.conn = None

    def _start(self):
        ctx = mp.get_context("spawn")  # same behaviour on every platform; Windows only has spawn
        self.conn, child = ctx.Pipe()
        self.proc = ctx.Process(target=_serve, args=(child, self.target), daemon=True)
        self.proc.start()
        child.close()

    def run(self, path):
        if self.proc is None or not self.proc.is_alive():
            self._start()
        try:
            self.conn.send(path)
            if self.conn.poll(self.timeout):
                out = self.conn.recv()
                if not isinstance(out, Exception):
                    return out
                reason = str(out)
            else:
                reason = "reading timed out"
        except (EOFError, OSError):
            reason = "reader process stopped unexpectedly"
        self.stop()
        return self.on_failure(path, reason)

    def stop(self):
        if self.proc is not None:
            self.proc.kill()
            self.proc.join(10)
            self.conn.close()
        self.proc = self.conn = None


class WorkerPool:
    """A fixed set of workers shared by background threads; each call blocks until a worker is free."""

    def __init__(self, target, size=2, timeout=DEFAULT_TIMEOUT):
        self.workers = [Worker(target, timeout) for _ in range(size)]
        self.free = queue.Queue()
        for w in self.workers:
            self.free.put(w)

    def run(self, path):
        w = self.free.get()
        try:
            return w.run(path)
        finally:
            self.free.put(w)

    def close(self):
        for w in self.workers:
            w.stop()
