import re

RE_SMTP = re.compile(
    r"(?P<month>\w+)\s+(?P<day>\d+)\s+(?P<time>\d+:\d+:\d+)"
    r".*?postfix/([^/]+/)?(smtp|lmtp|local|virtual|pipe)\[\d+\]:\s+(?P<qid>\w+):\s+"
    r"to=<(?P<to>[^>]+)>.*?"
    r"status=(?P<status>\w+)(?:\s+\((?P<resp>.*?)\))?"
)

RE_QID_RSPAMD = re.compile(
    r"postfix/(smtpd|cleanup)\[\d+\]:\s+(?P<qid>\w+):.*?milter-(reject|keep|accept|discard):.*?score=(?P<score>[\d\.-]+)\s+symbols=(?P<symbols>.*)"
)

# Test lines
line1 = "Mar 16 10:00:00 server postfix/smtp[123]: ABCDEF12345: to=<user@example.com>, relay=1.2.3.4[1.2.3.4]:25, delay=0.5, delays=0.1/0.1/0.1/0.2, dsn=2.0.0, status=sent (250 2.0.0 Ok: queued as XYZ)"
line2 = "Mar 16 10:00:01 server postfix/smtp[123]: ABCDEF12346: to=<user2@example.com>, relay=none, delay=0.1, status=deferred"
line3 = "Mar 16 10:00:02 server postfix/cleanup[456]: ABCDEF12347: milter-keep: END-OF-MESSAGE from unknown[1.1.1.1]: score=2.5 symbols=SYMBOL1,SYMBOL2"

m1 = RE_SMTP.search(line1)
print(f"Match 1: {m1.group('status')} - {m1.group('resp')}")

m2 = RE_SMTP.search(line2)
print(f"Match 2: {m2.group('status')} - {m2.group('resp')}")

m3 = RE_QID_RSPAMD.search(line3)
print(f"Match 3: {m3.group('qid')} - {m3.group('score')} - {m3.group('symbols')}")

print("Regex tests completed successfully")
