"""
core/settings.py - Global settings and alerting functionality.
"""
import os
import smtplib
from email.message import EmailMessage
from core.fileio import read_json, write_json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_SETTINGS = os.path.join(BASE_DIR, "config", "settings.json")

def get_settings():
    default_settings = {
        "mxtoolbox_api_key": "",
        "alert_email": {
            "enabled": False,
            "smtp_host": "127.0.0.1",
            "smtp_port": 25,
            "smtp_user": "",
            "smtp_pass": "",
            "from_email": "alerts@postfix-panel.local",
            "to_email": "vohoathuan.devt@gmail.com"
        }
    }
    return read_json(CONFIG_SETTINGS, default_settings)

def save_settings(data):
    write_json(CONFIG_SETTINGS, data)

def send_alert(subject: str, message: str) -> bool:
    """Send an email alert using the configured SMTP settings."""
    settings = get_settings()
    email_cfg = settings.get("alert_email", {})
    
    if not email_cfg.get("enabled"):
        return False
        
    try:
        msg = EmailMessage()
        msg.set_content(message)
        msg['Subject'] = f"[Postfix Panel Alert] {subject}"
        msg['From'] = email_cfg.get("from_email", "alerts@postfix-panel.local")
        msg['To'] = email_cfg.get("to_email", "vohoathuan.devt@gmail.com")
        
        host = email_cfg.get("smtp_host", "127.0.0.1")
        port = int(email_cfg.get("smtp_port", 25))
        user = email_cfg.get("smtp_user", "")
        password = email_cfg.get("smtp_pass", "")
        
        server = smtplib.SMTP(host, port, timeout=10)
        
        # Try STARTTLS if port is 587 or if an external host is likely used
        try:
            server.starttls()
        except Exception:
            pass # Ignore if not supported
            
        if user and password:
            server.login(user, password)
            
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"Failed to send alert email: {e}")
        return False
