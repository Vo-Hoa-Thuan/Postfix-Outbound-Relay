import sys
import asyncio

# Vá lõi cho Python 3.6
if sys.version_info < (3, 7):
    if not hasattr(asyncio, "create_task"):
        asyncio.create_task = asyncio.ensure_future
    if not hasattr(asyncio, "get_running_loop"):
        asyncio.get_running_loop = asyncio.get_event_loop
    if not hasattr(asyncio, "run"):
        def _poly_run(coro):
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(coro)
        asyncio.run = _poly_run

from fastapi import FastAPI
app = FastAPI()

@app.get("/")
def read_root():
    return {"status": "SUCCESS", "message": "FastAPI is NOT broken!"}

if __name__ == "__main__":
    import uvicorn
    # Test thu nhỏ không dính dáng gì tới đống file Code của Panel
    # Nếu chạy script này mà Web xoay vòng -> Lỗi tại thư viện Uvicorn/FastAPI trên Python 3.6
    # Nếu Web hiện chữ SUCCESS -> Lỗi nằm ở 1 dòng Code nào đó của tôi
    uvicorn.run(app, host="0.0.0.0", port=8000)
