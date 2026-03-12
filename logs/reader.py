"""
logs/reader.py – Parse /var/log/maillog and write structured JSON entries to logs/parsed.log.
Run this as a cron job on the production server, e.g.:
    * * * * * python /var/www/html/logs/reader.py >> /var/log/relay-reader.log 2>&1
"""

import os
import re
import json
import time

# Paths -----------------------------------------------------------------------
MAILLOG    = "/var/log/maillog"
BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARSED_LOG = os.path.join(BASE_DIR, "logs", "parsed.log")
STATE_FILE = os.path.join(BASE_DIR, "runtime", "reader_state.json")

# Regex patterns for Postfix SMTP delivery lines ------------------------------
# Example line:
# Feb 25 10:00:01 hostname postfix/smtp[1234]: ABCDEF123456: to=<user@example.com>,
#   relay=gmail-smtp-in.l.google.com[142.250.4.27]:25, status=sent (250 ...)

RE_LINE = re.compile(
    r"(?P<month>\w+)\s+(?P<day>\d+)\s+(?P<time>\d+:\d+:\d+)"
    r".*postfix/smtp\[\d+\]:\s+(?P<qid>[A-F0-9]+):\s+"
    r"to=<(?P<to>[^>]+)>.*?"
    r"relay=[^[]+\[(?P<dest_ip>\d+\.\d+\.\d+\.\d+)\].*?"
    r"status=(?P<status>\w+)"
)

RE_FROM = re.compile(r"from=<([^>]+)>")
RE_SUBJ  = re.compile(r"subject=([^,\n]+)")


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


MONTH_MAP = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5,  "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def _parse_timestamp(month: str, day: str, t: str) -> str:
    m = MONTH_MAP.get(month, 1)
    return f"{_current_year()}-{m:02d}-{int(day):02d} {t}"


def parse_maillog(limit: int = 5000) -> None:
    """
    Read new lines from maillog since last offset, parse SMTP delivery events,
    and append to parsed.log.
    """
    if not os.path.exists(MAILLOG):
        print(f"Maillog not found: {MAILLOG}")
        return

    state  = _read_state()
    offset = state.get("offset", 0)

    entries = []
    new_offset = offset

    with open(MAILLOG, "r", errors="replace") as f:
        f.seek(offset)
        count = 0
        for line in f:
            new_offset = f.tell()
            count += 1
            if count > limit:
                break
            m = RE_LINE.search(line)
            if not m:
                continue
            entry = {
                "time":     _parse_timestamp(m.group("month"), m.group("day"), m.group("time")),
                "from":     "",
                "to":       m.group("to"),
                "subject":  "",
                "dest_ip":  m.group("dest_ip"),
                "local_ip": "",  # extracted from envelope sender lookup or separate log line
                "status":   m.group("status"),
            }
            fm = RE_FROM.search(line)
            if fm:
                entry["from"] = fm.group(1)
            sm = RE_SUBJ.search(line)
            if sm:
                entry["subject"] = sm.group(1).strip()

            entries.append(entry)

    if entries:
        with open(PARSED_LOG, "a", encoding="utf-8") as out:
            for e in entries:
                out.write(json.dumps(e, ensure_ascii=False) + "\n")
        print(f"Wrote {len(entries)} entries to {PARSED_LOG}")

    _write_state({"offset": new_offset})


if __name__ == "__main__":
    parse_maillog()
