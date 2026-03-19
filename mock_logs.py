import os
import json
import random
from datetime import datetime, timedelta

log_path = os.path.join(os.path.dirname(__file__), "logs", "parsed.log")
os.makedirs(os.path.dirname(log_path), exist_ok=True)

now = datetime.now()
logs = []

statuses = ["sent", "sent", "sent", "deferred", "bounced"]
domains = ["gmail.com", "yahoo.com", "outlook.com", "tcs.com.vn", "aircambodia.com"]
subjects = [
    "Booking Angkorair",
    "Flight plan K6931 on 19 MAR 2026",
    "Re: AIR CAMBODIA",
    "[Spam] Fat Burning Bread",
    "New Message: Warning: 200 E-Mails have just been sent",
    "Undelivered Mail Returned to Sender",
    "Invoice from SMD Groups",
]

for i in range(15):
    t = now - timedelta(minutes=random.randint(0, 60))
    st = random.choice(statuses)
    entry = {
        "time": t.strftime("%Y-%m-%d %H:%M:%S"),
        "from": f"test_{i}@{random.choice(domains)}",
        "to": f"recipient_{i}@{random.choice(domains)}",
        "subject": random.choice(subjects),
        "local_ip": f"103.3.244.{random.randint(110, 115)}",
        "status": st,
        "msgid": f"<random-{i}@relay.local>",
        "qid": f"{random.randint(100000,999999)}",
        "response": "250 2.0.0 OK mx.test.com" if st=="sent" else "451 4.3.2 Try again later"
    }
    logs.append(json.dumps(entry))

# Sort by time
logs_objs = [json.loads(l) for l in logs]
logs_objs.sort(key=lambda x: x["time"])
logs = [json.dumps(l) for l in logs_objs]

with open(log_path, "w") as f:
    f.write("\n".join(logs) + "\n")

print("Added 15 mock logs with subjects.")
