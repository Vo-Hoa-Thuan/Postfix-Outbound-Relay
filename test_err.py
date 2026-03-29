import traceback
try:
    import app
    print("SUCCESS")
except Exception as e:
    traceback.print_exc()
