import urllib.request
import urllib.error
import json

urls = ['http://127.0.0.1:8000/', 'http://127.0.0.1:8000/queue', 'http://127.0.0.1:8000/api/status']
for u in urls:
    try:
        resp = urllib.request.urlopen(u)
        print(f"{u} -> {resp.getcode()}")
    except urllib.error.HTTPError as e:
        print(f"{u} -> ERR {e.code} | {e.read().decode('utf-8')[:200]}")
    except Exception as e:
        print(f"{u} -> EXC {str(e)}")
