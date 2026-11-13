# Dialog Access Review — Coolify Git Deployment

An independent Docker Compose stack with a responsive dark dashboard, FastAPI, PostgreSQL, and a TCP syslog receiver. Designed to live beside existing Coolify projects without touching existing databases.

## What is functional
- Admin sign-in using a server-validated 8-hour token
- Live overview, event explorer, devices, observed users, and rule-based failed-login alerts
- TCP syslog listener on port 5514 storing messages in PostgreSQL
- Dynamic observation of devices; no hardcoded sample data
- Collector is **bound to 127.0.0.1 on the VPS by default**, not exposed publicly

## IMPORTANT LIMITATIONS
- **WireGuard is not automatically installed/configured on the VPS host.** A privileged host operation is required, outside the Coolify app. Once `wg0` with `10.77.0.1` exists on the VPS, change `SYSLOG_BIND_IP` to `10.77.0.1` and redeploy the collector. Confirm interface binding works on your Docker host and firewall restricts traffic to VPN. Depending on Docker firewall behavior, DOCKER-USER filtering may also be required. Do not bind to 0.0.0.0.
- Windows Event Forwarding (WEF) requires Windows Event Collector (WEC) setup and a separate syslog bridge on Windows; neither is configured by this app.
- This is a **prototype**, not a production SIEM. Parsing is heuristic; device_id from syslog is claimed by source, user parsing is best-effort, and normalized event timestamps currently use ingestion time. Device status is based on event arrival, not heartbeat. Logging alone cannot determine permissions or exact employee work time. Some syslog TCP senders use octet-counted framing not supported by this line-delimited listener.
- Dashboard risk alerts are rules, **not yet AI**.
- VPN encryption secures transport, not necessarily device identity or untrusted message integrity. Additional authentication and audit controls are needed for production.

## Browser-only GitHub / Coolify deployment
1. Download the ZIP from ChatGPT, extract locally.
2. Open github.com -> New repository -> name `dialog-access-review` -> create a **private** repository. In GitHub use `Add file` -> `Upload files` and drag **the contents of the extracted folder** (including `docker-compose.yml`, `api/`, `frontend/`, `collector/`). Commit. GitHub's web uploader supports folder drag-and-drop on compatible desktop browsers. Alternatively import files using GitHub Desktop, without commands.
3. In Coolify: Project -> + New -> Private Repository (GitHub App or deploy key) -> select repo -> Build Pack / Build Strategy = **Docker Compose**. Base directory `/`, Docker Compose location `/docker-compose.yml` (use relative `docker-compose.yml` if that is what your version expects).
4. Environment Variables -> add `POSTGRES_PASSWORD`, `ADMIN_PASSWORD`, `JWT_SECRET`, `ADMIN_USERNAME=admin`, `SYSLOG_BIND_IP=127.0.0.1`. Generate unique strong secrets in your password manager. Minimum admin password 12 chars, JWT secret 32 chars. **Do not upload .env containing real secrets to GitHub.**
5. Under Domains, assign your HTTPS hostname **only to service `web` on internal port 80**. Do not add domains to db, api, or collector. Example: `https://logs.example.com:80` in Coolify's Compose domain format; browser URL is `https://logs.example.com`.
6. Click Deploy. The dashboard login should appear. Admin credentials are the environment variables you entered. Health endpoint accessible via the reverse proxy at `https://logs.example.com/api/health`. (The API's health endpoint is unauthenticated.)
7. Allow webhook/auto-deploy on Git commits in Coolify if desired.

Official Coolify Compose guide: https://coolify.io/docs/applications/builds/docker-compose

## Add Linux forwarding after VPN is configured
On Ubuntu client, install `wireguard` and `rsyslog`, provision client key + peer VPN connection to the VPS and test its tunnel. Configure `/etc/rsyslog.d/60-dialog.conf`:

```conf
*.* action(type="omfwd" target="10.77.0.1" port="5514" protocol="tcp" action.resumeRetryCount="-1" queue.type="linkedList" queue.filename="dialogfwd" queue.saveOnShutdown="on")
```

Run `sudo rsyslogd -N1 && sudo systemctl restart rsyslog`. Send `logger -t dialog-test 'Ubuntu log forwarded'` and check Event Explorer. Configure a dedicated log source allowlist and retention policy for real systems.

## Windows notes
WEF sends event logs to Windows WEC, not directly to Ubuntu. Use Windows native WEC setup (admin setup necessary) then a bridge capable of exporting WEC's ForwardedEvents via syslog over the WireGuard VPN. Consider NXLog/Winlogbeat alternatives if WEC is difficult in a non-domain lab. Configure only authorized logging on enrolled computers.

## Security and operation notes
- Use HTTPS and a private Git repository; never put credentials or WireGuard private keys in Git.
- Database volume `db_data` is persistent; set backups in Coolify. The app will create `events` table and indexes at API startup.
- Current ingestion limits each line to 64KB and stores 8KB text; raw logs may contain personal data. Define data retention, legal authorization, and consent notices. Do not collect passwords or sensitive content unnecessarily.
- Do not open port 5514 publicly. Docker published port firewall paths may bypass UFW; explicitly verify host port binding and Docker firewall rules.
- UI session uses sessionStorage; never run the dashboard without TLS.
- Each device needs a unique VPN key and documented owner. Rotate and revoke lost keys.
- For a local test when VPN is not installed, receiver is localhost only (127.0.0.1:5514) and dashboard initially shows zero events; this is expected.
