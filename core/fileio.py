"""
core/fileio.py – Thread-safe JSON file I/O with file locking.
Uses filelock for cross-platform process safety.
"""

import json
import os
from typing import Any, Optional
from filelock import FileLock, Timeout

def _get_lock(path: str) -> FileLock:
    return FileLock(path + ".lock", timeout=5)

def read_json(path: str, default: Optional[Any] = None) -> Any:
    """Read JSON from a file. Returns `default` if file does not exist or is invalid."""
    if not os.path.exists(path):
        return default if default is not None else {}
    lock = _get_lock(path)
    try:
        with lock.acquire(timeout=5):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                return json.loads(content) if content else (default if default is not None else {})
    except (json.JSONDecodeError, OSError, Timeout):
        return default if default is not None else {}

def write_json(path: str, data: Any, indent: int = 2) -> None:
    """Write data as JSON to a file with exclusive file lock."""
    dir_name = os.path.dirname(path)
    if dir_name:
        os.makedirs(dir_name, exist_ok=True)
    
    lock = _get_lock(path)
    try:
        with lock.acquire(timeout=5):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=indent, ensure_ascii=False)
    except Timeout:
        print(f"[FileIO] WARNING: Could not acquire lock to write {path}")

def ensure_json(path: str, default: Any) -> Any:
    """Ensure a JSON file exists with a default value; return current content."""
    if not os.path.exists(path):
        write_json(path, default)
        return default
    return read_json(path, default)
