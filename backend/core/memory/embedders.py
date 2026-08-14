"""Client-side embedders.

Optional: the default Pinecone backend embeds server-side (hosted inference), so
no embedder is needed for the common case. Provide one of these (via the
factory) to embed client-side instead — e.g. to use OpenAI embeddings or to use
a vector store without hosted inference.
"""

from __future__ import annotations


class OpenAIEmbedder:
    """Embeds text with the OpenAI embeddings API."""

    _DIMENSIONS = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }

    def __init__(self, api_key: str, model: str = "text-embedding-3-small", dimension: int | None = None):
        from openai import AsyncOpenAI

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

class OllamaEmbedder:
    """Embeds text via a local (or remote) Ollama instance.

    Uses Ollama's OpenAI-compatible /v1/embeddings endpoint so we can reuse
    the ``openai`` async client without an extra dependency.

    Known output dimensions for common embedding models; anything unlisted
    falls back to 768 (nomic-embed-text default).
    """

    _DIMENSIONS = {
        "nomic-embed-text": 768,
        "mxbai-embed-large": 1024,
        "all-minilm": 384,
        "bge-m3": 1024,
        "bge-large": 1024,
        "snowflake-arctic-embed": 1024,
        "paraphrase-multilingual": 768,
    }

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "nomic-embed-text",
        dimension: int | None = None,
    ):
        from openai import AsyncOpenAI

        url = base_url.rstrip("/")
        if not url.endswith("/v1"):
            url = url + "/v1"
        self._client = AsyncOpenAI(api_key="ollama", base_url=url)
        self._model = model
        dim_key = next((k for k in self._DIMENSIONS if k in model.lower()), None)
        self._dimension = dimension or (self._DIMENSIONS[dim_key] if dim_key else 768)

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        resp = await self._client.embeddings.create(model=self._model, input=texts)
        return [item.embedding for item in resp.data]
