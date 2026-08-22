from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware

# `frontend/index.html` links the Inter/Outfit/JetBrains Mono webfonts. Google
# serves the @font-face stylesheet from one host and the font files it points
# at from another, so both have to be allowed or the browser blocks the
# stylesheet outright and the app renders in the fallback system font.
_GOOGLE_FONTS_CSS = "https://fonts.googleapis.com"
_GOOGLE_FONTS_FILES = "https://fonts.gstatic.com"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, production: bool = False):
        super().__init__(app)
        self.production = production

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; base-uri 'self'; frame-ancestors 'none'; object-src 'none'; "
            f"img-src 'self' data: https:; font-src 'self' data: {_GOOGLE_FONTS_FILES}; "
            f"style-src 'self' 'unsafe-inline' {_GOOGLE_FONTS_CSS}; script-src 'self'; "
            "connect-src 'self' ws: wss: https:",
        )
        if self.production and request.url.scheme == "https":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response
