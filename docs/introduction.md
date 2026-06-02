# TradingAgents Documentation Index

Welcome to the detailed technical documentation for the **TradingAgents** platform. This repository contains a sophisticated, multi-agent AI system designed to automate financial analysis, debate investment theses, assess portfolios, and manage mock/simulation trades.

Here is the index of available documentation files:

1.  **[Introduction & System Overview](file:///c:/Users/JustS/Desktop/TradingAgents/docs/introduction.md):** High-level feature list, technology stack, and directory layout.
2.  **[System Architecture](file:///c:/Users/JustS/Desktop/TradingAgents/docs/architecture.md):** In-depth structural diagrams (using Mermaid), data flow boundaries, and backend-frontend interaction.
3.  **[Installation & Setup Guide](file:///c:/Users/JustS/Desktop/TradingAgents/docs/installation.md):** Step-by-step guides for single-command Linux deployments, Docker Compose containers, and local manual developer setups.
4.  **[Configuration & API Setup](file:///c:/Users/JustS/Desktop/TradingAgents/docs/configuration.md):** Complete guide to configuration files, environment variables (`.env`), LLM providers, and third-party data vendor setups.
5.  **[Multi-Agent Decision Core](file:///c:/Users/JustS/Desktop/TradingAgents/docs/multi_agent_system.md):** Detailed analysis of the LangGraph state machine, the Bull/Bear debate loop, risk analysts, the Portfolio Manager finalizer, and the self-correcting reflection loop.
6.  **[Developer Guide](file:///c:/Users/JustS/Desktop/TradingAgents/docs/developer_guide.md):** Guide on extending the system, registering custom analyst plugins, interacting with the real-time WebSocket progress stream, and configuring background cron schedulers.

---

## 🚀 System Design Paradigm

TradingAgents operates on three central design paradigms:
1.  **Fact Verification through Debate:** Rather than asking a single LLM model to analyze a security, the platform pits a dedicated Bull Researcher against a Bear Researcher. The Research Manager functions as an objective judge, ensuring all positive signals and risks are accounted for.
2.  **Strict Sizing and Risk Boundaries:** Even if a high-conviction buy signal is agreed upon by the debate agents, the plan is subjected to a secondary Risk Debate (Aggressive, Conservative, and Neutral agents) to negotiate position sizes, stop-losses, and profit targets.
3.  **Asynchronous Responsiveness:** The web frontend (React SPA) and backend (FastAPI) communicate continuously using WebSockets. Long-running multi-agent tasks are offloaded to asynchronous worker threads to keep the system responsive.
