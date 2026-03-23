"""
core/rotation.py – IP rotation scheduling logic.
"""

import os
import time
import json
from typing import Tuple, Optional

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from core.fileio import read_json
from core.relay  import select_next_ip, get_ip_state

ROTATION_CFG = os.path.join(BASE_DIR, "config", "rotation.json")
ROTATION_LOG = os.path.join(BASE_DIR, "logs", "rotation.log")


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


def log_rotation_event(old_ip: Optional[str], new_ip: str, reason: str = "scheduled"):
    """Appends a rotation event to logs/rotation.log."""
    event = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "old_ip": old_ip or "none",
        "new_ip": new_ip,
        "reason": reason
    }
    try:
        os.makedirs(os.path.dirname(ROTATION_LOG), exist_ok=True)
        with open(ROTATION_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
    except Exception as e:
        print(f"[Rotation] Log error: {e}")


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
    
    if new_ip and new_ip != current:
        log_rotation_event(current, new_ip, "scheduled")
        
    return True, new_ip or ""
