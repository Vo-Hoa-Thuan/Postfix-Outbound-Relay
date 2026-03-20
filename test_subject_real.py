import re

lines = [
    "Mar 20 23:36:01 relay postfix/cleanup[2059]: EEB73417678F: warning: header Subject: =?UTF-8?Q?Xin_Ch=C3=A0o?= from unknown[103.3.244.183]; from=<tuyendung@benhvienyhct.com> to=<vohoathuan.82004@gmail.com> proto=ESMTP helo=<filter1.sieutocviet.top>",
    "Mar 20 23:38:56 relay postfix/cleanup[3657]: 09177417678F: warning: header Subject: =?UTF-8?Q?Re=3A_Xin_Ch=C3=A0o?= from unknown[103.3.244.183]; from=<tuyendung@benhvienyhct.com> to=<vohoathuan.82004@gmail.com> proto=ESMTP helo=<filter1.sieutocviet.top>",
    "Mar 20 23:42:44 relay postfix/cleanup[5931]: 068504176791: warning: header Subject: Re: Test mail from unknown[103.3.244.183]; from=<tuyendung@benhvienyhct.com> to=<vohoathuan.82004@gmail.com> proto=ESMTP helo=<filter1.sieutocviet.top>"
]

RE_QID_SUBJECT = re.compile(
    r"postfix/([^/]+/)?cleanup\[\d+\]:\s+(?P<qid>\w+):.*?header Subject:\s+(?P<subject>.*?)(?=\s+from\s+[^;]+;|\s+from=|\s+proto=|\s+helo=|$)"
)

for line in lines:
    m = RE_QID_SUBJECT.search(line)
    if m:
        print(f"Subject: {m.group('subject')}")
    else:
        print("FAILED MATCH")

