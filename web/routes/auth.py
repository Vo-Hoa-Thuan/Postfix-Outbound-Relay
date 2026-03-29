import os
import secrets
import hashlib
import time
from fastapi import APIRouter, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from core.fileio import read_json
from core.auth import verify_password

BASE_DIR  = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
ADMIN_FILE = os.path.join(BASE_DIR, "config", "admin.json")

router = APIRouter()

def _generate_session_token(username: str, password_hash: str) -> str:
    """Tạo một chuỗi xác thực tĩnh nhẹ gắn với password giúp session chết khi đổi mk."""
    today = time.strftime("%Y-%m-%d") # Thay đổi token mỗi ngày
    raw = f"{username}:{password_hash}:{today}"
    return hashlib.sha256(raw.encode()).hexdigest()

@router.get("/login", response_class=HTMLResponse)
async def view_login(request: Request, error: str = ""):
    return templates.TemplateResponse("login.html", {"request": request, "error": error})

@router.post("/login")
async def do_login(
    response: Response,
    username: str = Form(...),
    password: str = Form(...)
):
    cfg = read_json(ADMIN_FILE, {"username": "admin", "password_hash": "empty"})
    correct_user = cfg.get("username", "admin").encode("utf8")
    
    is_user_ok = secrets.compare_digest(username.encode("utf8"), correct_user)
    is_pass_ok = verify_password(cfg.get("password_hash", ""), password)

    if not (is_user_ok and is_pass_ok):
        url = "/login?error=Invalid+username+or+password"
        return RedirectResponse(url, status_code=303)
        
    # Tạo session cookie
    token = _generate_session_token(cfg.get("username", "admin"), cfg.get("password_hash", "empty"))
    
    redirect_resp = RedirectResponse("/", status_code=303)
    redirect_resp.set_cookie(key="session_token", value=token, httponly=True, max_age=86400)
    return redirect_resp

@router.get("/logout")
async def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie("session_token")
    return resp
