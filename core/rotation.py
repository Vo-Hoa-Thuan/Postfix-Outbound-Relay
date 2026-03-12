"""
core/rotation.py – IP rotation scheduling logic.
"""

import os
import time
from typing import Tuple

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from core.fileio import read_json
from core.relay  import select_next_ip, get_ip_state

ROTATION_CFG = os.path.join(BASE_DIR, "config", "rotation.json")


def get_rotation_config() -> dict:
    return read_json(ROTATION_CFG, {"rotation_seconds": 60, "mode": "weighted"})


def get_time_remaining() -> int:
    """Return seconds until next scheduled rotation (0 if overdue)."""
    cfg   = get_rotation_config()
    state = get_ip_state()
    interval      = int(cfg.get("rotation_seconds", 60))
    last_rotated  = float(state.get("last_rotated", 0))
    elapsed       = time.time() - last_rotated
    remaining     = interval - elapsed
    return max(0, int(remaining))


def should_rotate() -> bool:
    return get_time_remaining() == 0


def rotate_if_needed() -> Tuple[bool, str]:
    """
    Check rotation schedule and rotate if needed.
    Returns (rotated: bool, new_ip: str).
    """
    if not should_rotate():
        state = get_ip_state()
        return False, state.get("active_ip", "")

    state   = get_ip_state()
    current = state.get("active_ip")
    new_ip  = select_next_ip(current_ip=current)
    return True, new_ip or ""
