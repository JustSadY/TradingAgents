# One-Command Linux Deployment

Deploys TradingAgents on a Linux server via a **single command** and configures it to run as a managed `systemd` daemon.

```bash
sudo bash deploy/install.sh
```

Upon completion, navigate your browser to `http://SERVER_IP:8000` and log in using the administrator username and password printed to the console by the script.

---

## What does it do?

1.  **System Packages:** Installs Python 3.10–3.13, Node.js 20 (for Vite builds), PostgreSQL, git, and curl.
2.  **Python Virtual Environment (`.venv`):** Configures a virtual environment and installs dependencies from `backend/requirements.txt`.
    *(No need for the pip `tradingagents` package — it imports the local copy at `backend/trading_agents` directly).*
3.  **Frontend Compilation:** Compiles the React UI using `npm run build` and outputs to `frontend/dist`. The static files are served directly by the FastAPI backend (no separate web server required).
4.  **PostgreSQL Instance:** Automatically provisions a local database and a user with a secure random password.
5.  **Environment Variables (`.env`):** Generates secure random credentials for `SECRET_KEY`, `ENCRYPTION_KEY`, database credentials, and administrator accounts.
    *(Only creates the file if it does not already exist — it will never overwrite your active configuration).*
6.  **Systemd Integration:** Configures a system service that starts on boot and automatically restarts if the process crashes.
7.  **Health Check & Diagnostics:** Starts the service, runs a status query, and outputs access credentials.

The installer script is fully **idempotent**: it is safe to run repeatedly (e.g. after updating source code, run the installer again and execute `systemctl restart`).

---

## Prerequisites

*   Debian/Ubuntu (`apt` package manager) or Fedora/RHEL/Rocky Linux/AlmaLinux (`dnf` or `yum` package manager).
*   `systemd` and root (`sudo`) access privileges.

---

## Customization (Optional Environment Variables)

You can pass configuration variables inline:

```bash
sudo APP_PORT=80 ADMIN_USERNAME=patron bash deploy/install.sh
```

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `APP_PORT` | `8000` | Target port. Port `80` is supported since the systemd service has the `CAP_NET_BIND_SERVICE` flag. |
| `SERVICE_NAME` | `tradingagents` | The name of the registered systemd service. |
| `SERVICE_USER` | *Invoking user* | System user that runs the daemon. |
| `ADMIN_USERNAME` | `admin` | Initial admin portal username. |
| `ADMIN_PASSWORD` | *Random* | Custom administrator password. If left blank, one is generated and printed. |
| `NODE_MAJOR` | `20` | Major Node.js version to install. |
| `SKIP_DB` | `0` | If set to `1`, skips database setup (use this if using an external database). |
| `BUILD_FRONTEND` | `1` | If set to `0`, skips React compilation (API-only setup). |

---

## After Installation: Set Up LLM API Keys

At least one LLM provider key is required to run agent analyses. Keys are **not** stored in `.env` — they are managed in the web dashboard and stored encrypted in the database:

1.  Log in at `http://SERVER_IP:8000` with the admin credentials printed by the installer.
2.  Open **Settings → Account & API Keys** (per-user keys) or **Admin Panel → Global Settings** (server-wide defaults).
3.  Enter the provider key(s); they take effect immediately — no service restart required.

---

## Automated Updates (Dashboard "Update" Button)

The installer configures a self-updating mechanism accessible from the web UI settings:
*   The backend regularly checks the remote Git repository (`origin/main`).
*   If new commits are detected, a notification banner is displayed on the UI for logged-in users.
*   Clicking **Update** starts a detached one-shot systemd service `tradingagents-update.service`.
*   This updater service runs `git pull`, `pip install`, and compiles the React frontend as the unprivileged `RUN_USER`, then restarts the main service under root.
*   Once updated, the browser client automatically refreshes.

> **Requirements:** The project directory must be owned by the `RUN_USER` (set up automatically by the installer), and the Git repository must be public or configure saved access credentials for `RUN_USER`.

To run updates manually from the terminal (without the UI):
```bash
sudo bash deploy/update.sh
```

---

## System Management

Use standard system utilities to manage the background service:

```bash
journalctl -u tradingagents -f          # Stream active log entries
systemctl status tradingagents          # Check service health status
systemctl restart tradingagents         # Restart the application
systemctl stop tradingagents            # Terminate the application
```

---

## Uninstallation

To remove the application:

*   **Remove service only** (retains database, logs, and venv files):
    ```bash
    sudo bash deploy/uninstall.sh
    ```
*   **Purge all files** (permanently deletes the PostgreSQL database, `.env`, virtual environment, and credentials):
    ```bash
    sudo bash deploy/uninstall.sh --purge
    ```

---

## Important Operational Notes

*   **Single-Process Execution (default):** The systemd service runs a single `uvicorn` process. With the default configuration the application uses in-memory WebSocket connections and an in-process `APScheduler`; running multiple workers would duplicate schedulers and break WebSocket routing. **Do not add `--workers`** to the service definition. To offload LLM-heavy analysis runs to a separate process, set `REDIS_URL` and `ANALYSIS_QUEUE_MODE=worker` in `.env` and run an additional `arq backend.worker.WorkerSettings` service — see `docs/configuration.md`.
*   **Permissions:** If running the service under a custom user account (`SERVICE_USER`), make sure the project directory is not placed in `/root`. Store it in directories like `/opt` or `/srv`.
*   **SPA Serving:** The frontend files are served by the backend from `frontend/dist` — no separate web server (such as nginx) is required. If SSL/TLS or domain mapping is needed, configure Caddy or nginx as a reverse proxy in front of port `8000`.
