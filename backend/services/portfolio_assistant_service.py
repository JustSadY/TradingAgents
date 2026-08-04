"""Portfolio Assistant — conversational AI with tool-calling.

The assistant can read portfolio, past analyses, watchlist, and alerts;
and can trigger actions (run analysis, set alert, place paper order)
with page-permission checks enforced per user.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.user import User
from backend.repositories import assistant as assistant_repo
from backend.repositories.permissions import list_allowed_page_keys
from backend.services.settings_service import get_or_create_settings
from backend.services.user_service import resolve_user_api_key

_logger = logging.getLogger(__name__)


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
- Prepare new price alerts for explicit user confirmation
- Trigger a new AI stock analysis in the configured queue
- Prepare paper trading orders for explicit user confirmation (simulation mode only)

Guidelines:
- Always fetch relevant data before answering a data question.
- Be concise and professional. Use bullet points for lists.
- Orders and alerts are two-step actions: prepare a preview first, then execute only after a later explicit user confirmation.
- When an analysis is triggered, inform the user it runs in the background and they can track it on the Analysis page.
- Today's date: {date}
"""

async def get_assistant_history(db: AsyncSession, user) -> list[dict]:
    messages = await assistant_repo.get_messages(db, user.id, limit=50)
    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "created_at": m.created_at.isoformat(),
        }
        for m in messages
    ]

async def clear_assistant_history(db: AsyncSession, user) -> None:
    await assistant_repo.clear_messages(db, user.id)
    await db.commit()

async def chat(db: AsyncSession, user: User, message: str) -> dict:
    from backend.services.agent_settings_service import build_agent_runtime_context
    from backend.trading_agents.llm_clients.factory import create_llm_client
    from backend.trading_agents.llm_clients.registry import provider_requires_api_key

    settings = await get_or_create_settings(db, user)
    allowed_pages = await _get_allowed_pages(db, user)

    explicitly_confirmed_ids = _explicit_confirmation_ids(message)
    tools = _make_tools(db, user, allowed_pages, confirmed_ids=explicitly_confirmed_ids)
    tool_map = {t.name: t for t in tools}

    lc_messages = await _prepare_lc_messages(db, user, message, settings)

    agent_ctx = await build_agent_runtime_context(db, user.id)
    pm_settings = agent_ctx.get("portfolio_manager", {}).get("settings", {})
    provider = pm_settings.get("llm_provider") or settings.llm_provider
    model = pm_settings.get("llm_model") or settings.llm_model

    user_key = resolve_user_api_key(user, provider)
    if provider_requires_api_key(provider) and not user_key:
        raise HTTPException(
            status_code=400,
            detail=f"No API key set for provider '{provider}'. Please add your API key in Settings.",
        )

    try:
        client = create_llm_client(provider=provider, model=model, api_key=user_key)
        llm = client.get_llm()
        llm_with_tools = llm.bind_tools(tools)
    except Exception as e:
        _logger.warning("Assistant client initialization failed: %s", e)
        raise HTTPException(status_code=400, detail="Assistant model could not be initialized.") from e

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

    action_tool_used = False
    action_tools = {"run_stock_analysis", "create_price_alert", "place_paper_order", "confirm_pending_action"}
    for _ in range(_MAX_TOOL_LOOP):
        try:
            response = await llm_with_tools.ainvoke(lc_messages)
        except Exception as e:
            _logger.warning("Assistant LLM error: %s", e)
            return "The assistant model could not complete this request. Please try again."

        lc_messages.append(response)

        if not response.tool_calls:
            from backend.services.llm_content import llm_text
            return llm_text(response)

        for tc in response.tool_calls:
            tool = tool_map.get(tc["name"])
            if tool is None:
                result_text = f"Unknown tool: {tc['name']}"
            elif tc["name"] in action_tools and action_tool_used:
                result_text = "Only one action or action preview may be requested per assistant message."
            else:
                if tc["name"] in action_tools:
                    action_tool_used = True
                try:
                    result_text = await tool.ainvoke(tc["args"])
                except Exception as e:
                    _logger.warning("Assistant tool execution failed for %s: %s", tc['name'], e)
                    result_text = f"Tool `{tc['name']}` could not complete safely."
            lc_messages.append(ToolMessage(content=str(result_text), tool_call_id=tc["id"]))

    return "I could not complete the request within the allowed steps. Please try again."

def _explicit_confirmation_ids(message: str) -> set[str]:
    """Return the one action ID the user explicitly and positively approved.

    Merely mentioning the word "confirm" must not expose the execution tool;
    negative phrases and messages containing multiple IDs are rejected.
    """
    normalized = " ".join((message or "").lower().split())
    negative = (
        "do not confirm", "don't confirm", "dont confirm", "not confirm", "reject", "cancel",
        "onaylama", "onaylamıyorum", "onaylamiyorum", "iptal", "reddet",
    )
    if any(token in normalized for token in negative):
        return set()
    positive = ("confirm", "approve", "onayla", "onaylıyorum", "onayliyorum")
    if not any(token in normalized for token in positive):
        return set()
    ids = set(re.findall(r"(?<![0-9a-f])[0-9a-f]{32}(?![0-9a-f])", normalized))
    return ids if len(ids) == 1 else set()


def _make_tools(
    db: AsyncSession, user: User, allowed_pages: set[str], *, confirmed_ids: set[str] | None = None
) -> list:
    confirmed_ids = confirmed_ids or set()
    from langchain_core.tools import tool

    @tool
    async def get_portfolio_summary() -> str:
        """Get the user's current paper trading portfolio: cash balance, open holdings with quantity/P&L, and total value."""
        return await _tool_get_portfolio_summary(db, user, allowed_pages)

    @tool
    async def get_analysis_history(ticker: str = "", limit: int = 5) -> str:
        """Get the user's past AI stock analysis results. Optionally filter by ticker (e.g. 'NVDA'). Returns signal, date, and summary for each."""
        return await _tool_get_analysis_history(db, user, allowed_pages, ticker, limit)

    @tool
    async def get_analysis_report(analysis_id: int) -> str:
        """Get the full AI analysis report for a specific analysis ID. Use get_analysis_history first to find IDs."""
        return await _tool_get_analysis_report(db, user, allowed_pages, analysis_id)

    @tool
    async def get_live_price(ticker: str) -> str:
        """Get the current live market price for a stock ticker symbol (e.g. 'AAPL', 'NVDA')."""
        return await _tool_get_live_price(user, allowed_pages, ticker)

    @tool
    async def get_watchlist() -> str:
        """Get the user's current watchlist tickers with live prices."""
        return await _tool_get_watchlist(db, user, allowed_pages)

    @tool
    async def get_alerts() -> str:
        """Get the user's active price alerts."""
        return await _tool_get_alerts(db, user, allowed_pages)

    @tool
    async def create_price_alert(ticker: str, condition: str, target_price: float) -> str:
        """Prepare a price-alert preview. This never creates the alert; it returns a confirmation ID for a later user-approved step."""
        return await _tool_create_price_alert(user, allowed_pages, ticker, condition, target_price)

    @tool
    async def run_stock_analysis(ticker: str) -> str:
        """Trigger a new AI analysis for a validated stock ticker using the configured analysis queue."""
        return await _tool_run_stock_analysis(user, allowed_pages, ticker)

    @tool
    async def place_paper_order(ticker: str, action: str, quantity: float) -> str:
        """Prepare a paper-order preview. This never places the order; it returns a confirmation ID for a later user-approved step."""
        return await _tool_place_paper_order(user, allowed_pages, ticker, action, quantity)

    @tool
    async def confirm_pending_action(confirmation_id: str) -> str:
        """Execute the exact pending action ID explicitly approved in this user message."""
        normalized_id = (confirmation_id or "").strip().lower()
        if normalized_id not in confirmed_ids:
            return "This action ID was not explicitly approved in the current user message."
        return await _tool_confirm_pending_action(user, allowed_pages, normalized_id)

    tool_pages = [
        (get_portfolio_summary, "portfolio"),
        (get_analysis_history, "analysis"),
        (get_analysis_report, "analysis"),
        (get_live_price, "chart"),
        (get_watchlist, "watchlist"),
        (get_alerts, "alerts"),
        (create_price_alert, "alerts"),
        (run_stock_analysis, "analysis"),
        (place_paper_order, "trading"),
    ]
    result = [tool_def for tool_def, page_key in tool_pages if _has_page_access(user, allowed_pages, page_key)]
    if confirmed_ids and (
        _has_page_access(user, allowed_pages, "alerts")
        or _has_page_access(user, allowed_pages, "trading")
    ):
        result.append(confirm_pending_action)
    return result

def _has_page_access(user: User, allowed_pages: set[str], page_key: str) -> bool:
    return bool(getattr(user, "is_admin", False)) or page_key in allowed_pages

def _page_denied(user: User, allowed_pages: set[str], page_key: str, label: str) -> str | None:
    if _has_page_access(user, allowed_pages, page_key):
        return None
    return f"Permission denied: you do not have access to the {label} page."

async def _tool_get_portfolio_summary(db: AsyncSession, user: User, allowed_pages: set[str]) -> str:
    denied = _page_denied(user, allowed_pages, "portfolio", "Portfolio")
    if denied:
        return denied
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
        _logger.warning("Assistant failed to fetch portfolio summary: %s", e)
        return "Portfolio data could not be loaded safely."

async def _tool_get_analysis_history(
    db: AsyncSession, user: User, allowed_pages: set[str], ticker: str, limit: int
) -> str:
    denied = _page_denied(user, allowed_pages, "analysis", "Analysis")
    if denied:
        return denied
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
        _logger.warning("Assistant failed to fetch analysis history: %s", e)
        return "Analysis history could not be loaded safely."

async def _tool_get_analysis_report(db: AsyncSession, user: User, allowed_pages: set[str], analysis_id: int) -> str:
    denied = _page_denied(user, allowed_pages, "analysis", "Analysis")
    if denied:
        return denied
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
        _logger.warning("Assistant failed to fetch analysis report %s: %s", analysis_id, e)
        return "The analysis report could not be loaded safely."

async def _tool_get_live_price(user: User, allowed_pages: set[str], ticker: str) -> str:
    denied = _page_denied(user, allowed_pages, "chart", "Chart")
    if denied:
        return denied
    try:
        from backend.services.market_data_service import get_live_price as _get_price

        price = await _get_price(ticker.strip().upper())
        if price is None:
            return f"Could not fetch live price for {ticker.upper()}."
        return f"{ticker.upper()}: ${price:,.2f}"
    except Exception as e:
        _logger.warning("Assistant live price lookup failed for %s: %s", ticker, e)
        return "The live price could not be loaded safely."

async def _tool_get_watchlist(db: AsyncSession, user: User, allowed_pages: set[str]) -> str:
    denied = _page_denied(user, allowed_pages, "watchlist", "Watchlist")
    if denied:
        return denied
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
        _logger.warning("Assistant failed to fetch watchlist: %s", e)
        return "The watchlist could not be loaded safely."

async def _tool_get_alerts(db: AsyncSession, user: User, allowed_pages: set[str]) -> str:
    denied = _page_denied(user, allowed_pages, "alerts", "Alerts")
    if denied:
        return denied
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
        _logger.warning("Assistant failed to fetch alerts: %s", e)
        return "Alerts could not be loaded safely."

async def _create_pending_action(user_id: int, action: str, payload: dict) -> str:
    from backend.core.database import AsyncSessionLocal
    from backend.models.assistant import AssistantPendingAction

    confirmation_id = uuid.uuid4().hex
    async with AsyncSessionLocal() as action_db:
        action_db.add(
            AssistantPendingAction(
                id=confirmation_id,
                user_id=user_id,
                action=action,
                payload=payload,
                expires_at=datetime.now(UTC) + timedelta(minutes=10),
            )
        )
        await action_db.commit()
    return confirmation_id

async def _tool_create_price_alert(
    user: User, allowed_pages: set[str], ticker: str, condition: str, target_price: float
) -> str:
    denied = _page_denied(user, allowed_pages, "alerts", "Alerts")
    if denied:
        return denied
    cond = condition.lower().strip()
    if cond not in ("above", "below"):
        return "condition must be 'above' or 'below'."
    if not (0 < float(target_price) <= 10_000_000):
        return "target_price must be greater than zero and within the supported range."
    try:
        from backend.core.utils import safe_ticker_component

        clean_ticker = safe_ticker_component(ticker.strip().upper(), max_len=20)
        confirmation_id = await _create_pending_action(
            user.id,
            "create_price_alert",
            {"ticker": clean_ticker, "condition": cond, "target_price": float(target_price)},
        )
        return (
            f"Alert preview: notify when {clean_ticker} goes {cond} ${float(target_price):,.2f}. "
            f"Nothing has been created. To approve, explicitly confirm action `{confirmation_id}` "
            "within 10 minutes."
        )
    except ValueError as exc:
        return f"Alert preview rejected: {exc}"
    except Exception as exc:
        _logger.warning("Assistant alert preview failed for %s: %s", ticker, exc)
        return "Alert preview could not be created safely."

async def _tool_run_stock_analysis(user: User, allowed_pages: set[str], ticker: str) -> str:
    denied = _page_denied(user, allowed_pages, "analysis", "Analysis")
    if denied:
        return denied
    task_id = str(uuid.uuid4())
    trade_date = datetime.now(UTC).strftime("%Y-%m-%d")

    try:
        from backend.core.database import AsyncSessionLocal
        from backend.repositories.analysis import create_analysis_result, update_analysis_result
        from backend.services.analysis_queue import dispatch_analysis
        from backend.services.analysis_service import discard_queued_task, register_queued_task
        from backend.services.settings_service import get_or_create_settings as _get_settings
        from backend.services.ticker_validation_service import validate_analysis_ticker

        validated = await validate_analysis_ticker(ticker.strip().upper(), asset_type="stock")
        clean_ticker = validated.ticker
        async with AsyncSessionLocal() as settings_db:
            bg_settings = await _get_settings(settings_db, user)
            queued_row = await create_analysis_result(
                settings_db,
                task_id=task_id,
                user_id=user.id,
                ticker=clean_ticker,
                trade_date=trade_date,
                asset_type="stock",
                status="queued",
                heartbeat_at=datetime.now(UTC),
                triggered_by="assistant",
            )

        await register_queued_task(
            task_id,
            ticker=clean_ticker,
            trade_date=trade_date,
            asset_type="stock",
            user_id=user.id,
        )
        try:
            await dispatch_analysis(
                None,
                ticker=clean_ticker,
                trade_date=trade_date,
                asset_type="stock",
                settings=bg_settings,
                task_id=task_id,
                user=user,
                triggered_by="assistant",
            )
        except Exception:
            async with AsyncSessionLocal() as failure_db:
                await update_analysis_result(
                    failure_db,
                    queued_row.id,
                    status="failed",
                    heartbeat_at=datetime.now(UTC),
                )
            await discard_queued_task(task_id, user.id)
            raise
        return (
            f"Analysis started for {clean_ticker} (date: {trade_date}, task_id: {task_id}). "
            "Track progress and results on the Analysis page."
        )
    except Exception as exc:
        _logger.warning("Assistant analysis trigger failed for %s: %s", ticker, exc)
        return "The analysis could not be started safely. Verify the symbol and try again."

async def _tool_place_paper_order(
    user: User, allowed_pages: set[str], ticker: str, action: str, quantity: float
) -> str:
    denied = _page_denied(user, allowed_pages, "trading", "Trading")
    if denied:
        return denied
    act = action.strip().upper()
    if act not in ("BUY", "SELL"):
        return "action must be 'BUY' or 'SELL'."
    if not (0 < float(quantity) <= 100_000):
        return "quantity must be greater than zero and no more than 100,000."
    try:
        from backend.core.utils import safe_ticker_component

        clean_ticker = safe_ticker_component(ticker.strip().upper(), max_len=20)
        confirmation_id = await _create_pending_action(
            user.id,
            "place_paper_order",
            {"ticker": clean_ticker, "action": act, "quantity": float(quantity)},
        )
        return (
            f"Paper-order preview: {act} {float(quantity):,.4f} shares of {clean_ticker}. "
            f"No order has been placed. To approve, explicitly confirm action `{confirmation_id}` "
            "within 10 minutes."
        )
    except ValueError as exc:
        return f"Order preview rejected: {exc}"
    except Exception as exc:
        _logger.warning("Assistant paper-order preview failed for %s: %s", ticker, exc)
        return "The paper-order preview could not be created safely."

async def _tool_confirm_pending_action(
    user: User, allowed_pages: set[str], confirmation_id: str
) -> str:
    confirmation_id = (confirmation_id or "").strip().lower()
    if len(confirmation_id) != 32 or any(ch not in "0123456789abcdef" for ch in confirmation_id):
        return "The confirmation ID is invalid."

    from sqlalchemy import select, update

    from backend.core.database import AsyncSessionLocal
    from backend.models.assistant import AssistantPendingAction

    async with AsyncSessionLocal() as action_db:
        row = (
            await action_db.execute(
                select(AssistantPendingAction).where(
                    AssistantPendingAction.id == confirmation_id,
                    AssistantPendingAction.user_id == user.id,
                )
            )
        ).scalar_one_or_none()
        now = datetime.now(UTC)
        if row is None:
            return "No pending action was found for that confirmation ID."
        if row.consumed_at is not None:
            return "That action has already been confirmed or cancelled."
        expires_at = row.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= now:
            await action_db.execute(
                update(AssistantPendingAction)
                .where(
                    AssistantPendingAction.id == confirmation_id,
                    AssistantPendingAction.user_id == user.id,
                    AssistantPendingAction.consumed_at.is_(None),
                )
                .values(consumed_at=now)
            )
            await action_db.commit()
            return "That confirmation expired. Prepare the action again."

        payload = dict(row.payload or {})
        if row.action == "create_price_alert":
            denied = _page_denied(user, allowed_pages, "alerts", "Alerts")
        elif row.action == "place_paper_order":
            denied = _page_denied(user, allowed_pages, "trading", "Trading")
        else:
            denied = None
        if denied:
            return denied

        # Claim and commit before executing the side effect.  PostgreSQL row
        # locks already serialized this path, but SQLite ignores FOR UPDATE; a
        # conditional update gives every supported database the same at-most-
        # once semantics under concurrent confirmations.  A failed side effect
        # remains consumed deliberately: the user must prepare a new preview
        # rather than risk replaying an order whose outcome is uncertain.
        claim = await action_db.execute(
            update(AssistantPendingAction)
            .where(
                AssistantPendingAction.id == confirmation_id,
                AssistantPendingAction.user_id == user.id,
                AssistantPendingAction.consumed_at.is_(None),
                AssistantPendingAction.expires_at > now,
            )
            .values(consumed_at=now)
        )
        if claim.rowcount != 1:
            await action_db.rollback()
            return "That action has already been confirmed, cancelled, or expired."
        await action_db.commit()

        try:
            if row.action == "create_price_alert":
                from backend.services.alert_creation_service import create_alert_with_guardrails

                alert = await create_alert_with_guardrails(
                    action_db,
                    user_id=user.id,
                    ticker=payload["ticker"],
                    condition=payload["condition"],
                    target_price=float(payload["target_price"]),
                    auto_analyze=False,
                    creation_source="assistant",
                )
                await action_db.commit()
                if alert is None:
                    return "The alert was not created because a configured alert limit is active."
                return (
                    f"Alert created (ID {alert.id}): notify when {payload['ticker']} goes "
                    f"{payload['condition']} ${float(payload['target_price']):,.2f}."
                )

            if row.action == "place_paper_order":
                from backend.services.mock_trading_service import execute_order

                result = await execute_order(
                    action_db,
                    ticker=payload["ticker"],
                    action=payload["action"],
                    quantity=float(payload["quantity"]),
                    user=user,
                )
                await action_db.commit()
                filled = float(result.get("quantity", payload["quantity"]))
                price = float(result.get("price", 0))
                return (
                    f"Paper order placed: {payload['action']} {filled:.4f} shares of "
                    f"{payload['ticker']} @ ${price:,.2f}. Total: ${filled * price:,.2f}."
                )

            return "The pending action type is no longer supported."
        except Exception as exc:
            await action_db.rollback()
            _logger.warning("Assistant confirmed action failed id=%s: %s", confirmation_id, exc)
            return "The confirmed action was rejected or could not be completed safely."

