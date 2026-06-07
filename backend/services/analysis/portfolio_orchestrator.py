from __future__ import annotations

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import AsyncSessionLocal
from backend.models.portfolio_analysis import MultiTickerAnalysis
from backend.models.settings import AppSettings
from backend.repositories.analysis import get_system_settings
from backend.services.tool_access_service import get_user_agent_access
from backend.services.tool_settings_service import build_global_runtime_context
from backend.trading_agents.agents.sub.managers.super_portfolio_manager import create_super_portfolio_manager
from backend.trading_agents.graph.trading_graph import TradingAgentsGraph

from .config_builder import build_analysis_config, inject_tool_credentials
from .emitter import AnalysisEmitter
from .orchestrator import run_individual_analysis

_logger = logging.getLogger(__name__)


async def run_portfolio_analysis(
    tickers: list[str],
    trade_date: str,
    asset_type: str,
    settings: AppSettings,
    db: AsyncSession,
    triggered_by: str = "manual",
    user=None,
):
    username = user.username if user else "system"
    _logger.info("Starting portfolio analysis for tickers=%s user=%s triggered_by=%s", tickers, username, triggered_by)

    sys_settings = await get_system_settings(db)
    config = build_analysis_config(settings, user=user, sys_settings=sys_settings)
    concurrency = settings.analyst_concurrency_limit or 1
    semaphore = asyncio.Semaphore(concurrency)

    async def _run_one(ticker: str):
        async with semaphore:
            _logger.info("Portfolio analysis: running %s for user=%s", ticker, username)
            async with AsyncSessionLocal() as t_db:
                # Portfolio analysis doesn't have a single task_id for the whole thing yet in the UI,
                # but each individual run gets its own.
                import uuid

                task_id = str(uuid.uuid4())
                emitter = AnalysisEmitter(task_id)
                _, row = await run_individual_analysis(
                    ticker, trade_date, asset_type, settings, t_db, emitter, triggered_by, user=user
                )
                data = {
                    "id": row.id,
                    "trader_plan": row.trader_plan,
                    "portfolio_decision": row.final_decision,
                }
                await t_db.commit()
            return ticker, data

    results = await asyncio.gather(*[_run_one(t.upper()) for t in tickers], return_exceptions=True)
    ticker_reports: dict = {}
    analysis_ids: list[int] = []
    for res in results:
        if isinstance(res, Exception):
            _logger.warning("Portfolio ticker run failed for user=%s: %s", username, res)
            continue
        ticker, data = res
        analysis_ids.append(data["id"])
        ticker_reports[ticker] = {
            "trader_plan": data["trader_plan"],
            "portfolio_decision": data["portfolio_decision"],
        }

    super_report = ""
    if ticker_reports:
        super_report = await _generate_super_report(db, user, config, ticker_reports)

    multi_row = MultiTickerAnalysis(
        trade_date=trade_date,
        asset_type=asset_type,
        super_portfolio_report=super_report,
        triggered_by=triggered_by,
        user_id=user.id if user is not None else None,
    )
    multi_row.tickers = tickers
    multi_row.analysis_ids = analysis_ids
    db.add(multi_row)
    await db.flush()
    _logger.info("Portfolio analysis complete for user=%s tickers=%s", username, tickers)
    return multi_row


async def _generate_super_report(db, user, config, ticker_reports) -> str:
    username = user.username if user else "system"
    try:
        user_id = user.id if user else None
        agent_access_map = await get_user_agent_access(db, user_id) if user_id else {}

        from backend.services.agent_settings_service import build_agent_runtime_context
        from backend.trading_agents.agent_catalog import list_analysts

        permitted_analysts = [a.key for a in list_analysts() if agent_access_map.get(a, True)]

        config["runtime_tool_context"] = await build_global_runtime_context(db, user_id)
        config["runtime_agent_context"] = await build_agent_runtime_context(db, user_id)
        inject_tool_credentials(config)

        ta = TradingAgentsGraph(selected_analysts=permitted_analysts, config=config)
        spm_node = create_super_portfolio_manager(ta.thinking_llm)
        state_out = await asyncio.to_thread(spm_node, {"ticker_reports": ticker_reports})
        return state_out.get("super_portfolio_report", "")
    except Exception as e:
        _logger.error("SuperPortfolioManager failed for user=%s: %s", username, e, exc_info=True)
        return f"Portfolio synthesis failed: {e}"
