# Developer Guide

This guide describes how to extend the TradingAgents platform, write and register custom analyst agents, hook into the WebSocket progression stream, and manage background tasks.

---

## 🔌 1. Creating and Registering a Custom Analyst

TradingAgents uses a dynamic registration system. You can add a new analyst agent without modifying the core LangGraph compilation scripts.

### Step A: Define your Analyst Class and Tools
Create your new analyst module in `backend/trading_agents/agents/analysts/your_analyst.py`. Use the `@register_analyst` decorator from [analyst_registry.py](file:///c:/Users/JustS/Desktop/TradingAgents/backend/trading_agents/agents/analyst_registry.py):

```python
from typing import List
from langchain_core.tools import tool
from tradingagents.agents.analyst_registry import register_analyst

# 1. Define custom tools for your analyst
@tool
def get_custom_sentiment_data(ticker: str) -> str:
    """Fetch custom alternative sentiment metrics for the asset."""
    # Your fetching logic (e.g. database queries, custom API calls)
    return "Positive sentiment index: 87"

# 2. Register the analyst with metadata and its declared tools
@register_analyst(
    key="custom_sentiment",
    label="Özel Duygu",
    description="Özel alternatif veri kaynakları ve duygu endeksleri",
    default_on=False,
    tools=[get_custom_sentiment_data]
)
class CustomSentimentAnalyst:
    def __init__(self, llm):
        self.llm = llm

    def run(self, state):
        # The agent's decision logic and tool execution
        # state contains current messages and reports
        pass
```

### Step B: Import the Module in Setup
To trigger the decorator on startup, import the module in [backend/trading_agents/graph/setup.py](file:///c:/Users/JustS/Desktop/TradingAgents/backend/trading_agents/graph/setup.py):

```python
# Around line 31
import tradingagents.agents.analysts.custom_sentiment_analyst # noqa: F401
```

### Step C: Update the Frontend Metadata
Add your new analyst key to the section dictionary inside [backend/core/catalog.py](file:///c:/Users/JustS/Desktop/TradingAgents/backend/core/catalog.py) to enable display labels and translation support:

```python
_ANALYST_META: dict[str, tuple[str, str, bool]] = {
    # ...
    "custom_sentiment": ("Özel Duygu", "Özel alternatif veri kaynakları ve duygu endeksleri", False),
}
```

The system will automatically configure the new LangGraph node, register its tools, and update the UI settings panel.

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

The platform uses `APScheduler` to run periodic background analyses for assets on the user's watchlist:
*   **Initialization:** The cron scheduler initializes in [backend/main.py](file:///c:/Users/JustS/Desktop/TradingAgents/backend/main.py) during the FastAPI startup event loop.
*   **Database Synchronization:** The scheduler reads cron intervals and settings directly from the PostgreSQL settings tables.
*   **Execution Flow:** When a scheduled event triggers, it queries the database for assets in the user's watchlist, starts a background task using `run_analysis` with `triggered_by="cron"`, and evaluates the resulting signal.
*   **Alert Notifications:** If the agent's final decision signal shifts (e.g. from `Hold` to `Sell`), it triggers alerts or webhooks, notifying the user.
