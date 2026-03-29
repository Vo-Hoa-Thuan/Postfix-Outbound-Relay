"""
core/system_safe.py - Operational safety for system configuration management.
Provides atomic writes, backups, validation, and safe reloads for Postfix and Rspamd.
"""

import os
import shutil
import subprocess
import datetime
from typing import Tuple, Optional, Callable

# Backup directory within the project
BACKUP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runtime", "backups")

def safe_write_config(path: str, content: str, validation_cmd: Optional[str] = None) -> Tuple[bool, str]:
    """
    Safely writes a configuration file.
    1. Creates a backup of the existing file.
    2. Writes to a temporary file.
    3. (Optional) Validates the temporary file.
    4. Atomically replaces the original file.
    5. Returns (success, message).
    """
    if not os.path.isabs(path):
        return False, f"Path must be absolute: {path}"

    # Ensure backup directory exists
    os.makedirs(BACKUP_DIR, exist_ok=True)

    # 1. Backup
    backup_path = None
    if os.path.exists(path):
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = os.path.basename(path) + f".bak_{timestamp}"
        backup_path = os.path.join(BACKUP_DIR, backup_name)
        try:
            shutil.copy2(path, backup_path)
        except Exception as e:
            return False, f"Failed to create backup: {e}"

    # 2. Write to temp file
    temp_path = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception as e:
        if os.path.exists(temp_path): os.remove(temp_path)
        return False, f"Failed to write temp file: {e}"

    # 3. Validate
    if validation_cmd:
        # Check if validation_cmd needs the temp file path injected
        cmd = validation_cmd.replace("{CHROOT_FILE}", temp_path) if "{CHROOT_FILE}" in validation_cmd else validation_cmd
        
        ok, out = run_command(cmd)
        if not ok:
            if os.path.exists(temp_path): os.remove(temp_path)
            return False, f"Validation failed: {out}"

    # 4. Atomic replace (on Linux)
    try:
        shutil.move(temp_path, path)
        return True, f"Configuration written successfully. Backup: {backup_path}"
    except Exception as e:
        if os.path.exists(temp_path): os.remove(temp_path)
        return False, f"Failed to replace original file: {e}"

def run_command(cmd: str, timeout: int = 15) -> Tuple[bool, str]:
    """Runs a shell command safely."""
    try:
        # Check if we are on Windows (dev mode)
        if os.name == 'nt' and not cmd.startswith("echo"):
            return False, f"Bypassing system command on Windows: {cmd}"

        result = subprocess.run(
            cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=timeout
        )
        out = (result.stdout + result.stderr).strip()
        return result.returncode == 0, out
    except subprocess.TimeoutExpired:
        return False, "Command timed out."
    except Exception as e:
        return False, str(e)

def safe_reload_postfix() -> Tuple[bool, str]:
    """Validate then reload Postfix."""
    ok, out = run_command("postfix check")
    if not ok:
        return False, f"Postfix check failed: {out}"
    
    return run_command("postfix reload")

def safe_reload_rspamd() -> Tuple[bool, str]:
    """Validate then reload Rspamd."""
    ok, out = run_command("rspamadm configtest")
    if not ok:
        return False, f"Rspamd configtest failed: {out}"
    
    # Rspamd can be reloaded via systemctl or rspamadm
    return run_command("systemctl reload rspamd")

def get_local_ips() -> list:
    """Returns a list of all IP addresses assigned to this machine."""
    ok, out = run_command("hostname -I")
    if ok and out:
        return out.split()
    return ["127.0.0.1"]

def is_ip_local(ip: str) -> bool:
    """Checks if the given IP address is assigned to a local interface."""
    if not ip or ip == "127.0.0.1":
        return True
    return ip.strip() in get_local_ips()

def rollback_config(path: str, backup_path: str) -> Tuple[bool, str]:
    """Restores a backup to the original path."""
    try:
        shutil.copy2(backup_path, path)
        return True, f"Rollback successful from {backup_path}"
    except Exception as e:
        return False, f"Rollback failed: {e}"
