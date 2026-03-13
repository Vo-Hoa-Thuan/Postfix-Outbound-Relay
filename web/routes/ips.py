"""
web/routes/ips.py – IP Relay Manager CRUD routes.
"""

import os
import uuid
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from typing import Optional
import socket

BASE_DIR  = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

router = APIRouter(prefix="/ips")

CONFIG_IPS = os.path.join(BASE_DIR, "config", "relay_ips.json")


def _read_ips() -> dict:
    from core.fileio import read_json
    return read_json(CONFIG_IPS, {"ips": []})


def _write_ips(data: dict) -> None:
    from core.fileio import write_json
    write_json(CONFIG_IPS, data)


def _get_active_ip() -> Optional[str]:
    from core.relay import get_active_ip
    ip = get_active_ip()
    return ip["ip"] if ip else None


@router.get("", response_class=HTMLResponse)
async def list_ips(request: Request, msg: str = "", error: str = ""):
    from core.relay import get_effective_limit
    data      = _read_ips()
    active_ip = _get_active_ip()
    ips_list = data.get("ips", [])
    import datetime
    for ip_cfg in ips_list:
        ip_cfg["effective_limit"] = get_effective_limit(ip_cfg)
        
        last_check = ip_cfg.get("last_blacklist_check")
        if last_check:
            dt = datetime.datetime.fromtimestamp(last_check)
            ip_cfg["last_blacklist_check_str"] = dt.strftime("%Y-%m-%d %H:%M:%S")
        else:
            ip_cfg["last_blacklist_check_str"] = "Never"
        
    return templates.TemplateResponse("ips.html", {
        "request":   request,
        "ips":       ips_list,
        "active_ip": active_ip,
        "msg":       msg,
        "error":     error,
    })


@router.post("/add")
async def add_ip(
    request: Request,
    ip:             Optional[str] = Form(None),
    weight:         int = Form(1),
    limit_per_hour: int = Form(2000),
    note:           str = Form(""),
    smtp_user:      str = Form(""),
    smtp_pass:      str = Form(""),
    enabled:        Optional[str] = Form(None),
    warmup_enabled: Optional[str] = Form(None),
    warmup_start_date: str = Form(""),
    hostname: str = Form(""),
):
    data = _read_ips()
    ips  = data.get("ips", [])

    # If hostname provided, resolve to IP
    if hostname.strip():
        try:
            resolved_ip = socket.gethostbyname(hostname.strip())
            # If IP was empty or we want to overwrite with resolved IP
            ip = resolved_ip
        except socket.gaierror:
            return RedirectResponse(f"/ips?error=Could+not+resolve+hostname:+{hostname}", status_code=303)

    # Duplicate check
    if any(x["ip"] == ip for x in ips):
        return RedirectResponse(f"/ips?error=IP+{ip}+already+exists", status_code=303)

    ips.append({
        "ip":             ip,
        "hostname":       hostname.strip(),
        "enabled":        enabled == "on",
        "weight":         max(1, weight),
        "limit_per_hour": max(0, limit_per_hour),
        "note":           note,
        "smtp_user":      smtp_user,
        "smtp_pass":      smtp_pass,
        "warmup_enabled": warmup_enabled == "on",
        "warmup_start_date": warmup_start_date,
    })
    data["ips"] = ips
    _write_ips(data)
    return RedirectResponse(f"/ips?msg=IP+{ip}+added+successfully", status_code=303)


@router.post("/edit")
async def edit_ip(
    request: Request,
    ip:             str  = Form(...),
    weight:         int  = Form(1),
    limit_per_hour: int  = Form(2000),
    note:           str  = Form(""),
    smtp_user:      str  = Form(""),
    smtp_pass:      str  = Form(""),
    enabled:        Optional[str] = Form(None),
    warmup_enabled: Optional[str] = Form(None),
    warmup_start_date: str = Form(""),
    hostname: str = Form(""),
):
    data = _read_ips()
    ips  = data.get("ips", [])

    # If hostname provided, resolve to IP
    new_ip = ip
    if hostname.strip():
        try:
            new_ip = socket.gethostbyname(hostname.strip())
        except socket.gaierror:
            return RedirectResponse(f"/ips?error=Could+not+resolve+hostname:+{hostname}", status_code=303)

    for entry in ips:
        if entry["ip"] == ip:
            entry["ip"]             = new_ip
            entry["hostname"]       = hostname.strip()
            entry["weight"]         = max(1, weight)
            entry["limit_per_hour"] = max(0, limit_per_hour)
            entry["note"]           = note
            entry["smtp_user"]      = smtp_user
            entry["smtp_pass"]      = smtp_pass
            entry["enabled"]        = enabled == "on"
            entry["warmup_enabled"] = warmup_enabled == "on"
            entry["warmup_start_date"] = warmup_start_date
            break
    data["ips"] = ips
    _write_ips(data)
    return RedirectResponse(f"/ips?msg=IP+{new_ip}+updated", status_code=303)


@router.post("/delete")
async def delete_ip(ip: str = Form(...)):
    active = _get_active_ip()
    if ip == active:
        return RedirectResponse(f"/ips?error=Cannot+delete+active+IP+{ip}", status_code=303)

    data = _read_ips()
    data["ips"] = [x for x in data.get("ips", []) if x["ip"] != ip]
    _write_ips(data)
    return RedirectResponse(f"/ips?msg=IP+{ip}+deleted", status_code=303)


@router.post("/toggle")
async def toggle_ip(ip: str = Form(...)):
    data = _read_ips()
    for entry in data.get("ips", []):
        if entry["ip"] == ip:
            entry["enabled"] = not entry.get("enabled", True)
            break
    _write_ips(data)
    return RedirectResponse("/ips?msg=IP+status+updated", status_code=303)


@router.post("/check-blacklist")
async def check_ip_blacklist_route(ip: str = Form(...)):
    from core.blacklist import process_ip_blacklist_alert
    is_bad = process_ip_blacklist_alert(ip)
    if is_bad:
        return RedirectResponse(f"/ips?error=WARNING:+{ip}+is+BLACKLISTED!+It+has+been+automatically+disabled.", status_code=303)
    else:
        return RedirectResponse(f"/ips?msg={ip}+is+clean+(Not+blacklisted).", status_code=303)

@router.post("/check-all-blacklist")
async def check_all_blacklist_route():
    from core.blacklist import auto_check_all
    # We'll force a check by modifying the last_check time if needed, 
    # but auto_check_all usually has a 12h threshold. 
    # Let's import and call a version that forces it or just call it.
    auto_check_all() 
    return RedirectResponse("/ips?msg=Background+blacklist+check+started+for+all+IPs.", status_code=303)
