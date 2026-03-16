"""
logs/reader.py – Parse Postfix and Kerio Connect logs. Supports file-based and journalctl-based logs.
Tracks QID to link 'From' addresses to 'Sent' events.
"""

import os
import re
import json
import time
import subprocess
from typing import Optional, Dict

# Paths -----------------------------------------------------------------------
BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARSED_LOG = os.path.join(BASE_DIR, "logs", "parsed.log")
STATE_FILE = os.path.join(BASE_DIR, "runtime", "reader_state.json")

# Regex patterns --------------------------------------------------------------
# Postfix
RE_SMTP = re.compile(
    r"(?P<month>\w+)\s+(?P<day>\d+)\s+(?P<time>\d+:\d+:\d+)"
    r".*?postfix/([^/]+/)?smtp\[\d+\]:\s+(?P<qid>\w+):\s+"
    r"to=<(?P<to>[^>]+)>.*?"
    r"status=(?P<status>\w+)"
)

RE_REJECT = re.compile(
    r"(?P<month>\w+)\s+(?P<day>\d+)\s+(?P<time>\d+:\d+:\d+)"
    r".*?postfix/([^/]+/)?smtpd\[\d+\]:\s+NOQUEUE: reject:.*?"
    r"(?P<reason>[^;:]+).*?"
    r"from=<(?P<from>[^>]+)>\s+to=<(?P<to>[^>]+)>"
)

# QID to From lookup (for Postfix)
RE_QID_FROM = re.compile(
    r"postfix/([^/]+/)?(smtpd|qmgr|cleanup)\[\d+\]:\s+(?P<qid>\w+):.*?from=<(?P<from>[^>]+)>"
)

# Extra fields lookup
RE_RELAY_IP = re.compile(r"relay=[^[]+\[(?P<ip>\d+\.\d+\.\d+\.\d+)\]")
RE_SUBJ     = re.compile(r"subject=([^,\n]+)")

# Kerio Connect
RE_KERIO_SENT = re.compile(
    r"\[(?P<day>\d+)/(?P<month>\w+)/(?P<year>\d+)\s+(?P<time>\d+:\d+:\d+)\]\s+"
    r"Sent:\s+Queue-ID:\s+(?P<qid>[^,]+),\s+Recipient:\s+<(?P<to>[^>]+)>,\s+"
    r"Result:\s+(?P<result>[^,]+),\s+Status:\s+(?P<status>[^,]+)"
)

RE_KERIO_RECV = re.compile(
    r"\[(?P<day>\d+)/(?P<month>\w+)/(?P<year>\d+)\s+(?P<time>\d+:\d+:\d+)\]\s+"
    r"Recv:\s+Queue-ID:\s+(?P<qid>[^,]+),.*?From:\s+<(?P<from>[^>]+)>,\s+To:\s+<(?P<to>[^>]+)>.*?"
    r"Subject:\s+(?P<subject>[^,]+)"
)

MONTH_MAP = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

def _read_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _write_state(state: dict) -> None:
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception:
        pass

def _current_year() -> int:
    return time.localtime().tm_year

def _parse_timestamp(month: str, day: str, t: str, year: Optional[str] = None) -> str:
    m = MONTH_MAP.get(month, 1)
    y = year if year else _current_year()
    return f"{y}-{m:02d}-{int(day):02d} {t}"

def parse_maillog(limit: int = 1000) -> None:
    """
    Main entry point. We will try to read from journalctl primarily for Postfix
    and then files for Kerio/System logs.
    """
    state = _read_state()
    if "qid_map" not in state: state["qid_map"] = {}
    
    # Priority 1: Journalctl (Real-time for Postfix on modern systems)
    _parse_journal(limit, state)
    
    # Priority 2: Files (Kerio, older systems)
    log_paths = [
        "/home/rescopykeriofirst/store/logs/mail.log",
        "/opt/kerio/mailserver/store/logs/mail.log",
        "/var/log/maillog", 
        "/var/log/mail.log"
    ]
    found_logs = [p for p in log_paths if os.path.exists(p) and os.path.getsize(p) > 0]
    if found_logs:
        _parse_files(found_logs, limit, state)
        
    # Periodic cleanup of old QID mappings (keep last 500)
    if len(state["qid_map"]) > 500:
        # Simple pop from start
        ks = list(state["qid_map"].keys())
        for k in ks[:200]: state["qid_map"].pop(k)
        
    _write_state(state)

def _parse_journal(limit: int, state: dict) -> None:
    try:
        # Read a good chunk of recent history to ensure we catch both QID/From and Sent lines
        cmd = ["journalctl", "-u", "postfix", "-n", str(limit * 2), "--no-pager"]
        output = subprocess.check_output(cmd, encoding="utf-8", errors="replace")
        
        # Track which lines we've already parsed to avoid duplicates in the same run
        # Note: journal parsing here is simplified without strict offset to ensure reliability
        entries = []
        for line in output.splitlines():
            # 1. Update QID Map
            mq = RE_QID_FROM.search(line)
            if mq:
                state["qid_map"][mq.group("qid")] = mq.group("from")
                continue
                
            # 2. Parse Lines
            entry = _parse_line(line, state["qid_map"])
            if entry:
                entries.append(entry)
        
        if entries:
            _save_entries(entries)
            print(f"[LogReader] Journal: Captured {len(entries)} events.")
    except Exception as e:
        print(f"[LogReader] Journal error: {e}")

def _parse_files(target_logs: list, limit_per_file: int, state: dict) -> None:
    if "offsets" not in state: state["offsets"] = {}
    
    for path in target_logs:
        offset = state["offsets"].get(path, 0)
        file_size = os.path.getsize(path)
        if file_size < offset: offset = 0
        
        entries = []
        new_offset = offset
        try:
            with open(path, "r", errors="replace") as f:
                f.seek(offset)
                count = 0
                for line in f:
                    new_offset = f.tell()
                    # Update QID map from file
                    mq = RE_QID_FROM.search(line)
                    if mq: state["qid_map"][mq.group("qid")] = mq.group("from")
                    
                    entry = _parse_line(line, state["qid_map"])
                    if entry: entries.append(entry)
                    count += 1
                    if count >= limit_per_file: break
            
            if entries:
                _save_entries(entries)
            state["offsets"][path] = new_offset
        except Exception as e:
            pass

def _parse_line(line: str, qid_map: Dict[str, str]) -> Optional[dict]:
    # Postfix SMTP
    m_smtp = RE_SMTP.search(line)
    if m_smtp:
        qid = m_smtp.group("qid")
        entry = {
            "time":     _parse_timestamp(m_smtp.group("month"), m_smtp.group("day"), m_smtp.group("time")),
            "qid":      qid,
            "from":     qid_map.get(qid, "-"), # Look up from CID map
            "to":       m_smtp.group("to"),
            "subject":  "-",
            "dest_ip":  "",
            "status":   m_smtp.group("status").lower(),
        }
        rip = RE_RELAY_IP.search(line); 
        if rip: entry["dest_ip"] = rip.group("ip")
        
        # Subject is rarely in smtp line, but check just in case
        sm = RE_SUBJ.search(line); 
        if sm: entry["subject"] = sm.group(1).strip()
        return entry

    # Postfix Reject
    m_rej = RE_REJECT.search(line)
    if m_rej:
        return {
            "time":     _parse_timestamp(m_rej.group("month"), m_rej.group("day"), m_rej.group("time")),
            "qid":      "REJECT",
            "from":     m_rej.group("from"),
            "to":       m_rej.group("to"),
            "subject":  f"Rejected: {m_rej.group('reason').strip()[:60]}",
            "dest_ip":  "blocked",
            "status":   "rejected",
        }

    # Kerio Sent
    mk_sent = RE_KERIO_SENT.search(line)
    if mk_sent:
        return {
            "time":     _parse_timestamp(mk_sent.group("month"), mk_sent.group("day"), mk_sent.group("time"), mk_sent.group("year")),
            "qid":      mk_sent.group("qid"),
            "from":     "-", # Kerio SENT line doesn't have from
            "to":       mk_sent.group("to"),
            "subject":  "-",
            "dest_ip":  "",
            "status":   mk_sent.group("status").lower() if mk_sent.group("status") else "sent",
        }

    # Kerio Recv
    mk_recv = RE_KERIO_RECV.search(line)
    if mk_recv:
        return {
            "time":     _parse_timestamp(mk_recv.group("month"), mk_recv.group("day"), mk_recv.group("time"), mk_recv.group("year")),
            "qid":      mk_recv.group("qid"),
            "from":     mk_recv.group("from"),
            "to":       mk_recv.group("to"),
            "subject":  mk_recv.group("subject").strip(),
            "dest_ip":  "incoming",
            "status":   "received",
        }
    return None

def _save_entries(entries: list) -> None:
    # Basic deduplication: don't write if same time+qid+to combo already exists in last 50 lines of parsed.log
    # (Simplified: just write for now, dashboard handles display)
    with open(PARSED_LOG, "a", encoding="utf-8") as out:
        for e in entries:
            out.write(json.dumps(e, ensure_ascii=False) + "\n")

if __name__ == "__main__":
    parse_maillog()
