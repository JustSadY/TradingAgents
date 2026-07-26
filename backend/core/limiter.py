from ipaddress import ip_address

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.core.config import get_settings


def _client_ip(request: Request) -> str:
    """Rate-limit key: the caller's IP.

    By default this is ``request.client.host`` — the only value a client
    can't spoof. When ``TRUST_PROXY_HEADERS`` is explicitly enabled (because
    this deployment sits behind a reverse proxy that overwrites, not appends
    to, X-Forwarded-For), use the left-most address in that header instead —
    otherwise every request behind the proxy collapses into one shared
    bucket (e.g. the login rate limit becomes "10/min for the whole server").
    """
    if get_settings().TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
            try:
                # Do not use arbitrary header text as a limiter key.  Aside
                # from keeping the key space bounded, this makes a malformed
                # proxy header fail closed to the directly connected proxy.
                return str(ip_address(client_ip))
            except ValueError:
                pass
    return get_remote_address(request)


limiter = Limiter(key_func=_client_ip)
