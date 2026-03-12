"""
web/routes/logs.py – SMTP Monitor log viewer route.
"""

import os
import json
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

BASE_DIR  = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

router = APIRouter(prefix="/logs")

PARSED_LOG = os.path.join(BASE_DIR, "logs", "parsed.log")
MAX_LINES  = 5000   # read last N lines from the log file


@router.get("", response_class=HTMLResponse)
async def view_logs(
    request:    Request,
    ip:         str = "",
    sender:     str = "",
    recipient:  str = "",
    date:       str = "",
    status:     str = "",
    page:       int = 1,
):
    entries = _read_parsed_log()

    # Apply filters
    if ip:
        entries = [e for e in entries if e.get("local_ip") == ip or e.get("dest_ip") == ip]
    if sender:
        entries = [e for e in entries if sender.lower() in e.get("from", "").lower()]
    if recipient:
        entries = [e for e in entries if recipient.lower() in e.get("to", "").lower()]
    if date:
        entries = [e for e in entries if e.get("time", "").startswith(date)]
    if status:
        entries = [e for e in entries if e.get("status") == status]

    # Newest first
    entries.reverse()

    # Pagination
    per_page   = 100
    total      = len(entries)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page       = max(1, min(page, total_pages))
    start      = (page - 1) * per_page
    page_entries = entries[start:start + per_page]

    # Collect unique local IPs for filter dropdown
    all_ips = sorted(set(e.get("local_ip", "") for e in _read_parsed_log() if e.get("local_ip")))

    return templates.TemplateResponse("logs.html", {
        "request":     request,
        "entries":     page_entries,
        "total":       total,
        "page":        page,
        "total_pages": total_pages,
        "all_ips":     all_ips,
        # Current filters (to repopulate form)
        "f_ip":        ip,
        "f_sender":    sender,
        "f_recipient": recipient,
        "f_date":      date,
        "f_status":    status,
    })


def _read_parsed_log() -> list:
    """Read all entries from parsed.log (JSONL). Returns list of dicts."""
    if not os.path.exists(PARSED_LOG):
        return []
    entries = []
    try:
        with open(PARSED_LOG, "r", encoding="utf-8") as f:
            lines = f.readlines()
        # Only last MAX_LINES
        for line in lines[-MAX_LINES:]:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    except Exception:
        pass
    return entries
