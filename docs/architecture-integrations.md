# Optional architecture integrations

This branch keeps the locked production environment stable while exposing
package-backed comparison and adapter paths for the architecture migration.
None of the optional research libraries are imported during normal startup.

## LiteLLM proxy

The existing LangChain clients remain the compatibility path. To route hosted
providers through an OpenAI-compatible LiteLLM Proxy, set:

```bash
LITELLM_PROXY_URL=http://litellm:4000
LITELLM_PROXY_KEY=...
LITELLM_ROUTE_ALL=true
# Set only when the proxy expects provider/model names rather than aliases.
LITELLM_PREFIX_PROVIDER=false
```

Ollama remains local. SDK retries stay disabled; the agent runtime remains the
single retry authority.

## OpenTelemetry

Technical traces are opt-in and do not replace product WebSocket events:

```bash
OTEL_ENABLED=true
OTEL_SERVICE_NAME=tradingagents-backend
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
```

Install the OpenTelemetry SDK, OTLP exporter, and FastAPI/httpx/SQLAlchemy
instrumentation packages in the deployment that enables this flag.

## Research/reference packages

`backend.services.research_integrations` contains isolated reference adapters
for OpenBB, TA-Lib, vectorbt, empyrical/QuantStats, and PyPortfolioOpt. They are
intentionally not the production source of truth and do not mutate application
caches or execution state. Install only the packages needed by a research job.

TA-Lib parity tests skip automatically when TA-Lib is absent. This allows the
native implementation to be compared before any production calculation is
replaced.

## Alpaca

`backend.services.execution.factory` prefers the official `alpaca-py` adapter
when the `alpaca` Python package is installed. Existing deployments retain the
legacy HTTP adapter as a compatibility fallback until their locked environment
is upgraded.

## PostgreSQL schema and tenant isolation

Alembic now owns the `vector` extension and `memory_vectors` table. Runtime
memory code performs read-only schema verification and asks operators to run
`alembic upgrade head` when the migration is missing.

The same migration creates row-level-security policies for application tables
that carry a direct `user_id` column. Authenticated HTTP and WebSocket requests
set transaction-local `app.user_id` / `app.is_admin` values before accessing
tenant data. Tables without a direct `user_id` continue to rely on their
existing repository ownership joins and application authorization boundaries.
