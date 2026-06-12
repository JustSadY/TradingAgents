# Developer Guide

This guide describes how to extend the TradingAgents platform, write and register custom analyst agents, hook into the WebSocket progression stream, and manage background tasks.

---

## 🔌 1. Creating and Registering a Custom Analyst

TradingAgents uses a dynamic registration system. You can add a new analyst agent without modifying the core LangGraph compilation scripts.

### Step A: Define your Analyst Node and Tools
Create your new analyst module in `backend/trading_agents/agents/sub/analysts/your_analyst.py`. Use the `@register_analyst` decorator from [analyst_registry.py](../backend/trading_agents/agents/analyst_registry.py). The decorator declares the **structural graph wiring** — the node names, the report column the analyst writes, and its tools:

```python
from langchain_core.tools import tool
from backend.trading_agents.agents.analyst_registry import register_analyst

# 1. Define custom tools for your analyst
@tool
def get_custom_sentiment_data(ticker: str) -> str:
    """Fetch custom alternative sentiment metrics for the asset."""
    # Your fetching logic (e.g. database queries, custom API calls)
    return "Positive sentiment index: 87"

# 2. Register the analyst node factory with its graph wiring + tools
@register_analyst(
    key="custom_sentiment",
    agent_node="Custom Sentiment Analyst",
    clear_node="Msg Clear Custom Sentiment",
    tool_node="tools_custom_sentiment",
    report_key="custom_sentiment_report",
    tools=[get_custom_sentiment_data],
)
def create_custom_sentiment_analyst(llm):
    def node(state):
        # build the prompt, bind tools, invoke the llm, return the report
        ...
    return node
```

### Step B: Import the Module in Setup
To trigger the decorator on startup, import the module in [backend/trading_agents/graph/setup.py](../backend/trading_agents/graph/setup.py):

```python
import backend.trading_agents.agents.sub.analysts.custom_sentiment_analyst  # noqa: F401
```

### Step C: Declare the UI/selection metadata (single source)
Add your analyst's **selection metadata** — label, description, parent node and
whether it is on by default — to the agent catalog
[backend/trading_agents/agent_catalog.py](../backend/trading_agents/agent_catalog.py)
(`AGENTS` list, category `"analyst"`). This is the single source the backend
exposes through `/api/meta`, so the frontend picks it up automatically (no
frontend edit needed). It also wires the analyst into the `AgentHierarchy`
kill-switch and LLM-fallback chain:

```python
AGENTS: list[AgentInfo] = [
    # ...
    AgentInfo(
        "custom_sentiment",
        "Custom Sentiment",
        "Alternative sentiment data sources and indices",
        category="analyst",
        parent="market_intelligence",
        default_enabled=False,
    ),
]
```

The system then configures the LangGraph node, registers its tools, and surfaces
the analyst in the settings panel via `/api/meta`.

---

## 📡 2. Real-Time WebSocket Progression Streaming

The frontend tracks the graph's execution using a persistent WebSocket connection:
1.  **WebSocket Endpoint:** The client establishes a connection to `ws://localhost:8000/ws/analysis/{task_id}`.
2.  **Streaming Updates:** During analysis, the backend streams updates to indicate the active node (e.g. Market Analyst, Bull Researcher, Risk Analyst):
    ```json
    {
      "type": "progress",
      "node": "Market Analyst Node",
      "label": "Market Analyst",
      "stage": "analyst"
    }
    ```
3.  **Streaming Reports:** As each analyst or debate manager finishes its execution and commits reports to the state, the backend patches the state stream to push report updates:
    ```json
    {
      "type": "report",
      "section": "market_report",
      "content": "### Market Technical Analysis\n* RSI: 62\n* Momentum: Neutral..."
    }
    ```
4.  **Completion Signal:** Once the Portfolio Manager outputs its decision, the connection returns the final decision parameters and closes:
    ```json
    {
      "type": "complete",
      "analysis_id": 45,
      "duration_seconds": 38.5,
      "llm_calls": 12
    }
    ```

---

## ⏰ 3. Managing Background Cron Services

The platform uses `APScheduler` to run periodic background analyses for assets on a per-user basis:
*   **Initialization:** The global cron scheduler initializes in [backend/main.py](../backend/main.py) during startup.
*   **User Configuration:** Each user can configure their own schedule and toggle status in the **Settings > Cron / Auto Scan** tab.
*   **Database Synchronization:** The `CronService` reads active schedules from `AppSettings` and assigns unique job IDs (`watchlist_scan_user_{id}`) for each user.
*   **Execution Flow:** When a user's cron triggers, it iterates through that specific user's **Watchlist**, starts background tasks using `run_analysis` with the user's active AI settings, and evaluates results.
*   **Permissions:** Administrators can toggle a user's ability to manage their own cron via the **Admin > Access Control** panel (`cron` key).

---

## 🌐 4. Frontend Localization (i18n)

The React client supports runtime multi-language localization (defaulting to English, with Turkish support). It operates through a custom, lightweight React Context instead of bulky third-party libraries.

### A. The Translation Hook and Context
Common navigation and general strings are managed directly in [LanguageContext.tsx](../frontend/src/contexts/LanguageContext.tsx). Page/module-specific translations are modularized under the [i18n/](../frontend/src/i18n) directory. At runtime, the context uses Vite's `import.meta.glob` to automatically discover and merge all translation files into a single active dictionary.

To use translations in any React component:

1.  **Import the Translation Hook:**
    ```typescript
    import { useTranslation } from '../contexts/LanguageContext'
    ```
2.  **Extract the Variables:**
    ```typescript
    const { language, setLanguage, t } = useTranslation();
    ```
3.  **Perform Translations in JSX:**
    ```typescript
    <h2>{t('dashboard.title')}</h2>
    ```
4.  **Perform Dynamic Locale-based Formatting:**
    ```typescript
    // Format currencies using the correct decimal character (e.g. 1,000.50 vs 1.000,50)
    const formatted = val.toLocaleString(language === 'tr' ? 'tr-TR' : 'en-US');
    ```

### B. Registering New Localization Strings
To register new translation properties:
1.  **For Common/Shared Labels:** Open [LanguageContext.tsx](../frontend/src/contexts/LanguageContext.tsx), locate the `TRANSLATIONS` map, and add your key to both the `en` and `tr` blocks.
2.  **For Page/Feature-Specific Labels:** Open the relevant translation file in [frontend/src/i18n/](../frontend/src/i18n) (e.g., [settings.ts](../frontend/src/i18n/settings.ts)) and append your keys.
3.  **For a New Page/Feature:** Create a new `.ts` file in [frontend/src/i18n/](../frontend/src/i18n) that default-exports a translations object structure:
    ```typescript
    const translations = {
      en: {
        'my_feature.title': 'My Feature',
      },
      tr: {
        'my_feature.title': 'Özelliğim',
      }
    }
    export default translations
    ```
    This file will be automatically merged into the global translations at load time.
4.  The system stores the user selection in `localStorage` under the key `ta_language` (with options `'en'` or `'tr'`), which is loaded automatically when the SPA boots up.

---

## 🛠️ 5. Implementation & Extension Guides for Advanced Features

This section provides technical guidance and code blueprints for developers implementing or extending the 16 advanced AI, visualization, and automated trading features.

### A. Interactive Q&A on Reports (Feature 1) — implemented
Report-grounded Q&A lives in
[backend/services/report_chat_service.py](../backend/services/report_chat_service.py)
(`answer_report_question`) and is exposed via `GET/POST /api/analysis/{id}/chat`
in [backend/api/analysis.py](../backend/api/analysis.py). The flow:

1.  Verify the analysis belongs to the caller (`scope_to_user`).
2.  Build a system prompt grounded **only** in the completed report sections
    (plus the user's output-language preference).
3.  Resolve the user's encrypted provider key, call the configured LLM through
    `backend.trading_agents.llm_clients` (`create_llm_client`), and persist both
    messages as `AnalysisChat` rows.

To extend it (e.g. adding new context sections), modify the prompt builder in
`report_chat_service.py` — keep the router handler thin.

### B. Streaming Live Bull & Bear Debate Exchanges (Feature 2)
Debate bubbles are emitted through the `AnalysisEmitter`
([backend/services/analysis/emitter.py](../backend/services/analysis/emitter.py)),
which routes events to local WebSockets — or across processes via Redis pub/sub
when `REDIS_URL` is configured:

```python
# Inside a graph callback that has access to the run's emitter:
await emitter.emit_debate_bubble(
    debate_type="investment",  # or "risk"
    message=f"BullResearcher: {message}",
)
```

The frontend receives `{"type": "debate_bubble", ...}` events on
`/ws/analysis/{task_id}` and renders them as live chat bubbles.

### C. Registering a New Investor Persona (Feature 4)
Personas are a **single-source catalog** in
[backend/trading_agents/personas.py](../backend/trading_agents/personas.py).
Register one `InvestorPersona(...)` (key, label, description and the Portfolio
Manager instruction block) — the Portfolio Manager prompt and the
`/api/meta.investor_personas` dropdown pick it up automatically, no other edits:

```python
# backend/trading_agents/personas.py
register_persona(
    InvestorPersona(
        key="esg_focused",
        label="ESG Focused",
        description="Prioritizes sustainable, high ESG-score companies",
        instructions=(
            "Filter allocations to prioritize high ESG scores and sustainable "
            "companies. Avoid fossil-fuel-heavy and controversy-flagged names."
        ),
    )
)
```

### D. Analyst Success Scorecard (Feature 3) — implemented
Per-analyst predictive performance is tracked by comparing past signals against
realized returns:

*   [backend/services/performance_service.py](../backend/services/performance_service.py)
    backfills realized returns/alpha for graded analyses and computes
    **analyst attribution stats** (`get_analyst_attribution_stats`), exposed at
    `GET /api/analysis/performance-attribution`.
*   [backend/services/analyst_prefilter_service.py](../backend/services/analyst_prefilter_service.py)
    uses those win rates to optionally **skip chronically underperforming
    analysts** before a run (configurable via the
    `analyst_prefilter_*` settings).

To change how performance feeds back into runs, extend the prefilter service —
not the Portfolio Manager prompt — so the behaviour stays configurable per user.

### E. Fractional Share Orders (Feature 16) — implemented convention
Fractional quantities are already supported: all money/quantity columns use the
exact-decimal `MONEY = Numeric(20, 8, asdecimal=True)` type from
`backend/core/database.py` (see `backend/models/order.py` —
`quantity_requested` / `quantity_filled` are `Decimal`). When extending order
logic:

*   **Never use `Float`** for prices, quantities, balances, or margins — use the
    `MONEY` column type and Python's `Decimal` end-to-end to avoid accumulative
    rounding errors.
*   The paper-trading engine (`backend/services/mock_trading_service.py`)
    performs all arithmetic in `Decimal`; follow the same pattern in new code.

### F. Safe Dynamic Indicator Engine & Evaluation Blueprint
Allows both analysts and users to write dynamic mathematical expressions (e.g. `(Close - SMA(20)) / STD(20)`) evaluated safely in the backend.

1. **Backend Evaluation Core:** Located in [indicator_service.py](../backend/services/indicator_service.py), it parses formula syntax, replaces calls like `SMA(N)`, `EMA(N)`, `STD(N)`, and `RSI(N)` with computed pandas series, and runs a sandboxed `pandas.eval`:
   ```python
   def evaluate_formula_safely(df: pd.DataFrame, formula: str) -> pd.Series:
       # Parsed tokens like SMA(10) get pre-calculated and mapped to SMA_10 in local_dict
       # Evaluates safely restricting the environment namespace
       res = pd.eval(processed_formula, local_dict=local_dict, engine='python')
       return pd.Series(res, index=df.index)
   ```
2. **API Router:** Exposes `/api/market/custom-indicator` to resolve queries by fetching the historical ticker data, calculating the formula series, and returning the time-series array.
3. **Frontend Custom Formula Input:** Integrated in [Chart.tsx](../frontend/src/pages/Chart.tsx) for dynamic user computations and plots them as line charts at the bottom of the candlestick panel.

### G. Drawing Agent-to-UI Annotations & Trendlines
Enables trading agents to interactively draw visual markers and trendlines on the user's chart.

1. **State-Safe Tool Execution:** Defined in [chart_tools.py](../backend/trading_agents/agents/data/chart_tools.py) as `add_chart_annotation`. Captures arguments (`type`, `time`, `price`, `text`, `time2`, `price2`) and registers them in the active thread-local context variable (`active_run_context`).
2. **Database Propagation:** Merged and saved into the `chart_annotations` column of `AnalysisResult` in [analysis_service.py](../backend/services/analysis_service.py).
3. **Frontend Render System:** [Chart.tsx](../frontend/src/pages/Chart.tsx) parses these annotations and feeds markers to the `CandlestickSeries` or adds separate line segments dynamically to the TradingView chart to represent trendlines.

### H. Vision-Based Pattern Recognition Pipeline
Numerical series can struggle with visual shapes. This system adds a visual analysis mechanism to identify classic chart patterns.

1. **Visual Plotting and Encoding:** The `get_vision_chart_analysis` tool in [chart_tools.py](../backend/trading_agents/agents/data/chart_tools.py) slices the last 90 trading days, renders a clean PNG chart via `mplfinance` (with candlestick and volume plots), and converts it into a Base64 string.
2. **Vision Model Call:** It sends the image payload along with a structured prompt to the active session's vision-capable LLM to extract visual pattern insights (e.g., Head and Shoulders, Cup and Handle) and returns the text evaluation back to the caller.

### I. Multi-Timeframe Alignment and Overlay Mapping
Ensures daily-chart decisions remain aligned with long-term macro trendlines.

1. **High-Timeframe Sampling:** The `get_mtf_trend` tool in [chart_tools.py](../backend/trading_agents/agents/data/chart_tools.py) fetches Weekly or Monthly historical data, computes a 20 EMA, and performs a backward merge/asof join mapping the values onto the daily trading index.
2. **Chart Overlay:** The resulting series is registered with an `"overlay": true` parameter, signaling [Chart.tsx](../frontend/src/pages/Chart.tsx) to plot the macro trend directly on top of the main daily price candlesticks as an overlay line.

