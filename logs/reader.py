"""
logs/reader.py – Parse /var/log/maillog and write structured JSON entries to logs/parsed.log.
Run this as a background task in app.py.
"""

import os
import re
import json
import time

# Paths -----------------------------------------------------------------------
BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARSED_LOG = os.path.join(BASE_DIR, "logs", "parsed.log")
STATE_FILE = os.path.join(BASE_DIR, "runtime", "reader_state.json")

# Regex patterns for Postfix SMTP delivery lines ------------------------------
RE_SMTP = re.compile(
    r"(?P<month>\w+)\s+(?P<day>\d+)\s+(?P<time>\d+:\d+:\d+)"
    r".*postfix/(smtps/)?smtp\[\d+\]:\s+(?P<qid>[A-F0-9]+):\s+"
    r"to=<(?P<to>[^>]+)>.*?"
    r"status=(?P<status>\w+)"
)

RE_REJECT = re.compile(
    r"(?P<month>\w+)\s+(?P<day>\d+)\s+(?P<time>\d+:\d+:\d+)"
    r".*postfix/(smtps/)?smtpd\[\d+\]:\s+NOQUEUE: reject:.*?"
    r"(?P<reason>[^;:]+).*?"
    r"from=<(?P<from>[^>]+)> to=<(?P<to>[^>]+)>.*?"
    r"proto=(?P<proto>\w+)"
)

# Helpers for extra fields
RE_RELAY_IP = re.compile(r"relay=[^[]+\[(?P<ip>\d+\.\d+\.\d+\.\d+)\]")
RE_RELAY_NONE = re.compile(r"relay=none")
RE_FROM = re.compile(r"from=<([^>]+)>")
RE_SUBJ  = re.compile(r"subject=([^,\n]+)")

MONTH_MAP = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5,  "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

def _read_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"offset": 0}

def _write_state(state: dict) -> None:
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def _current_year() -> int:
    return time.localtime().tm_year

def _parse_timestamp(month: str, day: str, t: str) -> str:
    m = MONTH_MAP.get(month, 1)
    return f"{_current_year()}-{m:02d}-{int(day):02d} {t}"

def parse_maillog(limit: int = 5000) -> None:
    """
    Read new lines from maillog since last offset, parse SMTP delivery events,
    and append to parsed.log.
    """
    # Try common log locations
    log_paths = ["/var/log/maillog", "/var/log/mail.log"]
    target_log = None
    for p in log_paths:
        if os.path.exists(p):
            target_log = p
            break
            
    if not target_log:
        return

    state  = _read_state()
    offset = state.get("offset", 0)

    # If log rotated (current log smaller than offset), reset to 0
    try:
        if os.path.getsize(target_log) < offset:
            offset = 0
    except Exception:
        offset = 0

    entries = []
    new_offset = offset

    try:
        with open(target_log, "r", errors="replace") as f:
            f.seek(offset)
            count = 0
            for line in f:
                new_offset = f.tell()
                count += 1
                if count > limit:
                    break
                
                # 1. Match standard SMTP delivery
                m_smtp = RE_SMTP.search(line)
                if m_smtp:
                    entry = {
                        "time":     _parse_timestamp(m_smtp.group("month"), m_smtp.group("day"), m_smtp.group("time")),
                        "qid":      m_smtp.group("qid"),
                        "from":     "",
                        "to":       m_smtp.group("to"),
                        "subject":  "",
                        "dest_ip":  "",
                        "status":   m_smtp.group("status").lower(),
                    }
                    
                    rip = RE_RELAY_IP.search(line)
                    if rip: entry["dest_ip"] = rip.group("ip")
                    
                    fm = RE_FROM.search(line)
                    if fm: entry["from"] = fm.group(1)
                    
                    sm = RE_SUBJ.search(line)
                    if sm: entry["subject"] = sm.group(1).strip()
                    
                    entries.append(entry)
                    continue

                # 2. Match Inbound Rejects (e.g. Relay Access Denied)
                m_rej = RE_REJECT.search(line)
                if m_rej:
                    entry = {
                        "time":     _parse_timestamp(m_rej.group("month"), m_rej.group("day"), m_rej.group("time")),
                        "qid":      "REJECT",
                        "from":     m_rej.group("from"),
                        "to":       m_rej.group("to"),
                        "subject":  f"Rejected: {m_rej.group('reason')[:50]}",
                        "dest_ip":  "blocked",
                        "status":   "rejected",
                    }
                    entries.append(entry)

        if entries:
            with open(PARSED_LOG, "a", encoding="utf-8") as out:
                for e in entries:
                    out.write(json.dumps(e, ensure_ascii=False) + "\n")
            print(f"[LogReader] Processed {len(entries)} new log entries.")

        _write_state({"offset": new_offset})
    except Exception as e:
        print(f"[LogReader] Error reading {target_log}: {e}")

if __name__ == "__main__":
    parse_maillog()
