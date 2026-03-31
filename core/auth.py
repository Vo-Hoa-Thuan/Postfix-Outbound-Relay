import os
import time
import hashlib
import binascii
from fastapi import Request, HTTPException, status

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADMIN_FILE = os.path.join(BASE_DIR, "config", "admin.json")

# Fallback import in case
try:
    from core.fileio import read_json
except ImportError:
    import json
    def read_json(path, default=None):
        if not os.path.exists(path): return default
        with open(path, "r") as f:
            try: return json.load(f)
            except: return default

def hash_password(password: str) -> str:
    """Mã hoá mật khẩu một chiều để ngăn lộ khi mất file (tuỳ mỗi máy tự sinh mã rác)"""
    salt = hashlib.sha256(os.urandom(60)).hexdigest().encode('ascii')
    pwdhash = hashlib.pbkdf2_hmac('sha512', password.encode('utf-8'), salt, 100000)
    pwdhash = binascii.hexlify(pwdhash)
    return (salt + pwdhash).decode('ascii')

def verify_password(stored_password: str, provided_password: str) -> bool:
    """So sánh mật khẩu người dùng gõ vào với mật khẩu trong file đã bị băm"""
    if len(stored_password) < 64: return False # Fake hash defense
    salt = stored_password[:64].encode('ascii')
    stored_hash = stored_password[64:]
    pwdhash = hashlib.pbkdf2_hmac('sha512', provided_password.encode('utf-8'), salt, 100000)
    pwdhash = binascii.hexlify(pwdhash).decode('ascii')
    return pwdhash == stored_hash

def _get_user_session_token(username: str, pwd_hash: str) -> str:
    """Tạo token phiên dựa trên username, password hash và ngày hiện tại."""
    today = time.strftime("%Y-%m-%d")
    raw = f"{username}:{pwd_hash}:{today}"
    return hashlib.sha256(raw.encode()).hexdigest()

def do_auth(request: Request):
    """
    Xác thực phiên của bất kỳ tài khoản người dùng nào hiện có.
    """
    from core.users import get_users
    session = request.cookies.get("session_token")
    if not session:
        if request.url.path.startswith("/api/"):
            raise HTTPException(status_code=401, detail="Not authenticated")
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    
    # Kiểm tra session có khớp với bất kỳ người dùng nào không
    users = get_users()
    for username, info in users.items():
        if session == _get_user_session_token(username, info.get("password_hash", "")):
            return username
            
    # Nếu không khớp ai
    if request.url.path.startswith("/api/"):
        raise HTTPException(status_code=401, detail="Invalid session")
    raise HTTPException(status_code=303, headers={"Location": "/login"})
