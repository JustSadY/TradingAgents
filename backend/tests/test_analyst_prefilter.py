"""Tests for per-ticker analyst pre-screening grading and selection."""

from types import SimpleNamespace

from backend.services.analyst_prefilter_service import (
    grade_analyst_winrates,
    select_underperformers,
)

# Minimal report-field map (field -> label); only the keys matter here.
_FIELDS = {
    "market_report": "Market",
    "options_report": "Options",
    "macro_report": "Macro",
}


def _row(raw_return, **reports):
    return SimpleNamespace(raw_return=raw_return, **{f: reports.get(f, "") for f in _FIELDS})


def test_grade_winrates_counts_correct_calls():
    rows = [
        # Options says Buy and price rose -> correct; Macro says Buy, price fell -> wrong.
        _row(5.0, options_report="Final rating: Buy", macro_report="Rating: Buy"),
        _row(-3.0, options_report="Final rating: Buy", macro_report="Rating: Buy"),
        _row(4.0, options_report="Final rating: Buy", macro_report="Rating: Sell"),
    ]
    wr = grade_analyst_winrates(rows, _FIELDS)
    # Options: 2 correct of 3 = 66.7%
    assert wr["options"]["samples"] == 3
    assert wr["options"]["win_rate"] == 66.7
    # Macro: Buy(wrong on row2 +? row1 raw +5 -> Buy correct), row2 Buy w/ -3 wrong, row3 Sell w/ +4 wrong
    assert wr["macro"]["samples"] == 3
    assert wr["macro"]["win_rate"] == 33.3
    # Market never issued a rating -> no samples.
    assert wr["market"]["samples"] == 0
    assert wr["market"]["win_rate"] is None


def test_select_underperformers_respects_min_samples():
    wr = {
        "options": {"samples": 3, "win_rate": 20.0},  # below threshold but too few samples
        "macro": {"samples": 10, "win_rate": 30.0},  # droppable
        "quant": {"samples": 10, "win_rate": 55.0},  # good
    }
    drop = select_underperformers(wr, min_samples=5, max_win_rate=40.0)
    assert drop == {"macro"}


def test_protected_analysts_never_dropped():
    wr = {
        "market": {"samples": 50, "win_rate": 5.0},  # terrible but protected
        "news": {"samples": 50, "win_rate": 5.0},
        "options": {"samples": 50, "win_rate": 5.0},  # droppable
    }
    drop = select_underperformers(wr, min_samples=5, max_win_rate=40.0)
    assert "market" not in drop and "news" not in drop
    assert "options" in drop


def test_none_winrate_is_ignored():
    wr = {"options": {"samples": 0, "win_rate": None}}
    assert select_underperformers(wr, min_samples=5, max_win_rate=40.0) == set()
