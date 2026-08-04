from typing import Any

from backend.services.analysis.reports import report_text


def llm_text(response_or_content: Any) -> str:
    """Normalize provider text/content-block variants into plain text."""
    return report_text(response_or_content)
