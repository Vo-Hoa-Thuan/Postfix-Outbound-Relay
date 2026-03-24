import urllib.request
import urllib.error

url = "http://127.0.0.1:8000/diagnostics"
try:
    req = urllib.request.Request(url)
    resp = urllib.request.urlopen(req)
    print("SUCCESS", resp.status)
except urllib.error.HTTPError as e:
    with open("debug_output.html", "w") as f:
        f.write(e.read().decode())
        print("Captured 500 error to debug_output.html")
except Exception as e:
    with open("debug_output.txt", "w") as f:
        f.write(str(e))
        print("Captured connection error to debug_output.txt")
