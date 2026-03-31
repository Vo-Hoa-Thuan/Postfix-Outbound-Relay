import os
import time
import hashlib
import binascii
from core.fileio import read_json, write_json, ensure_json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USERS_FILE = os.path.join(BASE_DIR, "config", "users.json")

def hash_password(password: str) -> str:
    """Mã hoá mật khẩu pbkdf2_hmac để bảo mật tối đa."""
    salt = hashlib.sha256(os.urandom(60)).hexdigest().encode('ascii')
    pwdhash = hashlib.pbkdf2_hmac('sha512', password.encode('utf-8'), salt, 100000)
    pwdhash = binascii.hexlify(pwdhash)
    return (salt + pwdhash).decode('ascii')

def verify_password(stored_password: str, provided_password: str) -> bool:
    """Xác thực mật khẩu đã hash."""
    if not stored_password or len(stored_password) < 64: return False
    salt = stored_password[:64].encode('ascii')
    stored_hash = stored_password[64:]
    pwdhash = hashlib.pbkdf2_hmac('sha512', provided_password.encode('utf-8'), salt, 100000)
    pwdhash = binascii.hexlify(pwdhash).decode('ascii')
    return pwdhash == stored_hash

def get_users() -> dict:
    """Lấy danh sách người dùng từ config/users.json."""
    return read_json(USERS_FILE, {"users": {}}).get("users", {})

def save_users(users: dict) -> None:
    """Lưu danh sách người dùng mới."""
    write_json(USERS_FILE, {"users": users})

def add_user(username: str, password: str, role: str = "admin") -> bool:
    """Thêm người dùng mới."""
    users = get_users()
    if username in users: return False
    users[username] = {
        "password_hash": hash_password(password),
        "role": role,
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    save_users(users)
    return True

def delete_user(username: str) -> bool:
    """Xoá người dùng (không được xoá tài khoản admin mặc định nếu chỉ còn 1 người)."""
    users = get_users()
    if username not in users: return False
    if len(users) <= 1: return False # Phải giữ ít nhất 1 user
    del users[username]
    save_users(users)
    return True

def change_password(username: str, new_password: str) -> bool:
    """Đổi mật khẩu cho người dùng."""
    users = get_users()
    if username not in users: return False
    users[username]["password_hash"] = hash_password(new_password)
    save_users(users)
    return True
