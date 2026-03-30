import re

s = "RAW: 2026-03-30 08:08:42 #20124(normal) <92984e>; task; rspamd_task_write_log: id: <fc88932669258286f5654e85ade9afce@benhvienyhct.com>, qid: <0E717441A450>, ip: 103.3.244.183, from: <benhvien@benhvienyhct.com>, (default: F (no action): [1.60/15.00] [HFILTER_HOSTNAME_UNKNOWN(2.50){},DMARC_POLICY_ALLOW(-0.50){benhvienyhct.com;none;}])"

reg = re.compile(r"qid: <(?P<qid>[^>]+)>.*?\(.*?[A-Z]\s*\([^)]*\):\s*\[(?P<score>[\d\.-]+)\/[\d\.-]+\]\s*\[(?P<symbols>.*?)\]\)")

m = reg.search(s)
if m:
    print(m.groupdict())
else:
    print("FAILED")
    
# Test simpler
reg2 = re.compile(r"qid: <(?P<qid>[^>]+)>.*?: \[(?P<score>[\d\.-]+)/[\d\.-]+\] \[(?P<symbols>.*?)\]")
m2 = reg2.search(s)
if m2:
    print("SIMPLER: ", m2.groupdict())
else:
    print("SIMPLER FAILED")
