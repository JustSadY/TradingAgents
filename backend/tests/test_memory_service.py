"""Tests for episodic memory record/recall against a fake store."""

from backend.core.memory import MemoryHit, MemoryRecord
from backend.services.memory_service import record_episode, recall_episode_lessons


class FakeStore:
    """In-memory MemoryStore stand-in that does substring-overlap scoring."""

    def __init__(self):
        self.data: dict[str, list[MemoryRecord]] = {}

    async def upsert(self, namespace, records):
        ns = self.data.setdefault(namespace, [])
        by_id = {r.id: r for r in ns}
        for r in records:
            by_id[r.id] = r
        self.data[namespace] = list(by_id.values())

    async def query(self, namespace, text, *, top_k=5, metadata_filter=None):
        hits = []
        for r in self.data.get(namespace, []):
            overlap = len(set(text.lower().split()) & set(r.text.lower().split()))
            hits.append(MemoryHit(id=r.id, score=float(overlap), text=r.text, metadata=r.metadata))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:top_k]


async def test_disabled_when_no_store():
    assert await record_episode(
        user_id=1, ticker="AAPL", trade_date="2024-01-01", signal="Buy",
        situation_text="x", decision="d", raw_return=0.1, alpha_return=0.05,
        reflection="r", store=None,
    ) is False
    assert await recall_episode_lessons(user_id=1, situation_text="x", store=None) == ""


async def test_record_then_recall_surfaces_losses_first():
    store = FakeStore()
    await record_episode(
        user_id=7, ticker="AAPL", trade_date="2024-01-10", signal="Buy",
        situation_text="strong uptrend breakout above resistance momentum",
        decision="Buy AAPL", raw_return=-0.12, alpha_return=-0.08,
        reflection="Chased a breakout that failed; avoid buying extended.", store=store,
    )
    await record_episode(
        user_id=7, ticker="MSFT", trade_date="2024-02-01", signal="Sell",
        situation_text="weak downtrend oversold bounce fade",
        decision="Sell MSFT", raw_return=0.05, alpha_return=0.03,
        reflection="Faded a weak bounce; worked.", store=store,
    )

    out = await recall_episode_lessons(
        user_id=7, situation_text="uptrend breakout above resistance momentum", store=store
    )
    assert "do NOT repeat" in out
    # the loss episode (AAPL) is the closest situation and appears
    assert "AAPL" in out
    assert "avoid buying extended" in out


async def test_episodes_are_isolated_per_user():
    store = FakeStore()
    await record_episode(
        user_id=1, ticker="AAPL", trade_date="2024-01-10", signal="Buy",
        situation_text="breakout momentum", decision="Buy", raw_return=-0.1,
        alpha_return=-0.05, reflection="lesson one", store=store,
    )
    # A different user must not see user 1's episode.
    out = await recall_episode_lessons(user_id=2, situation_text="breakout momentum", store=store)
    assert out == ""
