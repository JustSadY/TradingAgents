# Installation & Setup Guide

TradingAgents can be deployed in multiple environments depending on your use case. Below are detailed guides for deploying on Linux production servers, using Docker Compose, or configuring a local manual development workspace.

---

## 🚀 1. Production Linux Server Deployment (One-Click Setup)

This is the recommended method for Linux environments (Ubuntu, Debian, CentOS, AlmaLinux, Rocky Linux, Fedora, etc.). The installer script automatically handles:
1.  System packages installation (Python 3.10+, Node.js 20, PostgreSQL, git, curl).
2.  Setting up a PostgreSQL user and database with secure random credentials.
3.  Generating a Python Virtual Environment (`.venv`) and installing `backend/requirements.txt`.
4.  Compiling the React frontend bundle (`npm run build`).
5.  Creating a secure, randomized `.env` configuration file.
6.  Registering and starting a `systemd` background daemon to keep the application running.

### Quick Start Installation Command:
Execute the command below on your clean server:

```bash
sudo bash deploy/install.sh
```

### Customizing Installer Parameters:
You can control the installer's behavior by passing environment parameters:

```bash
sudo APP_PORT=80 ADMIN_USERNAME=manager bash deploy/install.sh
```

#### Supported Installer Variables:
| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `APP_PORT` | `8000` | The port the application listens on. |
| `SERVICE_NAME` | `tradingagents` | The name of the registered `systemd` daemon. |
| `ADMIN_USERNAME` | `admin` | The initial administrator username. |
| `ADMIN_PASSWORD` | *Random* | Custom password; if empty, a random password is generated and printed. |
| `SKIP_DB` | `0` | If set to `1`, skips local PostgreSQL setup (useful if using an external DB). |
| `BUILD_FRONTEND` | `1` | If set to `0`, skips React UI compilation (API-only setup). |

### Post-Installation Key Configuration:
To activate agent analysis, you can configure LLM provider keys (OpenAI, Anthropic, Gemini, etc.) directly in the Web UI under **Settings → API Keys** (or via the **Admin Panel → User API Keys** for specific users). 

---

## 🐳 2. Docker Compose Deployment

Ensure you have Docker and Docker Compose installed.

1.  Clone the repository and copy the environment variables example:
    ```bash
    cp .env.example .env
    ```
2.  Edit the `.env` file to set the infrastructure secrets (`SECRET_KEY`, `ENCRYPTION_KEY`, `ADMIN_PASSWORD_HASH`). LLM and data-provider keys are **not** environment variables — add them later in the Web UI (Settings → Account & API Keys).
3.  Build and launch the container ecosystem:
    ```bash
    docker-compose up -d --build
    ```
    The compose file starts PostgreSQL, Redis, the backend, a dedicated **arq analysis worker** (`ANALYSIS_QUEUE_MODE=worker`), and the frontend.
4.  Once running, you can connect to:
    *   **Frontend Client:** `http://localhost:5173`
    *   **FastAPI Backend Swagger Docs:** `http://localhost:8000/docs`

---

## 🛠️ 3. Local Developer Workspace Setup

To configure a local workspace on Windows, macOS, or Linux for active code contributions:

### Step A: Database Configuration
1.  Install PostgreSQL 15+ locally.
2.  Create a database named `tradingagents` and configure permissions.
3.  Note your database connection URL (e.g. `postgresql+asyncpg://postgres:postgres@localhost:5432/tradingagents`).

### Step B: Backend Dependencies & Startup
1.  Open your terminal inside the root project directory.
2.  Create a virtual environment:
    ```bash
    python -m venv .venv
    ```
3.  Activate the virtual environment:
    *   **Windows (PowerShell):** `.venv\Scripts\activate`
    *   **Linux / macOS:** `source .venv/bin/activate`
4.  Install the required packages:
    ```bash
    pip install -r backend/requirements.txt
    ```
5.  Create a `.env` file from the example and add your database URL:
    ```ini
    DATABASE_URL=postgresql+asyncpg://youruser:yourpass@localhost:5432/tradingagents
    ```
6.  Start the FastAPI application with reload enabled:
    ```bash
    uvicorn backend.main:app --reload --port 8000
    ```

### Step C: Frontend UI Compilation
1.  Open a separate terminal window.
2.  Navigate to the `frontend/` directory:
    ```bash
    cd frontend
    ```
3.  Install node modules:
    ```bash
    npm install
    ```
4.  Launch the Vite hot-reloading development server:
    ```bash
    npm run dev
    ```
5.  Access the developer client at `http://localhost:5173`.
