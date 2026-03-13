"""
core/blacklist.py - Check IP Blacklist status using MXToolbox API.
"""
import urllib.request
import urllib.error
import urllib.parse
import json

from core.settings import get_settings, send_alert

def check_ip_blacklist(ip_address: str) -> dict:
    """
    Checks an IP against MXToolbox Blacklist API.
    Returns a dict with 'is_blacklisted' boolean and 'details' list.
    """
    settings = get_settings()
    api_key = settings.get("mxtoolbox_api_key", "").strip()
    
    if not api_key:
        return {"error": "MXToolbox API Key not configured.", "is_blacklisted": False, "details": []}
        
    url = f"https://api.mxtoolbox.com/api/v1/lookup/blacklist/{urllib.parse.quote(ip_address)}"
    
    req = urllib.request.Request(url, headers={
        "Authorization": api_key,
        "Accept": "application/json"
    })
    
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode())
            
            # Find blacklisted entries
            failed_checks = [
                info for info in data.get("Failed", [])
                if info.get("IsBlacklisted", False)
            ]
            
            is_blacklisted = len(failed_checks) > 0
            
            return {
                "is_blacklisted": is_blacklisted,
                "details": failed_checks
            }
            
    except urllib.error.URLError as e:
        print(f"Failed to check MXToolbox for {ip_address}: {e}")
        return {"error": str(e), "is_blacklisted": False, "details": []}
    except Exception as e:
        print(f"Unexpected error checking MXToolbox for {ip_address}: {e}")
        return {"error": str(e), "is_blacklisted": False, "details": []}

def process_ip_blacklist_alert(ip_address: str):
    """
    Checks an IP, and if it is blacklisted, disables it and sends an email alert.
    Returns True if an action was taken (blacklisted), False otherwise.
    """
    from core.fileio import read_json, write_json
    import os
    
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    RELAY_IPS_FILE = os.path.join(BASE_DIR, "config", "relay_ips.json")
    
    result = check_ip_blacklist(ip_address)
    
    # Always update last check timestamp
    import time
    config = read_json(RELAY_IPS_FILE, {"ips": []})
    modified = False
    for ip_data in config.get("ips", []):
        if ip_data.get("ip") == ip_address:
            ip_data["last_blacklist_check"] = time.time()
            modified = True
            
            if result.get("is_blacklisted"):
                # IP is on a blacklist!
                details = result.get("details", [])
                reasons = ", ".join([d.get("Name", "Unknown") for d in details])
                
                # Disable the IP in configuration
                if ip_data.get("enabled", True):
                    ip_data["enabled"] = False
                    ip_data["note"] = f"(BLACKLISTED on {reasons}) " + ip_data.get("note", "")
                    
                    # Send Alert
                    alert_msg = f"CRITICAL: IP Address {ip_address} has been blacklisted!\n\n" \
                                f"Detected on the following blacklists:\n{reasons}\n\n" \
                                f"Action Taken: The system has automatically DISABLED this IP to protect your sender reputation."
                    send_alert(f"IP {ip_address} BLACKLISTED!", alert_msg)
            break
                
    if modified:
        write_json(RELAY_IPS_FILE, config)
        
    return result.get("is_blacklisted", False)

def auto_check_all():
    """
    Checks all enabled IPs in the background. Should be called periodically.
    """
    from core.fileio import read_json, write_json
    import os
    import time
    
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    RELAY_IPS_FILE = os.path.join(BASE_DIR, "config", "relay_ips.json")
    LAST_CHECK_FILE = os.path.join(BASE_DIR, "runtime", "last_blacklist_check.json")
    
    # Get interval from settings (default 12 hours)
    settings = get_settings()
    interval_hours = settings.get("blacklist_check_interval", 12)
    interval_seconds = interval_hours * 3600
    
    # Check max once every configured interval hours to save API calls
    last_check_data = read_json(LAST_CHECK_FILE, {"last_check": 0})
    now = time.time()
    
    if now - last_check_data.get("last_check", 0) < interval_seconds:
        return
        
    config = read_json(RELAY_IPS_FILE, {"ips": []})
    
    for ip_data in config.get("ips", []):
        if ip_data.get("enabled", True):
            # Check and alert/disable if needed
            process_ip_blacklist_alert(ip_data.get("ip"))
            time.sleep(2) # rate limiting for MXToolbox
            
    write_json(LAST_CHECK_FILE, {"last_check": now})

