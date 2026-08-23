import logging
from functools import lru_cache
from ipaddress import ip_address, ip_network

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.core.config import get_settings

_logger = logging.getLogger(__name__)

#: Peers already warned about, so a misconfiguration logs once, not per request.
_WARNED_PROXY_PEERS: set[str] = set()


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
    forwarded = request.headers.get("x-forwarded-for")

    if settings.TRUST_PROXY_HEADERS and _is_trusted_proxy(peer, raw_cidrs):
        if forwarded:
            client_ip = _forwarded_client_ip(forwarded)
            if client_ip:
                return client_ip
    elif forwarded:
        _warn_untrusted_proxy(peer, settings.TRUST_PROXY_HEADERS, raw_cidrs)

    return peer

def _warn_untrusted_proxy(peer: str, trust_enabled: bool, raw_cidrs: str) -> None:
    """Say once that every caller is sharing one rate-limit bucket.

    A proxy in front of the app makes ``request.client.host`` the proxy's
    address for every request, so one user exhausting a limit locks out all of
    them. The symptom is a burst of identical 429s from one IP, which reads as
    an attack rather than as a configuration gap, so name the gap explicitly.
    """
    if peer in _WARNED_PROXY_PEERS:
        return
    _WARNED_PROXY_PEERS.add(peer)

    if not trust_enabled:
        reason = "TRUST_PROXY_HEADERS is false"
    elif not raw_cidrs.strip():
        reason = "TRUSTED_PROXY_CIDRS is empty"
    else:
        reason = f"{peer} is not in TRUSTED_PROXY_CIDRS ({raw_cidrs})"

    _logger.warning(
        "Requests carry X-Forwarded-For but %s, so every client shares the rate-limit "
        "bucket for peer %s. Set TRUST_PROXY_HEADERS=true and list this proxy in "
        "TRUSTED_PROXY_CIDRS — only if the proxy overwrites X-Forwarded-For rather "
        "than appending to it.",
        reason,
        peer,
    )


limiter = Limiter(key_func=_client_ip)
