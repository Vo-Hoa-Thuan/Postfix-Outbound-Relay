"""
web/routes/settings.py - Global settings web routes.
"""
import os
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from typing import Optional

from core.settings import get_settings, save_settings, send_alert

BASE_DIR  = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

router = APIRouter(prefix="/settings")

@router.get("", response_class=HTMLResponse)
async def view_settings(request: Request, msg: str = "", error: str = ""):
    from core.postfix import get_postfix_limits
    settings = get_settings()
    postfix_limits = get_postfix_limits()
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "settings": settings,
        "postfix_limits": postfix_limits,
        "msg": msg,
        "error": error
    })

@router.post("/save")
async def save_settings_post(
    request: Request,
    mxtoolbox_api_key: str = Form(""),
    alert_enabled: Optional[str] = Form(None),
    smtp_host: str = Form("127.0.0.1"),
    smtp_port: int = Form(25),
    smtp_user: str = Form(""),
    smtp_pass: str = Form(""),
    from_email: str = Form(""),
    to_email: str = Form(""),
    blacklist_check_interval: int = Form(12),
    # Postfix Limits
    recipient_limit: int = Form(1000),
    message_size: int = Form(10240000),
    dest_concurrency: int = Form(20),
    dest_recipient_limit: int = Form(50)
):
    settings = get_settings()
    settings["mxtoolbox_api_key"] = mxtoolbox_api_key.strip()
    
    settings["alert_email"] = {
        "enabled": alert_enabled == "on",
        "smtp_host": smtp_host.strip(),
        "smtp_port": smtp_port,
        "smtp_user": smtp_user.strip(),
        "smtp_pass": smtp_pass.strip(),
        "from_email": from_email.strip(),
        "to_email": to_email.strip()
    }
    
    settings["blacklist_check_interval"] = max(1, blacklist_check_interval)
    
    save_settings(settings)

    # Apply Postfix Limits
    from core.postfix import apply_postfix_limits
    postfix_cfg = {
        "smtpd_recipient_limit": str(recipient_limit),
        "message_size_limit": str(message_size),
        "default_destination_concurrency_limit": str(dest_concurrency),
        "default_destination_recipient_limit": str(dest_recipient_limit)
    }
    ok, p_msg = apply_postfix_limits(postfix_cfg)
    
    msg = "Settings saved successfully"
    if not ok:
        return RedirectResponse(f"/settings?msg={msg}&error={p_msg}", status_code=303)
        
    return RedirectResponse(f"/settings?msg={msg}+and+Postfix limits+applied", status_code=303)

@router.post("/test-email")
async def test_email_post(request: Request):
    success = send_alert("Test Alert", "This is a test alert from Postfix Outbound Relay Panel.")
    if success:
        return RedirectResponse("/settings?msg=Test+email+sent+successfully", status_code=303)
    else:
        return RedirectResponse("/settings?error=Failed+to+send+test+email+(Check+settings+or+logs)", status_code=303)
