import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "runtime", "reader_state.json")
PARSED_LOG = os.path.join(BASE_DIR, "logs", "parsed.log")

def diagnostic():
    if not os.path.exists(PARSED_LOG):
        print("NO parsed.log FOUND")
        return
        
    print("--- LAST 5 PARSED ENTRIES ---")
    with open(PARSED_LOG, "r") as f:
        lines = f.readlines()
        for ln in lines[-5:]:
            try:
                data = json.loads(ln.strip())
                print(f"[{data.get('time')}] QID: {data.get('qid')} -> SCORE: {data.get('spam_score')} | SYMBOLS: {str(data.get('spam_symbols'))[:30]}")
            except:
                pass
                
    if not os.path.exists(STATE_FILE):
        print("NO state.json FOUND")
        return
        
    print("\n--- STATE MAP INFO ---")
    with open(STATE_FILE, "r") as f:
        state = json.load(f)
        qmap = state.get("qid_map", {})
        print(f"Total QIDs in memory: {len(qmap)}")
        
        # Check if recent QIDs had score populated
        scored_qids = [q for q, v in qmap.items() if isinstance(v, dict) and "spam_score" in v]
        print(f"Total QIDs with spam_score: {len(scored_qids)}")
        for sq in scored_qids[-3:]:
             print(f"  {sq}: {qmap[sq]['spam_score']}")

if __name__ == "__main__":
    diagnostic()
