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
    whitelist_ips:   str           = Form(""),
    blacklist_domains: str         = Form(""),
):
    from core.fileio import write_json
    from core.rspamd import generate_config, reload_rspamd

    wl_ips     = [x.strip() for x in whitelist_ips.split("\n")  if x.strip()]
    bl_domains = [x.strip() for x in blacklist_domains.split("\n") if x.strip()]

    cfg = {
        "enable":         enable == "on",
        "required_score": round(float(required_score), 1),
        "greylist":       greylist == "on",
        "rate_limit": {
            "enable": rl_enable == "on",
            "burst":  max(1, rl_burst),
            "rate":   rl_rate.strip() or "50 / 1min",
        },
        "whitelist_ips":     wl_ips,
        "blacklist_domains": bl_domains,
    }

    write_json(RSPAMD_CFG, cfg)

    ok, msg = generate_config()
    if not ok:
        return RedirectResponse(f"/rspamd?error={_enc(msg)}", status_code=303)

    ok2, msg2 = reload_rspamd()
    if not ok2:
        # Config saved, but reload failed (possibly dev environment)
        return RedirectResponse(f"/rspamd?msg=Config+saved.+Reload+note:+{_enc(msg2)}", status_code=303)

    return RedirectResponse("/rspamd?msg=Rspamd+config+saved+and+reloaded", status_code=303)


def _enc(s: str) -> str:
    return s.replace(" ", "+").replace("\n", " ")[:200]
