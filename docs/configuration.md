# Configuration & API Setup

TradingAgents is customized through environment variables stored in a `.env` file at the project root. These settings configure LLM endpoints, third-party data providers, database connections, and security parameters.

---

## 🔑 1. Security & Authentication Configuration

These settings control API encryption, password hashing, and CORS access:

```ini
# Security Token Secret Key (Required)
# Generate one using: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=change-me-to-a-random-32-character-string

# Administrator Settings
ADMIN_USERNAME=admin
# Optional bcrypt hash. If empty, defaults to hash of "changeme" or a randomly printed installer password
ADMIN_PASSWORD_HASH=

# DB Credential Encryption Key (Required)
# Used to encrypt sensitive API keys stored inside the settings database.
# Generate one using: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ENCRYPTION_KEY=your-fernet-key-here

# CORS Authorized Origins (Required)
# Must be a JSON array of domains allowed to call the FastAPI backend.
CORS_ORIGINS=["http://localhost:5173","http://localhost:3000"]
```

---

## 🗄️ 2. Database Connection

The database configuration utilizes SQLAlchemy async layers. PostgreSQL with the `asyncpg` driver is required:

```ini
# Format: postgresql+asyncpg://<user>:<password>@<host>:<port>/<dbname>
DATABASE_URL=postgresql+asyncpg://tradingagents:tradingagents@localhost:5432/tradingagents
```

---

## 🤖 3. LLM Provider Configurations

TradingAgents maps LLM requests to multiple model endpoints. Fill in the keys for the providers you plan to use:

```ini
# Core API Keys
OPENAI_API_KEY=               # GPT models (gpt-4o, o1, o3-mini)
ANTHROPIC_API_KEY=            # Claude models (claude-3-5-sonnet)
GOOGLE_API_KEY=               # Gemini models (gemini-2.0-flash/pro, gemini-2.5-flash)
XAI_API_KEY=                  # Grok models
DEEPSEEK_API_KEY=             # DeepSeek V3 / R1 models
OPENROUTER_API_KEY=           # Alternative multi-provider routing gateway
LITELLM_API_KEY=              # LiteLLM Proxy endpoint
AZURE_OPENAI_API_KEY=         # Enterprise Azure endpoints
```

### Provider-Specific Reasoning Configurations
Some reasoning models accept configuration parameters that are mapped dynamically from the application's configuration dictionary:
*   **Google Gemini:** Accepts `google_thinking_level` to control gemini thinking budget.
*   **OpenAI:** Accepts `openai_reasoning_effort` (low, medium, high) for o-series models.
*   **Anthropic:** Accepts `anthropic_effort` to control reasoning parameters.

---

## 📊 4. Data Vendor Configurations

To query stock/crypto details, sentiment, and news, configure the following APIs:

```ini
# Alpha Vantage (Optional)
# Used as an alternative data vendor for stock splits, technicals, or fundamentals.
# Get a key from: https://www.alphavantage.co/
ALPHA_VANTAGE_API_KEY=

# Reddit Sentiment API (Optional)
# Allows the Sentiment Analyst to fetch real-time discussions from subreddits like r/wallstreetbets.
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
REDDIT_USER_AGENT=TradingAgents/1.0
```

---

## 🔍 5. Search Engine Configuration (SearXNG)

The News Analyst queries search engines to fetch global current events. To avoid rate-limits, TradingAgents connects to a **SearXNG** instance:

```ini
# Local or public SearXNG URL (Required for News Analyst web searches)
SEARXNG_URL=http://localhost:8080
```

You can run a local SearXNG instance using Docker:
```bash
docker run -d -p 8080:8080 searxng/searxng
```

---

## 🎛️ 6. Platform Runtime Settings (Optional Overrides)

These environment variables can override the default parameters defined in [default_config.py](file:///c:/Users/JustS/Desktop/TradingAgents/backend/trading_agents/default_config.py):

```ini
# Select default LLM Provider (openai, anthropic, google, etc.)
TRADINGAGENTS_LLM_PROVIDER=openai

# Define default model name
TRADINGAGENTS_LLM_MODEL=gpt-4o-mini

# Language for generated markdown reports (e.g. English, Turkish)
TRADINGAGENTS_OUTPUT_LANGUAGE=English

# Max rounds for bull/bear and risk debates
TRADINGAGENTS_MAX_DEBATE_ROUNDS=2
TRADINGAGENTS_MAX_RISK_DISCUSS_ROUNDS=2

# Concurrency limits for analyst nodes (concurrency > 1 starts nodes in parallel)
TRADINGAGENTS_ANALYST_CONCURRENCY_LIMIT=2

# Include previous DB analysis reports in the AI graph context
TRADINGAGENTS_INCLUDE_HISTORICAL_ANALYSES=false

# Number of historical reports to fetch and include in context (1-50)
TRADINGAGENTS_HISTORICAL_ANALYSES_LIMIT=5

# JSON dictionary mapping analyst keys to specific provider-model strings.
# Example: {"market": "google:gemini-2.5-flash", "news": "deep", "social": "quick"}
# Special model choices: "deep" uses default deep model, "quick" or "" uses default model.
TRADINGAGENTS_ANALYST_MODELS={}
```
