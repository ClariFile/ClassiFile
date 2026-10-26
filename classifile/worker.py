"""Reader worker processes with per-file timeouts (decision record B7).

Reading, analysis and the internal summary run in child processes, so a parser crash or hang cannot take the
app down. A crash or timeout is an operational failure ("failed" with a fixed reason), never semantic evidence.
"""
import multiprocessing as mp
import os
import queue
import threading

from classifile.reader import ReadResult, sha256_file

DEFAULT_TIMEOUT = 300  # seconds per file. ponytail: one fixed value; scale with expected OCR work after E8.
TRANSFER_GRACE = 30    # seconds more for the whole exchange (sending the path, the result coming back): then the
                       # child is ended, so a stalled transfer can never hold a thread


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
        self.closed = False             # the app is closing: no new child, and failures are not hashed

    def _start(self):
        ctx = mp.get_context("spawn")  # same behaviour on every platform; Windows only has spawn
        self.conn, child = ctx.Pipe()
        self.proc = ctx.Process(target=_serve, args=(child, self.target), daemon=True)
        self.proc.start()
        child.close()

    def run(self, path):
        """The child's answer, or on_failure(path, reason). The whole exchange is bounded: the child is ended
        after timeout + TRANSFER_GRACE seconds whatever it is doing, which ends a stalled send or receive too."""
        if self.closed:
            return ReadResult("failed", "the app was closing", None, None), None, None
        if self.proc is None or not self.proc.is_alive():
            self._start()
        proc, conn = self.proc, self.conn
        watchdog = threading.Timer(self.timeout + TRANSFER_GRACE, proc.kill)
        watchdog.daemon = True
        watchdog.start()
        try:
            conn.send(path)
            if conn.poll(self.timeout):
                out = conn.recv()
                if not isinstance(out, Exception):
                    return out
                reason = str(out)
            else:
                reason = "reading timed out"
        except (EOFError, OSError, AttributeError):    # AttributeError: closed under it (stop() from closing)
            reason = "reader process stopped unexpectedly"
        finally:
            watchdog.cancel()
        self.stop()
        if self.closed:
            return ReadResult("failed", "the app was closing", None, None), None, None
        return self.on_failure(path, reason)

    def stop(self, close=False):
        """End the child (a new one starts on the next run), or for good with close=True."""
        self.closed = self.closed or close
        proc, conn, self.proc, self.conn = self.proc, self.conn, None, None
        if proc is not None:
            proc.kill()
            proc.join(10)
            conn.close()


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
            w.stop(close=True)
