# Postfix Outbound Relay Panel – Implementation Guide

This document outlines the architecture, features, and setup instructions for the production-ready Postfix Outbound Relay Panel.

## Features Completed

### 1. IP Relay & Blacklist Manager
- **Dynamic IP Management**: Add/Edit/Delete relay IPs with weight and rate limits.
- **Persistent Blacklist Cache**: Results are cached for 24 hours to save API quota.
- **Real-time Status**: Detailed badges (CLEAN, BLACKLISTED, CACHED, ERROR) with last check timestamp in the UI.
- **Bulk Checking**: Single-click check for all IPs with an option for "Force Refresh".

### 2. Production Anti-Spam (Rspamd)
- **Comprehensive Configuration**: Supports Rate Limiting, Virus Scanning (ClamAV), URL Blacklisting, DKIM Policies, Fuzzy Hashing, and Custom Lua Rules.
- **Safety Revalidate**: Automatically runs `rspamadm configtest` before applying any changes.
- **Tabbed UI**: Organized management for General, Security, Lists, and Lua Rule settings.

### 3. Postfix Relay Optimization
- **Operational Limits**: Manage `smtpd_recipient_limit`, `message_size_limit`, and destination concurrency directly from the settings.
- **Service Sync**: Automatically reloads Postfix after applying configuration changes.

### 4. Diagnostics & Tracking
- **SMTP Test Tool**: Send real emails through the local Postfix (127.0.0.1:25) to verify IP rotation and delivery truth.
- **Real-time Trace**: Polling system that displays `journalctl` or `mail.log` entries for a specific Message-ID immediately after sending.
- **Queue Management**: View Postfix queue summary and perform a manual "Flush Queue" action.

### 4. Operational Safety
- **Atomic Writes**: Uses `core/system_safe.py` for safe file replacements.
- **Backups**: Automatically creates backups in `runtime/backups/` before modifying system configs.
- **Dry-Run Friendly**: Detection for non-Linux or non-root environments to prevent crashes during development.

---

## Installation & Setup

### Prerequisites
- **OS**: Ubuntu 20.04/22.04 or Debian 11/12 (Recommended).
- **Services**: Postfix, Rspamd, ClamAV should be installed and managed by `systemd`.
- **Python**: 3.9+

### Step 1: Clone and Install Dependencies
```bash
git clone <repo_url>
cd Postfix-Outbound-Relay
pip install -r requirements.txt
```

### Step 2: Configure System Permissions
The web panel needs permissions to write to `/etc/postfix/` and `/etc/rspamd/local.d/`.
- Ensure the user running the FastAPI app (e.g., `www-data` or `postfix`) has sudo/write access to these paths.
- Alternatively, run the panel as `root` (caution advised).

### Step 3: Set MXToolbox API Key
Go to **Settings** in the panel and enter your **MXToolbox API Key** to enable blacklist monitoring.

### Step 4: Run the Application
```bash
# Production (using uvicorn)
uvicorn app:app --host 0.0.0.0 --port 8000
```

---

## Verification Steps

1. **IP Rotation**: Add two IPs, set rotation to 10 seconds. Observe the dashboard or run `postconf smtp_bind_address` to see it changing.
2. **Blacklist**: Add an IP and click "🛡️ Check". Verify it returns a status.
3. **Anti-Spam**: Enable "Virus Scan" in Rspamd and click "Apply". Check `/etc/rspamd/local.d/antivirus.conf` for the new config.
4. **Test Mail**: Go to **Diagnostics**, send a test mail to yourself, and watch the **Real-Time Trace** log for the "sent" status.
