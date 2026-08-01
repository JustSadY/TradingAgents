from __future__ import annotations

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import AsyncSessionLocal
from backend.models.portfolio_analysis import MultiTickerAnalysis
from backend.models.settings import AppSettings

from .emitter import AnalysisEmitter
from .orchestrator import run_individual_analysis

_logger = logging.getLogger(__name__)


def _portfolio_overview_labels(output_language: str | None) -> dict[str, str]:
    """Fixed copy for the non-executing multi-ticker overview.

    Individual Portfolio Manager reports own every executable rating and size.
    This summary is intentionally deterministic so it cannot become another
    LLM authority or silently revise any of those decisions.
    """
    language = str(output_language or "English").strip().casefold()
    if language in {"turkish", "türkçe"}:
        return {
            "title": "# Portföy Analizi Özeti",
            "notice": (
                "> Bu özet yeni bir alım/satım emri, miktar veya portföy dağılımı oluşturmaz. "
                "Her hissenin tek yetkili kararı kendi Nihai Portföy Yöneticisi raporundadır."
            ),
            "context": "## Mevcut Portföy Bağlamı (yalnız referans)",
            "decision": "Nihai Portföy Yöneticisi Kararı",
            "missing": "Bu hisse için doğrulanmış nihai Portföy Yöneticisi kararı yok.",
            "rule": "## İşlem Kuralı",
            "rule_text": (
                "Otomatik işlem yalnızca hisseye ait yapılandırılmış Nihai Portföy Yöneticisi kararıyla "
                "değerlendirilir; bu çoklu-hisse özeti emir veremez veya miktar değiştiremez."
            ),
        }
    return {
        "title": "# Portfolio Analysis Overview",
        "notice": (
            "> This overview does not create or amend a buy/sell order, quantity, or portfolio allocation. "
            "Each ticker's own final Portfolio Manager report remains the sole authority."
        ),
        "context": "## Current Portfolio Context (reference only)",
        "decision": "Final Portfolio Manager Decision",
        "missing": "No validated final Portfolio Manager decision is available for this ticker.",
        "rule": "## Execution Rule",
        "rule_text": (
            "Automatic execution considers only the structured final Portfolio Manager decision for that ticker; "
            "this multi-ticker overview cannot place an order or change a quantity."
        ),
    }


def build_portfolio_overview(
    ticker_reports: dict[str, dict],
    *,
    portfolio_context: str = "",
    output_language: str | None = None,
) -> str:
    """Render a read-only summary of already-final single-ticker decisions.

    No LLM is invoked here. This deliberately preserves the useful multi-ticker
    report without adding a second model that could contradict an individual
    Portfolio Manager's direction, stop, or amount.
    """
    labels = _portfolio_overview_labels(output_language)
    parts = [labels["title"], labels["notice"]]
    if portfolio_context.strip():
        parts.extend((labels["context"], portfolio_context.strip()))

    for ticker, report in sorted(ticker_reports.items()):
        decision = str(report.get("portfolio_decision") or "").strip()
        parts.extend(
            (
                f"## {ticker}",
                f"### {labels['decision']}",
                decision or labels["missing"],
            )
        )

    parts.extend((labels["rule"], labels["rule_text"]))
    return "\n\n".join(parts)


async def run_portfolio_analysis(
    tickers: list[str],
    trade_date: str,
    asset_type: str,
    settings: AppSettings,
    db: AsyncSession,
    triggered_by: str = "manual",
    user=None,
    task_id: str | None = None,
):
    username = user.username if user else "system"
    _logger.info("Starting portfolio analysis for tickers=%s user=%s triggered_by=%s", tickers, username, triggered_by)
    portfolio_emitter = AnalysisEmitter(task_id) if task_id else None
    total = len(tickers)
    completed = 0
    progress_lock = asyncio.Lock()

    if portfolio_emitter:
        await portfolio_emitter.emit_progress(f"Starting portfolio analysis ({total} tickers)", "starting", "portfolio")

    concurrency = settings.analyst_concurrency_limit or 1
    semaphore = asyncio.Semaphore(concurrency)

    async def _run_one(ticker: str):
        nonlocal completed
        async with semaphore:
            _logger.info("Portfolio analysis: running %s for user=%s", ticker, username)
            async with AsyncSessionLocal() as t_db:
                import uuid

                ticker_task_id = str(uuid.uuid4())
                emitter = AnalysisEmitter(ticker_task_id)
                _, row = await run_individual_analysis(
                    ticker, trade_date, asset_type, settings, t_db, emitter, triggered_by, user=user
                )
                data = {
                    "id": row.id,
                    "portfolio_decision": row.final_decision,
                }
            if portfolio_emitter:
                async with progress_lock:
                    completed += 1
                    done = completed
                await portfolio_emitter.emit_progress(f"{ticker} complete ({done}/{total})", "running", "portfolio")
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
            "portfolio_decision": data["portfolio_decision"],
        }

    super_report = ""
    if ticker_reports:
        super_report = await _generate_portfolio_overview(
            user=user,
            ticker_reports=ticker_reports,
            output_language=getattr(settings, "output_language", None),
        )

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

    if portfolio_emitter:
        await portfolio_emitter.emit(
            {
                "type": "complete",
                "multi_id": multi_row.id,
                "analysis_ids": analysis_ids,
                "completed": len(analysis_ids),
                "total": total,
            }
        )
        await portfolio_emitter.close()
    return multi_row


async def _generate_portfolio_overview(*, user, ticker_reports: dict[str, dict], output_language: str | None) -> str:
    """Build the report-only multi-ticker overview without a second decision LLM."""
    username = user.username if user else "system"
    try:
        user_id = user.id if user else None
        from backend.trading_agents.agents.runtime.portfolio_context import get_portfolio_context

        portfolio_context = await get_portfolio_context(user_id)
        return build_portfolio_overview(
            ticker_reports,
            portfolio_context=portfolio_context,
            output_language=output_language,
        )
    except Exception as e:
        _logger.exception("Portfolio overview failed for user=%s", username)
        return f"Portfolio overview failed: {e}"
