# Run Resilience & Agent/Tool Logging

A multi-agent run touches many LLM calls, external data APIs and tools — any of
which can fail transiently (rate limits, timeouts, 5xx) or hard (bad data, bugs).
Previously a single failing analyst, manager or tool raised through
`graph.invoke()` and **aborted the entire analysis**. This subsystem makes the
run resilient and gives it a dedicated, structured log stream.

Implementation: [`backend/trading_agents/agents/runtime/resilience.py`](../../backend/trading_agents/agents/runtime/resilience.py).

---

## 1. Dedicated run log stream

All agent/tool execution events are emitted on the **`tradingagents.run`** Python
logger as structured `run_event` records. Because the backend's DB log handler
captures standard logging, these show up under `/api/logs` (for admins) or `/api/logs/me` (for authenticated users) and can be filtered by the logger name to get a per-run, per-agent, per-tool trace.

Events: `node_start`, `node_end` (with `ms` duration), `retry` (with attempt /
delay / error), `node_error` (with truncated traceback), `node_skipped`,
`tool_error`. Each carries `node`/`kind` (`analyst` · `research` · `manager` ·
`risk` · `decision`) so the trace is easy to slice.

## 2. Failing **tools** fall through

Every `ToolNode` is created with `handle_tool_errors=tool_error_handler`
([trading_graph.py](../../backend/trading_agents/graph/trading_graph.py)
`_create_tool_nodes`). When a tool raises, the error is logged and returned to
the LLM as a message — so the agent simply **tries the next tool** or continues
with the data it already has, instead of crashing. (Falls back to the default
`ToolNode` if the installed langgraph lacks the kwarg.)

## 3. Failing **agents** retry, then skip (don't abort)

- **`retry_call(fn, …)`** retries with exponential backoff (`node_retry_attempts`
  total tries, `node_retry_base_delay` seconds — read from engine config, default
  `2` / `1.0s`). The analyst LLM turn in
  [`analyst_node_factory.run_tool_analyst`](../../backend/trading_agents/agents/runtime/analyst_node_factory.py)
  is wrapped in it.
- **`guard_node(fn, name, kind, fallback)`** wraps every graph node
  ([setup.py](../../backend/trading_agents/graph/setup.py)): it retries, logs, and
  on final failure returns a **safe fallback state update** so the graph
  continues in a *degraded* mode rather than aborting:
  | Node | Fallback on persistent failure |
  | --- | --- |
  | Any analyst | empty report note (`⚠️ … unavailable`), routes to the next analyst |
  | Bull / Bear researcher | advance the investment debate (count +1) |
  | Synthesis / Auditor | empty `synthesis_report` / `audit_report` |
  | Research Manager | placeholder `investment_plan` |
  | Risk Debate | neutral risk-guardrail state |
  | **Portfolio Manager** | `final_trade_decision = "Hold — automated fallback"` raw proposal, followed by controller fail-closed acceptance |

The Portfolio Manager fallback guarantees the run always produces a safe raw
proposal. The Decision Stability Controller then guarantees a canonical final
decision, so the analysis completes (as `Hold`) even if the terminal agent fails.

> Everything is **behaviour-preserving on the happy path** — retries/fallbacks
> only change what happens on error. Tunable via the engine config keys
> `node_retry_attempts` / `node_retry_base_delay`.

---

## 4. Further hardening (implemented)

Eight additional resilience features build on the foundation above:

### 4.1 Per-node / per-tool timeouts
- **Config:** `node_timeout_seconds` (default 120), `tool_timeout_seconds` (default 60)
- **Mechanism:** `asyncio.wait_for` wraps every LLM call in `retry_call` and every `ToolNode.ainvoke` in `_cap_tool_outputs`
- `asyncio.TimeoutError` is classified as transient and feeds into the retry path automatically
- **Source:** `resilience.py:retry_call`, `trading_graph.py:_cap_tool_outputs`

### 4.2 Circuit breaker
- **Config:** `circuit_breaker_threshold` (default 3), `circuit_breaker_cooldown` (default 60s)
- **Mechanism:** Module-level `_circuit_state` dict tracks consecutive failures per node (keyed by `{kind}:{name}`)
  - **Closed** → normal operation; failures increment a counter
  - **Open** → after threshold failures, skip directly to fallback without retrying
  - **Half-open** → after cooldown, allow one try; success resets to closed
- Emits `circuit_open` / `circuit_tripped` log events and `NODE_CIRCUIT_OPEN` Prometheus counter
- **Source:** `resilience.py:guard_node`

### 4.3 Provider/model fallback chain
- **Config:** `fallback_llm_chain` — an ordered list of `{"provider": ..., "model": ...}` entries.
- **Mechanism:** `FallbackLLM` now accepts a list of fallbacks. `bind_tools`, `with_structured_output`, `invoke`, `ainvoke`, `stream`, `astream` all apply the full chain via LangChain `with_fallbacks`
- Runtime provider failover on every LLM call — if the primary raises, the next fallback is tried in order
- **Source:** `llm_clients/fallback.py`, `trading_graph.py:_with_fallback`

### 4.4 Persisted run status & per-agent report card
- **DB columns:** `AnalysisResult.degraded` (bool), `AnalysisResult.failed_agents` (JSON list)
- **Mechanism:** `_run_report_card` contextvar (`contextvars.ContextVar`) is initialised before graph propagation; `guard_node` records each agent's retries/fallback/error into it; `orchestrator.py` reads it after propagation and stores in `final_payload`
- `degraded` is true when any agent was replaced by its fallback stub
- `failed_agents` lists the names of every agent that fell back
- **Source:** `resilience.py:_run_report_card`, `orchestrator.py`, `models/analysis.py`

### 4.5 Whole-run retry / dead-letter
- **Config:** `_ANALYSIS_RETRY_MAX = 1` (module-level constant in `analysis_service.py`)
- **Mechanism:** On unhandled exception in `run_analysis_task`, `_maybe_retry_analysis` checks `task_store.get_meta(task_id).retry_count`; if under max, increments and re-dispatches (inline `asyncio.create_task` or arq job). After max retries, logged as dead-letter.
- Re-uses the existing `task_store` metadata + `dispatch_analysis` pipeline
- **Source:** `analysis_service.py:_maybe_retry_analysis`

### 4.6 Error taxonomy & Prometheus metrics
- **Function:** `classify_error(exc)` returns `"auth" | "quota" | "timeout" | "transient" | "bug"`
- **New counters:**
  - `NODE_ERRORS_BY_TYPE` — labels `node, kind, error_type`
  - `TOOL_ERRORS` — labels `tool_name, error_type`
- `_log_node_error` and `tool_error_handler` classify every error and increment the appropriate counter
- **Source:** `resilience.py:classify_error`, `core/metrics.py`

### 4.7 Streaming the run-event trace over WebSocket
- **New emitter methods:** `emit_retry`, `emit_fallback`, `emit_node_error`, `emit_circuit_open`
- `_emit_retry_progress` now also sends a typed `retry` event alongside the existing `progress` warning
- Circuit breaker open → `emit_circuit_open` event
- Node error after retry exhaustion → `emit_node_error` event (with `error_type` classification)
- Fallback activation → `emit_fallback` event
- All WS events are fire-and-forget (best-effort, never crash the run)
- **Source:** `emitter.py`, `resilience.py:_emit_retry_progress`

### 4.8 Stall/heartbeat detection
- **Config:** `stall_timeout_seconds` (default 120)
- **Mechanism:** `_heartbeat_monitor` async task runs alongside graph propagation; emits a heartbeat `progress` event every 30s. Monitors `last_event_time` in `_stream_observer`; if no node event for `stall_timeout_seconds`, emits a `stall_warning` WS event and logs a warning.
- The heartbeat task is cancelled when propagation completes normally.
- **Source:** `orchestrator.py:_heartbeat_monitor`

### Config keys added

| Key | Type | Default | Settings UI | Description |
|-----|------|---------|-------------|-------------|
| `node_timeout_seconds` | int | 120 | Agent Run Resilience | Hard timeout per node |
| `tool_timeout_seconds` | int | 60 | Agent Run Resilience | Hard timeout per tool |
| `circuit_breaker_threshold` | int | 3 | Circuit Breaker | Failures before circuit opens |
| `circuit_breaker_cooldown` | int | 60s | Circuit Breaker | Cooldown before half-open |
| `stall_timeout_seconds` | int | 120 | Circuit Breaker | Seconds without output before stall warning |
