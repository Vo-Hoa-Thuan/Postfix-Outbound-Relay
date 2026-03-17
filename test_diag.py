
import os
import sys

# Add current dir to path
sys.path.insert(0, os.getcwd())

try:
    print("Testing Diagnostics imports and core calls...")
    from web.routes.diagnostics import diagnostics_home
    from core.postfix import get_postfix_identity
    from core.tracking import get_queue_status
    
    print("Calling get_queue_status()...")
    q = get_queue_status()
    print(f"Queue: {q}")
    
    print("Calling get_postfix_identity()...")
    ident = get_postfix_identity()
    print(f"Identity: {ident}")
    
    print("Success! No crashes in core logic.")
except Exception as e:
    import traceback
    print("CRASH DETECTED:")
    traceback.print_exc()
