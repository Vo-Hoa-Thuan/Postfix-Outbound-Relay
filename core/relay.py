"""
core/relay.py – IP selection logic (weighted round-robin) and per-IP rate limiting.
"""

import os
import time
from typing import Optional, Dict, Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from core.fileio import read_json, write_json

CONFIG_IPS   = os.path.join(BASE_DIR, "config", "relay_ips.json")
IP_STATE     = os.path.join(BASE_DIR, "runtime", "ip_state.json")
COUNTERS     = os.path.join(BASE_DIR, "runtime", "counters.json")


# ── Helpers ──────────────────────────────────────────────────────────────────

def get_enabled_ips() -> list:
    data = read_json(CONFIG_IPS, {"ips": []})
    return [ip for ip in data.get("ips", []) if ip.get("enabled", True)]


def get_active_ip() -> Optional[Dict[str, Any]]:
    """Return the currently active IP dict, or None."""
    state = read_json(IP_STATE, {})
    active = state.get("active_ip")
    if not active:
        return None
    config = read_json(CONFIG_IPS, {"ips": []})
    for ip in config.get("ips", []):
        if ip["ip"] == active:
            return ip
    return None


def get_ip_state() -> Dict[str, Any]:
    return read_json(IP_STATE, {"active_ip": None, "last_rotated": 0})


def select_next_ip(current_ip: Optional[str] = None) -> Optional[str]:
    """
    Pick the next IP using weighted round-robin.
    Returns the IP string or None if no IPs are available.
    """
    enabled = get_enabled_ips()
    if not enabled:
        return None

    # Load rotation mode
    from core.rotation import get_rotation_config
    mode = get_rotation_config().get("mode", "weighted")

    # Build pool based on mode
    pool = []
    for ip_cfg in enabled:
        weight = max(1, ip_cfg.get("weight", 1)) if mode == "weighted" else 1
        pool.extend([ip_cfg["ip"]] * weight)

    if not pool:
        return None

    state = read_json(IP_STATE, {})
    active_index = state.get("active_index", -1)

    # If the active index is valid and it corresponds to the current IP, we just step forward
    if 0 <= active_index < len(pool) and pool[active_index] == current_ip:
        next_idx = (active_index + 1) % len(pool)
    else:
        # Fallback if config changed or this is the first run
        if current_ip and current_ip in pool:
            # Find the FIRST occurrence to start there, then move to the next.
            idx = pool.index(current_ip)
            next_idx = (idx + 1) % len(pool)
            
            # If we want to guarantee it forces a CHANGE when clicking manual trigger (and pool allows):
            # We can skip identical IPs if there are distinct ones available.
            # But normally, just stepping forward is correct for weighted roundrobin.
        else:
            next_idx = 0

    chosen = pool[next_idx]

    # Persist state
    state["active_ip"] = chosen
    state["active_index"] = next_idx
    state["last_rotated"] = time.time()
    write_json(IP_STATE, state)
    return chosen


# ── Rate limiting ─────────────────────────────────────────────────────────────

def _get_current_window() -> int:
    """Return current hour as integer epoch (seconds truncated to hour)."""
    return int(time.time() // 3600) * 3600


def _reset_stale_counter(counters: Dict, ip: str) -> Dict:
    window = _get_current_window()
    if counters.get(ip, {}).get("window") != window:
        counters[ip] = {"window": window, "count": 0}
    return counters


def check_limit(ip: str) -> bool:
    """Return True if IP is under its hourly send limit (or no limit set)."""
    config = read_json(CONFIG_IPS, {"ips": []})
    ip_cfg = next((x for x in config.get("ips", []) if x["ip"] == ip), None)
    if not ip_cfg:
        return True
    limit = ip_cfg.get("limit_per_hour", 0)
    if limit <= 0:
        return True  # no limit

    counters = read_json(COUNTERS, {})
    counters = _reset_stale_counter(counters, ip)
    return counters[ip]["count"] < limit


def increment_counter(ip: str) -> int:
    """Increment hourly send counter for IP. Returns new count."""
    counters = read_json(COUNTERS, {})
    counters = _reset_stale_counter(counters, ip)
    counters[ip]["count"] += 1
    write_json(COUNTERS, counters)
    return counters[ip]["count"]


def get_all_counters() -> Dict[str, Any]:
    """Return dict of ip -> {window, count} for current hour."""
    counters = read_json(COUNTERS, {})
    window = _get_current_window()
    result = {}
    for ip, data in counters.items():
        if data.get("window") == window:
            result[ip] = data
    return result


def get_total_sent_this_hour() -> int:
    return sum(v.get("count", 0) for v in get_all_counters().values())
