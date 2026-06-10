import logging

_logger = logging.getLogger(__name__)

SCENARIOS = [
    {
        "id": "rate_hike",
        "title": "Fed Interest Rate Hike (+0.25%)",
        "description": "The Federal Reserve unexpectedly raises interest rates by 25 basis points to combat stubborn inflation.",
        "impact_hint": "Tech/Growth stocks usually suffer due to higher discount rates. Financials might see improved margins."
    },
    {
        "id": "btc_crash",
        "title": "Bitcoin Flash Crash (-10%)",
        "description": "Bitcoin suddenly drops 10% in a single day due to a regulatory crackdown on a major exchange.",
        "impact_hint": "Risk-off sentiment might spread to high-beta stocks. Crypto-linked companies (COIN, MARA) will be hit hard."
    },
    {
        "id": "oil_spike",
        "title": "Oil Price Spike (+5%)",
        "description": "Geopolitical tensions in the Middle East cause a sudden 5% increase in crude oil prices.",
        "impact_hint": "Energy stocks usually benefit. Transportation and consumer discretionary might face higher costs."
    }
]

def get_active_scenarios() -> str:
    """Return a Markdown summary of current 'What-If' scenarios for agent analysis."""
    md = "=== 'WHAT-IF' STRESS TEST SCENARIOS ===\n"
    md += "Evaluate how the following hypothetical market shifts would impact this instrument and the portfolio:\n\n"

    for s in SCENARIOS:
        md += f"#### {s['title']}\n"
        md += f"- **Situation**: {s['description']}\n"
        md += f"- **Expected Sector Impact**: {s['impact_hint']}\n\n"

    md += "[TASK] In your report (specifically in the Risk/Macro sections), explicitly discuss at least one of these scenarios and provide a 'What-If Resilience' rating (High/Medium/Low).\n\n"
    return md
