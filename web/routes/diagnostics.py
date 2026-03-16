"""
web/routes/diagnostics.py – SMTP Test tool and Log Tracking.
"""
import os
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from typing import Optional

from core.test_mail import send_test_email
from core.tracking import get_message_history, get_queue_status, flush_queue

BASE_DIR  = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

router = APIRouter(prefix="/diagnostics")

@router.get("", response_class=HTMLResponse)
async def diagnostics_home(request: Request, msg: str = "", error: str = ""):
    queue = get_queue_status()
    return templates.TemplateResponse("diagnostics.html", {
        "request": request,
        "queue": queue,
        "msg": msg,
        "error": error
    })

@router.post("/send-test")
async def send_test(
    recipient: str = Form(...),
    sender:    str = Form("test@relay.local"),
    subject:   str = Form("SMTP Relay Test")
):
    result = send_test_email(recipient, sender, subject)
    if result["success"]:
        return RedirectResponse(f"/diagnostics?msg={result['message']}&msg_id={result['msg_id']}", status_code=303)
    else:
        return RedirectResponse(f"/diagnostics?error={result['message']}", status_code=303)

@router.get("/trace/{msg_id}")
async def trace_message(msg_id: str):
    history = get_message_history(msg_id)
    return JSONResponse(history)

@router.post("/queue/flush")
async def queue_flush():
    if flush_queue():
        return RedirectResponse("/diagnostics?msg=Queue+flushed+successfully", status_code=303)
    return RedirectResponse("/diagnostics?error=Failed+to+flush+queue", status_code=303)
