"""Portfolio Assistant — conversational AI with tool-calling.

The assistant can read portfolio, past analyses, watchlist, and alerts;
and can trigger actions (run analysis, set alert, place paper order)
with page-permission checks enforced per user.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user import User
from backend.repositories import assistant as assistant_repo
from backend.repositories.permissions import list_allowed_page_keys
from backend.services.settings_service import get_or_create_settings
from backend.services.user_service import resolve_user_api_key

_logger = logging.getLogger(__name__)

_BACKGROUND_TASKS: set[asyncio.Task] = set()

_MAX_TOOL_LOOP = 5
_HISTORY_LIMIT = 20

_SYSTEM_PROMPT = """You are an intelligent portfolio assistant for the TradingAgents platform.
You help users manage their investments by answering questions and taking actions on their behalf.

You have access to tools that let you:
- Check portfolio holdings, cash balance, and P&L
- Review past AI analysis reports (filter by ticker symbol)
- Get the full text of a specific analysis report
- Look up current live stock prices
- See the user's watchlist and price alerts
- Create new price alerts
- Trigger a new AI stock analysis (takes 2-3 minutes, runs in background)
- Place paper trading orders (simulation mode only)

Guidelines:
- Always fetch relevant data before answering a data question.
- Be concise and professional. Use bullet points for lists.
- When placing orders or creating alerts, confirm the details clearly.
- When an analysis is triggered, inform the user it runs in the background and they can track it on the Analysis page.
- Today's date: {date}
"""


async def get_assistant_history(db: AsyncSession, user_id: int) -> list[dict]:
    messages = await assistant_repo.get_messages(db, user_id, limit=50)
    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "created_at": m.created_at.isoformat(),
        }
        for m in messages
    ]


async def clear_assistant_history(db: AsyncSession, user_id: int) -> None:
    await assistant_repo.clear_messages(db, user_id)
    await db.commit()


async def chat(db: AsyncSession, user: User, message: str) -> dict:
    from backend.services.agent_settings_service import build_agent_runtime_context
    from backend.trading_agents.llm_clients.factory import create_llm_client

    settings = await get_or_create_settings(db, user)
    allowed_pages = await _get_allowed_pages(db, user)

    tools = _make_tools(db, user, allowed_pages)
    tool_map = {t.name: t for t in tools}

    lc_messages = await _prepare_lc_messages(db, user, message, settings)

    agent_ctx = await build_agent_runtime_context(db, user.id)
    pm_settings = agent_ctx.get("portfolio_manager", {}).get("settings", {})
    provider = pm_settings.get("llm_provider") or settings.llm_provider
    model = pm_settings.get("llm_model") or settings.llm_model

    user_key = resolve_user_api_key(user, provider)
    if not user_key and not user.is_admin:
        raise HTTPException(
            status_code=400,
            detail=f"No API key set for provider '{provider}'. Please add your API key in Settings.",
        )

    try:
        client = create_llm_client(provider=provider, model=model, api_key=user_key)
        llm = client.get_llm()
        llm_with_tools = llm.bind_tools(tools)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    final_content = await _run_tool_loop(llm_with_tools, lc_messages, tool_map)

    await assistant_repo.add_message(db, user.id, "user", message)
    assistant_msg = await assistant_repo.add_message(db, user.id, "assistant", final_content)
    await db.commit()

    return {
        "id": assistant_msg.id,
        "role": "assistant",
        "content": final_content,
        "created_at": assistant_msg.created_at.isoformat(),
    }


async def _get_allowed_pages(db: AsyncSession, user: User) -> set[str]:
    if user.is_admin:
        return {"analysis", "trading", "portfolio", "alerts", "watchlist"}
    return await list_allowed_page_keys(db, user.id)


async def _prepare_lc_messages(db: AsyncSession, user: User, message: str, settings) -> list:
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    history = await assistant_repo.get_messages(db, user.id, limit=_HISTORY_LIMIT)
    lang = (settings.output_language or "English").strip()
    lang_inst = "" if lang.lower() == "english" else f" Write your entire response in {lang}."

    system_content = _SYSTEM_PROMPT.format(date=datetime.now(UTC).strftime("%Y-%m-%d")) + lang_inst
    lc_messages = [SystemMessage(content=system_content)]
    for msg in history:
        lc_messages.append(HumanMessage(content=msg.content) if msg.role == "user" else AIMessage(content=msg.content))
    lc_messages.append(HumanMessage(content=message))
    return lc_messages


async def _run_tool_loop(llm_with_tools, lc_messages: list, tool_map: dict) -> str:
    from langchain_core.messages import ToolMessage

    for _ in range(_MAX_TOOL_LOOP):
        try:
            response = await llm_with_tools.ainvoke(lc_messages)
        except Exception as e:
            _logger.warning("Assistant LLM error: %s", e)
            return f"I encountered an error: {e}"

        lc_messages.append(response)

        if not response.tool_calls:
            return response.content if isinstance(response.content, str) else str(response.content)

        for tc in response.tool_calls:
            tool = tool_map.get(tc["name"])
            if tool is None:
                result_text = f"Unknown tool: {tc['name']}"
            else:
                try:
                    result_text = await tool.ainvoke(tc["args"])
                except Exception as e:
                    result_text = f"Tool error ({tc['name']}): {e}"
            lc_messages.append(ToolMessage(content=str(result_text), tool_call_id=tc["id"]))

    return "I could not complete the request within the allowed steps. Please try again."


def _make_tools(db: AsyncSession, user: User, allowed_pages: set[str]) -> list:
    from langchain_core.tools import tool

    @tool
    async def get_portfolio_summary() -> str:
        """Get the user's current paper trading portfolio: cash balance, open holdings with quantity/P&L, and total value."""
        return await _tool_get_portfolio_summary(db, user)

    @tool
    async def get_analysis_history(ticker: str = "", limit: int = 5) -> str:
        """Get the user's past AI stock analysis results. Optionally filter by ticker (e.g. 'NVDA'). Returns signal, date, and summary for each."""
        return await _tool_get_analysis_history(db, user, ticker, limit)

    @tool
    async def get_analysis_report(analysis_id: int) -> str:
        """Get the full AI analysis report for a specific analysis ID. Use get_analysis_history first to find IDs."""
        return await _tool_get_analysis_report(db, user, analysis_id)

    @tool
    async def get_live_price(ticker: str) -> str:
        """Get the current live market price for a stock ticker symbol (e.g. 'AAPL', 'NVDA')."""
        return await _tool_get_live_price(ticker)

    @tool
    async def get_watchlist() -> str:
        """Get the user's current watchlist tickers with live prices."""
        return await _tool_get_watchlist(db, user)

    @tool
    async def get_alerts() -> str:
        """Get the user's active price alerts."""
        return await _tool_get_alerts(db, user)

    @tool
    async def create_price_alert(ticker: str, condition: str, target_price: float) -> str:
        """Create a new price alert. condition must be 'above' or 'below'. target_price is the trigger price in USD."""
        return await _tool_create_price_alert(user, allowed_pages, ticker, condition, target_price)

    @tool
    async def run_stock_analysis(ticker: str) -> str:
        """Trigger a new AI analysis for a stock ticker. Runs in the background (2-3 minutes). User can track progress on the Analysis page."""
        return await _tool_run_stock_analysis(user, allowed_pages, ticker)

    @tool
    async def place_paper_order(ticker: str, action: str, quantity: float) -> str:
        """Place a paper trading order. action must be 'BUY' or 'SELL'. quantity is number of shares (can be fractional)."""
        return await _tool_place_paper_order(user, allowed_pages, ticker, action, quantity)

    return [
        get_portfolio_summary,
        get_analysis_history,
        get_analysis_report,
        get_live_price,
        get_watchlist,
        get_alerts,
        create_price_alert,
        run_stock_analysis,
        place_paper_order,
    ]


async def _tool_get_portfolio_summary(db: AsyncSession, user: User) -> str:
    try:
        from backend.repositories.portfolio import get_simulation_portfolio
        from backend.services.market_data_service import get_live_prices_batch

        portfolio = await get_simulation_portfolio(db, user.id)
        if not portfolio:
            return "No portfolio found. The user has not started paper trading yet."

        lines = [
            f"Cash available: ${float(portfolio.cash_available):,.2f}",
            f"Total balance: ${float(portfolio.current_balance):,.2f}",
        ]
        if portfolio.holdings:
            tickers = [h.ticker for h in portfolio.holdings]
            prices = await get_live_prices_batch(tickers)
            lines.append(f"\nHoldings ({len(portfolio.holdings)}):")
            for h in portfolio.holdings:
                price = prices.get(h.ticker)
                price_str = f"${price:,.2f}" if price else "N/A"
                pnl = float(h.unrealized_pnl)
                pnl_str = f"+${pnl:,.2f}" if pnl >= 0 else f"-${abs(pnl):,.2f}"
                lines.append(
                    f"  {h.ticker}: {float(h.quantity):.4f} shares @ avg ${float(h.avg_buy_price):,.2f} | "
                    f"current {price_str} | P&L {pnl_str}"
                )
        else:
            lines.append("\nNo open holdings.")
        return "\n".join(lines)
    except Exception as e:
        return f"Could not fetch portfolio: {e}"


async def _tool_get_analysis_history(db: AsyncSession, user: User, ticker: str, limit: int) -> str:
    try:
        from sqlalchemy import select

        from backend.models.analysis import AnalysisResult
        from backend.repositories.common import scope_to_user

        n = max(1, min(limit, 10))
        q = (
            select(
                AnalysisResult.id,
                AnalysisResult.ticker,
                AnalysisResult.trade_date,
                AnalysisResult.signal,
                AnalysisResult.final_decision,
                AnalysisResult.created_at,
            )
            .where(AnalysisResult.status == "completed")
            .order_by(AnalysisResult.created_at.desc())
            .limit(n)
        )
        q = scope_to_user(q, AnalysisResult, user)
        if ticker.strip():
            q = q.where(AnalysisResult.ticker == ticker.strip().upper())

        rows = (await db.execute(q)).fetchall()
        if not rows:
            return f"No completed analyses found{' for ' + ticker.upper() if ticker else ''}."

        lines = []
        for row in rows:
            summary = (row.final_decision or "")[:300].strip()
            if len(row.final_decision or "") > 300:
                summary += "…"
            lines.append(f"[ID {row.id}] {row.ticker} | {row.trade_date} | Signal: {row.signal or 'N/A'}\n  {summary}")
        return "\n\n".join(lines)
    except Exception as e:
        return f"Could not fetch analysis history: {e}"


async def _tool_get_analysis_report(db: AsyncSession, user: User, analysis_id: int) -> str:
    try:
        from sqlalchemy import select

        from backend.models.analysis import AnalysisResult
        from backend.repositories.common import scope_to_user

        q = select(AnalysisResult).where(AnalysisResult.id == analysis_id)
        q = scope_to_user(q, AnalysisResult, user)
        analysis = (await db.execute(q)).scalar_one_or_none()
        if analysis is None:
            return f"Analysis ID {analysis_id} not found."

        sections = []
        for label, attr in [
            ("Final Decision", "final_decision"),
            ("Market Report", "market_report"),
            ("Fundamentals", "fundamentals_report"),
            ("News", "news_report"),
            ("Sentiment", "sentiment_report"),
        ]:
            text = (getattr(analysis, attr, "") or "").strip()
            if text:
                sections.append(f"### {label}\n{text[:2000]}")

        return (
            f"Analysis for {analysis.ticker} ({analysis.trade_date}) — Signal: {analysis.signal or 'N/A'}\n\n"
            + "\n\n".join(sections)
        )
    except Exception as e:
        return f"Could not fetch report: {e}"


async def _tool_get_live_price(ticker: str) -> str:
    try:
        from backend.services.market_data_service import get_live_price as _get_price

        price = await _get_price(ticker.strip().upper())
        if price is None:
            return f"Could not fetch live price for {ticker.upper()}."
        return f"{ticker.upper()}: ${price:,.2f}"
    except Exception as e:
        return f"Price lookup failed: {e}"


async def _tool_get_watchlist(db: AsyncSession, user: User) -> str:
    try:
        from backend.services.market_data_service import get_live_prices_batch
        from backend.services.settings_service import get_or_create_settings as _get_settings

        s = await _get_settings(db, user)
        tickers = s.watchlist if isinstance(s.watchlist, list) else []
        if not tickers:
            return "Watchlist is empty."
        prices = await get_live_prices_batch(tickers)
        lines = [f"  {t}: ${prices[t]:,.2f}" if t in prices else f"  {t}: N/A" for t in tickers]
        return "Watchlist:\n" + "\n".join(lines)
    except Exception as e:
        return f"Could not fetch watchlist: {e}"


async def _tool_get_alerts(db: AsyncSession, user: User) -> str:
    try:
        from backend.repositories.alerts import list_alerts

        alerts = await list_alerts(db, user=user)
        if not alerts:
            return "No price alerts set."
        lines = []
        for a in alerts:
            status = "triggered" if a.triggered_at else ("active" if a.enabled else "disabled")
            lines.append(f"  [{a.id}] {a.ticker} — {a.condition} ${float(a.target_price):,.2f} | {status}")
        return "Price alerts:\n" + "\n".join(lines)
    except Exception as e:
        return f"Could not fetch alerts: {e}"


async def _tool_create_price_alert(
    user: User, allowed_pages: set[str], ticker: str, condition: str, target_price: float
) -> str:
    if "alerts" not in allowed_pages and not user.is_admin:
        return "Permission denied: you do not have access to the Alerts page."
    cond = condition.lower().strip()
    if cond not in ("above", "below"):
        return "condition must be 'above' or 'below'."
    try:
        from backend.core.database import AsyncSessionLocal
        from backend.repositories.alerts import create_alert as _create

        async with AsyncSessionLocal() as alert_db:
            alert = await _create(
                alert_db,
                user_id=user.id,
                ticker=ticker.strip().upper(),
                condition=cond,
                target_price=target_price,
                auto_analyze=False,
            )
            await alert_db.commit()
        return f"Alert created (ID {alert.id}): notify when {ticker.upper()} goes {cond} ${target_price:,.2f}."
    except Exception as e:
        return f"Alert creation failed: {e}"


async def _tool_run_stock_analysis(user: User, allowed_pages: set[str], ticker: str) -> str:
    if "analysis" not in allowed_pages and not user.is_admin:
        return "Permission denied: you do not have access to the Analysis page."
    clean_ticker = ticker.strip().upper()
    task_id = str(uuid.uuid4())
    trade_date = datetime.now(UTC).strftime("%Y-%m-%d")

    try:
        from backend.core.database import AsyncSessionLocal
        from backend.services.analysis_service import register_task_owner, run_analysis_task
        from backend.services.settings_service import get_or_create_settings as _get_settings

        await register_task_owner(task_id, user.id)

        async def _bg() -> None:
            async with AsyncSessionLocal() as bg_db:
                bg_settings = await _get_settings(bg_db, user)
                await run_analysis_task(clean_ticker, trade_date, "stock", bg_settings, task_id, user)

        task = asyncio.create_task(_bg())
        _BACKGROUND_TASKS.add(task)
        task.add_done_callback(_BACKGROUND_TASKS.discard)
        return f"Analysis started for {clean_ticker} (date: {trade_date}, task_id: {task_id}). It will take about 2-3 minutes. Go to the Analysis page to track progress and see results."
    except Exception as e:
        return f"Could not start analysis: {e}"


async def _tool_place_paper_order(
    user: User, allowed_pages: set[str], ticker: str, action: str, quantity: float
) -> str:
    if "trading" not in allowed_pages and not user.is_admin:
        return "Permission denied: you do not have access to the Trading page."
    act = action.strip().upper()
    if act not in ("BUY", "SELL"):
        return "action must be 'BUY' or 'SELL'."
    if quantity <= 0:
        return "quantity must be positive."
    try:
        from backend.core.database import AsyncSessionLocal
        from backend.services.mock_trading_service import execute_order

        async with AsyncSessionLocal() as order_db:
            result = await execute_order(
                order_db, ticker=ticker.strip().upper(), action=act, quantity=quantity, user=user
            )
        filled = result.get("filled_quantity", quantity)
        price = result.get("price_per_share", 0)
        return f"Order placed: {act} {filled:.4f} shares of {ticker.upper()} @ ${float(price):,.2f}. Total: ${float(filled) * float(price):,.2f}."
    except ValueError as e:
        return f"Order rejected: {e}"
    except Exception as e:
        return f"Order failed: {e}"
