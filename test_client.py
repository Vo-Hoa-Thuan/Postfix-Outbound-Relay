import sys
sys.path.append(r"d:\mailp\Postfix-Outbound-Relay")
from fastapi.testclient import TestClient
from app import app
import traceback

client = TestClient(app)

try:
    response = client.get("/diagnostics")
    print(f"Status Code: {response.status_code}")
    if response.status_code != 200:
        print("Response body:")
        print(response.text)
except Exception as e:
    print("Caught Exception:")
    traceback.print_exc()
