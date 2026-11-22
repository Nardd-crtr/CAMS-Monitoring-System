import os, sqlite3, hashlib, time, threading, csv, io, json
from datetime import datetime, timezone, timedelta
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response, send_file, flash
from werkzeug.security import check_password_hash, generate_password_hash
from config import Config

app=Flask(__name__); app.config.from_object(Config)
def db():
    c=sqlite3.connect(Config.DATABASE, timeout=10); c.row_factory=sqlite3.Row; c.execute("PRAGMA foreign_keys=ON"); return c
def now(): return datetime.now(timezone.utc).isoformat()
def log_event(c, cid, old, new, ms=None, event="status"):
    c.execute("INSERT INTO monitoring_history(computer_id,previous_status,current_status,timestamp,response_time,event) VALUES(?,?,?,?,?,?)",
              (cid,old,new,now(),ms,event))
def notify(c,cid,msg,kind):
    c.execute("INSERT INTO notifications(computer_id,message,notification_type,timestamp) VALUES(?,?,?,?)",(cid,msg,kind,now()))
def admin_required(f):
    @wraps(f)
    def w(*a,**kw):
        if not session.get("admin_id"): return jsonify(error="Authentication required"),401
        return f(*a,**kw)
    return w
@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        c=db(); row=c.execute("SELECT * FROM admin WHERE username=?",(request.form.get("username",""),)).fetchone(); c.close()
        if row and check_password_hash(row["password_hash"],request.form.get("password","")):
            session.clear(); session["admin_id"]=row["id"]; session["username"]=row["username"]
            session.permanent=True
            return redirect(url_for("index"))
        flash("Invalid username or password","error")
    return render_template("login.html")
@app.route("/logout")
def logout(): session.clear(); return redirect(url_for("login"))
@app.route("/")
def index():
    if not session.get("admin_id"): return redirect(url_for("login"))
    return render_template("index.html",username=session.get("username"))
@app.post("/api/heartbeat")
def heartbeat():
    data=request.get_json(silent=True) or {}
    name=data.get("computer_name",""); token=request.headers.get("X-CAMS-TOKEN","")
    if not name or not token: return jsonify(error="Missing computer name or token"),400
    c=db(); row=c.execute("SELECT * FROM computers WHERE computer_name=?",(name,)).fetchone()
    if not row or not hashlib.sha256(token.encode()).hexdigest()==row["token_hash"]:
        c.close(); return jsonify(error="Invalid credentials"),401
    if not row["monitoring_enabled"] or row["maintenance_mode"]:
        c.close(); return jsonify(accepted=False,reason="monitoring disabled or maintenance"),200
    ms=data.get("response_time_ms")
    old=row["status"]
    c.execute("UPDATE computers SET status='AVAILABLE',last_seen=?,response_time=? WHERE id=?",(now(),ms,row["id"]))
    if old!="AVAILABLE":
        log_event(c,row["id"],old,"AVAILABLE",ms,"heartbeat")
        notify(c,row["id"],f"{name} is AVAILABLE","reconnect" if old=="NOT AVAILABLE" else "online")
    else:
        c.execute("INSERT INTO monitoring_history(computer_id,previous_status,current_status,timestamp,response_time,event) VALUES(?,?,?,?,?,?)",
                  (row["id"],old,old,now(),ms,"heartbeat"))
    c.commit(); c.close()
    return jsonify(accepted=True,server_time=now())
@app.route("/api/state")
@admin_required
def state():
    c=db()
    computers=[dict(r) for r in c.execute("SELECT id,computer_name,ip_address,status,last_seen,response_time,monitoring_enabled,maintenance_mode FROM computers ORDER BY computer_name")]
    hist=[dict(r) for r in c.execute("""SELECT h.*,p.computer_name FROM monitoring_history h JOIN computers p ON p.id=h.computer_id ORDER BY h.id DESC LIMIT 200""")]
    notes=[dict(r) for r in c.execute("""SELECT n.*,p.computer_name FROM notifications n LEFT JOIN computers p ON p.id=n.computer_id ORDER BY n.id DESC LIMIT 50""")]
    settings={r["setting_name"]:r["setting_value"] for r in c.execute("SELECT * FROM settings")}
    c.close()
    available=sum(x["status"]=="AVAILABLE" for x in computers)
    unavailable=sum(x["status"]=="NOT AVAILABLE" for x in computers)
    return jsonify(computers=computers,history=hist,notifications=notes,settings=settings,
                   stats={"total":len(computers),"available":available,"unavailable":unavailable,
                          "maintenance":sum(x["status"]=="MAINTENANCE" for x in computers),
                          "percentage":round(available/len(computers)*100,1) if computers else 0},
                   server_time=now())
@app.route("/api/computers",methods=["POST"])
@admin_required
def add_computer():
    d=request.get_json() or {}; name=str(d.get("computer_name","")).strip(); ip=str(d.get("ip_address","")).strip()
    import re
    if not re.fullmatch(r"[A-Za-z0-9_-]{2,40}",name) or not re.fullmatch(r"[A-Fa-f0-9:.]{3,45}",ip):
        return jsonify(error="Enter a valid computer name and IPv4/IPv6 address"),400
    import secrets
    token=secrets.token_urlsafe(32); c=db()
    try:
        cur=c.execute("INSERT INTO computers(computer_name,ip_address,token_hash,status,created_at) VALUES(?,?,?,'UNKNOWN',?)",
                      (name,ip,hashlib.sha256(token.encode()).hexdigest(),now()))
        log_event(c,cur.lastrowid,None,"UNKNOWN",event="registered"); c.commit()
    except sqlite3.IntegrityError: c.close(); return jsonify(error="Computer name already exists"),409
    c.close(); return jsonify(ok=True,computer_name=name,agent_token=token),201
@app.route("/api/computers/<int:cid>",methods=["PUT","DELETE"])
@admin_required
def manage_computer(cid):
    c=db(); row=c.execute("SELECT * FROM computers WHERE id=?",(cid,)).fetchone()
    if not row: c.close(); return jsonify(error="Not found"),404
    if request.method=="DELETE":
        c.execute("DELETE FROM computers WHERE id=?",(cid,)); c.commit(); c.close(); return jsonify(ok=True)
    d=request.get_json() or {}; name=str(d.get("computer_name",row["computer_name"])).strip()
    ip=str(d.get("ip_address",row["ip_address"])).strip()
    enabled=int(bool(d.get("monitoring_enabled",row["monitoring_enabled"])))
    maintenance=int(bool(d.get("maintenance_mode",row["maintenance_mode"])))
    old=row["status"]; new="MAINTENANCE" if maintenance else ("UNKNOWN" if old=="MAINTENANCE" else old)
    c.execute("UPDATE computers SET computer_name=?,ip_address=?,monitoring_enabled=?,maintenance_mode=?,status=? WHERE id=?",
              (name,ip,enabled,maintenance,new,cid))
    if new!=old:
        log_event(c,cid,old,new,event="admin"); notify(c,cid,f"{name} marked {new}","maintenance" if maintenance else "status")
    c.commit(); c.close(); return jsonify(ok=True)
@app.post("/api/settings")
@admin_required
def save_settings():
    d=request.get_json() or {}; allowed={"monitor_interval","offline_threshold","automatic_monitoring","system_name","notify_offline","notify_reconnect"}
    c=db()
    for k,v in d.items():
        if k in allowed: c.execute("INSERT INTO settings(setting_name,setting_value) VALUES(?,?) ON CONFLICT(setting_name) DO UPDATE SET setting_value=excluded.setting_value",(k,str(v)))
    c.commit(); c.close(); return jsonify(ok=True)
@app.post("/api/notifications/read")
@admin_required
def read_notifications():
    c=db(); c.execute("UPDATE notifications SET is_read=1"); c.commit(); c.close(); return jsonify(ok=True)
@app.route("/api/export.csv")
@admin_required
def export_csv():
    c=db(); rows=c.execute("""SELECT p.computer_name,h.previous_status,h.current_status,h.timestamp,h.response_time,h.event
                               FROM monitoring_history h JOIN computers p ON p.id=h.computer_id ORDER BY h.timestamp DESC""").fetchall(); c.close()
    s=io.StringIO(); w=csv.writer(s); w.writerow(["Computer","Previous status","Current status","Timestamp (UTC)","Response ms","Event"])
    for r in rows: w.writerow(list(r))
    return Response("\\ufeff"+s.getvalue(),mimetype="text/csv",headers={"Content-Disposition":"attachment; filename=cams-report.csv"})
def monitor_loop():
    while True:
        try:
            c=db(); settings={r["setting_name"]:r["setting_value"] for r in c.execute("SELECT * FROM settings")}
            interval=max(2,int(settings.get("monitor_interval","5"))); threshold=max(1,int(settings.get("offline_threshold","3")))
            if settings.get("automatic_monitoring","true").lower()=="true":
                cutoff=datetime.now(timezone.utc)-timedelta(seconds=interval*threshold)
                rows=c.execute("SELECT * FROM computers WHERE monitoring_enabled=1 AND maintenance_mode=0 AND status!='NOT AVAILABLE' AND status!='UNKNOWN'").fetchall()
                for r in rows:
                    try: last=datetime.fromisoformat(r["last_seen"])
                    except: continue
                    if last < cutoff:
                        c.execute("UPDATE computers SET status='NOT AVAILABLE' WHERE id=?",(r["id"],))
                        log_event(c,r["id"],r["status"],"NOT AVAILABLE",r["response_time"],"missed heartbeat")
                        notify(c,r["id"],f"{r['computer_name']} is NOT AVAILABLE","offline")
            c.commit(); c.close()
            time.sleep(interval)
        except Exception:
            time.sleep(5)
threading.Thread(target=monitor_loop,daemon=True).start()
if __name__=="__main__":
    app.run(host=Config.HOST,port=Config.PORT,debug=False,threaded=True)
