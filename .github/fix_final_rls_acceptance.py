from pathlib import Path


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"pattern not found in {path}: {old[:160]!r}")
    p.write_text(text.replace(old, new, count), encoding="utf-8")


# The existing public-share API is a flat SharedReportResponse; the RLS test
# must verify security without changing that frontend-facing response contract.
replace(
    "backend/postgres_tests/test_rls_integration.py",
    '        assert active.json()["analysis"]["final_decision"] == "A report"\n',
    '        assert active.json()["final_decision"] == "A report"\n',
)

# Keep logging independent of ORM expiration/lazy loading around repository
# commits. The selected username is immutable for this scan and can be snapped
# before the first commit.
replace(
    "backend/services/cron_service.py",
    '''            trade_date = _trade_date_for_asset("stock")\n            _logger.info(\n                "User cron watchlist scan started for user=%s (id=%d), date=%s",\n                user.username, user_id, trade_date,\n            )\n''',
    '''            trade_date = _trade_date_for_asset("stock")\n            username = user.username\n            _logger.info(\n                "User cron watchlist scan started for user=%s (id=%d), date=%s",\n                username, user_id, trade_date,\n            )\n''',
)
cron = Path("backend/services/cron_service.py")
text = cron.read_text(encoding="utf-8")
segment_start = text.index("    async def _run_user_watchlist_scan_once")
segment_end = text.index("\n    def get_status", segment_start)
segment = text[segment_start:segment_end]
segment = segment.replace("user.username", "username")
text = text[:segment_start] + segment + text[segment_end:]
cron.write_text(text, encoding="utf-8")
