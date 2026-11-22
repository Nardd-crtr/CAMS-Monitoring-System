import os, sqlite3, secrets, hashlib
from werkzeug.security import generate_password_hash
from config import Config

con = sqlite3.connect(Config.DATABASE)
con.executescript("""
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS computers(
 id INTEGER PRIMARY KEY AUTOINCREMENT, computer_name TEXT NOT NULL UNIQUE,
 ip_address TEXT NOT NULL, token_hash TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'UNKNOWN',
 last_seen TEXT, response_time REAL, monitoring_enabled INTEGER NOT NULL DEFAULT 1,
 maintenance_mode INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS monitoring_history(
 id INTEGER PRIMARY KEY AUTOINCREMENT, computer_id INTEGER NOT NULL,
 previous_status TEXT, current_status TEXT NOT NULL, timestamp TEXT NOT NULL,
 response_time REAL, event TEXT, FOREIGN KEY(computer_id) REFERENCES computers(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS admin(
 id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notifications(
 id INTEGER PRIMARY KEY AUTOINCREMENT, computer_id INTEGER,
 message TEXT NOT NULL, notification_type TEXT NOT NULL, timestamp TEXT NOT NULL,
 is_read INTEGER NOT NULL DEFAULT 0,
 FOREIGN KEY(computer_id) REFERENCES computers(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS settings(
 id INTEGER PRIMARY KEY AUTOINCREMENT, setting_name TEXT NOT NULL UNIQUE, setting_value TEXT NOT NULL
);
""")
from datetime import datetime, timezone
now = datetime.now(timezone.utc).isoformat()
for i in range(1,11):
    name=f"PC-{i:02d}"
    if not con.execute("SELECT 1 FROM computers WHERE computer_name=?", (name,)).fetchone():
        token=secrets.token_urlsafe(32)
        con.execute("""INSERT INTO computers(computer_name,ip_address,token_hash,status,created_at)
                       VALUES(?,?,?,?,?)""",(name,f"192.168.1.{100+i}",hashlib.sha256(token.encode()).hexdigest(),"UNKNOWN",now))
        print(f"{name} agent token: {token}")
if not con.execute("SELECT 1 FROM admin WHERE username='admin'").fetchone():
    password=os.environ.get("CAMS_ADMIN_PASSWORD","ChangeMe-Now-2026!")
    con.execute("INSERT INTO admin(username,password_hash) VALUES(?,?)",("admin",generate_password_hash(password)))
    print(f"Initial administrator: admin / {password}")
defaults={"monitor_interval":"5","offline_threshold":"3","automatic_monitoring":"true",
          "system_name":"CAMS • Computer Availability","notify_offline":"true","notify_reconnect":"true"}
for k,v in defaults.items(): con.execute("INSERT OR IGNORE INTO settings(setting_name,setting_value) VALUES(?,?)",(k,v))
con.commit(); con.close()
print("\\nDatabase initialized. Copy each printed token into that PC's agent_config.json.")
