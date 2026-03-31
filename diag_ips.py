import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.system_safe import run_command, get_local_ips
from core.fileio import read_json

def check_ips():
    print("--- SYSTEM IP DIAGNOSTICS ---")
    ok, out = run_command("hostname -I")
    system_ips = out.split() if ok else []
    print(f"System Detected IPs: {system_ips}")
    
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "relay_ips.json")
    config = read_json(config_path, {"ips": []})
    configured_ips = [x["ip"] for x in config.get("ips", [])]
    
    print(f"Configured IPs: {configured_ips}")
    
    missing = []
    for ip in configured_ips:
        if ip not in system_ips:
            missing.append(ip)
            
    if missing:
        print(f"\n[WARNING] The following IPs are configured but NOT found on the system network interfaces:")
        for m in missing:
            print(f" - {m}")
        print("\nPostfix cannot bind to these IPs. It will fall back to the default server IP.")
    else:
        print("\n[SUCCESS] All configured IPs are present on the system.")

    print("\n--- POSTFIX CONFIGURATION ---")
    ok1, bind_addr = run_command("postconf -h smtp_bind_address")
    print(f"Current smtp_bind_address: {bind_addr.strip() or '(empty)'}")
    
    ok2, relay_host = run_command("postconf -h relayhost")
    print(f"Current relayhost: {relay_host.strip() or '(empty)'}")

if __name__ == "__main__":
    check_ips()
