import sys, os, asyncio
sys.path.append(r"d:\mailp\Postfix-Outbound-Relay")

from fastapi import Request
from web.routes.diagnostics import diagnostics_home

async def test():
    class DummyRequest:
        def __init__(self):
            self.query_params = {}
            self.cookies = {}
            self.headers = {}
    
    req = DummyRequest()
    try:
        resp = await diagnostics_home(req)
        print("Length of response:", len(resp.body))
    except Exception as e:
        import traceback
        with open("error.txt", "w") as f:
            traceback.print_exc(file=f)

asyncio.run(test())
