"""
web/routes/rspamd.py – Rspamd configuration and reload routes.
"""

import os
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from typing import Optional

BASE_DIR  = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

router = APIRouter(prefix="/rspamd")

RSPAMD_CFG = os.path.join(BASE_DIR, "config", "rspamd.json")


@router.get("", response_class=HTMLResponse)
async def show_rspamd(request: Request, msg: str = "", error: str = ""):
    from core.fileio  import read_json
    from core.rspamd  import get_status
    cfg = read_json(RSPAMD_CFG, {})
    return templates.TemplateResponse("rspamd.html", {
        "request":    request,
        "cfg":        cfg,
        "status":     get_status(),
        "msg":        msg,
        "error":      error,
    })


@router.post("/save")
async def save_rspamd(
    enable:          Optional[str] = Form(None),
    required_score:  float         = Form(6.0),
    greylist:        Optional[str] = Form(None),
    rl_enable:       Optional[str] = Form(None),
    rl_burst:        int           = Form(100),
    rl_rate:         str           = Form("50 / 1min"),
    vs_enable:       Optional[str] = Form(None),
    vs_type:         str           = Form("clamav"),
    vs_socket:       str           = Form("/var/run/clamav/clamd.ctl"),
    url_bl_enable:   Optional[str] = Form(None),
    url_bl_domains:  str           = Form(""),
    dkim_enable:     Optional[str] = Form(None),
    dkim_verify:     Optional[str] = Form(None),
    dkim_sign:       Optional[str] = Form(None),
    fz_enable:       Optional[str] = Form(None),
    fz_threshold:    float         = Form(10.0),
    custom_lua:      str           = Form(""),
    whitelist_ips:   str           = Form(""),
    blacklist_domains: str         = Form(""),
):
    from core.fileio import write_json
    from core.rspamd import generate_config

    wl_ips     = [x.strip() for x in whitelist_ips.split("\n")  if x.strip()]
    bl_domains = [x.strip() for x in blacklist_domains.split("\n") if x.strip()]
    url_domains = [x.strip() for x in url_bl_domains.split("\n") if x.strip()]

    cfg = {
        "enable":         enable == "on",
        "required_score": round(float(required_score), 1),
        "greylist":       greylist == "on",
        "rate_limit": {
            "enable": rl_enable == "on",
            "burst":  max(1, rl_burst),
            "rate":   rl_rate.strip() or "50 / 1min",
        },
        "virus_scan": {
            "enable": vs_enable == "on",
            "type":   vs_type,
            "socket": vs_socket,
        },
        "url_blacklist": {
            "enable": url_bl_enable == "on",
            "custom_domains": url_domains,
        },
        "dkim_policy": {
            "enable": dkim_enable == "on",
            "verification": dkim_verify == "on",
            "signing": dkim_sign == "on",
        },
        "fuzzy_hash": {
            "enable": fz_enable == "on",
            "threshold": fz_threshold,
        },
        "custom_lua":        custom_lua,
        "whitelist_ips":     wl_ips,
        "blacklist_domains": bl_domains,
    }

    write_json(RSPAMD_CFG, cfg)

    # generate_config now handles both writing files and reloading
    ok, apply_msg = generate_config()
    if not ok:
        return RedirectResponse(f"/rspamd?error={_enc(apply_msg)}", status_code=303)

    return RedirectResponse("/rspamd?msg=Rspamd+production+config+applied+and+reloaded", status_code=303)


def _enc(s: str) -> str:
    """Safe URL encoder for simple messages."""
    try:
        if not s:
            return ""
        # Simple string replacement for URL safe chars
        res = s.replace(" ", "+").replace("\n", " ")
        return res[:200]
    except Exception:
        return "Error"
