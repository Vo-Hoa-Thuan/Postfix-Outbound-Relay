"""
web/routes/ips.py – IP Relay Manager CRUD routes.
"""

import os
import uuid
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from typing import Optional

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
    data      = _read_ips()
    active_ip = _get_active_ip()
    return templates.TemplateResponse("ips.html", {
        "request":   request,
        "ips":       data.get("ips", []),
        "active_ip": active_ip,
        "msg":       msg,
        "error":     error,
    })


@router.post("/add")
async def add_ip(
    request: Request,
    ip:             str = Form(...),
    weight:         int = Form(1),
    limit_per_hour: int = Form(2000),
    note:           str = Form(""),
    smtp_user:      str = Form(""),
    smtp_pass:      str = Form(""),
    enabled:        Optional[str] = Form(None),
):
    data = _read_ips()
    ips  = data.get("ips", [])

    # Duplicate check
    if any(x["ip"] == ip for x in ips):
        return RedirectResponse(f"/ips?error=IP+{ip}+already+exists", status_code=303)

    ips.append({
        "ip":             ip,
        "enabled":        enabled == "on",
        "weight":         max(1, weight),
        "limit_per_hour": max(0, limit_per_hour),
        "note":           note,
        "smtp_user":      smtp_user,
        "smtp_pass":      smtp_pass,
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
):
    data = _read_ips()
    ips  = data.get("ips", [])
    for entry in ips:
        if entry["ip"] == ip:
            entry["weight"]         = max(1, weight)
            entry["limit_per_hour"] = max(0, limit_per_hour)
            entry["note"]           = note
            entry["smtp_user"]      = smtp_user
            entry["smtp_pass"]      = smtp_pass
            entry["enabled"]        = enabled == "on"
            break
    data["ips"] = ips
    _write_ips(data)
    return RedirectResponse(f"/ips?msg=IP+{ip}+updated", status_code=303)


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
