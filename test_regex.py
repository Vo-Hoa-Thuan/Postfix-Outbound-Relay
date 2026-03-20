import re

log_lines = [
    "Mar 19 23:52:39 server postfix/smtp[123]: 3ABC123: to=<a@b.com>, relay=gmail-smtp-in.l.google.com[74.125.130.26]:25, delay=1.2, delays=0.1/0/0.5/0.6, dsn=2.0.0, status=sent (250 2.0.0 OK)",
    "Mar 20 12:34:56 server postfix/cleanup[1234]: 3ABC123: warning: header Subject: My subject is here from local; from=<a@b.com> to=<c@d.com> proto=ESMTP helo=<helo>",
    "Mar 20 12:35:00 server postfix/smtpd[5678]: connect from unknown[103.3.244.111]"
]

RE_SMTP = re.compile(r"(?P<month>\w+)\s+(?P<day>\d+)\s+(?P<time>\d+:\d+:\d+).*?postfix/([^/]+/)?smtp\[\d+\]:\s+(?P<qid>\w+):\s+to=<(?P<to>[^>]+)>.*?status=(?P<status>\w+)")
RE_QID_SUBJECT = re.compile(r"postfix/([^/]+/)?cleanup\[\d+\]:\s+(?P<qid>\w+):.*?header Subject:\s+(?P<subject>.*?)(?:\s+from\s+[^;]+;|\s+from=|\s+proto=|\s+helo=)")
RE_RELAY_IP = re.compile(r"relay=[^[]+\[(?P<ip>\d+\.\d+\.\d+\.\d+)\]")

for line in log_lines:
    if RE_SMTP.search(line):
        print(f"SMTP MATCH: {RE_SMTP.search(line).groupdict()}")
    if RE_QID_SUBJECT.search(line):
        print(f"SUBJECT MATCH: {RE_QID_SUBJECT.search(line).groupdict()}")
    if RE_RELAY_IP.search(line):
        print(f"RELAY MAP: {RE_RELAY_IP.search(line).groupdict()}")
