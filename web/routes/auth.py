import os
import secrets
import hashlib
import time
from fastapi import APIRouter, Request, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from core.fileio import read_json
from core.users import get_users, verify_password
from core.auth import _get_user_session_token

BASE_DIR  = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

router = APIRouter()

@router.get("/login", response_class=HTMLResponse)
async def view_login(request: Request, error: str = ""):
    return templates.TemplateResponse("login.html", {"request": request, "error": error})

@router.post("/login")
async def do_login(
    response: Response,
    username: str = Form(...),
    password: str = Form(...)
):
    users = get_users()
    
    if username not in users:
        url = "/login?error=Invalid+username+or+password"
        return RedirectResponse(url, status_code=303)
        
    info = users[username]
    is_pass_ok = verify_password(info.get("password_hash", ""), password)

    if not is_pass_ok:
        url = "/login?error=Invalid+username+or+password"
        return RedirectResponse(url, status_code=303)
        
    # Tạo session cookie gán với user này
    token = _get_user_session_token(username, info.get("password_hash"))
    
    redirect_resp = RedirectResponse("/", status_code=303)
    redirect_resp.set_cookie(key="session_token", value=token, httponly=True, max_age=86400)
    return redirect_resp

@router.get("/logout")
async def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie("session_token")
    return resp
