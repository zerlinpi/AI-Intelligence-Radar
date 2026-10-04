from contextlib import contextmanager
import os
from pathlib import Path
import threading

try:
    import fcntl
except ImportError:  # pragma: no cover - production deployment is Linux.
    fcntl = None


LOCK_FILE = os.getenv("RADAR_LOCK_FILE", "/tmp/ai-intelligence-radar.lock")
_process_lock = threading.Lock()
_named_process_locks = {}
_named_process_locks_guard = threading.Lock()


def _thread_lock_for(path: str) -> threading.Lock:
    key = str(path or "")
    with _named_process_locks_guard:
        lock = _named_process_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _named_process_locks[key] = lock
        return lock


@contextmanager
def named_execution_lock(lock_file: str):
    """Non-blocking lock shared by processes that see the same filesystem path."""
    path = Path(str(lock_file or LOCK_FILE)).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)

    if fcntl is None:
        lock = _thread_lock_for(str(path))
        acquired = lock.acquire(blocking=False)
        try:
            yield acquired
        finally:
            if acquired:
                lock.release()
        return

    handle = open(path, "a+")
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

    with named_execution_lock(LOCK_FILE) as acquired:
        yield acquired
