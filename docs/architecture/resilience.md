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
  | Trader | placeholder `trader_investment_plan` + empty proposal |
  | Risk debators | advance the risk debate (count +1) |
  | **Portfolio Manager** | `final_trade_decision = "Hold — automated fallback"` |

The Portfolio Manager fallback guarantees the run always produces a final
decision, so the analysis completes (as `Hold`) even if the terminal agent fails.

> Everything is **behaviour-preserving on the happy path** — retries/fallbacks
> only change what happens on error. Tunable via the engine config keys
> `node_retry_attempts` / `node_retry_base_delay`.

---

## 4. Ideas for further hardening (roadmap)

Concrete next steps that build on this foundation:

1. **Per-node / per-tool timeouts** — wrap LLM and tool calls with a hard wall
   clock so a hung provider can't stall a run; treat a timeout as a transient
   error feeding the existing retry path.
2. **Circuit breaker** — after N consecutive failures of a given tool/provider in
   a run (or window), short-circuit it (skip + log) instead of retrying, and
   surface "degraded" in the result.
3. **Provider/model fallback chain** — on repeated LLM failure for a provider,
   transparently fail over to a configured secondary model/provider before
   giving up on the agent.
4. **Persisted run status & per-agent report card** — record which agents
   succeeded / retried / were skipped on the `AnalysisResult` (e.g. a
   `degraded: bool` + `failed_agents: [...]`), expose it in the API and badge it
   in the UI so users know a report ran in degraded mode.
5. **Whole-run retry / dead-letter** — if an analysis fails non-transiently,
   enqueue it for a delayed automatic re-run (the cron/queue already exists);
   keep a dead-letter list after K attempts.
6. **Error taxonomy & metrics** — classify errors (auth / quota / data / bug),
   count success & retry rates per agent and per tool over time, and show them on
   the existing Performance / A-B Testing dashboards to spot flaky tools/providers.
7. **Streaming the run-event trace over WebSocket** — push `run_event`s to the
   live analysis view so users watch retries/skips happen in real time.
8. **Stall/heartbeat detection** — emit periodic heartbeats; if a run produces no
   `node_*` event for T seconds, flag and (optionally) cancel + retry it.
