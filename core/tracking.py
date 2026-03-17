"""
core/tracking.py – Parse Postfix logs to track message status.
"""
import os
import subprocess
import re
from typing import List, Dict, Optional, Any

# Regex for Postfix log lines
# Example: Mar 16 10:00:00 server postfix/smtp[123]: ABCDEF12345: to=<user@example.com>, relay=... status=sent (250 2.0.0 Ok: queued as XYZ)
POSTFIX_LOG_RE = re.compile(r"(\w{3}\s+\d+\s+[\d:]+)\s+\S+\s+postfix/(\w+)\[\d+\]:\s+([A-F0-9]+):\s+(.*)")

def get_message_history(msg_id_snippet: str, limit: int = 50) -> List[Dict[str, str]]:
    """
    Searches logs for a specific Message-ID/Queue ID.
    If a Queue ID is found for a Message-ID, it traces the entire lifecycle.
    """
    events = []
    try:
        # Step 1: Find the first occurrence to resolve Queue ID if we only have Message-ID
        # We search the last hour of logs
        cmd_base = ""
        if os.name != 'nt':
            if subprocess.run("which journalctl", shell=True, capture_output=True).returncode == 0:
                cmd_base = "journalctl -u postfix --since '1 hour ago'"
            elif os.path.exists("/var/log/mail.log"):
                cmd_base = "cat /var/log/mail.log"
        
        if not cmd_base:
            return [{"error": "Unsupported environment for log tracking"}]

        # Try to find the Queue ID first
        find_qid_cmd = f"{cmd_base} | grep '{msg_id_snippet}' | head -n 1"
        res = subprocess.run(find_qid_cmd, shell=True, capture_output=True, text=True, timeout=5)
        
        search_term = msg_id_snippet
        first_line = res.stdout.strip()
        if first_line:
            match = POSTFIX_LOG_RE.search(first_line)
            if match:
                # Groups: timestamp, component, qid, rest
                search_term = match.group(3) # Use the Queue ID for a full trace

        # Step 2: Get all lines for that search_term (Queue ID)
        trace_cmd = f"{cmd_base} | grep '{search_term}' | tail -n {limit}"
        res = subprocess.run(trace_cmd, shell=True, capture_output=True, text=True, timeout=10)

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
    """Get Postfix queue summary and breakdown counts."""
    status = {
        "summary": "Queue is empty",
        "active": 0,
        "deferred": 0,
        "hold": 0,
        "incoming": 0
    }
    
    if os.name == 'nt':
        status["summary"] = "N/A (Windows Dev)"
        return status

    try:
        # Use qshape or count files in spool if available
        # But for basics, we parse 'mailq'
        res = subprocess.run("mailq | tail -n 1", shell=True, capture_output=True, text=True)
        line = res.stdout.strip()
        if line:
            status["summary"] = line
            # Parse "-- 10 Kbytes in 5 Requests."
            match = re.search(r"in (\d+) Request", line)
            if match:
                # We can't easily distinguish from just the summary line
                # So we'll put them in active for now or actually try to count
                # In most real setups, we'd use 'qshape'
                pass
        
        # Actual count from spool (requires permissions)
        for qtype in ["active", "deferred", "hold", "incoming"]:
            q_path = f"/var/spool/postfix/{qtype}"
            if os.path.exists(q_path):
                # Count files recursively
                count = sum([len(files) for r, d, files in os.walk(q_path)])
                status[qtype] = count

    except Exception as e:
        status["summary"] = f"Error: {str(e)}"
        
    return status

def flush_queue() -> bool:
    """Flush Postfix queue."""
    res = subprocess.run("postfix flush", shell=True)
    return res.returncode == 0
