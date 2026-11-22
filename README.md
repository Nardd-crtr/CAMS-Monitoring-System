# CAMS — Computer Availability Monitoring System

A Flask + SQLite LAN monitoring dashboard with authenticated HTTP heartbeat agents, a dark/neon-green responsive UI, event history, notifications, settings and CSV export.

## Requirements
- Windows 10/11 or Linux server with Python 3.10+
- All client PCs and server can communicate over the LAN
- Allow inbound TCP port 5000 on the server firewall, restricted to your trusted LAN

## Server installation (Windows)
1. Extract this folder.
2. Open PowerShell in the project directory.
3. Create and activate a virtual environment (recommended):
   `python -m venv .venv`
   `.\.venv\Scripts\Activate.ps1`
4. Install packages: `pip install -r requirements.txt`
5. Set a strong secret and initial admin password before initializing:
   `$env:CAMS_SECRET_KEY = "replace-with-a-long-random-secret"`
   `$env:CAMS_ADMIN_PASSWORD = "use-a-unique-strong-password"`
6. Initialize SQLite and create ten UNKNOWN endpoints:
   `python init_db.py`
   **Copy the ten printed agent tokens securely.** They are shown only during first registration; only token hashes are stored.
7. Find the server LAN IPv4 address with `ipconfig` (for example `192.168.1.10`).
8. Permit inbound TCP 5000 in Windows Defender Firewall, preferably only on the Private network profile and limited to the client subnet.
9. Start: `python app.py`
10. Open `http://127.0.0.1:5000` on the server, or `http://SERVER-LAN-IP:5000` from an authorized LAN device.

Initial username is `admin`; the password is the value of `CAMS_ADMIN_PASSWORD` used at first initialization. If not set, the development default printed by `init_db.py` is `ChangeMe-Now-2026!`. Change it immediately for any non-test use.

## Install an agent on each client
1. Copy the `agent` directory to each client PC. Python 3.10+ is required.
2. Copy `agent_config.example.json` to `agent_config.json`.
3. Set `server_url` to the server LAN address, e.g. `http://192.168.1.10:5000`.
4. Set `computer_name` to the exact registered name (PC-01 ... PC-10).
5. Paste that computer's unique token printed by `init_db.py`.
6. Keep `interval_seconds` at 5 (match the server setting).
7. Run `python agent.py`. For unattended use, configure Windows Task Scheduler to start it at user/system startup and restart on failure.

Each agent sends an authenticated HTTP heartbeat every five seconds. The server records a successful heartbeat and round-trip response measurement (the current sample agent prints RTT locally; server-side response_time is left null in this starter agent). The server declares NOT AVAILABLE after the configured interval × missed-heartbeat threshold has elapsed since the last accepted heartbeat. A missed heartbeat can mean the client is off, the network path is down, the agent stopped, or the server is unreachable; it does not prove the PC is powered off.

## Security and operational notes
- The default Flask development server is suitable for a trusted LAN test, not public exposure. Do not port-forward it to the internet.
- Use HTTPS and a production WSGI server/reverse proxy for production deployment. Restrict firewall access to the management subnet.
- Change `SECRET_KEY` and the initial admin password. Back up `cams.sqlite3`.
- Heartbeat tokens are per-computer bearer credentials. Keep them private and rotate by re-registering/implementing token rotation if compromised.
- Admin endpoints require a session. Use a strong password and trusted network. For production, add CSRF protection, rate limiting, HTTPS, and an administrator password-change flow.
- The agent currently measures/prints local RTT. The backend response-time field is reserved; see note below. No ping fallback is used, so status means an authenticated agent heartbeat was received, not merely ICMP reachability.

## Features
- Ten initial PCs (192.168.1.101–110), initially UNKNOWN, never falsely online.
- Login with Werkzeug password hashing and HTTP-only Flask session cookie defaults.
- Computer add/edit/delete, enable/disable monitoring and maintenance mode.
- Background offline detection independent of the viewed page.
- Dashboard polls API every two seconds; monitoring agents heartbeat every five seconds.
- Searchable history, notifications, live stats, Chart.js charts, CSV export and settings.

## Troubleshooting
- If agents cannot reach server, verify server IP, subnet, firewall TCP 5000 and `server_url`.
- If an endpoint remains UNKNOWN, verify the agent token and exact computer name.
- If all endpoints go offline simultaneously, check the server process/network before assuming all clients failed.
