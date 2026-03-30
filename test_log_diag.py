import os
import re

LOG_PATH = "/var/log/rspamd/rspamd.log"

RE_RSPAMD_LOG = re.compile(
    r"qid: <(?P<qid>[^>]+)>.*?\(.*?: \w \((?P<score>[\d\.-]+)\/[\d\.-]+\)\s*\[(?P<symbols>[^\]]*)\]"
)

def test_rspamd():
    if not os.path.exists(LOG_PATH):
        print(f"File {LOG_PATH} NOT FOUND!")
        return

    print(f"--- TAIL OF {LOG_PATH} ---")
    
    with open(LOG_PATH, "r", errors="replace") as f:
        # read last 20 lines with qid
        lines = f.readlines()
        matched = 0
        
        for line in reversed(lines):
            if "rspamd_task_write_log" in line and "qid: <" in line:
                print("RAW: " + line.strip())
                m = RE_RSPAMD_LOG.search(line)
                if m:
                    print(f"  -> MATCHED! QID={m.group('qid')}, SCORE={m.group('score')}, SYMBOLS={m.group('symbols')}")
                    matched += 1
                else:
                    print("  -> FAILED TO MATCH REGEX!")
                
                print("-" * 50)
                if matched >= 5:
                    break

def test_postfix():
    with open("/var/log/maillog", "r", errors="replace") as f:
        lines = f.readlines()[-50:]
        for line in lines:
            if "warning: header Subject" in line:
                print("POSTFIX SUBJECT WARNING: " + line.strip())

if __name__ == "__main__":
    test_rspamd()
    test_postfix()
