import sys
import os
import time

# Ensure we can import core modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.system_safe import run_command, get_local_ips
from core.fileio import read_json

def get_postfix_bind():
    ok, out = run_command("postconf -h smtp_bind_address")
    return out.strip() if ok else "unknown"

def main():
    print("="*60)
    print(" POSTFIX OUTBOUND RELAY - IP HEALTH CHECK ")
    print("="*60)
    
    # 1. Detect System IPs
    system_ips = get_local_ips()
    print("[*] IPs detected on this VPS: {}".format(', '.join(system_ips)))
    
    # 2. Read Configured IPs
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "relay_ips.json")
    config = read_json(config_path, {"ips": []})
    ips = config.get("ips", [])
    
    total = len(ips)
    enabled = len([x for x in ips if x.get("enabled", True)])
    
    print("[*] Configured IPs in Panel: {} total ({} enabled)".format(total, enabled))
    
    # 3. Validation
    print("\n[ Verification Details ]")
    print("-" * 30)
    
    errors = 0
    for item in ips:
        ip = item["ip"]
        is_enabled = item.get("enabled", True)
        status = "ENABLED" if is_enabled else "DISABLED"
        
        if ip in system_ips:
            print("  [OK]  {:<15} | Status: {:<8} | Found on interface".format(ip, status))
        else:
            if is_enabled:
                print("  [!!]  {:<15} | Status: {:<8} | NOT FOUND ON VPS card!".format(ip, status))
                errors += 1
            else:
                print("  [--]  {:<15} | Status: {:<8} | Not on card (but disabled)".format(ip, status))

    # 4. Postfix Status
    print("\n[ Postfix Current State ]")
    print("-" * 30)
    current_bind = get_postfix_bind()
    print("  Current smtp_bind_address: {}".format(current_bind or '(None - Using default IP)'))
    
    if current_bind and current_bind not in system_ips:
        print("  [WARNING] Postfix is currently trying to bind to an IP NOT on this server!")

    # 5. Summary
    print("\n" + "="*60)
    if errors > 0:
        print(" RESULT: {} IP(s) are configured but missing from the VPS network card.".format(errors))
        print(" ACTION: Please run 'ip addr add <IP>/24 dev eth0' (or equivalent) for each missing IP.")
    else:
        print(" RESULT: All enabled IPs are correctly assigned to the VPS.")
        print(" Logic seems okay. If it still doesn't rotate, check Postfix logs.")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
