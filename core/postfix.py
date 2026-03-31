"""
core/postfix.py – Postfix service management and smtp_bind_address sync.

IP Rotation strategy:
  We set `smtp_bind_address` in /etc/postfix/main.cf so Postfix sends mail
  directly to recipients (MX lookup) using the chosen IP as the SOURCE address.
  This is the correct method for multi-IP outbound relay.

  The transport map approach (routing mail *through* the IP) caused a relay
  loop and is NOT used here.
"""

import os
import subprocess
from typing import Tuple, Dict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MAIN_CF = "/etc/postfix/main.cf"


def get_status() -> str:
    """Return 'running' | 'stopped' | 'unknown'."""
    return _service_status("postfix")


def reload_postfix() -> Tuple[bool, str]:
    """Reload Postfix configuration without dropping connections."""
    ok, out = _run("postfix reload")
    if ok:
        return True, "Postfix reloaded successfully."
    return False, f"Reload failed: {out}"


def sync_transport(active_ip: str) -> Tuple[bool, str]:
    """
    If the active IP has smtp_user/smtp_pass: Configure Postfix as Smarthost.
    Otherwise: Set smtp_bind_address locally.
    """
    from core.rotation import log_rotation_event
    if not active_ip:
        return False, "No active IP provided."

    from core.fileio import read_json
    config = read_json(os.path.join(BASE_DIR, "config", "relay_ips.json"), {"ips": []})
    ip_cfg = next((x for x in config.get("ips", []) if x["ip"] == active_ip), None)
    
    if not ip_cfg:
        return False, f"IP {active_ip} not found in config."

    smtp_user = ip_cfg.get("smtp_user", "").strip()
    smtp_pass = ip_cfg.get("smtp_pass", "").strip()

    try:
        if smtp_user and smtp_pass:
            # --- SASL Smarthost Mode ---
            _run("postconf -e 'smtp_bind_address='")  # clear local bind
            _run(f"postconf -e 'relayhost=[{active_ip}]:587'") # or 25/465 depending on requirement, defaults to 587
            _run("postconf -e 'smtp_sasl_auth_enable=yes'")
            _run("postconf -e 'smtp_sasl_password_maps=hash:/etc/postfix/sasl_passwd'")
            _run("postconf -e 'smtp_sasl_security_options=noanonymous'")
            _run("postconf -e 'smtp_tls_security_level=may'")

            sasl_content = f"[{active_ip}]:587 {smtp_user}:{smtp_pass}\n"
            _write_if_possible("/etc/postfix/sasl_passwd", sasl_content)
            
            # Hash the passwd file
            ok, out = _run("postmap /etc/postfix/sasl_passwd")
            if not ok:
                return False, f"postmap failed: {out}"
                
            msg = f"SASL Auth enabled for smarthost [{active_ip}] and Postfix reloaded."
        else:
            # --- Local Bind Mode ---
            from core.system_safe import is_ip_local
            if not is_ip_local(active_ip):
                msg = f"IP {active_ip} is NOT assigned to this VPS. Binding failed for safety."
                log_rotation_event(None, active_ip, f"ERROR: {msg}")
                return False, msg

            _run(f"postconf -e 'smtp_bind_address={active_ip}'")
            _run("postconf -e 'relayhost='") # clear smarthost
            _run("postconf -e 'smtp_sasl_auth_enable=no'")
            
            msg = f"smtp_bind_address set to {active_ip} and Postfix reloaded."

        # Clear any stale transport_maps to avoid relay loops
        _run("postconf -e 'transport_maps='")

        # Reload Postfix to apply
        ok2, out2 = _run("postfix reload")
        if not ok2:
            msg = f"Postfix reload failed: {out2}"
            log_rotation_event(None, active_ip, f"ERROR: {msg}")
            return False, msg

        log_rotation_event(None, active_ip, f"SUCCESS: {msg}")
        return True, msg
    except Exception as e:
        log_rotation_event(None, active_ip, f"CRITICAL: {str(e)}")
        return False, str(e)


from core.system_safe import run_command, safe_reload_postfix

def get_postfix_limits() -> Dict[str, str]:
    """Read current Postfix limits using postconf."""
    limits = {
        "smtpd_recipient_limit": "1000",
        "message_size_limit": "10240000",
        "default_destination_concurrency_limit": "20",
        "default_destination_recipient_limit": "50"
    }
    for key in limits.keys():
        ok, out = run_command(f"postconf -h {key}")
        if ok and out:
            limits[key] = out.strip()
    return limits

def apply_postfix_limits(limits: Dict[str, str]) -> Tuple[bool, str]:
    """Apply Postfix limits using postconf -e."""
    try:
        for key, val in limits.items():
            run_command(f"postconf -e '{key}={val}'")
        
        ok, out = safe_reload_postfix()
        if not ok:
            return False, f"Failed to reload Postfix: {out}"
        return True, "Postfix limits updated and service reloaded."
    except Exception as e:
        return False, str(e)


def get_postfix_identity() -> Dict[str, str]:
    """Read myhostname and mydomain from Postfix."""
    identity = {"myhostname": "localhost", "mydomain": "local"}
    for key in identity.keys():
        ok, out = run_command(f"postconf -h {key}")
        if ok and out:
            identity[key] = out.strip()
    return identity

def apply_postfix_identity(hostname: str, domain: str) -> Tuple[bool, str]:
    """Apply myhostname and mydomain to Postfix."""
    try:
        if hostname: run_command(f"postconf -e 'myhostname={hostname}'")
        if domain:   run_command(f"postconf -e 'mydomain={domain}'")
        
        ok, out = safe_reload_postfix()
        if not ok:
            return False, f"Failed to reload Postfix: {out}"
        return True, "Postfix identity updated and service reloaded."
    except Exception as e:
        return False, str(e)


def get_mynetworks() -> str:
    """Read current mynetworks from Postfix."""
    ok, out = run_command("postconf -h mynetworks")
    if ok and out:
        return out.strip()
    return "127.0.0.0/8"

def apply_mynetworks(networks_str: str) -> Tuple[bool, str]:
    """Apply mynetworks to Postfix."""
    try:
        # Basic validation: ensure 127.0.0.0/8 is always included for safety
        if "127.0.0.0/8" not in networks_str:
            networks_str = "127.0.0.0/8 " + networks_str
            
        run_command(f"postconf -e 'mynetworks={networks_str.strip()}'")
        
        ok, out = safe_reload_postfix()
        if not ok:
            return False, f"Failed to reload Postfix: {out}"
        return True, "Trusted Relay IPs updated and service reloaded."
    except Exception as e:
        return False, str(e)


def apply_postfix_settings_batch(identity: Dict[str, str], networks: str, limits: Dict[str, str]) -> Tuple[bool, str]:
    """Apply all settings at once and reload once for performance."""
    try:
        # Atomic gathering of commands
        cmds = []
        if identity.get("myhostname"): cmds.append(f"postconf -e 'myhostname={identity['myhostname']}'")
        if identity.get("mydomain"):   cmds.append(f"postconf -e 'mydomain={identity['mydomain']}'")
        
        # Networks
        if networks:
            if "127.0.0.0/8" not in networks: networks = "127.0.0.0/8 " + networks
            cmds.append(f"postconf -e 'mynetworks={networks.strip()}'")
            
        # Limits
        for key, val in limits.items():
            cmds.append(f"postconf -e '{key}={val}'")
            
        # Execute all postconf commands (silent, we check final reload)
        for cmd in cmds:
            run_command(cmd)
            
        # Single reload
        ok, out = safe_reload_postfix()
        if not ok:
            return False, f"Postfix update failed during reload: {out}"
        return True, "All Postfix settings applied successfully."
    except Exception as e:
        return False, str(e)


# ── Internal helpers ─────────────────────────────────────────────────────────

def _run(cmd: str) -> Tuple[bool, str]:
    """Internal runner using system_safe helper."""
    return run_command(cmd)


def _service_status(service: str) -> str:
    ok, out = run_command(f"systemctl is-active {service}")
    if ok and out.strip() == "active":
        return "running"
    return "stopped"


def _write_if_possible(path: str, content: str) -> None:
    if not path.startswith("/"):
        return  # skip on Windows dev
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
