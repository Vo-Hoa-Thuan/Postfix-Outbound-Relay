"""
core/tracking.py – Parse Postfix logs to track message status.
"""
import subprocess
import re
from typing import List, Dict, Optional, Any

# Regex for Postfix log lines
# Example: Mar 16 10:00:00 server postfix/smtp[123]: ABCDEF12345: to=<user@example.com>, relay=... status=sent (250 2.0.0 Ok: queued as XYZ)
POSTFIX_LOG_RE = re.compile(r"(\w{3}\s+\d+\s+[\d:]+)\s+\S+\s+postfix/(\w+)\[\d+\]:\s+([A-F0-9]+):\s+(.*)")

def get_message_history(msg_id_snippet: str, limit: int = 50) -> List[Dict[str, str]]:
    """
    Searches journalctl or mail.log for a specific Message-ID snippet or Queue ID.
    """
    events = []
    try:
        # Use journalctl for modern systems, fallback to tailing mail.log
        cmd = f"journalctl -u postfix --since '1 hour ago' | grep '{msg_id_snippet}' | tail -n {limit}"
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        
        if not res.stdout.strip():
            # Fallback to /var/log/mail.log if journalctl empty
            cmd = f"grep '{msg_id_snippet}' /var/log/mail.log | tail -n {limit}"
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)

        for line in res.stdout.splitlines():
            line = line.strip()
            if not line: continue
            
            match = POSTFIX_LOG_RE.search(line)
            if match:
                timestamp, component, qid, rest = match.groups()
                events.append({
                    "time": timestamp,
                    "component": component,
                    "qid": qid,
                    "info": rest
                })
            else:
                events.append({"raw": line})
                
    except Exception as e:
        events.append({"error": str(e)})
        
    return events

def get_queue_status() -> Dict[str, Any]:
    """Get Postfix queue summary using mailq."""
    try:
        res = subprocess.run("mailq | tail -n 1", shell=True, capture_output=True, text=True)
        # Expected: "-- 0 Kbytes in 0 Requests."
        return {"summary": res.stdout.strip() or "Queue is empty"}
    except:
        return {"summary": "Unknown (mailq failed)"}

def flush_queue() -> bool:
    """Flush Postfix queue."""
    res = subprocess.run("postfix flush", shell=True)
    return res.returncode == 0
