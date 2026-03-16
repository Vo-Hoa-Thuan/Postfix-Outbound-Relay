"""
core/test_mail.py – Send test emails via local Postfix for verification.
"""
import smtplib
import time
import uuid
from email.message import EmailMessage
from typing import Tuple, Dict, Any

def send_test_email(to_email: str, from_email: str = "test@relay.local", subject: str = "SMTP Test Message") -> Dict[str, Any]:
    """
    Sends a test email via local Postfix (127.0.0.1:25).
    Returns a dict with msg_id and success status.
    """
    msg_id = str(uuid.uuid4())
    msg = EmailMessage()
    msg["Subject"] = f"{subject} [{msg_id}]"
    msg["From"] = from_email
    msg["To"] = to_email
    msg["Message-ID"] = f"<{msg_id}@relay.local>"
    
    body = f"""This is a test message sent from the Postfix Outbound Relay Panel.
    
    Timestamp: {time.ctime()}
    Message-ID: {msg_id}
    Sender: {from_email}
    Recipient: {to_email}
    
    Please check the Tracking page to see the delivery status.
    """
    msg.set_content(body)

    try:
        with smtplib.SMTP("127.0.0.1", 25, timeout=10) as server:
            server.send_message(msg)
        return {
            "success": True,
            "msg_id": msg_id,
            "message": "Email queued successfully in Postfix."
        }
    except Exception as e:
        return {
            "success": False,
            "msg_id": msg_id,
            "message": f"SMTP Error: {str(e)}"
        }
