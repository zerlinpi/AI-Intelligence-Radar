from contextlib import contextmanager
import os
import threading

try:
    import fcntl
except ImportError:  # pragma: no cover - production deployment is Linux.
    fcntl = None


LOCK_FILE = os.getenv("RADAR_LOCK_FILE", "/tmp/ai-intelligence-radar.lock")
_process_lock = threading.Lock()


@contextmanager
def execution_lock():
    """Prevent overlapping radar runs across scheduler, API and CLI processes."""
    if fcntl is None:
        acquired = _process_lock.acquire(blocking=False)
        try:
            yield acquired
        finally:
            if acquired:
                _process_lock.release()
        return

    handle = open(LOCK_FILE, "a+")
    acquired = False

    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except BlockingIOError:
            acquired = False

        yield acquired
    finally:
        if acquired:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()
