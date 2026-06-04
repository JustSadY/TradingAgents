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

The platform uses `APScheduler` to run periodic background analyses for assets on a per-user basis:
*   **Initialization:** The global cron scheduler initializes in [backend/main.py](file:///c:/Users/JustS/Desktop/TradingAgents/backend/main.py) during startup.
*   **User Configuration:** Each user can configure their own schedule and toggle status in the **Settings > Cron / Auto Scan** tab.
*   **Database Synchronization:** The `CronService` reads active schedules from `AppSettings` and assigns unique job IDs (`watchlist_scan_user_{id}`) for each user.
*   **Execution Flow:** When a user's cron triggers, it iterates through that specific user's **Watchlist**, starts background tasks using `run_analysis` with the user's active AI settings, and evaluates results.
*   **Permissions:** Administrators can toggle a user's ability to manage their own cron via the **Admin > Access Control** panel (`cron` key).

---

## 🌐 4. Frontend Localization (i18n)

The React client supports runtime multi-language localization (defaulting to English, with Turkish support). It operates through a custom, lightweight React Context instead of bulky third-party libraries.

### A. The Translation Hook and Context
Common navigation and general strings are managed directly in [LanguageContext.tsx](file:///c:/Users/JustS/Desktop/TradingAgents/frontend/src/contexts/LanguageContext.tsx). Page/module-specific translations are modularized under the [i18n/](file:///c:/Users/JustS/Desktop/TradingAgents/frontend/src/i18n/) directory. At runtime, the context uses Vite's `import.meta.glob` to automatically discover and merge all translation files into a single active dictionary.

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
1.  **For Common/Shared Labels:** Open [LanguageContext.tsx](file:///c:/Users/JustS/Desktop/TradingAgents/frontend/src/contexts/LanguageContext.tsx), locate the `TRANSLATIONS` map, and add your key to both the `en` and `tr` blocks.
2.  **For Page/Feature-Specific Labels:** Open the relevant translation file in [frontend/src/i18n/](file:///c:/Users/JustS/Desktop/TradingAgents/frontend/src/i18n/) (e.g., [settings.ts](file:///c:/Users/JustS/Desktop/TradingAgents/frontend/src/i18n/settings.ts)) and append your keys.
3.  **For a New Page/Feature:** Create a new `.ts` file in [frontend/src/i18n/](file:///c:/Users/JustS/Desktop/TradingAgents/frontend/src/i18n/) that default-exports a translations object structure:
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

### A. Setting Up Interactive Q&A Handler (Feature 1)
To handle interactive questions on completed reports, create a new router under [backend/api/analysis.py](file:///c:/Users/JustS/Desktop/TradingAgents/backend/api/analysis.py):

```python
from fastapi import APIRouter, Depends
from backend.services.analysis_service import get_analysis_by_id
from backend.trading_agents.llm_clients.factory import get_llm_client

router = APIRouter()

@router.post("/{analysis_id}/chat")
async def chat_with_report(analysis_id: int, user_message: str, db=Depends(get_db)):
    # 1. Fetch historical analysis report
    analysis = await get_analysis_by_id(analysis_id, db)
    report_content = analysis.markdown_report
    
    # 2. Construct LLM client and system instructions loaded with the report
    llm = get_llm_client(provider="openai", model="gpt-4o-mini")
    system_prompt = (
        f"You are the Portfolio Manager agent of TradingAgents. The user wants to discuss the "
        f"following analysis report they generated.\n\nReport Content:\n{report_content}\n\n"
        f"Answer their questions concisely, matching your analysis findings."
    )
    
    # 3. Request LLM response
    response = await llm.generate(
        system_instruction=system_prompt,
        messages=[{"role": "user", "content": user_message}]
    )
    return {"reply": response}
```

### B. Streaming Live Bull & Bear Debate Exchanges (Feature 2)
To push live debate bubble flows over WebSockets, hook into the node loop in [backend/trading_agents/graph/trading_graph.py](file:///c:/Users/JustS/Desktop/TradingAgents/backend/trading_agents/graph/trading_graph.py):

```python
# During the debate node processing, send intermediate outputs to the WebSocket manager
async def debate_step_callback(agent_name: str, message: str, task_id: str):
    from backend.core.websocket import manager
    await manager.send_to_task(
        task_id,
        {
            "type": "debate_bubble",
            "agent": agent_name,  # "BullResearcher" or "BearResearcher"
            "message": message,
            "timestamp": datetime.utcnow().isoformat()
        }
    )
```

### C. Registering a New Investor Persona (Feature 4)
Personas govern LLM advisory behaviors. Add options to [backend/trading_agents/config.py](file:///c:/Users/JustS/Desktop/TradingAgents/backend/trading_agents/config.py) and map them inside [backend/trading_agents/agents/managers/portfolio_manager.py](file:///c:/Users/JustS/Desktop/TradingAgents/backend/trading_agents/agents/managers/portfolio_manager.py):

```python
# 1. In backend/trading_agents/config.py
investor_persona: str = "conservative"  # Choices: conservative, risk_loving, esg_focused

# 2. In backend/trading_agents/agents/managers/portfolio_manager.py
PERSONA_PROMPTS = {
    "conservative": "Prioritize high-yield dividend stocks, cash conservation, and blue-chips. Avoid leverage.",
    "risk_loving": "Seek high beta, cryptocurrency assets, and swing options setups. Prioritize growth.",
    "esg_focused": "Filter allocations to prioritize high ESG scores and sustainable companies."
}

def get_portfolio_manager_prompt(persona: str) -> str:
    persona_instruction = PERSONA_PROMPTS.get(persona, PERSONA_PROMPTS["conservative"])
    return f"You are the Portfolio Manager. Persona instructions: {persona_instruction}"
```

### D. Implementing the Analyst Success Scorecard (Feature 3)
Track the performance of individual analysts by comparing their signals against actual prices. Define the SQL model in [backend/models/portfolio_analysis.py](file:///c:/Users/JustS/Desktop/TradingAgents/backend/models/portfolio_analysis.py):

```python
from sqlalchemy import Column, String, Float, Integer
from backend.core.database import Base

class AnalystScorecard(Base):
    __tablename__ = "analyst_scorecards"
    
    id = Column(Integer, primary_key=True)
    analyst_key = Column(String, unique=True, index=True)  # e.g., "market", "news"
    total_predictions = Column(Integer, default=0)
    correct_predictions = Column(Integer, default=0)
    success_rate = Column(Float, default=1.0)  # Total correct / Total predictions
```

A daily task runs in `backend/services/stats_handler.py` to update these values using yFinance actual closing prices after 7 days and 30 days. In `portfolio_manager.py`, apply these as node weights:
```python
def weigh_analysts(signals: dict, scorecards: dict[str, float]) -> dict:
    weighted_signals = {}
    for analyst, signal in signals.items():
        weight = scorecards.get(analyst, 1.0)
        weighted_signals[analyst] = signal * weight
    return weighted_signals
```

### E. Enabling Fractional Share Orders (Feature 16)
To support small account sizes, upgrade the order managers to support floating-point quantities. 

1.  **Modify Table Models:** Change quantities in `backend/models/order.py` from `Integer` to `Float`:
    ```python
    quantity = Column(Float, nullable=False)  # Supports fractional values (e.g. 0.05)
    ```
2.  **Adjust Simulation Routing:** Update `backend/services/execution/simulation.py` to perform operations on float quantities:
    ```python
    def execute_simulated_buy(portfolio, ticker, quantity, price):
        cost = quantity * price
        if portfolio.cash >= cost:
            portfolio.cash -= cost
            # Add or update asset holding with fractional float addition
            portfolio.holdings[ticker] = portfolio.holdings.get(ticker, 0.0) + quantity
    ```

### F. Safe Dynamic Indicator Engine & Evaluation Blueprint
Allows both analysts and users to write dynamic mathematical expressions (e.g. `(Close - SMA(20)) / STD(20)`) evaluated safely in the backend.

1. **Backend Evaluation Core:** Located in [indicator_service.py](file:///c:/Users/JustS/Desktop/TradingAgents/backend/services/indicator_service.py), it parses formula syntax, replaces calls like `SMA(N)`, `EMA(N)`, `STD(N)`, and `RSI(N)` with computed pandas series, and runs a sandboxed `pandas.eval`:
   ```python
   def evaluate_formula_safely(df: pd.DataFrame, formula: str) -> pd.Series:
       # Parsed tokens like SMA(10) get pre-calculated and mapped to SMA_10 in local_dict
       # Evaluates safely restricting the environment namespace
       res = pd.eval(processed_formula, local_dict=local_dict, engine='python')
       return pd.Series(res, index=df.index)
   ```
2. **API Router:** Exposes `/api/market/custom-indicator` to resolve queries by fetching the historical ticker data, calculating the formula series, and returning the time-series array.
3. **Frontend Custom Formula Input:** Integrated in [Chart.tsx](file:///c:/Users/JustS/Desktop/TradingAgents/frontend/src/pages/Chart.tsx) for dynamic user computations and plots them as line charts at the bottom of the candlestick panel.

### G. Drawing Agent-to-UI Annotations & Trendlines
Enables trading agents to interactively draw visual markers and trendlines on the user's chart.

1. **State-Safe Tool Execution:** Defined in [chart_tools.py](file:///c:/Users/JustS/Desktop/TradingAgents/backend/trading_agents/agents/utils/chart_tools.py) as `add_chart_annotation`. Captures arguments (`type`, `time`, `price`, `text`, `time2`, `price2`) and registers them in the active thread-local context variable (`active_run_context`).
2. **Database Propagation:** Merged and saved into the `chart_annotations` column of `AnalysisResult` in [analysis_service.py](file:///c:/Users/JustS/Desktop/TradingAgents/backend/services/analysis_service.py).
3. **Frontend Render System:** [Chart.tsx](file:///c:/Users/JustS/Desktop/TradingAgents/frontend/src/pages/Chart.tsx) parses these annotations and feeds markers to the `CandlestickSeries` or adds separate line segments dynamically to the TradingView chart to represent trendlines.

### H. Vision-Based Pattern Recognition Pipeline
Numerical series can struggle with visual shapes. This system adds a visual analysis mechanism to identify classic chart patterns.

1. **Visual Plotting and Encoding:** The `get_vision_chart_analysis` tool in [chart_tools.py](file:///c:/Users/JustS/Desktop/TradingAgents/backend/trading_agents/agents/utils/chart_tools.py) slices the last 90 trading days, renders a clean PNG chart via `mplfinance` (with candlestick and volume plots), and converts it into a Base64 string.
2. **Vision Model Call:** It sends the image payload along with a structured prompt to the active session's vision-capable LLM to extract visual pattern insights (e.g., Head and Shoulders, Cup and Handle) and returns the text evaluation back to the caller.

### I. Multi-Timeframe Alignment and Overlay Mapping
Ensures daily-chart decisions remain aligned with long-term macro trendlines.

1. **High-Timeframe Sampling:** The `get_mtf_trend` tool in [chart_tools.py](file:///c:/Users/JustS/Desktop/TradingAgents/backend/trading_agents/agents/utils/chart_tools.py) fetches Weekly or Monthly historical data, computes a 20 EMA, and performs a backward merge/asof join mapping the values onto the daily trading index.
2. **Chart Overlay:** The resulting series is registered with an `"overlay": true` parameter, signaling [Chart.tsx](file:///c:/Users/JustS/Desktop/TradingAgents/frontend/src/pages/Chart.tsx) to plot the macro trend directly on top of the main daily price candlesticks as an overlay line.

