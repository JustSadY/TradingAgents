from __future__ import annotations

from backend.repositories.asset_strategy import compare_and_swap_asset_strategy, create_asset_strategy


async def test_strategy_api_returns_current_snapshot_and_cross_lineage_audit_history(
    db_session,
    authenticated_client,
    test_user,
):
    first = await create_asset_strategy(
        db_session,
        user_id=test_user.id,
        ticker="NVDA",
        state={"strategic_bias": "BULLISH", "conviction": 0.72, "thesis": "Original thesis"},
    )
    closed = await compare_and_swap_asset_strategy(
        db_session,
        strategy_id=first.id,
        expected_version=1,
        updates={"status": "CLOSED"},
        revision_action="REBUILD",
    )
    assert closed.applied
    replacement = await create_asset_strategy(
        db_session,
        user_id=test_user.id,
        ticker="NVDA",
        state={"strategic_bias": "BEARISH", "conviction": 0.76, "thesis": "Replacement thesis"},
        revision_action="REBUILD",
    )
    await db_session.flush()

    current = await authenticated_client.get("/api/analysis/strategies/NVDA")
    history = await authenticated_client.get("/api/analysis/strategies/NVDA/history")

    assert current.status_code == 200
    assert current.json()["id"] == replacement.id
    assert current.json()["strategic_bias"] == "BEARISH"
    assert history.status_code == 200
    assert {item["strategy_id"] for item in history.json()} == {first.id, replacement.id}
    assert {item["revision_action"] for item in history.json()} >= {"CREATE", "REBUILD"}
