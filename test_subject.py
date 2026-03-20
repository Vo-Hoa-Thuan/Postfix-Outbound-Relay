import re

logs = [
    "Mar 20 19:47:06 server postfix/cleanup[12345]: 3ABC123: warning: header Subject: Test Subject from local; from=<a@b> to=<c@d>",
    "Mar 20 19:47:06 server postfix/cleanup[12345]: 3ABC123: warning: header Subject: Subject without anything else",
    "Mar 20 19:47:06 server postfix/cleanup[12345]: 3ABC123: warning: header Subject: My subject from source; from=<x@y.com> to=<z@w.com> proto=ESMTP helo=<test>"
]

RE_QID_SUBJECT = re.compile(r"postfix/([^/]+/)?cleanup\[\d+\]:\s+(?P<qid>\w+):.*?header Subject:\s+(?P<subject>.*?)(?=\s+from\s+[^;]+;|\s+from=|\s+proto=|\s+helo=|$)")

for log in logs:
    m = RE_QID_SUBJECT.search(log)
    if m:
        print(f"MATCH: {m.group('subject')}")
    else:
        print("NO MATCH")
