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
            # Estimate 250 bytes per log line on average
            bytes_to_read = min(size, limit * 250 + 10000)
            offset = max(0, size - bytes_to_read)
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
    from core.tracking  import get_queue_status
    
    active_ip_cfg  = get_active_ip()
    active_ip      = active_ip_cfg["ip"] if active_ip_cfg else "—"
    time_remaining = get_time_remaining()
    
    # Lightweight stats
    counters       = get_all_counters()
    deferred       = _count_deferred_this_hour()
    total_sent     = get_total_sent_this_hour()
    queue_status   = get_queue_status()
    
    # Blacklist Alerts
    RELAY_IPS_FILE = os.path.join(BASE_DIR, "config", "relay_ips.json")
    all_ips_cfg = read_json(RELAY_IPS_FILE, {"ips": []}).get("ips", [])
    blacklisted_ips = [ip for ip in all_ips_cfg if ip.get("blacklist_status") == "BLACKLISTED"]
    
    # Summary stats for the new header strip
    stats = {
        "active_ips": len([ip for ip in all_ips_cfg if ip.get("enabled", True)]),
        "disabled_ips": len([ip for ip in all_ips_cfg if not ip.get("enabled", True)]),
        "blacklisted_ips": len(blacklisted_ips),
        "queue_size": queue_status.get("active", 0) + queue_status.get("deferred", 0),
        "total_sent_1h": total_sent,
        "total_deferred_1h": deferred
    }

    # Fetch unique local IPs and Dates for the filter dropdown
    recent_for_stats = _read_recent_logs(2000)
    unique_local_ips = sorted(list(set(l.get("local_ip") for l in recent_for_stats if l.get("local_ip"))))
    unique_dates = sorted(list(set(l.get("time", "")[:10] for l in recent_for_stats if len(l.get("time", "")) >= 10)), reverse=True)[:5]

    # Top stats logic
    from collections import Counter
    top_senders = Counter(l.get("from") for l in recent_for_stats if l.get("from")).most_common(10)
    top_ips     = Counter(l.get("local_ip") for l in recent_for_stats if l.get("local_ip")).most_common(20)

    return templates.TemplateResponse("dashboard.html", {
        "request":         request,
        "postfix_status":  postfix_status(),
        "rspamd_status":   rspamd_status(),
        "active_ip":       active_ip,
        "active_ip_cfg":   active_ip_cfg,
        "all_ips":         all_ips_cfg,
        "counters":        counters,
        "time_remaining":  time_remaining,
        "stats":           stats,
        "recent_logs":     recent_for_stats[:50],
        "unique_ips":      unique_local_ips,
        "unique_dates":    unique_dates,
        "top_senders":     top_senders,
        "top_ips":         top_ips,
        "active_page":     "dashboard"
    })

@router.get("/api/logs")
async def api_logs(
    ip: str = "",
    status: str = "",
    sender: str = "",
    recipient: str = "",
    date: str = "",
    limit: int = 50
):
    """Enhanced logs API with filtering."""
    # Read more lines if we are filtering
    read_limit = 2000 if (ip or status or sender or recipient or date) else limit
    logs = _read_recent_logs(read_limit)
    
    filtered = []
    for l in logs:
        if date and not l.get("time", "").startswith(date): continue
        if ip and l.get("local_ip") != ip: continue
        if status and l.get("status") != status: continue
        if sender and sender.lower() not in l.get("from", "").lower(): continue
        if recipient and recipient.lower() not in l.get("to", "").lower(): continue
        filtered.append(l)
        if len(filtered) >= limit: break
        
    return filtered

@router.get("/api/status")
async def api_status():
    from core.postfix   import get_status as postfix_status
    from core.rspamd    import get_status as rspamd_status
    from core.relay     import get_active_ip, get_total_sent_this_hour
    from core.rotation  import get_time_remaining
    from core.fileio    import read_json
    from core.tracking  import get_queue_status

    active_ip_cfg = get_active_ip()
    config = read_json(os.path.join(BASE_DIR, "config", "relay_ips.json"), {"ips": []})
    all_ips = config.get("ips", [])
    blacklisted = [ip for ip in all_ips if ip.get("blacklist_status") == "BLACKLISTED"]
    queue_status = get_queue_status()
    
    return {
        "postfix_status":  postfix_status(),
        "rspamd_status":   rspamd_status(),
        "active_ip":       active_ip_cfg["ip"] if active_ip_cfg else "—",
        "time_remaining":  get_time_remaining(),
        "total_sent":      get_total_sent_this_hour(),
        "total_deferred":  _count_deferred_this_hour(),
        "blacklisted_count": len(blacklisted),
        "stats": {
            "active_ips": len([ip for ip in all_ips if ip.get("enabled", True)]),
            "disabled_ips": len([ip for ip in all_ips if not ip.get("enabled", True)]),
            "blacklisted_ips": len(blacklisted),
            "queue_size": queue_status.get("active", 0) + queue_status.get("deferred", 0),
            "queue_breakdown": {
                "active": queue_status.get("active", 0),
                "deferred": queue_status.get("deferred", 0),
                "hold": queue_status.get("hold", 0),
                "incoming": queue_status.get("incoming", 0)
            }
        }
    }

@router.get("/queue", response_class=HTMLResponse)
async def queue_page(request: Request):
    from core.tracking import get_queue_status
    status = get_queue_status()
    return templates.TemplateResponse("queue.html", {
        "request": request,
        "queue": status,
        "active_page": "queue"
    })

@router.post("/flush")
async def flush_all_queues():
    from core.tracking import flush_queue
    success = flush_queue()
    if success:
        return {"success": True}
    return {"success": False, "error": "Postfix flush failed"}

@router.get("/api/chart")
async def api_chart():
    from core.fileio import read_json
    cache_path = os.path.join(BASE_DIR, "runtime", "chart_cache.json")
    if os.path.exists(cache_path):
        return read_json(cache_path, {})
    return {"labels": [], "datasets": {"sent": [], "deferred": [], "bounced": []}}

@router.get("/api/rotation-history")
async def api_rotation_history(limit: int = 20):
    """Returns the latest IP rotation events."""
    rotation_log = os.path.join(BASE_DIR, "logs", "rotation.log")
    if not os.path.exists(rotation_log):
        return []
    
    events = []
    try:
        with open(rotation_log, "r", encoding="utf-8") as f:
            lines = f.readlines()
            for line in reversed(lines):
                line = line.strip()
                if not line: continue
                try:
                    events.append(json.loads(line))
                    if len(events) >= limit: break
                except: continue
    except Exception as e:
        print(f"[Dashboard] Rotation history error: {e}")
    
    return events
