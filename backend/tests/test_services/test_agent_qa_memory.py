from __future__ import annotations

from backend.core.memory import MemoryHit
from backend.services.memory_service import recall_agent_qa, record_agent_qa


class _Store:
    def __init__(self, hits=None):
        self.upserts = []
        self.queries = []
        self.hits = list(hits or [])

    async def upsert(self, namespace, records):
        self.upserts.append((namespace, records))

    async def query(self, namespace, text, *, top_k=5, metadata_filter=None):
        self.queries.append((namespace, text, top_k, metadata_filter))
        return self.hits[:top_k]


async def test_record_agent_qa_uses_a_separate_user_namespace() -> None:
    store = _Store()

    written = await record_agent_qa(
        user_id=7,
        ticker="NVDA",
        trade_date="2026-09-03",
        situation_text="Market and valuation analysts disagree on the multiple.",
        transcript="### Analyst Cross-Examination\n\nQ&A body",
        store=store,
    )

    assert written is True
    assert len(store.upserts) == 1
    namespace, records = store.upserts[0]
    assert namespace == "qa_user_7"
    assert records[0].id == "7:NVDA:2026-09-03:agent_qa"
    assert records[0].metadata["memory_type"] == "agent_qa"
    assert "Q&A body" in records[0].metadata["transcript"]


async def test_recall_agent_qa_filters_future_transcripts_for_historical_context() -> None:
    store = _Store(
        [
            MemoryHit(
                id="old",
                score=0.91,
                text="old",
                metadata={
                    "ticker": "NVDA",
                    "trade_date": "2026-08-01",
                    "observed_at": "2026-08-01T18:00:00+00:00",
                    "transcript": "Known historical disagreement.",
                },
            ),
            MemoryHit(
                id="future",
                score=0.99,
                text="future",
                metadata={
                    "ticker": "NVDA",
                    "trade_date": "2026-09-10",
                    "observed_at": "2026-09-10T18:00:00+00:00",
                    "transcript": "Future disagreement must not leak.",
                },
            ),
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
    assert store.queries[0][0] == "qa_user_7"
