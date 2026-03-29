import subprocess
import os
import sys

print(f"OS name: {os.name}")
print(f"Python version: {sys.version}")

try:
    cmd = "systemctl is-active postfix"
    print(f"Running command: {cmd}")
    
    # Test safe system call
    result = subprocess.run(
        cmd, 
        shell=True, 
        stdout=subprocess.PIPE, 
        stderr=subprocess.PIPE, 
        universal_newlines=True, 
        timeout=15
    )
    
    print(f"Return code: {result.returncode}")
    print(f"STDOUT: '{result.stdout.strip()}'")
    print(f"STDERR: '{result.stderr.strip()}'")
    print("SUCCESS: Subprocess completed without Python exceptions.")

except Exception as e:
    import traceback
    print("FAILED with Exception:")
    traceback.print_exc()
