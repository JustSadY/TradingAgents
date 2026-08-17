# TradingAgents Documentation Index

TradingAgents is a multi-agent investment analysis and execution platform built around FastAPI, React, PostgreSQL, and LangGraph. Specialized analysts collect evidence, research agents challenge competing theses, a single risk-panel node surfaces guardrails from aggressive/conservative/neutral perspectives, the Portfolio Manager produces a raw structured proposal, and the deterministic Decision Stability Controller records or accepts the canonical decision. The surrounding application provides portfolio simulation, optional broker execution, scheduling, alerts, reporting, administration, and real-time progress streaming.

This documentation describes the current repository behavior. Retired architecture and point-in-time migration/audit snapshots are not part of the current documentation contract.

## Documentation map

1. **[System Architecture](architecture/overview.md)** — Current high-level components, execution flow, persistence, workers, and frontend/backend boundaries.
2. **[Installation & Setup](installation.md)** — Linux/systemd, Docker Compose, monitoring stack, and local development setup.
3. **[Configuration & API Setup](configuration.md)** — Infrastructure environment variables, provider configuration, Redis worker mode, and runtime settings.
4. **[Multi-Agent Decision Core](architecture/multi_agent_system.md)** — LangGraph decision stages, analyst/research/risk responsibilities, and Portfolio Manager authority.
5. **[Strategy Continuity & Stability](architecture/strategy_continuity.md)** — Persistent Asset Strategy state, neutral planning, versioning, hysteresis, time-travel safety, and rollout scorecard.
6. **[Modular Tool System](architecture/modular_tool_system.md)** — Dynamic agent-tool registry, settings schemas, access control, and runtime activation.
7. **[Backend Layering & Conventions](architecture/backend.md)** — FastAPI/service/repository/model boundaries and backend implementation rules.
8. **[Developer Guide](developer_guide.md)** — Extension points, custom analysts/tools, WebSocket events, and development workflows.
9. **[Backend README](../backend/README.md)** — Practical backend package and API overview.
10. **[Agent Engine README](../backend/trading_agents/README.md)** — Agent hierarchy, tool registration, LLM clients, and LangGraph package layout.
11. **[Deployment README](../deploy/README.md)** — Linux installer, systemd service, self-updater, and operational commands.

---

## Current decision model

TradingAgents intentionally separates **evidence production**, **risk evaluation**, and **execution authority**.

### 1. Analyst evidence

The Market Intelligence stage runs the enabled analyst plugins. The current system supports 12 analyst roles covering technical/market data, social sentiment, news, fundamentals, macroeconomics, options, quantitative factors, earnings calls, performance review, catalysts, insider activity, and institutional ownership.

Analysts produce evidence and reports. They do not have final execution authority.

### 2. Cross-examination and research debate

The system can cross-examine analyst outputs, synthesize disagreements, and run Bull/Bear research debate. Research and auditing stages are responsible for identifying conflicting evidence and producing a better-supported thesis, not for placing orders directly.

### 3. Risk guardrails

The Risk Debate node asks one model call for aggressive, conservative, and neutral perspectives on the research result. The panel surfaces downside conditions, invalidation criteria, liquidity/exposure concerns, and other guardrails.

Risk perspectives are **not order authorities**. They do not independently issue the final Buy/Sell/Hold direction, quantity, allocation, leverage, stop, or target. Their output is evidence consumed by the final proposal stage.

### 4. Portfolio Manager proposal and accepted decision

The Portfolio Manager is the sole AI agent that proposes a structured rating and portfolio intent. It evaluates active analyst reports, the research debate, and risk-panel evidence, but its output is a raw proposal rather than an executable order.

The Decision Stability Controller compares that proposal with the previous *accepted* decision, structured evidence, invalidations, run quality, and calibrated confidence. In `shadow` mode it records its counterfactual only; in `enforce` mode it becomes the canonical accepted decision. Any resulting order still passes deterministic application-side controls. Cash availability, concentration limits, exposure constraints, stop/risk rules, broker mode, and execution settings can reduce or reject the accepted decision.

See [Strategy Continuity & Stability](architecture/strategy_continuity.md) for the distinction between exact Asset Strategy state and episodic memory, historical replay safeguards, and rollout metrics.

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
- Docker Compose with PostgreSQL, Redis, backend, worker, frontend, Prometheus, PostgreSQL exporter, and Redis exporter.
- Manual local development with PostgreSQL, a Python virtual environment, and the Vite development server.

See [installation.md](installation.md) for the current commands and required environment values.
