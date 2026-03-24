import sys
with open("debug_output.txt", "w") as f:
    sys.stdout = f
    sys.stderr = f
    
    try:
        sys.path.append(r"d:\mailp\Postfix-Outbound-Relay")
        
        from fastapi.testclient import TestClient
        from app import app
        
        client = TestClient(app)
        
        print("Testing /diagnostics...")
        response = client.get("/diagnostics")
        print(f"Status Code: {response.status_code}")
        if response.status_code != 200:
            print("Response body:")
            print(response.text)
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        
    finally:
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
