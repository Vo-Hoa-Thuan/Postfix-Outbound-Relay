"""
web/routes/rotation.py – IP Rotation configuration routes.
"""

import os
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

BASE_DIR  = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

router = APIRouter(prefix="/rotation")

ROTATION_CFG = os.path.join(BASE_DIR, "config", "rotation.json")


@router.get("", response_class=HTMLResponse)
async def show_rotation(request: Request, msg: str = "", error: str = ""):
    from core.fileio   import read_json
    from core.rotation import get_time_remaining
    cfg = read_json(ROTATION_CFG, {"rotation_seconds": 60, "mode": "weighted"})
    return templates.TemplateResponse("rotation.html", {
        "request":       request,
        "rotation_secs": cfg.get("rotation_seconds", 60),
        "mode":          cfg.get("mode", "weighted"),
        "time_remaining": get_time_remaining(),
        "msg":           msg,
        "error":         error,
    })


@router.post("/save")
async def save_rotation(
    rotation_seconds: int = Form(60),
    mode:             str = Form("weighted"),
):
    from core.fileio import write_json
    if rotation_seconds < 10:
        return RedirectResponse("/rotation?error=Minimum+rotation+interval+is+10+seconds", status_code=303)
    if mode not in ("roundrobin", "weighted"):
        mode = "weighted"
    write_json(ROTATION_CFG, {
        "rotation_seconds": rotation_seconds,
        "mode":             mode,
    })
    return RedirectResponse("/rotation?msg=Rotation+settings+saved", status_code=303)


@router.post("/trigger")
async def trigger_rotation(request: Request):
    """Manually force an IP rotation now."""
    from core.rotation import get_time_remaining, log_rotation_event
    
    current_cfg = get_active_ip()
    current_ip  = current_cfg["ip"] if current_cfg else None
    new_ip  = select_next_ip(current_ip=current_ip)
    
    if new_ip and new_ip != current_ip:
        log_rotation_event(current_ip, new_ip, "manually_triggered")
        sync_transport(new_ip)
        # Check if requested via AJAX
        if "application/json" in request.headers.get("accept", ""):
            return {
                "success": True, 
                "new_ip": new_ip, 
                "time_remaining": get_time_remaining(),
                "msg": f"Rotated to {new_ip}"
            }
        return RedirectResponse(f"/rotation?msg=Rotated+to+{new_ip}", status_code=303)
    
    if "application/json" in request.headers.get("accept", ""):
        return {"success": False, "error": "No enabled IPs available"}
    return RedirectResponse("/rotation?error=No+enabled+IPs+available", status_code=303)
@router.get("/history", response_class=HTMLResponse)
async def rotation_history_page(request: Request):
    return templates.TemplateResponse("rotation_history.html", {
        "request": request,
        "active_page": "rotation_history"
    })
