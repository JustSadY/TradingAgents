# 🤖 TradingAgents AI: Multi-Agent Decision Engine

This directory contains the core multi-agent AI system designed to analyze securities, conduct investment thesis debates, negotiate position sizing parameters under risk constraints, and execute final trades. 

Built using **LangGraph** and **LangChain Core**, the system models complex financial decision-making as a state machine with asynchronous execution, self-correction reflection loops, and streaming updates.

---

## 🧭 Multi-Agent Workflow Architecture

Instead of relying on a single, general-purpose LLM prompt to make investment decisions, TradingAgents splits work among specialized AI personas. The execution flow is structured as follows:

```mermaid
graph TD
    Start([Start Run]) --> InitState[Initialize State]
    InitState --> AnalystExecution[Analyst Execution Node]
    
    subgraph Analysts [9 Specialized Analyst Plugins]
        AnalystExecution --> A1[Technical / Market]
        AnalystExecution --> A2[Social Sentiment]
        AnalystExecution --> A3[Global News]
        AnalystExecution --> A4[Fundamental Balance Sheet]
        AnalystExecution --> A5[Macroeconomics]
        AnalystExecution --> A6[Options Chain]
        AnalystExecution --> A7[Quantitative Factor]
        AnalystExecution --> A8[Earnings Call Transcript]
        AnalystExecution --> A9[Performance Review]
    end
    
    A1 & A2 & A3 & A4 & A5 & A6 & A7 & A8 & A9 --> SynthesisManager{Synthesis Manager}
    
    subgraph Debate [The Thesis Debate Loop]
        SynthesisManager --> Bull[Bull Researcher]
        SynthesisManager --> Bear[Bear Researcher]
        Bull & Bear --> Auditor[Auditor Node]
        Auditor --> Judge[Research Manager]
    end
    
    Judge --> RiskDebate{Risk Debate Node}
    
    subgraph Risk [Position Sizing & Safety Negotiation]
        RiskDebate --> RA[Aggressive Risk Agent]
        RiskDebate --> RC[Conservative Risk Agent]
        RiskDebate --> RN[Neutral Risk Agent]
    end
    
    RA & RC & RN --> FinalExecution[Portfolio Manager Decision Node]
    FinalExecution --> Reflection{Reflection & Correction Loop}
    Reflection -->|Validation Failed| AnalystExecution
    Reflection -->|Validation Approved| EndNode([Final Output & Execution])
```

---

## 📁 Package Layout

```text
trading_agents/
├── agents/                  # Prompt engineering, agent behaviors, and schemas
│   ├── analyst_registry.py   # Registry manager to load and execute analyst plugins
│   ├── schemas.py           # Structured output schemas (Pydantic models)
│   ├── analysts/            # Implementation of the 9 analyst plugins
│   ├── researchers/         # Bull & Bear thesis builders
│   ├── managers/            # Research, Synthesis, and Auditor managers
│   ├── risk_mgmt/           # Risk analyst personalities (Aggressive, Conservative, Neutral)
│   └── trader/              # Portfolio Manager (executes final buys/sells and sizes)
├── graph/                   # State machine structure (LangGraph engine)
│   ├── setup.py             # Instantiates, compiles, and chains StateGraph nodes
│   ├── checkpointer.py      # Persists conversation states and node states
│   ├── analyst_execution.py  # Coordinates parallel mapping execution of active analysts
│   ├── conditional_logic.py # Defines dynamic routing criteria between nodes
│   ├── reflection.py        # Logic to review outputs for hallucination or errors
│   └── trading_graph.py     # Graph entry runner with stream event hooks
├── llm_clients/             # Unified API clients for LLMs
│   └── client.py            # Adapts OpenAI, Claude, Gemini, DeepSeek, Grok, and Ollama
└── mock_trading/            # Internal mock accounts database / orders sandbox
```

---

## 🔬 Core Components

### 1. Dynamic Analyst Registry
All analyst plugins inherit from a base analyst class and register dynamically via [analyst_registry.py](agents/analyst_registry.py). Each analyst is given access to tools (e.g. `yfinance`, web search via SearXNG, social media APIs) to compile an isolated PDF/text report and extract key quantitative signal metrics.

The 9 analysts are:
1.  **Market Analyst:** Pulls historical stock prices, calculates MACD, RSI, Moving Averages, and visualizes trends.
2.  **Social Sentiment Analyst:** Mines Reddit (e.g., r/wallstreetbets) and StockTwits for bullish/bearish mentions and volumes.
3.  **News Analyst:** Fetches global news feeds and ranks general news sentiment.
4.  **Fundamentals Analyst:** Downloads income statements, balance sheets, and cash flow statements to assess corporate health.
5.  **Macroeconomics Analyst:** Examines interest rates, inflation metrics, and GDP indicators.
6.  **Options Chain Analyst:** Analyzes open interest, call/put volume ratios, and implied volatility curves.
7.  **Quantitative Factor Analyst:** Executes statistical models, factor loadings, and returns anomalies.
8.  **Earnings Call Analyst:** Summarizes corporate earnings calls, management tone, and guidance changes.
9.  **Performance Review Analyst:** Compares historical agent suggestions against simulated returns to optimize weights.

### 2. The Thesis Debate & Synthesis
To avoid LLM bias, analyst reports are synthesized by the **Synthesis Manager** to identify key conflicts. These are then debated by the **Bull Researcher** and **Bear Researcher**.
*   **Auditor Node:** Before the final decision, an Auditor node fact-checks the debate transcript against original reports to prevent hallucinations.
*   **Research Manager:** Reviews both arguments and the Auditor's report to summarize verified claims.

### 3. Risk Management & Portfolio Allocation
The Research Manager's summary is evaluated by three risk personas:
*   **Aggressive Risk Agent:** Argues for larger position sizing and wider stop-losses to capture maximum upside.
*   **Conservative Risk Agent:** Focuses on downside risk, urging tight stop-losses, hedging strategies, or skipping the trade entirely.
*   **Neutral Risk Agent:** Seeks a balanced allocation target.
They negotiate a compromise on:
- **Signal Strength:** (Buy / Sell / Hold / Avoid)
- **Position Allocation Size:** Percentage of total available cash.
- **Stop Loss & Take Profit Levels.**

### 4. Self-Correcting Reflection Loop
Before publishing the final report, the **Reflection Node** checks the generated output:
- It verifies that the recommended actions comply with the portfolio limits.
- It scans for hallucinations (e.g., mismatched prices or tickers).
- If validation fails, it loops back to the analyst or researcher nodes with a refinement request.

### 5. Modular Agent Tool Registry and Runtime Flow
To support dynamic tool schema extraction and runtime tool activation, the platform decouples individual tools from the core agent execution:
*   **BaseAgentTool Class (`agents/tools/base.py`):** Individual tools (e.g., Reddit Sentiment, Macroeconomic Data) inherit from `BaseAgentTool`, defining their execution logic (`_run` / `_arun`), their target analyst nodes, and their configurable settings schema (`ToolSettingField`).
*   **Tool Registry (`agents/tools/registry.py`):** Acts as the source of truth for all tools. Standard tools are registered at bootstrap (`agents/tools/bootstrap.py`).
*   **Thread-Safe Context Injection (`graph/trading_graph.py`):** Before running the state machine, user-specific or system-default settings are loaded from the database and merged into a `runtime_tool_context`. This context is stored in the LangGraph thread configuration.
*   **Runtime Tool Adaptation (`agents/utils/analyst_node_factory.py`):** In the analyst execution lifecycle (`run_tool_analyst`), the runtime filters active tools based on the context and adapts them dynamically into LangChain/LangGraph-compatible bindings.

### How to Register a New Agent Tool

To implement and register a new tool in the modular system, follow these steps:

1. **Implement the Tool Class:**
   Create a new file under `backend/trading_agents/agents/tools/builtin/` (e.g., `my_custom_tool.py`) extending `BaseAgentTool` or using `FunctionToolAdapter`:
   ```python
   from backend.trading_agents.agents.tools.base import BaseAgentTool, ToolSettingField, ToolContext
   from backend.trading_agents.agents.tools.registry import registry
   
   class MyCustomTool(BaseAgentTool):
       key = "my_custom_tool"
       category = "market"
       default_enabled = True
       allowed_analysts = ["market"]
       label_key = "tools.my_custom_tool.label"
       description_key = "tools.my_custom_tool.description"
       
       # Define the schema representing parameters the user/admin can configure:
       settings_schema = [
           ToolSettingField(
               key="max_items",
               type="number",
               scope="both",
               label_key="tools.my_custom_tool.max_items",
               default=10.0,
               min=1.0,
               max=100.0,
           )
       ]
       
       def get_langchain_tools(self, settings: dict, context: ToolContext) -> list:
           # Define or return standard LangChain @tool functions:
           from langchain_core.tools import tool
           
           limit = int(settings.get("max_items", 10))
           
           @tool
           def run_custom_query(query: str) -> str:
               """Run a custom analytical query."""
               return f"Results for '{query}' (limit: {limit})"
               
           return [run_custom_query]
           
   # Register it:
   registry.register(MyCustomTool())
   ```

2. **Add to Bootstrap Loader:**
   Import your module inside [backend/trading_agents/agents/tools/bootstrap.py](file:///home/lykia/Desktop/TradingAgents/backend/trading_agents/agents/tools/bootstrap.py) so it registers on server startup:
   ```python
   from .builtin import my_custom_tool
   ```

3. **Provide Localization Translations:**
   Add labels and descriptions in [tools.ts](file:///home/lykia/Desktop/TradingAgents/frontend/src/i18n/tools.ts) for:
   * `tools.my_custom_tool.label`
   * `tools.my_custom_tool.description`
   * `tools.my_custom_tool.max_items`

---

## 🔌 LLM Provider Integration

The system uses [llm_clients/](llm_clients) to abstract away API differences. It supports:
- **OpenAI:** `gpt-4o`, `o1`, `o3-mini`, etc. (Supports structured Pydantic output parsing).
- **Anthropic Claude:** `claude-3-5-sonnet-latest`.
- **Google Gemini:** `gemini-2.0-flash`, `gemini-2.5-pro` via native google SDK.
- **DeepSeek:** Native API support (`deepseek-chat`, `deepseek-reasoner`).
- **xAI Grok:** Grok API endpoint.
- **Ollama:** Enables running local models (like `llama3`, `mistral`, or `qwen`) for local development without API costs.
- **Azure OpenAI:** Enterprise private endpoints.

---

## 🚀 Advanced Institutional Features

TradingAgents is designed for high-conviction, professional analysis through three core pillars:

1.  **SEC & Insider Intelligence:** The **Fundamentals Analyst** leverages specialized tools (`get_sec_filings`, `get_insider_transactions_deep`) to monitor regulatory filings (10-K, 10-Q) and Form 4 insider transactions to gauge management sentiment and regulatory risks.
2.  **Mathematical Risk Sizing:** The **Portfolio Manager** uses a mathematical risk engine based on the **Kelly Criterion** (`K% = W - [(1 - W) / R]`) and **Sharpe Ratio** to calculate mathematically optimal position sizes based on win probability and risk/reward profiles.
3.  **Continuous Learning Loop:** The **Synthesis Manager** automated historical backtests set performance baselines, and past failures are injected as constraints to prevent the system from repeating historical errors on specific assets.
