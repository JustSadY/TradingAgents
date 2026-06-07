"""Client-side embedders.

Optional: the default Pinecone backend embeds server-side (hosted inference), so
no embedder is needed for the common case. Provide one of these (via the
factory) to embed client-side instead — e.g. to use OpenAI embeddings or to use
a vector store without hosted inference.
"""

from __future__ import annotations


class OpenAIEmbedder:
    """Embeds text with the OpenAI embeddings API."""

    # Known output dimensions for OpenAI's current embedding models.
    _DIMENSIONS = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }

    def __init__(self, api_key: str, model: str = "text-embedding-3-small", dimension: int | None = None):
        from openai import AsyncOpenAI  # lazy: only needed when this embedder is used

        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        self._dimension = dimension or self._DIMENSIONS.get(model, 1536)

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        resp = await self._client.embeddings.create(model=self._model, input=texts)
        return [item.embedding for item in resp.data]
