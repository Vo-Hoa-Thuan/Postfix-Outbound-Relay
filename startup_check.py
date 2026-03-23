import os
import sys

log_file = "diag_results.txt"

def log(msg):
    with open(log_file, "a") as f:
        f.write(msg + "\n")
    print(msg)

if os.path.exists(log_file): os.remove(log_file)

log("Step 1: Importing core.fileio")
try:
    from core.fileio import read_json, write_json, ensure_json
    log("OK")
except Exception as e:
    log(f"FAIL: {e}")

log("Step 2: Importing logs.reader")
try:
    import logs.reader
    log("OK")
except Exception as e:
    import traceback
    with open(log_file, "a") as f:
        traceback.print_exc(file=f)
    log(f"FAIL: {e}")

log("Step 3: Importing web.routes.dashboard")
try:
    from web.routes.dashboard import router
    log("OK")
except Exception as e:
    import traceback
    with open(log_file, "a") as f:
        traceback.print_exc(file=f)
    log(f"FAIL: {e}")

log("Step 4: Importing app")
try:
    import app
    log("OK")
except Exception as e:
    import traceback
    with open(log_file, "a") as f:
        traceback.print_exc(file=f)
    log(f"FAIL: {e}")

log("All steps completed")
