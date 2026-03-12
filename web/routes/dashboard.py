"""
web/routes/dashboard.py – Dashboard overview route.
"""

import os
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

BASE_DIR  = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    from core.postfix   import get_status as postfix_status
    from core.rspamd    import get_status as rspamd_status
    from core.relay     import get_active_ip, get_total_sent_this_hour, get_all_counters
    from core.rotation  import get_time_remaining, get_rotation_config

    active_ip_cfg  = get_active_ip()
    active_ip      = active_ip_cfg["ip"] if active_ip_cfg else "—"
    rotation_cfg   = get_rotation_config()
    time_remaining = get_time_remaining()
    counters       = get_all_counters()

    # Count deferred (from parsed log, last 100 entries)
    deferred = _count_deferred_this_hour()

    return templates.TemplateResponse("dashboard.html", {
        "request":         request,
        "postfix_status":  postfix_status(),
        "rspamd_status":   rspamd_status(),
        "active_ip":       active_ip,
        "active_ip_cfg":   active_ip_cfg,
        "rotation_mode":   rotation_cfg.get("mode", "weighted"),
        "rotation_secs":   rotation_cfg.get("rotation_seconds", 60),
        "time_remaining":  time_remaining,
        "total_sent":      get_total_sent_this_hour(),
        "total_deferred":  deferred,
        "counters":        counters,
    })


@router.get("/api/status")
async def api_status():
    from core.postfix   import get_status as postfix_status
    from core.rspamd    import get_status as rspamd_status
    from core.relay     import get_active_ip, get_total_sent_this_hour, get_all_counters
    from core.rotation  import get_time_remaining, get_rotation_config

    active_ip_cfg  = get_active_ip()
    active_ip      = active_ip_cfg["ip"] if active_ip_cfg else "—"
    rotation_cfg   = get_rotation_config()
    time_remaining = get_time_remaining()
    
    # We omit counters here to keep it simple, or return them if table reloading is wanted.
    # For now, just general stats
    return {
        "postfix_status":  postfix_status(),
        "rspamd_status":   rspamd_status(),
        "active_ip":       active_ip,
        "active_ip_cfg":   active_ip_cfg,
        "rotation_mode":   rotation_cfg.get("mode", "weighted"),
        "rotation_secs":   rotation_cfg.get("rotation_seconds", 60),
        "time_remaining":  time_remaining,
        "total_sent":      get_total_sent_this_hour(),
        "total_deferred":  _count_deferred_this_hour()
    }


def _count_deferred_this_hour() -> int:
    import json, time
    from datetime import datetime
    parsed_log = os.path.join(BASE_DIR, "logs", "parsed.log")
    if not os.path.exists(parsed_log):
        return 0
    now_hour = datetime.now().strftime("%Y-%m-%d %H:")
    count = 0
    try:
        with open(parsed_log, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("status") == "deferred" and entry.get("time", "").startswith(now_hour):
                        count += 1
                except Exception:
                    pass
    except Exception:
        pass
    return count
