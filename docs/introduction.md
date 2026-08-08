# TradingAgents Documentation Index

TradingAgents is a multi-agent investment analysis and execution platform built around FastAPI, React, PostgreSQL, and LangGraph. Specialized analysts collect evidence, research agents challenge competing theses, risk agents surface guardrails, and a single Portfolio Manager produces the final structured investment decision. The surrounding application provides portfolio simulation, optional broker execution, scheduling, alerts, reporting, administration, and real-time progress streaming.

This documentation describes the current repository behavior. Historical audit, patch-note, and validation files under `docs/` are point-in-time records and should not be treated as the current architecture specification.

## Documentation map

1. **[System Architecture](architecture/overview.md)** — Current high-level components, execution flow, persistence, workers, and frontend/backend boundaries.
2. **[Installation & Setup](installation.md)** — Linux/systemd, Docker Compose, monitoring stack, and local development setup.
3. **[Configuration & API Setup](configuration.md)** — Infrastructure environment variables, provider configuration, Redis worker mode, and runtime settings.
4. **[Multi-Agent Decision Core](architecture/multi_agent_system.md)** — LangGraph decision stages, analyst/research/risk responsibilities, and Portfolio Manager authority.
5. **[Modular Tool System](architecture/modular_tool_system.md)** — Dynamic agent-tool registry, settings schemas, access control, and runtime activation.
6. **[Backend Layering & Conventions](architecture/backend.md)** — FastAPI/service/repository/model boundaries and backend implementation rules.
7. **[Developer Guide](developer_guide.md)** — Extension points, custom analysts/tools, WebSocket events, and development workflows.
8. **[Backend README](../backend/README.md)** — Practical backend package and API overview.
9. **[Agent Engine README](../backend/trading_agents/README.md)** — Agent hierarchy, tool registration, LLM clients, and LangGraph package layout.
10. **[Deployment README](../deploy/README.md)** — Linux installer, systemd service, self-updater, and operational commands.

---

## Current decision model

TradingAgents intentionally separates **evidence production**, **risk evaluation**, and **execution authority**.

### 1. Analyst evidence

The Market Intelligence stage runs the enabled analyst plugins. The current system supports 12 analyst roles covering technical/market data, social sentiment, news, fundamentals, macroeconomics, options, quantitative factors, earnings calls, performance review, catalysts, insider activity, and institutional ownership.

Analysts produce evidence and reports. They do not have final execution authority.

### 2. Cross-examination and research debate

The system can cross-examine analyst outputs, synthesize disagreements, and run Bull/Bear research debate. Research and auditing stages are responsible for identifying conflicting evidence and producing a better-supported thesis, not for placing orders directly.

### 3. Risk guardrails

Aggressive, Conservative, and Neutral risk agents evaluate the research result from different risk perspectives. They surface downside conditions, invalidation criteria, liquidity/exposure concerns, and other guardrails.

Risk agents are **not order authorities**. They do not independently issue the final Buy/Sell/Hold direction, quantity, allocation, leverage, stop, or target. Their output is evidence consumed by the final decision stage.

### 4. Portfolio Manager authority

The Portfolio Manager is the sole agent responsible for the final structured investment decision. It evaluates active analyst reports, the research debate, and risk-agent evidence and emits the final rating and portfolio intent.

Any resulting order still passes deterministic application-side controls. Cash availability, concentration limits, exposure constraints, stop/risk rules, broker mode, and execution settings can reduce or reject the agent proposal.

---

## Runtime architecture

The React frontend communicates with the FastAPI backend over REST and authenticated WebSockets. Analysis runs can execute in one of two modes:

- `ANALYSIS_QUEUE_MODE=inline` — analysis runs inside the web process.
- `ANALYSIS_QUEUE_MODE=worker` — analysis is queued to a dedicated `arq` worker and requires Redis.

When Redis is enabled, it also supports cross-process progress/event fan-out, task ownership, and cancellation so the web process can stream worker activity to connected clients.

PostgreSQL is the primary application database. Provider keys and other sensitive user settings are stored encrypted in the database rather than being placed in `.env`.

---

## Deployment model

The repository supports:

- One-command Linux/systemd deployment through `deploy/install.sh`.
- Docker Compose with PostgreSQL, Redis, backend, worker, frontend, Prometheus, Grafana, PostgreSQL exporter, and Redis exporter.
- Manual local development with PostgreSQL, a Python virtual environment, and the Vite development server.

See [installation.md](installation.md) for the current commands and required environment values.