# Installation & Setup Guide

TradingAgents supports three deployment modes: a one-command Linux/systemd installation, Docker Compose, and a manual developer setup. This guide reflects the current `main` branch behavior.

---

## 1. Production Linux Server Deployment

For Debian/Ubuntu and Fedora/RHEL-family servers, the supported production path is the installer in `deploy/install.sh`.

```bash
sudo bash deploy/install.sh
```

The installer provisions the supported Python runtime, Node.js 20, PostgreSQL, the project virtual environment, frontend production build, root `.env`, and the `systemd` service. It is designed to be idempotent and can be rerun after source updates.

### Supported installer variables

```bash
sudo APP_PORT=80 ADMIN_USERNAME=manager bash deploy/install.sh
```

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `APP_PORT` | `8000` | HTTP port used by the FastAPI service. |
| `SERVICE_NAME` | `tradingagents` | `systemd` service name. |
| `SERVICE_USER` | invoking user | OS user that runs the application. |
| `ADMIN_USERNAME` | `admin` | Initial administrator username. |
| `ADMIN_PASSWORD` | random | Optional initial administrator password. |
| `NODE_MAJOR` | `20` | Node.js major version installed for frontend builds. |
| `SKIP_DB` | `0` | Set to `1` when PostgreSQL is managed externally. |
| `BUILD_FRONTEND` | `1` | Set to `0` for API-only installation. |

After installation, use the URL and administrator credentials printed by the installer. The production frontend is served directly by FastAPI from `frontend/dist`; a separate nginx instance is not required unless you want TLS/domain reverse proxying.

### LLM and data-provider keys

LLM and provider credentials are **not** configured in `.env`. Add them from the Web UI after logging in:

- **Preferences / Settings → Account & API Keys** for per-user keys.
- **Admin Panel → Global Settings** for server-wide defaults and server-scoped tools.

Sensitive values are stored encrypted in PostgreSQL and take effect without restarting the service.

### Optional worker mode

The default Linux install runs analyses in the web process. For a separate analysis worker, configure Redis and worker mode in `.env`:

```ini
REDIS_URL=redis://localhost:6379/0
ANALYSIS_QUEUE_MODE=worker
```

Then run an additional worker service using:

```bash
arq backend.worker.WorkerSettings
```

Redis is also used for cross-process analysis events, task ownership, cancellation, and WebSocket fan-out.

For detailed systemd and updater behavior, see [`../deploy/README.md`](../deploy/README.md).

---

## 2. Docker Compose Deployment

Docker Compose is the easiest way to run the complete multi-process stack.

### Prepare the environment

```bash
cp .env.example .env
```

At minimum, review and set the infrastructure values required by Compose and production security. In particular:

```ini
DB_PASSWORD=<strong-postgres-password>
SECRET_KEY=<random-secret>
ENCRYPTION_KEY=<fernet-key>
ADMIN_PASSWORD_HASH=<bcrypt-hash>
```

`DB_PASSWORD` is required by the current `docker-compose.yml`. `METRICS_TOKEN` is optional; when empty, the backend `/metrics` endpoint stays disabled.

Do not put LLM, Pinecone, Reddit, Alpha Vantage, or SearXNG credentials into `.env` unless a specific server-managed integration explicitly documents an environment variable. User/provider settings are normally configured in the Web UI.

### Start the stack

```bash
docker compose up -d --build
```

The current Compose stack includes:

| Service | Purpose |
| :--- | :--- |
| `postgres` | Primary PostgreSQL database. |
| `redis` | Worker queue, task registry, and event fan-out. |
| `backend` | FastAPI web/API process. |
| `worker` | Dedicated `arq` analysis worker. |
| `frontend` | nginx-served React production build and public reverse proxy. |
| `prometheus` | Metrics collection. |
| `postgres-exporter` | PostgreSQL Prometheus metrics. |
| `redis-exporter` | Redis Prometheus metrics. |

### Local endpoints

- Frontend: `http://localhost:5173`
- Backend/Swagger from the Docker host: `http://localhost:8000/docs`
- Prometheus: `http://localhost:9090`
- PostgreSQL exporter: `http://localhost:9187`
- Redis exporter: `http://localhost:9121`

The backend and monitoring ports are intentionally bound to loopback in the Compose file. Public application traffic should go through the frontend proxy. If remote monitoring access is required, put an authenticated reverse proxy or VPN in front of the monitoring endpoints rather than publishing them directly.

Docker forces:

```ini
REDIS_URL=redis://redis:6379/0
ANALYSIS_QUEUE_MODE=worker
```

so long-running analyses execute in the dedicated worker while progress events return to the backend over Redis.

---

## 3. Manual Developer Setup

### Prerequisites

- Python 3.11–3.13 recommended for the backend.
- Node.js 20+ for the frontend.
- PostgreSQL running locally or remotely.

### Backend

From the repository root:

```bash
python -m venv .venv
```

Activate it:

```bash
# Windows PowerShell
.venv\Scripts\activate

# Linux/macOS
source .venv/bin/activate
```

Install dependencies:

```bash
cd backend && uv sync --frozen
```

Create the root environment file:

```bash
cp .env.example .env
```

Set at least a valid PostgreSQL URL and secure development secrets as appropriate:

```ini
DATABASE_URL=postgresql+asyncpg://youruser:yourpass@localhost:5432/tradingagents
```

Start the API:

```bash
uvicorn backend.main:app --reload --port 8000
```

The application creates missing tables and applies supported additive startup migrations automatically. Databases explicitly managed by Alembic defer to Alembic; see `backend/alembic/README.md` for that workflow.

Swagger is available at `http://localhost:8000/docs`.

### Frontend

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

The Vite development server is available at `http://localhost:5173` and proxies `/api`, `/auth`, and `/ws` requests to the backend on port `8000`.

### Configure provider credentials

Once the UI is running, log in and configure LLM/provider credentials from the application settings. They are stored in the database, not in the developer `.env` file.

---

## 4. Updating an Installed Linux Server

The Linux installer configures the dashboard self-updater. When a newer `origin/main` commit is detected, an administrator can start the update from the UI. The updater uses an isolated worktree, installs dependencies, builds the frontend, handles migrations, switches the release, and rolls back if the restarted service fails.

To start the same update flow manually:

```bash
sudo bash deploy/update.sh
```

---

## 5. Configuration Reference

For environment variables, API/provider configuration, Redis worker mode, observability, and runtime settings, see [`configuration.md`](configuration.md).