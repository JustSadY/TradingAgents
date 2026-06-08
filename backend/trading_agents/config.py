import os
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

_HOME = Path.home() / ".tradingagents"


class TradingAgentsConfig(BaseModel):
    project_dir: str = Field(
        default_factory=lambda: str(Path(__file__).parent.resolve()),
    )
    results_dir: str = Field(
        default_factory=lambda: os.environ.get("TRADINGAGENTS_RESULTS_DIR", str(_HOME / "logs")),
    )
    data_cache_dir: str = Field(
        default_factory=lambda: os.environ.get(
            "TRADINGAGENTS_CACHE_DIR", os.environ.get("TRADINGAGENTS_DATA_CACHE_DIR", str(_HOME / "cache"))
        ),
    )
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"
    google_thinking_level: str | None = None
    openai_reasoning_effort: str | None = None
    anthropic_effort: str | None = None
    output_language: str = "English"
    investor_persona: str = "conservative"
    max_debate_rounds: int = Field(default=1, ge=1, le=10)
    max_risk_discuss_rounds: int = Field(default=1, ge=1, le=10)
    max_recur_limit: int = Field(default=1000, ge=1)
    analyst_concurrency_limit: int = Field(default=1, ge=1)
    node_retry_attempts: int = Field(default=2, ge=1)
    node_retry_base_delay: float = Field(default=1.0, ge=0.0)
    strict_backtest_learning: bool = True
    super_portfolio_manager_prompt: str = (
        "You are a Super Portfolio Manager advising a new investor with a $100,000 portfolio. "
        "Your team of analysts and traders has analyzed multiple assets, and your job is to build a "
        "clear, beginner-friendly allocation across those assets. "
        "Prioritize capital preservation, diversification, position sizing discipline, and "
        "risk-adjusted returns over aggressive speculation. "
        "Provide percentage allocations for each ticker (e.g., AAPL: 40%, MSFT: 35%) and include a "
        "cash allocation when the risk/reward profile is not attractive. "
        "Avoid concentrating too much capital in a single high-risk asset unless the reports provide "
        "unusually strong evidence. "
        "Write a detailed but easy-to-understand summary explaining the allocation strategy, the key "
        "risks, and what a new investor should monitor after entering the positions."
    )
    news_article_limit: int = Field(default=20, ge=1)
    global_news_article_limit: int = Field(default=10, ge=1)
    global_news_lookback_days: int = Field(default=7, ge=1)
    global_news_queries: list[str] = Field(
        default_factory=lambda: [
            "Federal Reserve interest rates inflation",
            "S&P 500 earnings GDP economic outlook",
            "geopolitical risk trade war sanctions",
            "ECB Bank of England BOJ central bank policy",
            "oil commodities supply chain energy",
        ]
    )
    data_vendors: dict[str, str] = Field(
        default_factory=lambda: {
            "core_stock_apis": "yfinance",
            "technical_indicators": "yfinance",
            "fundamental_data": "yfinance",
            "news_data": "yfinance",
        }
    )
    tool_vendors: dict[str, str] = Field(default_factory=dict)
    benchmark_ticker: str | None = None
    benchmark_map: dict[str, str] = Field(
        default_factory=lambda: {
            ".NS": "^NSEI",
            ".BO": "^BSESN",
            ".T": "^N225",
            ".HK": "^HSI",
            ".L": "^FTSE",
            ".TO": "^GSPTSE",
            ".AX": "^AXJO",
            "": "SPY",
        }
    )

    @field_validator("llm_provider", mode="before")
    @classmethod
    def normalise_provider(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("anthropic_effort", "openai_reasoning_effort", mode="before")
    @classmethod
    def normalise_effort(cls, v):
        if v is None:
            return v
        return v.strip().lower()

    def to_dict(self) -> dict:
        return self.model_dump()
