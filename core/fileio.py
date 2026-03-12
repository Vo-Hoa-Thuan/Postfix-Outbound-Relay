"""
core/fileio.py – Thread-safe JSON file I/O with file locking.
On Linux: uses fcntl.flock for advisory locking.
On Windows (dev): uses a threading.Lock fallback.
"""

import json
import os
import sys
import threading
from typing import Any, Dict, Optional

# Per-path threading locks for multi-thread safety on Windows dev
_thread_locks: Dict[str, threading.Lock] = {}
_registry_lock = threading.Lock()

def _get_thread_lock(path: str) -> threading.Lock:
    with _registry_lock:
        if path not in _thread_locks:
            _thread_locks[path] = threading.Lock()
        return _thread_locks[path]


def read_json(path: str, default: Optional[Any] = None) -> Any:
    """Read JSON from a file. Returns `default` if file does not exist or is invalid."""
    if not os.path.exists(path):
        return default if default is not None else {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            _lock_shared(f)
            try:
                content = f.read().strip()
                return json.loads(content) if content else (default if default is not None else {})
            finally:
                _unlock(f)
    except (json.JSONDecodeError, OSError):
        return default if default is not None else {}


def write_json(path: str, data: Any, indent: int = 2) -> None:
    """Write data as JSON to a file with exclusive file lock."""
    os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
    thread_lock = _get_thread_lock(path)
    with thread_lock:
        with open(path, "w", encoding="utf-8") as f:
            _lock_exclusive(f)
            try:
                json.dump(data, f, indent=indent, ensure_ascii=False)
            finally:
                _unlock(f)


def ensure_json(path: str, default: Any) -> Any:
    """Ensure a JSON file exists with a default value; return current content."""
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        write_json(path, default)
        return default
    return read_json(path, default)


# ── Platform-specific file locking ──────────────────────────────────────────

if sys.platform == "win32":
    import msvcrt

    def _lock_shared(f):
        pass  # Windows dev fallback – threading.Lock used instead

    def _lock_exclusive(f):
        pass

    def _unlock(f):
        pass
else:
    import fcntl

    def _lock_shared(f):
        fcntl.flock(f.fileno(), fcntl.LOCK_SH)

    def _lock_exclusive(f):
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)

    def _unlock(f):
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
