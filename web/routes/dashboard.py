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

@router.get("/api/chart")
async def api_chart():
    import json
    from datetime import datetime, timedelta
    
    parsed_log = os.path.join(BASE_DIR, "logs", "parsed.log")
    
    # Initialize the last 24 hours with 0
    now = datetime.now()
    hours_labels = []
    chart_data = {"sent": {}, "deferred": {}, "bounced": {}}
    
    # Create x-axis labels for the last 24 hours (including current hour)
    for i in range(23, -1, -1):
        h_time = now - timedelta(hours=i)
        label = h_time.strftime("%H:00")
        prefix = h_time.strftime("%Y-%m-%d %H") # Key for matching log time
        hours_labels.append({"label": label, "prefix": prefix})
        
        chart_data["sent"][prefix] = 0
        chart_data["deferred"][prefix] = 0
        chart_data["bounced"][prefix] = 0
        
    oldest_prefix = hours_labels[0]["prefix"]
    
    if os.path.exists(parsed_log):
        try:
            with open(parsed_log, "r", encoding="utf-8") as f:
                # To avoid reading massive files, we could read lines from bottom up, 
                # but standard python reading top-down is fine for small/medium logs.
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        log_time = entry.get("time", "")
                        status = entry.get("status", "")
                        
                        # Match the YYYY-MM-DD HH prefix
                        if len(log_time) >= 13:
                            prefix = log_time[:13]
                            if prefix >= oldest_prefix and prefix in chart_data[status]:
                                chart_data[status][prefix] += 1
                                
                    except Exception:
                        pass
        except Exception:
            pass
            
    # Format into arrays matching the labels
    sent_arr = [chart_data["sent"][h["prefix"]] for h in hours_labels]
    deferred_arr = [chart_data["deferred"][h["prefix"]] for h in hours_labels]
    bounced_arr = [chart_data["bounced"][h["prefix"]] for h in hours_labels]
    
    return {
        "labels": [h["label"] for h in hours_labels],
        "datasets": {
            "sent": sent_arr,
            "deferred": deferred_arr,
            "bounced": bounced_arr
        }
    }
