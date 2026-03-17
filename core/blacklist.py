"""
core/blacklist.py - Check IP Blacklist status using MXToolbox API with 24h caching.
"""
import urllib.request
import urllib.error
import urllib.parse
import json
import time
import os
from typing import Dict, Any, List

from core.settings import get_settings, send_alert
from core.fileio import read_json, write_json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_FILE = os.path.join(BASE_DIR, "runtime", "blacklist_cache.json")
RELAY_IPS_FILE = os.path.join(BASE_DIR, "config", "relay_ips.json")

def check_ip_blacklist(ip_address: str, force_refresh: bool = False) -> Dict[str, Any]:
    """
    Checks an IP against MXToolbox Blacklist API with 24h caching.
    Returns normalized status: CLEAN, BLACKLISTED, ERROR, CACHED.
    """
    now = time.time()
    cache = read_json(CACHE_FILE, {})
    
    # Check cache (24 hours = 86400 seconds)
    cached_result = cache.get(ip_address)
    if not force_refresh and cached_result:
        cache_age = now - cached_result.get("checked_at", 0)
        if cache_age < 86400:
            cached_result["status"] = "CACHED"
            cached_result["cache_age_seconds"] = int(cache_age)
            return cached_result

    # Real check logic
    settings = get_settings()
    api_key = settings.get("mxtoolbox_api_key", "").strip()
    
    if not api_key:
        return {
            "ip": ip_address,
            "status": "ERROR",
            "error": "MXToolbox API Key not configured.",
            "is_blacklisted": False,
            "blacklists": [],
            "checked_at": now
        }
        
    url = f"https://api.mxtoolbox.com/api/v1/lookup/blacklist/{urllib.parse.quote(ip_address)}"
    
    req = urllib.request.Request(url, headers={
        "Authorization": api_key,
        "Accept": "application/json"
    })
    
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode())
            
            failed_checks = [
                info.get("Name", "Unknown") for info in data.get("Failed", [])
                if info.get("IsBlacklisted", False)
            ]
            
            is_blacklisted = len(failed_checks) > 0
            
            result = {
                "ip": ip_address,
                "status": "BLACKLISTED" if is_blacklisted else "CLEAN",
                "is_blacklisted": is_blacklisted,
                "blacklists": failed_checks,
                "checked_at": now,
                "source": "MXToolbox"
            }
            
            # Update cache
            cache[ip_address] = result
            write_json(CACHE_FILE, cache)
            
            return result
            
    except urllib.error.HTTPError as e:
        if e.code == 403: error_msg = "API Key Invalid or Quota Exceeded (403)"
        elif e.code == 429: error_msg = "Rate limit exceeded (429)"
        else: error_msg = f"HTTP Error {e.code}"
    except urllib.error.URLError as e:
        error_msg = f"Network Error: {e.reason}"
    except Exception as e:
        error_msg = f"Unexpected Error: {str(e)}"

    # If error occurred, return whatever we have in cache if it exists, otherwise return error
    if cached_result:
        cached_result["status"] = "CACHED (STALE)"
        cached_result["error_note"] = error_msg
        return cached_result
        
    return {
        "ip": ip_address,
        "status": "ERROR",
        "error": error_msg,
        "is_blacklisted": False,
        "blacklists": [],
        "checked_at": now
    }

def process_ip_blacklist_alert(ip_address: str, force_refresh: bool = False):
    """
    Checks an IP and automates disabling/alerting.
    """
    result = check_ip_blacklist(ip_address, force_refresh=force_refresh)
    
    # Update relay_ips.json with latest check info
    config = read_json(RELAY_IPS_FILE, {"ips": []})
    modified = False
    
    for ip_data in config.get("ips", []):
        if ip_data.get("ip") == ip_address:
            ip_data["last_blacklist_check"] = result.get("checked_at")
            ip_data["blacklist_status"] = result.get("status")
            modified = True
            
            if result.get("is_blacklisted"):
                reasons = ", ".join(result.get("blacklists", []))
                
                if ip_data.get("enabled", True):
                    ip_data["enabled"] = False
                    ip_data["note"] = f"(BLACKLISTED on {reasons}) " + ip_data.get("note", "")
                    
                    alert_msg = f"CRITICAL: IP {ip_address} BLACKLISTED!\n\n" \
                                f"Lists: {reasons}\n" \
                                f"Action: System has automatically DISABLED this IP."
                    send_alert(f"IP {ip_address} BLACKLISTED!", alert_msg)
            break
                
    if modified:
        write_json(RELAY_IPS_FILE, config)
        
    return result

def auto_check_all():
    """Background loop entry point - optimized to be faster and non-blocking."""
    settings = get_settings()
    # Support intervals from 1m to 24h
    interval_hours = settings.get("blacklist_check_interval", 6)
    
    LAST_CHECK_FILE = os.path.join(BASE_DIR, "runtime", "last_auto_check.json")
    last_check_data = read_json(LAST_CHECK_FILE, {"last_check": 0, "status": "idle"})
    
    now = time.time()
    if now - last_check_data.get("last_check", 0) < (interval_hours * 3600):
        return
        
    print(f"[Blacklist] Starting scheduled check (Interval: {interval_hours}h)...")
    last_check_data["status"] = "running"
    last_check_data["start_at"] = now
    write_json(LAST_CHECK_FILE, last_check_data)
    
    config = read_json(RELAY_IPS_FILE, {"ips": []})
    blacklisted_count = 0
    checked_count = 0
    
    for ip_data in config.get("ips", []):
        ip = ip_data.get("ip")
        if ip_data.get("enabled", True) or ip_data.get("blacklist_status") == "BLACKLISTED":
            res = process_ip_blacklist_alert(ip)
            checked_count += 1
            if res.get("is_blacklisted"):
                blacklisted_count += 1
            time.sleep(1) # Small delay
            
    summary = {
        "last_check": time.time(),
        "status": "completed",
        "checked": checked_count,
        "blacklisted": blacklisted_count,
        "took_seconds": int(time.time() - now)
    }
    write_json(LAST_CHECK_FILE, summary)
    print(f"[Blacklist] Check completed. Found {blacklisted_count} issues.")

