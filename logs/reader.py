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

# QID to metadata lookup (for Postfix)
RE_QID_FROM = re.compile(
    r"postfix/([^/]+/)?(smtpd|qmgr|cleanup)\[\d+\]:\s+(?P<qid>\w+):.*?from=<(?P<from>[^>]+)>"
)
RE_QID_SUBJECT = re.compile(
    r"postfix/([^/]+/)?cleanup\[\d+\]:\s+(?P<qid>\w+):.*?header Subject:\s+(?P<subject>.*?)(?=\s+from\s+[^;]+;|\s+from=|\s+proto=|\s+helo=|$)"
)
RE_QID_CLIENT = re.compile(
    r"postfix/([^/]+/)?smtpd\[\d+\]:\s+(?P<qid>\w+):.*?client=[^\[]+\[(?P<ip>\d+\.\d+\.\d+\.\d+)\]"
)

# Extra fields lookup
RE_RELAY_IP = re.compile(r"relay=[^\[]+\[(?P<ip>\d+\.\d+\.\d+\.\d+)\]")
RE_SUBJ     = re.compile(r"(?i)(?:subject=|warning: header Subject: )([^,\n;]+)")

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

def parse_maillog(limit: int = 500) -> None:
    """
    Main entry point. We will try to read from journalctl primarily for Postfix
    and then files for Kerio/System logs.
    """
    state = _read_state()
    if "qid_map" not in state: state["qid_map"] = {}
    
    # Priority 1: Journalctl (Incremental using Cursor)
    _parse_journal_incremental(state)
    
    # Priority 2: Files (Incremental using Offsets)
    log_paths = [
        "/home/rescopykeriofirst/store/logs/mail.log",
        "/opt/kerio/mailserver/store/logs/mail.log",
        "/var/log/maillog", 
        "/var/log/mail.log"
    ]
    found_logs = [p for p in log_paths if os.path.exists(p) and os.path.getsize(p) > 0]
    if found_logs:
        _parse_files(found_logs, limit, state)
        
    # Cleanup QID mappings
    if len(state["qid_map"]) > 1000:
        ks = list(state["qid_map"].keys())
        for k in ks[:500]: state["qid_map"].pop(k)
        
    _write_state(state)

def _parse_journal_incremental(state: dict) -> None:
    """Read only NEW journal entries since the last recorded cursor."""
    if os.name == 'nt':
        return # journalctl doesn't exist on Windows
        
    try:
        # Check if journalctl is available
        import shutil
        if not shutil.which("journalctl"):
            return
            
        cursor = state.get("journal_cursor")
        cmd = ["journalctl", "-u", "postfix", "--no-pager", "-o", "json"]
        if cursor:
            cmd += ["--after-cursor", cursor]
        else:
            cmd += ["-n", "50000"] # First run, get more history since file might be dead

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8")
        stdout, _ = proc.communicate()
        
        entries = []
        new_cursor = cursor
        
        for line in stdout.splitlines():
            try:
                msg_json = json.loads(line)
                new_cursor = msg_json.get("__CURSOR")
                msg_text = msg_json.get("MESSAGE", "")
                
                # Reconstruct standard syslog line since regexes expect it
                import datetime
                ts = int(msg_json.get("__REALTIME_TIMESTAMP", 0)) / 1000000.0
                if ts > 0:
                    dt = datetime.datetime.fromtimestamp(ts)
                    syslog_time = dt.strftime("%b %d %H:%M:%S")
                else:
                    syslog_time = msg_json.get("SYSLOG_TIMESTAMP", "Jan 01 00:00:00")
                    
                ident = msg_json.get("SYSLOG_IDENTIFIER", "postfix")
                pid = msg_json.get("_PID", msg_json.get("SYSLOG_PID", "0"))

                # Reconstruct: Mar 19 23:43:00 hostname postfix/smtp[123]: <msg_text>
                full_line = f"{syslog_time} relay {ident}[{pid}]: {msg_text}"
                
                # Update QID Map (From and Subject)
                mq_from = RE_QID_FROM.search(full_line)
                if mq_from:
                    qid = mq_from.group("qid")
                    if qid not in state["qid_map"]: state["qid_map"][qid] = {}
                    if isinstance(state["qid_map"][qid], str): state["qid_map"][qid] = {"from": state["qid_map"][qid]}
                    state["qid_map"][qid]["from"] = mq_from.group("from")
                    continue
                
                mq_subj = RE_QID_SUBJECT.search(full_line)
                if mq_subj:
                    qid = mq_subj.group("qid")
                    if qid not in state["qid_map"]: state["qid_map"][qid] = {}
                    if isinstance(state["qid_map"][qid], str): state["qid_map"][qid] = {"from": state["qid_map"][qid]}
                    state["qid_map"][qid]["subject"] = mq_subj.group("subject").strip()
                    continue

                mq_client = RE_QID_CLIENT.search(full_line)
                if mq_client:
                    qid = mq_client.group("qid")
                    if qid not in state["qid_map"]: state["qid_map"][qid] = {}
                    if isinstance(state["qid_map"][qid], str): state["qid_map"][qid] = {"from": state["qid_map"][qid]}
                    state["qid_map"][qid]["client"] = mq_client.group("ip")
                    continue
                    
                entry = _parse_line(full_line, state["qid_map"])
                if entry:
                    entries.append(entry)
            except Exception as j_err:
                pass
        
        if entries:
            _save_entries(entries)
            print(f"[LogReader] Journal: Incremental {len(entries)} events.")
        
        if new_cursor:
            state["journal_cursor"] = new_cursor
            
    except Exception as e:
        print(f"[LogReader] Journal incremental error: {e}")

def _parse_files(target_logs: list, limit_per_file: int, state: dict) -> None:
    if "offsets" not in state: state["offsets"] = {}
    
    for path in target_logs:
        offset = state["offsets"].get(path, 0)
        file_size = os.path.getsize(path)
        if file_size < offset: offset = 0
        
        # If starting fresh on a giant file, fast-forward to the last 5MB
        if offset == 0 and file_size > 5 * 1024 * 1024:
            offset = file_size - (5 * 1024 * 1024)
            
        entries = []
        new_offset = offset
        try:
            with open(path, "r", errors="replace") as f:
                f.seek(offset)
                count = 0
                for line in f:
                    new_offset = f.tell()
                    # Update QID map from file
                    mq_from = RE_QID_FROM.search(line)
                    if mq_from:
                        qid = mq_from.group("qid")
                        if qid not in state["qid_map"]: state["qid_map"][qid] = {}
                        if isinstance(state["qid_map"][qid], str): state["qid_map"][qid] = {"from": state["qid_map"][qid]}
                        state["qid_map"][qid]["from"] = mq_from.group("from")
                    
                    mq_subj = RE_QID_SUBJECT.search(line)
                    if mq_subj:
                        qid = mq_subj.group("qid")
                        if qid not in state["qid_map"]: state["qid_map"][qid] = {}
                        if isinstance(state["qid_map"][qid], str): state["qid_map"][qid] = {"from": state["qid_map"][qid]}
                        state["qid_map"][qid]["subject"] = mq_subj.group("subject").strip()
                        
                    mq_client = RE_QID_CLIENT.search(line)
                    if mq_client:
                        qid = mq_client.group("qid")
                        if qid not in state["qid_map"]: state["qid_map"][qid] = {}
                        if isinstance(state["qid_map"][qid], str): state["qid_map"][qid] = {"from": state["qid_map"][qid]}
                        state["qid_map"][qid]["client"] = mq_client.group("ip")
                    
                    entry = _parse_line(line, state["qid_map"])
                    if entry: entries.append(entry)
                    count += 1
                    if count >= limit_per_file: break
            
            if entries:
                _save_entries(entries)
            state["offsets"][path] = new_offset
        except Exception as e:
            print(f"[LogReader] Exception reading file {path}: {e}")

def _parse_line(line: str, qid_map: Dict[str, str]) -> Optional[dict]:
    # Postfix SMTP
    m_smtp = RE_SMTP.search(line)
    if m_smtp:
        qid = m_smtp.group("qid")
        qid_info = qid_map.get(qid, {})
        # Compatibility with old string-based qid_map
        msg_from = qid_info if isinstance(qid_info, str) else qid_info.get("from", "-")
        msg_subj = qid_info.get("subject", "-") if isinstance(qid_info, dict) else "-"
        client_ip = qid_info.get("client", "") if isinstance(qid_info, dict) else ""
        
        entry = {
            "time":     _parse_timestamp(m_smtp.group("month"), m_smtp.group("day"), m_smtp.group("time")),
            "qid":      qid,
            "from":     msg_from,
            "to":       m_smtp.group("to"),
            "subject":  msg_subj,
            "local_ip":  client_ip,
            "dest_ip":   "",
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
            "local_ip":  "",
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
            "local_ip":  "",
            "dest_ip":   "",
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
            "local_ip":  "",
            "dest_ip":  "incoming",
            "status":   "received",
        }
    return None

def _save_entries(entries: list) -> None:
    with open(PARSED_LOG, "a", encoding="utf-8") as out:
        for e in entries:
            out.write(json.dumps(e, ensure_ascii=False) + "\n")

# ── Chart Aggregator ────────────────────────────────────────────────────────
CHART_CACHE_FILE = os.path.join(BASE_DIR, "runtime", "chart_cache.json")

def pre_aggregate_chart():
    """Build a 24h summary from parsed.log and cache it to disk."""
    import datetime
    if not os.path.exists(PARSED_LOG):
        return
        
    now = datetime.datetime.now()
    hours_labels = []
    # Key = "YYYY-MM-DD HH", Value = {"sent": 0, "deferred": 0, "bounced": 0}
    chart_data = {}
    
    for i in range(23, -1, -1):
        h_time = now - datetime.timedelta(hours=i)
        label = h_time.strftime("%H:00")
        prefix = h_time.strftime("%Y-%m-%d %H")
        hours_labels.append({"label": label, "prefix": prefix})
        chart_data[prefix] = {"sent": 0, "deferred": 0, "bounced": 0}
        
    oldest_prefix = hours_labels[0]["prefix"]
    
    try:
        # We only really care about the last ~10-20MB of this file for chart
        file_size = os.path.getsize(PARSED_LOG)
        read_start = max(0, file_size - (1024 * 1024 * 10)) # Last 10MB
        
        with open(PARSED_LOG, "r", encoding="utf-8") as f:
            if read_start > 0:
                f.seek(read_start)
                f.readline() # Skip partial line
                
            for line in f:
                line = line.strip()
                if not line: continue
                try:
                    entry = json.loads(line)
                    log_time = entry.get("time", "")
                    status = entry.get("status", "")
                    if len(log_time) >= 13:
                        prefix = log_time[:13]
                        if prefix >= oldest_prefix and prefix in chart_data:
                            if status in ["sent", "deferred", "bounced"]:
                                chart_data[prefix][status] += 1
                except: pass
                
        # Format arrays
        result = {
            "updated_at": time.time(),
            "labels": [h["label"] for h in hours_labels],
            "datasets": {
                "sent": [chart_data[h["prefix"]]["sent"] for h in hours_labels],
                "deferred": [chart_data[h["prefix"]]["deferred"] for h in hours_labels],
                "bounced": [chart_data[h["prefix"]]["bounced"] for h in hours_labels],
            }
        }
        
        os.makedirs(os.path.dirname(CHART_CACHE_FILE), exist_ok=True)
        with open(CHART_CACHE_FILE, "w") as f:
            json.dump(result, f)
            
    except Exception as e:
        print(f"[LogReader] Chart Aggregation error: {e}")

if __name__ == "__main__":
    parse_maillog()
    pre_aggregate_chart()
