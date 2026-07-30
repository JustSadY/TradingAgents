from __future__ import annotations

import base64
import json
import logging
import time
from collections.abc import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)
from backend.trading_agents.dataflows.config import get_config

_PUBLIC_SEARCH = "https://www.reddit.com/r/{sub}/search.json?{qs}"
_OAUTH_SEARCH = "https://oauth.reddit.com/r/{sub}/search?{qs}"
_OAUTH_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
_DEFAULT_UA = "tradingagents/0.2 (+https://github.com/TauricResearch/TradingAgents)"

_TOKEN_CACHE: dict[str, tuple[str, float]] = {}


def _get_user_agent() -> str:
    cfg_ua = get_config().get("reddit_user_agent")
    if cfg_ua:
        return cfg_ua
    return _DEFAULT_UA


def _get_credentials() -> tuple[str, str] | None:
    """Reddit app credentials, injected from the modular tool settings
    (``reddit_sentiment`` tool, user scope). ``None`` when not configured."""
    cfg = get_config()
    client_id = cfg.get("reddit_client_id")
    client_secret = cfg.get("reddit_client_secret")
    if client_id and client_secret:
        return client_id, client_secret
    return None


def _get_oauth_token(client_id: str, client_secret: str, user_agent: str, timeout: float) -> str:
    """Fetch (and cache) an application-only OAuth bearer token."""
    now = time.time()
    cached = _TOKEN_CACHE.get(client_id)
    if cached and cached[1] - 30 > now:
        return cached[0]
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    req = Request(
        _OAUTH_TOKEN_URL,
        data=urlencode({"grant_type": "client_credentials"}).encode(),
        headers={
            "Authorization": f"Basic {basic}",
            "User-Agent": user_agent,
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    with urlopen(req, timeout=timeout) as resp:
        payload = json.loads(resp.read())
    token = payload.get("access_token")
    if not token:
        raise ValueError("reddit oauth response missing access_token")
    _TOKEN_CACHE[client_id] = (token, now + float(payload.get("expires_in", 3600)))
    return token


def _parse_children(payload: dict) -> list[dict]:
    children = (payload.get("data") or {}).get("children") or []
    return [c.get("data", {}) for c in children if isinstance(c, dict)]


DEFAULT_SUBREDDITS = ("wallstreetbets", "stocks", "investing")


def _fetch_subreddit(
    ticker: str,
    sub: str,
    limit: int,
    timeout: float,
) -> list[dict]:
    qs = urlencode(
        {
            "q": ticker,
            "restrict_sr": "on",
            "sort": "new",
            "t": "week",
            "limit": limit,
        }
    )
    user_agent = _get_user_agent()

    creds = _get_credentials()
    if creds:
        try:
            token = _get_oauth_token(creds[0], creds[1], user_agent, timeout)
            req = Request(
                _OAUTH_SEARCH.format(sub=sub, qs=qs),
                headers={
                    "Authorization": f"Bearer {token}",
                    "User-Agent": user_agent,
                    "Accept": "application/json",
                },
            )
            with urlopen(req, timeout=timeout) as resp:
                return _parse_children(json.loads(resp.read()))
        except (HTTPError, URLError, json.JSONDecodeError, TimeoutError, ValueError) as exc:
            logger.warning(
                "Reddit OAuth fetch failed for r/%s · %s (%s); falling back to public API",
                sub,
                ticker,
                exc,
            )
            _TOKEN_CACHE.pop(creds[0], None)

    req = Request(
        _PUBLIC_SEARCH.format(sub=sub, qs=qs),
        headers={"User-Agent": user_agent, "Accept": "application/json"},
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            return _parse_children(json.loads(resp.read()))
    except (HTTPError, URLError, json.JSONDecodeError, TimeoutError) as exc:
        logger.warning("Reddit fetch failed for r/%s · %s: %s", sub, ticker, exc)
        return []


def fetch_reddit_posts(
    ticker: str,
    subreddits: Iterable[str] = DEFAULT_SUBREDDITS,
    limit_per_sub: int = 5,
    timeout: float = 10.0,
    inter_request_delay: float = 0.4,
) -> str:
    blocks = []
    total_posts = 0
    for i, sub in enumerate(subreddits):
        if i > 0:
            time.sleep(inter_request_delay)
        posts = _fetch_subreddit(ticker, sub, limit_per_sub, timeout)
        total_posts += len(posts)
        if not posts:
            blocks.append(f"r/{sub}: <no posts found mentioning {ticker.upper()} in the past 7 days>")
            continue
        lines = [f"r/{sub} — {len(posts)} recent posts mentioning {ticker.upper()}:"]
        for p in posts:
            title = (p.get("title") or "").replace("\n", " ").strip()
            score = p.get("score", 0)
            comments = p.get("num_comments", 0)
            created = p.get("created_utc")
            created_str = time.strftime("%Y-%m-%d", time.gmtime(created)) if created else "?"
            selftext = (p.get("selftext") or "").replace("\n", " ").strip()
            if len(selftext) > 240:
                selftext = selftext[:240] + "…"
            lines.append(
                f"  [{created_str} · {score:>4}↑ · {comments:>3}c] {title}"
                + (f"\n    body excerpt: {selftext}" if selftext else "")
            )
        blocks.append("\n".join(lines))
    if total_posts == 0:
        return (
            f"<no Reddit posts found mentioning {ticker.upper()} across "
            f"{', '.join(f'r/{s}' for s in subreddits)} in the past 7 days>"
        )
    return "\n\n".join(blocks)
