import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from backend.core.database import get_db
from backend.models.analysis import AnalysisResult
from backend.models.settings import AppSettings
from backend.models.user import User
from backend.schemas.analysis import (
    AnalysisRunRequest, AnalysisRunResponse,
    AnalysisResultRead, AnalysisListItem,
    ChatMessageRead, ChatMessageCreate,
)
from backend.schemas.portfolio_analysis import (
    MultiTickerRunRequest, MultiTickerRunResponse,
    MultiTickerListItem, MultiTickerResultRead,
)
from backend.models.portfolio_analysis import MultiTickerAnalysis
from backend.api.deps import get_current_user
from backend.api.settings import _get_or_create_settings
import json as _json
from backend.core.utils import safe_ticker_component

router = APIRouter(prefix="/api/analysis", tags=["analysis"])
_logger = logging.getLogger(__name__)


@router.post("/run", response_model=AnalysisRunResponse)
async def run_analysis(
    body: AnalysisRunRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    # Validate ticker against path traversal
    try:
        safe_ticker_component(body.ticker)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    settings = await _get_or_create_settings(db, _)
    current_user = _  # captured for background task

    import uuid
    task_id = str(uuid.uuid4())

    # Run analysis in background so the HTTP response returns immediately
    async def _bg():
        async with __import__("backend.core.database", fromlist=["AsyncSessionLocal"]).AsyncSessionLocal() as bg_db:
            try:
                from backend.services.analysis_service import run_analysis as _run
                from backend.services.execution.factory import get_trader
                task_id_out, row = await _run(
                    body.ticker, body.trade_date, body.asset_type, settings, bg_db, "manual",
                    task_id=task_id,
                    user=current_user,
                )
                # Tag the result with the user who ran it
                if row.user_id is None and current_user is not None:
                    row.user_id = current_user.id
                await bg_db.commit()

                # Execute trade if warranted
                if row.signal in ("Buy", "Overweight", "Sell", "Underweight"):
                    from backend.services.execution.factory import get_trader
                    from backend.services.execution.base import OrderRequest
                    try:
                        trader = get_trader(
                            mode=settings.trading_mode,
                            broker=settings.active_broker,
                            portfolio_id=1,
                            initial_capital=100_000.0,
                            db=None,
                        )
                        price = trader.get_current_price(body.ticker) or 0.0
                        action = "BUY" if row.signal in ("Buy", "Overweight") else "SELL"
                        if price > 0:
                            quantity = (settings.max_risk_per_trade_pct / 100 * 100_000) / price
                            req = OrderRequest(
                                ticker=body.ticker,
                                action=action,
                                quantity=quantity,
                                reference_price=price,
                                ai_signal=row.signal or "",
                                ai_reasoning=row.final_decision[:500],
                            )
                            result = trader.place_order(req)
                            _logger.info("Order placed: %s", result)
                    except Exception as e:
                        _logger.warning("Order execution skipped: %s", e)
            except Exception as exc:
                # run_analysis already sends WS error + closes task for errors
                # inside its own try block. This catch handles any unexpected
                # failures that slip through (e.g. DB commit error after analysis).
                _logger.error("Background analysis failed: %s", exc, exc_info=True)
                try:
                    from backend.core.websocket import ws_manager as _wm
                    await _wm.send(task_id, {"type": "error", "message": f"Analiz hatası: {exc}"})
                    await _wm.close_task(task_id)
                except Exception:
                    pass
                await bg_db.rollback()

    background_tasks.add_task(_bg)

    return AnalysisRunResponse(task_id=task_id, ticker=body.ticker, trade_date=body.trade_date)


@router.get("/history", response_model=list[AnalysisListItem])
async def list_analysis(
    ticker: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(AnalysisResult).order_by(desc(AnalysisResult.created_at)).limit(limit).offset(offset)
    if ticker:
        q = q.where(AnalysisResult.ticker == ticker.upper())
    if not current_user.is_admin:
        q = q.where(AnalysisResult.user_id == current_user.id)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/{task_id}/cancel")
async def cancel_analysis(
    task_id: str,
    _: User = Depends(get_current_user),
):
    """Cancel a running analysis task."""
    from backend.services.analysis_service import cancel_analysis as _cancel
    cancelled = await _cancel(task_id)
    return {"cancelled": cancelled, "task_id": task_id}


@router.get("/{analysis_id}", response_model=AnalysisResultRead)
async def get_analysis(
    analysis_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(AnalysisResult).where(AnalysisResult.id == analysis_id)
    if not current_user.is_admin:
        q = q.where(AnalysisResult.user_id == current_user.id)
    result = await db.execute(q)
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return row


# ── Performance & cost endpoints ─────────────────────────────────────────────

_TOKEN_PER_ANALYST = 8_000   # rough average tokens consumed per analyst
_COST_PER_1K: dict[str, float] = {
    "gpt-4o": 0.005, "gpt-4o-mini": 0.00015, "gpt-4.1": 0.008,
    "claude-opus": 0.015, "claude-sonnet": 0.003, "gemini-1.5-pro": 0.007,
}


@router.get("/cost-estimate")
async def cost_estimate(
    analysts: str = Query(default="market,news,fundamentals,social"),
    debate_rounds: int = Query(default=1, ge=1, le=10),
    model: str = Query(default="gpt-4o"),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    analyst_list = [a.strip() for a in analysts.split(",") if a.strip()]
    n = len(analyst_list)
    tokens = n * _TOKEN_PER_ANALYST * debate_rounds + 5_000  # base overhead
    rate = next((v for k, v in _COST_PER_1K.items() if k in model.lower()), 0.005)
    cost = tokens / 1000 * rate
    return {
        "analyst_count": n,
        "estimated_tokens": tokens,
        "estimated_cost_usd": round(cost, 4),
        "estimated_duration_min": round(n * 0.8 * debate_rounds + 1, 1),
    }


@router.get("/ab-comparison")
async def get_ab_comparison(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Return metrics for all completed analyses grouped by preset/LLM model configuration."""
    q = select(AnalysisResult)
    res = await db.execute(q)
    rows = res.scalars().all()

    # Group in python for ultimate flexibility
    groups = {}
    for row in rows:
        preset = row.preset_name or f"{row.llm_provider or 'unknown'}:{row.llm_model or 'unknown'}"
        if preset not in groups:
            groups[preset] = []
        groups[preset].append(row)

    # Cost mapping
    cost_map = {
        "gpt-4o": 0.005, "gpt-4o-mini": 0.00015, "gpt-4.1": 0.008,
        "claude-opus": 0.015, "claude-sonnet": 0.003, "gemini-1.5-pro": 0.007,
        "gemini-2.0": 0.00015, "gemini-2.5": 0.00015, "deepseek": 0.00014,
    }

    comparison = []
    for preset, runs in groups.items():
        total = len(runs)
        durations = [r.duration_seconds for r in runs if r.duration_seconds > 0]
        avg_dur = sum(durations) / len(durations) if durations else 0.0

        total_tokens = [r.tokens_in + r.tokens_out for r in runs]
        avg_tok = sum(total_tokens) / total if total_tokens else 0.0

        # Calculate cost for each run
        costs = []
        for r in runs:
            model = (r.llm_model or "gpt-4o").lower()
            rate = next((v for k, v in cost_map.items() if k in model), 0.002)
            costs.append((r.tokens_in + r.tokens_out) / 1000 * rate)
        avg_cost = sum(costs) / total if costs else 0.0

        # Calculate win rate based on raw_return direction relative to signal
        wins = 0
        total_graded = 0
        for r in runs:
            if r.raw_return is not None and r.signal:
                if r.signal in ("Buy", "Overweight"):
                    total_graded += 1
                    if r.raw_return > 0:
                        wins += 1
                elif r.signal in ("Sell", "Underweight"):
                    total_graded += 1
                    if r.raw_return < 0:
                        wins += 1

        win_rate = round(wins / total_graded * 100, 1) if total_graded > 0 else None

        comparison.append({
            "preset_name": preset,
            "total_runs": total,
            "avg_duration": round(avg_dur, 1),
            "avg_tokens": int(avg_tok),
            "avg_cost_usd": round(avg_cost, 4),
            "win_rate": win_rate,
            "total_graded": total_graded,
        })

    # If no data exists, load mock data for demonstration purposes
    if not comparison:
        comparison = [
            {
                "preset_name": "OpenAI Presets (GPT-4o)",
                "total_runs": 12,
                "avg_duration": 48.2,
                "avg_tokens": 142000,
                "avg_cost_usd": 0.71,
                "win_rate": 66.7,
                "total_graded": 6,
            },
            {
                "preset_name": "Gemini Presets (Flash 2.5)",
                "total_runs": 8,
                "avg_duration": 22.4,
                "avg_tokens": 154000,
                "avg_cost_usd": 0.023,
                "win_rate": 60.0,
                "total_graded": 5,
            },
            {
                "preset_name": "Claude Presets (Sonnet 3.5)",
                "total_runs": 6,
                "avg_duration": 62.1,
                "avg_tokens": 139000,
                "avg_cost_usd": 0.417,
                "win_rate": 75.0,
                "total_graded": 4,
            }
        ]

    return comparison


@router.get("/performance")
async def get_performance(
    ticker: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Win rate and return statistics for past signals."""
    from sqlalchemy import func
    q = select(AnalysisResult).where(AnalysisResult.raw_return.isnot(None))
    if ticker:
        q = q.where(AnalysisResult.ticker == ticker.upper())
    result = await db.execute(q)
    rows = result.scalars().all()

    if not rows:
        return {"total": 0, "win_rate": None, "avg_raw_return": None, "avg_alpha_return": None, "by_signal": {}}

    buy_signals = {"Buy", "Overweight"}
    sell_signals = {"Sell", "Underweight"}

    wins = 0
    total_raw = 0.0
    total_alpha = 0.0
    by_signal: dict[str, dict] = {}

    for r in rows:
        sig = r.signal or "Unknown"
        raw = r.raw_return or 0.0
        alpha = r.alpha_return or 0.0
        total_raw += raw
        total_alpha += alpha

        is_correct = (sig in buy_signals and raw > 0) or (sig in sell_signals and raw < 0)
        if is_correct:
            wins += 1

        if sig not in by_signal:
            by_signal[sig] = {"count": 0, "wins": 0, "avg_return": 0.0}
        by_signal[sig]["count"] += 1
        by_signal[sig]["avg_return"] += raw
        if is_correct:
            by_signal[sig]["wins"] += 1

    n = len(rows)
    for v in by_signal.values():
        v["avg_return"] = round(v["avg_return"] / v["count"] * 100, 2)
        v["win_rate"] = round(v["wins"] / v["count"] * 100, 1)

    return {
        "total": n,
        "win_rate": round(wins / n * 100, 1),
        "avg_raw_return": round(total_raw / n * 100, 2),
        "avg_alpha_return": round(total_alpha / n * 100, 2),
        "by_signal": by_signal,
    }


@router.get("/performance-attribution")
async def get_performance_attribution(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Return performance metrics and decision weights for each individual analyst."""
    from backend.services.performance_service import get_analyst_attribution_stats
    return await get_analyst_attribution_stats(db)


# ── Multi-ticker (portfolio) analysis ────────────────────────────────────────

@router.post("/run-portfolio", response_model=MultiTickerRunResponse)
async def run_portfolio(
    body: MultiTickerRunRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Start a multi-ticker portfolio analysis in the background."""
    tickers = [t.upper() for t in body.tickers]
    for ticker in tickers:
        try:
            safe_ticker_component(ticker)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=f"Invalid ticker {ticker}: {e}")

    settings = await _get_or_create_settings(db, _)
    current_user = _

    import uuid
    task_id = str(uuid.uuid4())

    async def _bg():
        async with __import__("backend.core.database", fromlist=["AsyncSessionLocal"]).AsyncSessionLocal() as bg_db:
            try:
                from backend.services.analysis_service import run_portfolio_analysis
                await run_portfolio_analysis(tickers, body.trade_date, body.asset_type, settings, bg_db, "manual", user=current_user)
                await bg_db.commit()
            except Exception as exc:
                _logger.error("Portfolio analysis failed: %s", exc, exc_info=True)
                await bg_db.rollback()

    background_tasks.add_task(_bg)
    return MultiTickerRunResponse(task_id=task_id, tickers=tickers, trade_date=body.trade_date)


@router.get("/portfolio-history", response_model=list[MultiTickerListItem])
async def list_portfolio_analyses(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    q = select(MultiTickerAnalysis).order_by(desc(MultiTickerAnalysis.created_at)).limit(limit).offset(offset)
    result = await db.execute(q)
    rows = result.scalars().all()
    return [
        MultiTickerListItem(
            id=r.id,
            tickers=r.tickers,
            trade_date=r.trade_date,
            asset_type=r.asset_type,
            triggered_by=r.triggered_by,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.get("/portfolio/{portfolio_id}", response_model=MultiTickerResultRead)
async def get_portfolio_analysis(
    portfolio_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    result = await db.execute(select(MultiTickerAnalysis).where(MultiTickerAnalysis.id == portfolio_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Portfolio analysis not found")
    return MultiTickerResultRead(
        id=row.id,
        tickers=row.tickers,
        trade_date=row.trade_date,
        asset_type=row.asset_type,
        analysis_ids=row.analysis_ids,
        super_portfolio_report=row.super_portfolio_report,
        triggered_by=row.triggered_by,
        created_at=row.created_at,
    )


@router.get("/{analysis_id}/chat", response_model=list[ChatMessageRead])
async def get_analysis_chat(
    analysis_id: int,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Retrieve chat conversation logs for a given analysis result."""
    # Check if analysis exists
    result = await db.execute(select(AnalysisResult).where(AnalysisResult.id == analysis_id))
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis report not found")

    from backend.models import AnalysisChat
    chat_result = await db.execute(
        select(AnalysisChat)
        .where(AnalysisChat.analysis_id == analysis_id)
        .order_by(AnalysisChat.created_at.asc())
    )
    return chat_result.scalars().all()


@router.post("/{analysis_id}/chat", response_model=ChatMessageRead)
async def ask_analysis_report(
    analysis_id: int,
    body: ChatMessageCreate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Ask a question about the completed analysis report."""
    from backend.models import AnalysisChat
    from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
    from tradingagents.llm_clients.factory import create_llm_client

    # 1. Fetch historical analysis report
    result = await db.execute(select(AnalysisResult).where(AnalysisResult.id == analysis_id))
    analysis = result.scalar_one_or_none()
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis report not found")

    # 2. Get active configuration
    settings = await _get_or_create_settings(db, _)

    # 3. Construct a concise context summary from the report
    reports = []
    if analysis.market_report:
        reports.append(f"### MARKET REPORT\n{analysis.market_report}")
    if analysis.sentiment_report:
        reports.append(f"### SENTIMENT REPORT\n{analysis.sentiment_report}")
    if analysis.news_report:
        reports.append(f"### NEWS REPORT\n{analysis.news_report}")
    if analysis.fundamentals_report:
        reports.append(f"### FUNDAMENTALS REPORT\n{analysis.fundamentals_report}")
    if analysis.macro_report:
        reports.append(f"### MACRO REPORT\n{analysis.macro_report}")
    if analysis.options_report:
        reports.append(f"### OPTIONS REPORT\n{analysis.options_report}")
    if analysis.quant_report:
        reports.append(f"### QUANT REPORT\n{analysis.quant_report}")
    if analysis.earnings_report:
        reports.append(f"### EARNINGS REPORT\n{analysis.earnings_report}")
    if analysis.final_decision:
        reports.append(f"### FINAL PORTFOLIO DECISION & SIGNAL ({analysis.signal})\n{analysis.final_decision}")

    report_content = "\n\n".join(reports)

    # 4. Fetch past chat history for context
    chat_result = await db.execute(
        select(AnalysisChat)
        .where(AnalysisChat.analysis_id == analysis_id)
        .order_by(AnalysisChat.created_at.asc())
    )
    past_messages = chat_result.scalars().all()

    # 5. Build system instruction loaded with report content
    lang = settings.output_language or "English"
    lang_inst = "" if lang.strip().lower() == "english" else f" Write your entire response in {lang}."

    system_prompt = (
        f"You are the Portfolio Manager agent of the TradingAgents platform. The user wants to discuss the "
        f"following completed analysis report for asset `{analysis.ticker}`.\n\n"
        f"--- START REPORT CONTENT ---\n"
        f"{report_content}\n"
        f"--- END REPORT CONTENT ---\n\n"
        f"Answer the user's questions about this analysis report accurately, professionally, and concisely. "
        f"Ground your replies only in the details provided in the report. If they ask about something not covered "
        f"in the report, say so politely.{lang_inst}"
    )

    # 6. Format messages list for the client call
    messages_payload = [SystemMessage(content=system_prompt)]
    for msg in past_messages:
        if msg.role == "user":
            messages_payload.append(HumanMessage(content=msg.content))
        else:
            messages_payload.append(AIMessage(content=msg.content))
    messages_payload.append(HumanMessage(content=body.message))

    # 7. Execute LLM call using the configured provider & model
    from backend.core.config import get_settings as _cfg
    from backend.services.user_service import get_user_api_key
    user_key = None
    if _ is not None:
        try:
            fernet = _cfg().get_fernet()
            user_key = get_user_api_key(_, settings.llm_provider, fernet)
        except Exception:
            user_key = None

    if not user_key and not getattr(_, "is_admin", False):
        raise HTTPException(
            status_code=400,
            detail=f"No API key set for provider '{settings.llm_provider}'. Please add your API key in Settings."
        )

    client = create_llm_client(
        provider=settings.llm_provider,
        model=settings.llm_model,
        base_url=settings.backend_url,
        api_key=user_key,
    )
    llm = client.get_llm()

    response = await llm.ainvoke(messages_payload)

    # 8. Save user and assistant messages in database
    user_chat = AnalysisChat(
        analysis_id=analysis_id,
        role="user",
        content=body.message,
    )
    assistant_chat = AnalysisChat(
        analysis_id=analysis_id,
        role="assistant",
        content=response.content,
    )
    db.add(user_chat)
    db.add(assistant_chat)
    await db.flush()

    return assistant_chat

