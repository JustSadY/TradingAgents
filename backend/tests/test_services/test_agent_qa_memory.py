from __future__ import annotations

from backend.services.memory_service import recall_agent_qa, record_agent_qa


class _Memory:
    def __init__(self, hits=None):
        self.adds = []
        self.deletes = []
        self.searches = []
        self.hits = list(hits or [])

    def delete_all(self, **kwargs):
        self.deletes.append(kwargs)
        return {"message": "deleted"}

    def add(self, messages, **kwargs):
        self.adds.append((messages, kwargs))
        return {"results": [{"event": "ADD"}]}

    def search(self, query, **kwargs):
        self.searches.append((query, kwargs))
        return {"results": self.hits[: kwargs.get("top_k", 5)]}


async def test_record_agent_qa_uses_mem0_user_agent_and_run_scopes() -> None:
    store = _Memory()

    written = await record_agent_qa(
        user_id=7,
        ticker="NVDA",
        trade_date="2026-09-03",
        situation_text="Market and valuation analysts disagree on the multiple.",
        transcript="### Analyst Cross-Examination\n\nQ&A body",
        store=store,
    )

    assert written is True
    assert store.deletes == [
        {
            "user_id": "7",
            "agent_id": "trading-agent-qa",
            "run_id": "7:NVDA:2026-09-03:agent_qa",
        }
    ]
    assert len(store.adds) == 1
    messages, kwargs = store.adds[0]
    assert "Q&A body" in messages
    assert kwargs["user_id"] == "7"
    assert kwargs["agent_id"] == "trading-agent-qa"
    assert kwargs["run_id"] == "7:NVDA:2026-09-03:agent_qa"
    assert kwargs["infer"] is False
    assert kwargs["metadata"]["memory_type"] == "agent_qa"
    assert kwargs["metadata"]["memory_key"] == "7:NVDA:2026-09-03:agent_qa"


async def test_recall_agent_qa_filters_future_transcripts_for_historical_context() -> None:
    store = _Memory(
        [
            {
                "id": "old",
                "score": 0.91,
                "memory": "old",
                "metadata": {
                    "ticker": "NVDA",
                    "trade_date": "2026-08-01",
                    "observed_at": "2026-08-01T18:00:00+00:00",
                    "transcript": "Known historical disagreement.",
                },
            },
            {
                "id": "future",
                "score": 0.99,
                "memory": "future",
                "metadata": {
                    "ticker": "NVDA",
                    "trade_date": "2026-09-10",
                    "observed_at": "2026-09-10T18:00:00+00:00",
                    "transcript": "Future disagreement must not leak.",
                },
            },
        ]
    )

    recalled = await recall_agent_qa(
        user_id=7,
        situation_text="valuation conflict",
        top_k=3,
        as_of="2026-09-03",
        store=store,
    )

    assert "Known historical disagreement" in recalled
    assert "Future disagreement" not in recalled
    query, kwargs = store.searches[0]
    assert query == "valuation conflict"
    assert kwargs["filters"] == {"user_id": "7", "agent_id": "trading-agent-qa"}
    assert kwargs["top_k"] == 15
