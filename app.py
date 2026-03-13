"""
app.py – Postfix Outbound Relay Panel
FastAPI entry point. Mounts static files, registers all route blueprints,
and initialises default config/runtime files on first run.
"""

import os
import sys

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
from web.routes.logs      import router as logs_router
from web.routes.settings  import router as settings_router

app.include_router(dashboard_router)
app.include_router(ips_router)
app.include_router(rotation_router)
app.include_router(rspamd_router)
app.include_router(logs_router)
app.include_router(settings_router)


import asyncio

async def _rotation_loop():
    from core.rotation import rotate_if_needed
    from core.postfix import sync_transport
    from core.blacklist import auto_check_all
    
    print("[RelayPanel] Started background IP rotation loop.")
    while True:
        try:
            rotated, new_ip = rotate_if_needed()
            if rotated and new_ip:
                print(f"[RelayPanel] Auto-rotated to IP: {new_ip}")
                sync_transport(new_ip)
                
            # Periodic background checks (the function itself throttles to 12h)
            auto_check_all()
            
        except Exception as e:
            print(f"[RelayPanel] Rotation loop error: {e}")
        await asyncio.sleep(5)


# ── Startup: ensure default config & runtime files exist ─────────────────────
@app.on_event("startup")
async def _init_defaults():
    from core.fileio import ensure_json

    defaults = {
        os.path.join(BASE_DIR, "config", "relay_ips.json"):  {"ips": []},
        os.path.join(BASE_DIR, "config", "rotation.json"):   {"rotation_seconds": 60, "mode": "weighted"},
        os.path.join(BASE_DIR, "config", "rspamd.json"): {
            "enable": True, "required_score": 6.0, "greylist": True,
            "rate_limit": {"enable": True, "burst": 100, "rate": "50 / 1min"},
            "whitelist_ips": [], "blacklist_domains": []
        },
        os.path.join(BASE_DIR, "config", "limits.json"):     {},
        os.path.join(BASE_DIR, "runtime", "ip_state.json"):  {"active_ip": None, "last_rotated": 0},
        os.path.join(BASE_DIR, "runtime", "counters.json"):  {},
    }

    for path, default in defaults.items():
        ensure_json(path, default)

    # Ensure logs/parsed.log exists
    parsed_log = os.path.join(BASE_DIR, "logs", "parsed.log")
    if not os.path.exists(parsed_log):
        os.makedirs(os.path.dirname(parsed_log), exist_ok=True)
        open(parsed_log, "w").close()

    print("[RelayPanel] Startup complete - all config files verified.")
    asyncio.create_task(_rotation_loop())



# ── Run directly ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
