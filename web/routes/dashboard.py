"""
web/routes/dashboard.py – Optimized Dashboard overview route.
"""

import os
import json
import time
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

BASE_DIR  = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

router = APIRouter()

def _read_recent_logs(limit=20):
    """Fast tail-read of the parsed.log file without reading the whole file."""
    parsed_log = os.path.join(BASE_DIR, "logs", "parsed.log")
    if not os.path.exists(parsed_log): return []
    try:
        with open(parsed_log, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            # Seek back 64KB - plenty for dozens of JSON lines
            offset = max(0, size - 65536)
            f.seek(offset)
            raw = f.read().decode("utf-8", errors="replace")
            lines = raw.splitlines()
            
            results = []
            # Iterate backwards to get latest first
            for line in reversed(lines):
                line = line.strip()
                if not line: continue
                try:
                    results.append(json.loads(line))
                    if len(results) >= limit: break
                except: continue
            return results
    except Exception as e:
        print(f"[Dashboard] Log tail error: {e}")
        return []

def _count_deferred_this_hour() -> int:
    """Estimated count using recent logs for performance."""
    from datetime import datetime
    now_hour = datetime.now().strftime("%Y-%m-%d %H:")
    count = 0
    # Read last 300 lines to estimate hour count (much faster than full scan)
    logs = _read_recent_logs(300)
    for entry in logs:
        if entry.get("status") == "deferred" and entry.get("time", "").startswith(now_hour):
            count += 1
    return count

@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    from core.postfix   import get_status as postfix_status
    from core.rspamd    import get_status as rspamd_status
    from core.relay     import get_active_ip, get_total_sent_this_hour, get_all_counters
    from core.rotation  import get_time_remaining
    from core.fileio    import read_json
    
    active_ip_cfg  = get_active_ip()
    active_ip      = active_ip_cfg["ip"] if active_ip_cfg else "—"
    time_remaining = get_time_remaining()
    
    # Lightweight stats
    counters       = get_all_counters()
    deferred       = _count_deferred_this_hour()
    total_sent     = get_total_sent_this_hour()
    
    # Blacklist Alerts
    RELAY_IPS_FILE = os.path.join(BASE_DIR, "config", "relay_ips.json")
    all_ips = read_json(RELAY_IPS_FILE, {"ips": []}).get("ips", [])
    blacklisted_ips = [ip for ip in all_ips if ip.get("blacklist_status") == "BLACKLISTED"]

    return templates.TemplateResponse("dashboard.html", {
        "request":         request,
        "postfix_status":  postfix_status(),
        "rspamd_status":   rspamd_status(),
        "active_ip":       active_ip,
        "active_ip_cfg":   active_ip_cfg,
        "time_remaining":  time_remaining,
        "total_sent":      total_sent,
        "total_deferred":  deferred,
        "counters":        counters,
        "blacklisted_ips": blacklisted_ips,
        "recent_logs":     _read_recent_logs(15),
    })

@router.get("/api/logs")
async def api_logs():
    return _read_recent_logs(15)

@router.get("/api/status")
async def api_status():
    from core.postfix   import get_status as postfix_status
    from core.rspamd    import get_status as rspamd_status
    from core.relay     import get_active_ip, get_total_sent_this_hour
    from core.rotation  import get_time_remaining
    from core.fileio    import read_json

    active_ip_cfg = get_active_ip()
    config = read_json(os.path.join(BASE_DIR, "config", "relay_ips.json"), {"ips": []})
    blacklisted = [ip for ip in config.get("ips", []) if ip.get("blacklist_status") == "BLACKLISTED"]
    
    return {
        "postfix_status":  postfix_status(),
        "rspamd_status":   rspamd_status(),
        "active_ip":       active_ip_cfg["ip"] if active_ip_cfg else "—",
        "time_remaining":  get_time_remaining(),
        "total_sent":      get_total_sent_this_hour(),
        "total_deferred":  _count_deferred_this_hour(),
        "blacklisted_count": len(blacklisted)
    }

@router.get("/api/chart")
async def api_chart():
    from core.fileio import read_json
    cache_path = os.path.join(BASE_DIR, "runtime", "chart_cache.json")
    if os.path.exists(cache_path):
        return read_json(cache_path, {})
    return {"labels": [], "datasets": {"sent": [], "deferred": [], "bounced": []}}
