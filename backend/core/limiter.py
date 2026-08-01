from functools import lru_cache
from ipaddress import ip_address, ip_network

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.core.config import get_settings

@lru_cache(maxsize=32)
def _trusted_proxy_networks(raw_cidrs: str) -> tuple:
    """Parse the configured reverse-proxy CIDRs, failing closed on typos.

    Rate-limit identity must never start trusting a caller supplied header
    merely because an operator made a malformed configuration change.  Invalid
    entries are therefore ignored; a missing/invalid complete value means no
    peer can be trusted to provide X-Forwarded-For.
    """
    networks = []
    for value in raw_cidrs.split(","):
        value = value.strip()
        if not value:
            continue
        try:
            networks.append(ip_network(value, strict=False))
        except ValueError:
            continue
    return tuple(networks)

def _is_trusted_proxy(peer: str, raw_cidrs: str) -> bool:
    try:
        peer_ip = ip_address(peer)
    except ValueError:
        return False
    return any(peer_ip in network for network in _trusted_proxy_networks(raw_cidrs))

def _forwarded_client_ip(forwarded: str) -> str | None:
    """Return a sanitized client address from a trusted proxy header.

    The bundled Nginx **overwrites** X-Forwarded-For with ``$remote_addr``;
    its one-value header is therefore the caller's actual address, even when
    it is a Docker/private-network address. Once the directly connected peer
    has passed the explicit CIDR trust check, use the left-most value for
    compatible chained proxies as well. Deployments that append an inherited
    client header must not enable this setting until their proxy is changed to
    overwrite it.
    """
    candidates: list[str] = []
    for value in forwarded.split(","):
        value = value.strip()
        try:
            candidates.append(str(ip_address(value)))
        except ValueError:
            return None

    return candidates[0] if candidates else None

def _client_ip(request: Request) -> str:
    """Rate-limit key: the caller's IP.

    By default this is ``request.client.host`` — the only value a client
    can't spoof. When proxy headers are explicitly enabled *and* the directly
    connected peer belongs to ``TRUSTED_PROXY_CIDRS``, recover the original
    caller from X-Forwarded-For.  This prevents the Docker/Nginx deployment
    from collapsing every user into one rate-limit bucket without allowing a
    direct caller to forge its own bucket.
    """
    settings = get_settings()
    peer = get_remote_address(request)
    raw_cidrs = getattr(settings, "TRUSTED_PROXY_CIDRS", "") or ""
    if settings.TRUST_PROXY_HEADERS and _is_trusted_proxy(peer, raw_cidrs):
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            client_ip = _forwarded_client_ip(forwarded)
            if client_ip:
                return client_ip
    return peer

limiter = Limiter(key_func=_client_ip)
