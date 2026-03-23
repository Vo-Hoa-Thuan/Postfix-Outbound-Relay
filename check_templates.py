import os
from fastapi.templating import Jinja2Templates
import traceback

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

def test_template(name):
    try:
        env = templates.env
        template = env.get_template(name)
        print(f"[{name}] Syntax OK")
    except Exception as e:
        print(f"[{name}] ERROR: {e}")
        traceback.print_exc()

test_template("dashboard.html")
test_template("queue.html")
test_template("rotation_history.html")
test_template("base.html")
test_template("ips.html")
test_template("rspamd.html")
test_template("settings.html")
