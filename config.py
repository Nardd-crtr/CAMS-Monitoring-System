import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
class Config:
    SECRET_KEY = os.environ.get("CAMS_SECRET_KEY", "CHANGE-THIS-TO-A-LONG-RANDOM-SECRET")
    DATABASE = os.path.join(BASE_DIR, "cams.sqlite3")
    HOST = os.environ.get("CAMS_HOST", "0.0.0.0")
    PORT = int(os.environ.get("CAMS_PORT", "5000"))
    MONITOR_INTERVAL = 5
    OFFLINE_THRESHOLD = 3
