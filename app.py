"""
app.py – Postfix Outbound Relay Panel
FastAPI entry point. Mounts static files, registers all route blueprints,
and initialises default config/runtime files on first run.
"""

import os
import sys
import time
import asyncio

# BẢN VÁ CHO PYTHON 3.6 TRÊN CENTOS CŨ CỦA NGƯỜI DÙNG:
if sys.version_info < (3, 7):
    import asyncio
    if not hasattr(asyncio, "create_task"):
        asyncio.create_task = asyncio.ensure_future
    if not hasattr(asyncio, "get_running_loop"):
        asyncio.get_running_loop = asyncio.get_event_loop
    if not hasattr(asyncio, "current_task"):
        asyncio.current_task = getattr(asyncio.Task, "current_task", None)
    if not hasattr(asyncio, "all_tasks"):
        asyncio.all_tasks = getattr(asyncio.Task, "all_tasks", None)
    if not hasattr(asyncio, "run"):
        def _poly_run(coro):
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(coro)
        asyncio.run = _poly_run

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

# ── Path setup ────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

# ── App init ──────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Postfix Relay Panel",
    description="Outbound SMTP relay management UI",
    version="1.0.0",
    docs_url=None,   # hide Swagger in production
    redoc_url=None,
)

# ── Static files ──────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# ── Route routers ─────────────────────────────────────────────────────────────
from web.routes.dashboard import router as dashboard_router
from web.routes.ips       import router as ips_router
from web.routes.rotation  import router as rotation_router
from web.routes.rspamd    import router as rspamd_router
from web.routes.settings  import router as settings_router
from web.routes.diagnostics import router as diagnostics_router
from web.routes.auth      import router as auth_router

from fastapi import Depends
from core.auth import do_auth
auth_dep = [Depends(do_auth)]

app.include_router(auth_router) # Không cần check session
app.include_router(dashboard_router, dependencies=auth_dep)
app.include_router(ips_router, dependencies=auth_dep)
app.include_router(rotation_router, dependencies=auth_dep)
app.include_router(rspamd_router, dependencies=auth_dep)
app.include_router(settings_router, dependencies=auth_dep)
app.include_router(diagnostics_router, dependencies=auth_dep)


import asyncio

async def _background_tasks():
    from core.rotation import rotate_if_needed
    from core.postfix import sync_transport
    from core.blacklist import auto_check_all
    from logs.reader import parse_maillog, pre_aggregate_chart
    
    print("[RelayPanel] Started background operations worker.")
    
    # Track last run times for different intervals
    last_chart_agg = 0
    last_log_parse = 0
    
    while True:
        try:
            loop = asyncio.get_event_loop()
            now = time.time()
            
            # 1. IP Rotation (Every check, has internal logic) - Thread-safe because it writes files
            rotated, new_ip = await loop.run_in_executor(None, rotate_if_needed)
            if rotated and new_ip:
                print(f"[RelayPanel] Auto-rotated to IP: {new_ip}")
                # sync_transport reloads postfix, which is slow - run in executor
                await loop.run_in_executor(None, sync_transport, new_ip)
                
            # 2. Blacklist Check (Has internal throttling/interval) - VERY SLOW
            await loop.run_in_executor(None, auto_check_all)

            # 3. Incremental Log Monitoring (Every 3 seconds)
            if now - last_log_parse > 3:
                await loop.run_in_executor(None, parse_maillog, 5000)
                last_log_parse = now
                
            # 4. Chart Pre-Aggregation (Every 60 seconds)
            if now - last_chart_agg > 60:
                await loop.run_in_executor(None, pre_aggregate_chart)
                last_chart_agg = now
            
        except Exception as e:
            print(f"[RelayPanel] Background worker error: {e}")
            
        await asyncio.sleep(5)


# ── Startup: ensure default config & runtime files exist ─────────────────────
@app.on_event("startup")
async def _init_defaults():
    from core.fileio import ensure_json

    from core.auth import hash_password

    defaults = {
        os.path.join(BASE_DIR, "config", "relay_ips.json"):  {"ips": []},
        os.path.join(BASE_DIR, "config", "rotation.json"):   {"rotation_seconds": 60, "mode": "weighted"},
        os.path.join(BASE_DIR, "config", "rspamd.json"): {
            "enable": True, "required_score": 6.0, "greylist": True,
            "rate_limit": {"enable": True, "burst": 100, "rate": "50 / 1min"},
            "whitelist_ips": [], "blacklist_domains": []
        },
        os.path.join(BASE_DIR, "config", "limits.json"):     {},
        os.path.join(BASE_DIR, "config", "admin.json"):      {"username": "admin", "password_hash": hash_password("sieutocviet")},
        os.path.join(BASE_DIR, "runtime", "ip_state.json"):  {"active_ip": None, "last_rotated": 0},
        os.path.join(BASE_DIR, "runtime", "counters.json"):  {},
    }

    for path, default in defaults.items():
        ensure_json(path, default)

    # Lọc migration cho admin.json từ plaintext lên Hash
    admin_path = os.path.join(BASE_DIR, "config", "admin.json")
    from core.fileio import read_json, write_json
    admin_cfg = read_json(admin_path, {})
    if "password" in admin_cfg:
        pw = admin_cfg.pop("password")
        if "password_hash" not in admin_cfg:
            # Nếu người dùng đã cài pass cũ, giữ pass đó nhưng mã hoá. Chỗ này sẽ chuyển mật khẩu cũ thành mã hoá.
            # Nhờ user yêu cầu đổi pass thành sieutocviet, ta ưu tiên ghi đè:
            admin_cfg["password_hash"] = hash_password("sieutocviet")
        write_json(admin_path, admin_cfg)

    # Ensure logs/parsed.log exists
    parsed_log = os.path.join(BASE_DIR, "logs", "parsed.log")
    rotation_log = os.path.join(BASE_DIR, "logs", "rotation.log")
    for log_path in [parsed_log, rotation_log]:
        if not os.path.exists(log_path):
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            open(log_path, "w").close()

    print("[RelayPanel] Startup complete - all config files verified.")
    loop = asyncio.get_event_loop()
    loop.create_task(_background_tasks())



# ── Run directly ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    import sys
    
    # Xử lý Lỗi thư viện Uvicorn gọi asyncio.run() không tồn tại trên Python 3.6
    if sys.version_info < (3, 7):
        import asyncio
        config = uvicorn.Config("app:app", host="0.0.0.0", port=8000, reload=False)
        server = uvicorn.Server(config)
        loop = asyncio.get_event_loop()
        loop.run_until_complete(server.serve())
    else:
        uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
