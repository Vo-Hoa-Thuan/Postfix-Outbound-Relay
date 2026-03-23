import re

RE_SMTP = re.compile(
    r"(?P<month>\w+)\s+(?P<day>\d+)\s+(?P<time>\d+:\d+:\d+)"
    r".*?postfix/([^/]+/)?(smtp|lmtp|local|virtual|pipe)\[\d+\]:\s+(?P<qid>\w+):\s+"
    r"to=<(?P<to>[^>]+)>.*?"
    r"(?:delay=(?P<delay>[\d\.]+),\s+delays=(?P<delays>[\d\./]+),\s+.*?)?"
    r"status=(?P<status>\w+)(?:\s+\((?P<resp>.*?)\))?"
)

RE_QID_FROM = re.compile(
    r"postfix/([^/]+/)?(smtpd|qmgr|cleanup)\[\d+\]:\s+(?P<qid>\w+):.*?from=<(?P<from>[^>]+)>.*?(?:size=(?P<size>\d+))?"
)

RE_QID_CLIENT = re.compile(
    r"postfix/([^/]+/)?smtpd\[\d+\]:\s+(?P<qid>\w+):.*?client=[^\[]+\[(?P<ip>\d+\.\d+\.\d+\.\d+)\](?:.*?(?:sasl_username=(?P<sasl>[^,\s]+)))?"
)

RE_QID_TLS = re.compile(
    r"postfix/([^/]+/)?smtp\[\d+\]:\s+(?P<qid>\w+):.*?(?:Untrusted|Trusted|Verified|Anonymous)?\s*TLS connection established to .*?:\s+(?P<tls_ver>[A-Za-z0-9\.]+)\s+with cipher\s+(?P<cipher>[A-Za-z0-9_\-]+)"
)

tests = [
    # SMTP
    ("Aug 12 10:00:00 host postfix/smtp[123]: QID123: to=<a@b.com>, relay=abc, delay=1.5, delays=0.1/0.1/1.0/0.3, dsn=2.0.0, status=sent (250 OK)", RE_SMTP),
    ("Aug 12 10:00:00 host postfix/smtp[123]: QID123: to=<a@b.com>, status=deferred (timeout)", RE_SMTP),
    
    # FROM
    ("Aug 12 10:00:00 host postfix/qmgr[123]: QID123: from=<a@b.com>, size=1543, nrcpt=1", RE_QID_FROM),
    ("Aug 12 10:00:00 host postfix/smtpd[123]: QID123: client=unknown[10.0.0.1]", RE_QID_FROM), # should fail or match mostly? Actually smtpd might not log from here, but qmgr does.
    
    # CLIENT
    ("Aug 12 10:00:00 host postfix/smtpd[123]: QID123: client=client.com[1.2.3.4], sasl_method=LOGIN, sasl_username=user1", RE_QID_CLIENT),
    ("Aug 12 10:00:00 host postfix/smtpd[123]: QID123: client=client.com[1.2.3.4]", RE_QID_CLIENT),
    
    # TLS
    ("Aug 12 10:00:00 host postfix/smtp[123]: QID123: Untrusted TLS connection established to mx.google.com[142.250.1.1]:25: TLSv1.3 with cipher TLS_AES_256_GCM_SHA384 (256/256 bits)", RE_QID_TLS),
    ("Aug 12 10:00:00 host postfix/smtp[123]: QID123: Anonymous TLS connection established to mx.google.com[142.250.1.1]:25: TLSv1.2 with cipher ECDHE-RSA-AES256-GCM-SHA384 (256/256 bits)", RE_QID_TLS)
]

for t, regex in tests:
    m = regex.search(t)
    print(f"[{regex.pattern[:15]}...] ->", m.groupdict() if m else "NO MATCH")
