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
    r".*?postfix/([^/]+/)?(smtp|lmtp|local|virtual|pipe)\[\d+\]:\s+(?P<qid>\w+):\s+"
    r"to=<(?P<to>[^>]+)>.*?"
    r"(?:relay=(?P<relay>[^\s,]+)[,\s]+)?"
    r"(?:delay=(?P<delay>[\d\.]+),\s+delays=(?P<delays>[\d\./]+),\s+.*?)?"
    r"status=(?P<status>\w+)(?:\s+\((?P<resp>.*?)\))?"
)

RE_REJECT = re.compile(
    r"(?P<month>\w+)\s+(?P<day>\d+)\s+(?P<time>\d+:\d+:\d+)"
    r".*?postfix/([^/]+/)?smtpd\[\d+\]:\s+NOQUEUE: (?:reject|milter-reject):.*?"
    r"(?:RCPT from [^:]+|END-OF-MESSAGE from [^:]+)?:\s*(?P<reason>[^;]+).*?"
    r"from=<(?P<from>[^>]+)>\s+to=<(?P<to>[^>]+)>"
)

# QID to metadata lookup (for Postfix)
RE_QID_FROM = re.compile(
    r"postfix/([^/]+/)?(smtpd|qmgr|cleanup)\[\d+\]:\s+(?P<qid>\w+):.*?from=<(?P<from>[^>]+)>.*?(?:size=(?P<size>\d+))?"
)
RE_QID_SUBJECT = re.compile(
    r"postfix/([^/]+/)?cleanup\[\d+\]:\s+(?P<qid>\w+):.*?header Subject:\s+(?P<subject>.*?)(?=\s+from\s+[^;]+;|\s+from=|\s+proto=|\s+helo=|$)"
)
RE_QID_CLIENT = re.compile(
    r"postfix/([^/]+/)?smtpd\[\d+\]:\s+(?P<qid>\w+):.*?client=[^\[]+\[(?P<ip>\d+\.\d+\.\d+\.\d+)\](?:.*?(?:sasl_username=(?P<sasl>[^,\s]+)))?"
)
RE_QID_ERROR = re.compile(
    r"postfix/([^/]+)\[\d+\]:\s+(?P<qid>\w+):\s+(?P<level>fatal|error|warning):\s+(?!header Subject)(?P<msg>.*)"
)
RE_QID_RSPAMD = re.compile(
    r"postfix/(smtpd|cleanup)\[\d+\]:\s+(?P<qid>\w+):.*?milter-(reject|keep|accept|discard):.*?score=(?P<score>[\d\.-]+)\s+symbols=(?P<symbols>.*)"
)
RE_QID_TLS = re.compile(
    r"postfix/([^/]+/)?smtp\[\d+\]:\s+(?P<qid>\w+):.*?(?:Untrusted|Trusted|Verified|Anonymous)?\s*TLS connection established to .*?:\s+(?P<tls_ver>[A-Za-z0-9\.]+)\s+with cipher\s+(?P<cipher>[A-Za-z0-9_\-]+)"
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
    
    # Priority 0: Đọc trực tiếp Log của riêng Rspamd để rút điểm Score
    _parse_rspamd_log(state)
    
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
                    if mq_from.group("size"): state["qid_map"][qid]["size"] = mq_from.group("size")
                
                mq_subj = RE_QID_SUBJECT.search(full_line)
                if mq_subj:
                    qid = mq_subj.group("qid")
                    if qid not in state["qid_map"]: state["qid_map"][qid] = {}
                    if isinstance(state["qid_map"][qid], str): state["qid_map"][qid] = {"from": state["qid_map"][qid]}
                    state["qid_map"][qid]["subject"] = mq_subj.group("subject").strip()

                mq_client = RE_QID_CLIENT.search(full_line)
                if mq_client:
                    qid = mq_client.group("qid")
                    if qid not in state["qid_map"]: state["qid_map"][qid] = {}
                    if isinstance(state["qid_map"][qid], str): state["qid_map"][qid] = {"from": state["qid_map"][qid]}
                    state["qid_map"][qid]["client"] = mq_client.group("ip")
                    if mq_client.group("sasl"): state["qid_map"][qid]["sasl"] = mq_client.group("sasl")

                mq_tls = RE_QID_TLS.search(full_line)
                if mq_tls:
                    qid = mq_tls.group("qid")
                    if qid not in state["qid_map"]: state["qid_map"][qid] = {}
                    if isinstance(state["qid_map"][qid], str): state["qid_map"][qid] = {"from": state["qid_map"][qid]}
                    state["qid_map"][qid]["tls_ver"] = mq_tls.group("tls_ver")
                    state["qid_map"][qid]["cipher"] = mq_tls.group("cipher")

                mq_error = RE_QID_ERROR.search(full_line)
                if mq_error:
                    qid = mq_error.group("qid")
                    if qid not in state["qid_map"]: state["qid_map"][qid] = {}
                    if isinstance(state["qid_map"][qid], str): state["qid_map"][qid] = {"from": state["qid_map"][qid]}
                    state["qid_map"][qid]["error"] = mq_error.group("msg").strip()
                
                mq_rspamd = RE_QID_RSPAMD.search(full_line)
                if mq_rspamd:
                    qid = mq_rspamd.group("qid")
                    if qid not in state["qid_map"]: state["qid_map"][qid] = {}
                    if isinstance(state["qid_map"][qid], str): state["qid_map"][qid] = {"from": state["qid_map"][qid]}
                    state["qid_map"][qid]["spam_score"] = float(mq_rspamd.group("score"))
                    state["qid_map"][qid]["spam_symbols"] = mq_rspamd.group("symbols").strip()
                    
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

RE_RSPAMD_LOG = re.compile(
    r"qid: <(?P<qid>[^>]+)>.*?\[(?P<score>[\d\.-]+)\/[\d\.-]+\]\s*\[(?P<symbols>.*?)\]\)"
)

def _parse_rspamd_log(state: dict) -> None:
    rspamd_log = "/var/log/rspamd/rspamd.log"
    if not os.path.exists(rspamd_log):
        return
        
    if "rspamd_offset" not in state: state["rspamd_offset"] = 0
    offset = state["rspamd_offset"]
    
    file_size = os.path.getsize(rspamd_log)
    if file_size < offset: offset = 0
    if offset == 0 and file_size > 1 * 1024 * 1024:
        offset = file_size - (1 * 1024 * 1024)
        
    new_offset = offset
    try:
        with open(rspamd_log, "r", errors="replace") as f:
            f.seek(offset)
            while True:
                line = f.readline()
                if not line: break
                
                new_offset = f.tell()
                if "rspamd_task_write_log" in line:
                    m = RE_RSPAMD_LOG.search(line)
                    if m:
                        qid = m.group("qid")
                        if qid not in state["qid_map"]: state["qid_map"][qid] = {}
                        if isinstance(state["qid_map"][qid], str): state["qid_map"][qid] = {"from": state["qid_map"][qid]}
                        state["qid_map"][qid]["spam_score"] = float(m.group("score"))
                        # Symbol check disabled for minimal robust matching
                        state["qid_map"][qid]["spam_symbols"] = ""
        state["rspamd_offset"] = new_offset
    except Exception as e:
        pass

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
                        if mq_from.group("size"): state["qid_map"][qid]["size"] = mq_from.group("size")
                    
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
                        if mq_client.group("sasl"): state["qid_map"][qid]["sasl"] = mq_client.group("sasl")

                    mq_tls = RE_QID_TLS.search(line)
                    if mq_tls:
                        qid = mq_tls.group("qid")
                        if qid not in state["qid_map"]: state["qid_map"][qid] = {}
                        if isinstance(state["qid_map"][qid], str): state["qid_map"][qid] = {"from": state["qid_map"][qid]}
                        state["qid_map"][qid]["tls_ver"] = mq_tls.group("tls_ver")
                        state["qid_map"][qid]["cipher"] = mq_tls.group("cipher")

                    mq_error = RE_QID_ERROR.search(line)
                    if mq_error:
                        qid = mq_error.group("qid")
                        if qid not in state["qid_map"]: state["qid_map"][qid] = {}
                        if isinstance(state["qid_map"][qid], str): state["qid_map"][qid] = {"from": state["qid_map"][qid]}
                        state["qid_map"][qid]["error"] = mq_error.group("msg").strip()

                    mq_rspamd = RE_QID_RSPAMD.search(line)
                    if mq_rspamd:
                        qid = mq_rspamd.group("qid")
                        if qid not in state["qid_map"]: state["qid_map"][qid] = {}
                        if isinstance(state["qid_map"][qid], str): state["qid_map"][qid] = {"from": state["qid_map"][qid]}
                        state["qid_map"][qid]["spam_score"] = float(mq_rspamd.group("score"))
                        state["qid_map"][qid]["spam_symbols"] = mq_rspamd.group("symbols").strip()
                    
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
    match_smtp = RE_SMTP.search(line)
    if match_smtp:
        s_dict = match_smtp.groupdict()
        time_str = _parse_timestamp(s_dict['month'], s_dict['day'], s_dict['time'])
        qid = s_dict["qid"]
        dest = s_dict["to"]
        status = s_dict["status"]
        resp = s_dict.get("resp") or ""
        delay = s_dict.get("delay")
        delays = s_dict.get("delays")
        
        qid_info = qid_map.get(qid, {})
        caller_from = qid_info if isinstance(qid_info, str) else qid_info.get("from", "unknown")
        subj = qid_info.get("subject", "") if isinstance(qid_info, dict) else ""
        client = qid_info.get("client", "") if isinstance(qid_info, dict) else ""
        sasl = qid_info.get("sasl", "") if isinstance(qid_info, dict) else ""
        error_msg = qid_info.get("error", "") if isinstance(qid_info, dict) else ""
        spam_score = qid_info.get("spam_score", None) if isinstance(qid_info, dict) else None
        spam_symbols = qid_info.get("spam_symbols", "") if isinstance(qid_info, dict) else ""
        msg_size = qid_info.get("size", None) if isinstance(qid_info, dict) else None
        tls_ver = qid_info.get("tls_ver", None) if isinstance(qid_info, dict) else None
        cipher = qid_info.get("cipher", None) if isinstance(qid_info, dict) else None
        
        relay_str = s_dict.get("relay") or ""
        dest_ip = ""
        if relay_str:
            rip_m = RE_RELAY_IP.search(f"relay={relay_str}")
            if rip_m: dest_ip = rip_m.group("ip")
            
        entry = {
            "time": time_str,
            "msgid": "", # Hard to get from syslog reliably without another regex
            "qid": qid,
            "from": caller_from,
            "to": dest,
            "subject": subj,
            "status": status,
            "response": resp,
            "local_ip": client, # Sử dụng Client IP thay thế cho Local Interface
            "dest_ip": dest_ip,
            "client_ip": client,
            "sasl": sasl,
            "error_msg": error_msg,
            "spam_score": spam_score,
            "spam_symbols": spam_symbols,
            "delay": delay,
            "delays": delays,
            "size": msg_size,
            "tls_ver": tls_ver,
            "cipher": cipher
        }
        return entry

    # Postfix QID Error (Catching fatal/warning lines)
    m_err = RE_QID_ERROR.search(line)
    if m_err:
        qid = m_err.group("qid")
        qid_info = qid_map.get(qid, {})
        msg_from = qid_info if isinstance(qid_info, str) else qid_info.get("from", "-")
        
        return {
            "time":     _parse_timestamp(line.split()[0], line.split()[1], line.split()[2]),
            "qid":      qid,
            "from":     msg_from,
            "to":       "-",
            "subject":  f"SYSTEM ERROR: {m_err.group('msg').strip()[:60]}",
            "local_ip":  "",
            "dest_ip":  "error",
            "status":   "bounced",
        }

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

from filelock import FileLock, Timeout

def _save_entries(entries: list) -> None:
    if not entries: return
    
    lock = FileLock(PARSED_LOG + ".lock", timeout=5)
    try:
        with lock.acquire(timeout=5):
            # Rotate if file > 50MB
            if os.path.exists(PARSED_LOG) and os.path.getsize(PARSED_LOG) > 50 * 1024 * 1024:
                bak_path = PARSED_LOG + ".1"
                if os.path.exists(bak_path):
                    os.remove(bak_path)
                os.rename(PARSED_LOG, bak_path)
                
            with open(PARSED_LOG, "a", encoding="utf-8") as out:
                for e in entries:
                    out.write(json.dumps(e, ensure_ascii=False) + "\n")
    except Timeout:
        print("[LogReader] WARNING: Could not acquire lock for parsed.log")

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
