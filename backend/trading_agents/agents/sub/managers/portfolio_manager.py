"""Portfolio Manager raw proposal generation.

Upstream analysts, the research manager, and the risk panel deliberately
produce evidence and guardrails rather than competing buy/sell instructions.
This node is the one place where that evidence is converted into a structured
raw PortfolioDecision proposal. A deterministic controller decides whether it
becomes executable.
"""

from __future__ import annotations

import logging

from backend.trading_agents.agents.runtime.report_aggregator import tail_history
from backend.trading_agents.agents.runtime.structured import (
    ainvoke_structured_or_freetext,
    bind_structured,
)
from backend.trading_agents.agents.schemas import PortfolioDecision, render_pm_decision
from backend.trading_agents.agents.utils.agent_utils import (
    build_instrument_context,
    get_general_settings_block,
    get_system_instruction_override,
)

_logger = logging.getLogger(__name__)

_DEFAULT_INSTRUCTION = (
    "As the Portfolio Manager, evaluate all available evidence and risk guardrails, "
    "then issue one coherent raw trade proposal and execution recommendation."
)
_MAX_FALLBACK_REPORT_CHARS = 2_400
_MAX_DECISION_CONTEXT_CHARS = 3_500


def _point_in_time_portfolio_exclusion(trade_date: object) -> str:
    """Explain why a replay cannot see the mutable live portfolio.

    ``trade_date`` alone is not enough to infer this: a time-travel replay may
    deliberately resume an analysis created *today*.  In that case the current
    cash/holdings are still future knowledge relative to the checkpoint, so
    the graph's explicit ``historical_mode`` flag is the authority.
    """

    return (
        "=== PORTFOLIO CONTEXT EXCLUDED ===\n"
        f"This is a point-in-time replay as of {trade_date or 'the selected checkpoint'}; "
        "the mutable current portfolio must not influence its tactical sizing."
    )

def _prompt_report_limit() -> int:
    """Return a bounded fallback budget for reports without an executive summary."""
    try:
        from backend.trading_agents.dataflows.config import get_config

        configured = int(get_config().get("max_report_chars_in_prompts", _MAX_FALLBACK_REPORT_CHARS))
    except Exception:  # noqa: BLE001 - prompt compaction must never stop a run
        configured = _MAX_FALLBACK_REPORT_CHARS
    return max(800, min(configured, _MAX_FALLBACK_REPORT_CHARS))

def _optional_context_section(label: str, content: object, *, limit: int = _MAX_DECISION_CONTEXT_CHARS) -> str:
    """Render one bounded supplemental evidence section when it exists."""
    from backend.services.llm_content import llm_text

    text = llm_text(content).strip()
    if not text:
        return ""

    from backend.trading_agents.agents.runtime.report_aggregator import middle_truncate

    return f"### {label}\n{middle_truncate(text, limit)}"

def build_portfolio_manager_evidence(state: dict) -> str:
    """Build the PM's dynamic evidence packet from every active analyst report.

    ``get_report_fields`` is registry-driven, so a new enabled analyst appears
    here automatically. ``build_resources(summary_only=True)`` keeps every
    report's conclusion when present and safely falls back to a bounded raw
    report when it has no recognisable executive summary. Synthesis, audit, and
    cross-examination are separate evidence artifacts and are added explicitly.
    """
    from backend.trading_agents.agents.analyst_registry import get_report_fields
    from backend.trading_agents.agents.runtime.report_aggregator import build_resources

    analyst_evidence = build_resources(
        state,
        get_report_fields(),
        prefix="### ",
        max_chars_per_report=_prompt_report_limit(),
        summary_only=True,
    )
    sections = []
    if analyst_evidence:
        sections.append("## Active Analyst Evidence\n" + analyst_evidence)

    for label, key in (
        ("Synthesis Manager Conflict Map", "synthesis_report"),
        ("Auditor Fact Check", "audit_report"),
        ("Analyst Cross-Examination", "agent_qa_report"),
        ("Strategy Reconciliation (non-executable)", "strategy_reconciliation_report"),
    ):
        section = _optional_context_section(label, state.get(key))
        if section:
            sections.append(section)

    return "\n\n".join(sections) or "No analyst evidence was available for this run."

def create_portfolio_manager(llm):
    structured_llm = bind_structured(llm, PortfolioDecision, "Portfolio Manager")

    async def portfolio_manager_node(state) -> dict:
        company_name = state["company_of_interest"]
        asset_type = state.get("asset_type", "stock")
        instrument_context = build_instrument_context(company_name, asset_type)
        risk_debate_state = state.get("risk_debate_state") or {}
        risk_history = tail_history(risk_debate_state.get("history", ""))
        research_plan = state.get("investment_plan") or "No research evidence brief was available."
        evidence_packet = build_portfolio_manager_evidence(state)

        from backend.trading_agents.dataflows.config import get_config

        memory_lessons = ""
        try:
            from backend.services.memory_service import recall_episode_lessons

            memory_lessons = await recall_episode_lessons(
                user_id=get_config().get("user_id"),
                situation_text=state.get("market_report") or research_plan,
                top_k=get_config().get("memory_recall_count", 5),
                as_of=state.get("trade_date"),
            )
        except Exception as exc:  # noqa: BLE001 - memory is advisory
            _logger.debug("Memory recall skipped: %s", exc)

        from backend.trading_agents.agents.runtime.portfolio_context import get_portfolio_context

        # Direct node callers from extensions/tests do not always carry a
        # trade date.  Supplying ``as_of=None`` buys us no point-in-time
        # protection and needlessly breaks the older one-argument context
        # adapters, while graph runs always take the as-of path below.
        portfolio_user_id = get_config().get("user_id")
        trade_date = state.get("trade_date")
        # ``historical_mode`` includes a same-day time-travel resume.  Do not
        # delegate that safety decision solely to the calendar date inside
        # get_portfolio_context: today's live holdings can still be newer than
        # the checkpoint being replayed.
        if bool(get_config().get("historical_mode", False)):
            portfolio_context = _point_in_time_portfolio_exclusion(trade_date)
        elif trade_date:
            portfolio_context = await get_portfolio_context(portfolio_user_id, as_of=trade_date)
        else:
            portfolio_context = await get_portfolio_context(portfolio_user_id)
        past_context = "\n\n".join(
            part for part in (memory_lessons, state.get("past_context", "")) if part
        )

        from backend.trading_agents.personas import DEFAULT_PERSONA, get_persona_instructions

        persona = get_config().get("investor_persona", DEFAULT_PERSONA)
        persona_instructions = get_config().get("investor_persona_instructions") or get_persona_instructions(persona)
        instruction = get_system_instruction_override("portfolio_manager") or _DEFAULT_INSTRUCTION

        prompt = f"""{instruction}
{persona_instructions}
{instrument_context}
---
You are the **only** agent allowed to produce a final Buy, Overweight, Hold,
Underweight, or Sell *proposal* and its execution fields. This proposal is
non-executable: the deterministic Decision Stability Controller has final
execution authority and may accept it, downgrade it to Hold, or issue a
risk-only reduction. Treat the Research Manager's posture and the Risk Debate
as non-authoritative evidence and guardrails, not as orders. Do not
mechanically copy or average them; resolve their conflicts against the complete
analyst evidence and the live portfolio.

**Final Rating Scale** (use exactly one):
- **Buy**: Enter or materially add to a position.
- **Overweight**: Increase toward a measured target allocation.
- **Hold**: Do not place a new order.
- **Underweight**: Reduce toward a lower target allocation.
- **Sell**: Exit or avoid the position.

{portfolio_context}
---
## Research Manager Evidence Brief (non-executable)
{research_plan}
---
## Risk Debate Guardrails (non-executable)
{risk_history or 'No risk-panel transcript was available.'}
---
{evidence_packet}
---
## Prior lessons and ambient market context
{past_context or 'No prior lessons were available.'}
---
Return one coherent raw PortfolioDecision. For Buy/Overweight, provide an
honest raw confidence score, entry, stop loss, take profit, target allocation percentage,
suggested capital, and leverage. For Sell, use a 0% target allocation for a
full exit; for Underweight, give the lower desired final allocation. For Hold,
use no entry/stop/take-profit, no new capital, and a null target allocation.
All prices must use the instrument quote currency from the context. Base the
target allocation on actual cash, existing holdings, and portfolio equity;
never propose spending more cash than is available. The execution engine will
enforce its own hard limits, so do not evade risk controls by inflating the
confidence or leverage. Keep leverage at 1.0 unless the evidence and defined
stop clearly justify more; volatile/speculative instruments should remain at
1.0-2.0.{get_general_settings_block()}"""

        result = await ainvoke_structured_or_freetext(
            structured_llm,
            llm,
            prompt,
            "Portfolio Manager",
            schema=PortfolioDecision,
        )

        final_signal: str | None = None
        # Preserve the legacy serialized state contract here.  The controller
        # normalises either a mapping or a JSON string and replaces this field
        # with the accepted mapping at the end of a full graph run.
        decision_json: dict | str = "{}"
        proposal_json: dict = {}
        if isinstance(result, str):
            final_trade_decision = result
        else:
            final_trade_decision = render_pm_decision(result)
            final_signal = result.rating.value
            decision_json = result.model_dump_json()
            proposal_json = {
                "proposed_decision": result.model_dump(mode="json"),
                "rationale": result.investment_thesis or result.executive_summary,
                "supporting_evidence_ids": [],
                "triggered_invalidation_ids": [],
            }

        new_risk_debate_state = {
            "judge_decision": final_trade_decision,
            "history": risk_debate_state.get("history", ""),
            "aggressive_history": risk_debate_state.get("aggressive_history", ""),
            "conservative_history": risk_debate_state.get("conservative_history", ""),
            "neutral_history": risk_debate_state.get("neutral_history", ""),
            "latest_speaker": "Portfolio Manager",
            "current_aggressive_response": risk_debate_state.get("current_aggressive_response", ""),
            "current_conservative_response": risk_debate_state.get("current_conservative_response", ""),
            "current_neutral_response": risk_debate_state.get("current_neutral_response", ""),
            "count": risk_debate_state.get("count", 0),
        }
        out = {
            "risk_debate_state": new_risk_debate_state,
            "pm_proposal_json": proposal_json,
            "pm_proposal_report": final_trade_decision,
            # The graph controller overwrites these legacy aliases with the
            # accepted canonical decision. Keeping them here preserves direct
            # node callers and older checkpoint decoding during migration.
            "final_trade_decision": final_trade_decision,
            "portfolio_decision_json": decision_json,
        }
        if final_signal is not None:
            out["final_signal"] = final_signal
        return out

    return portfolio_manager_node
