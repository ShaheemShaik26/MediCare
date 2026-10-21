from __future__ import annotations

from collections import OrderedDict
from threading import Lock
from time import monotonic
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from app.api.routes.account import router as account_router
from app.api.routes.auth import router as auth_router
from app.api.routes.documents import router as documents_router
from app.api.routes.lifestyle import router as lifestyle_router
from app.api.routes.knowledge import router as knowledge_router
from app.config import settings


app = FastAPI(title=settings.app_name, version="0.1.0")
_RATE_LIMITS = {
    "/api/auth/login": (10, 60),
    "/api/auth/register": (5, 60 * 60),
    "/api/documents/upload": (20, 60),
    "/api/knowledge/search": (10, 60),
}
_rate_limit_entries: OrderedDict[tuple[str, str], tuple[float, int]] = OrderedDict()
_rate_limit_lock = Lock()


def _request_origin(request: Request) -> str | None:
    try:
        origin = request.headers.get("origin")
        if origin:
            parsed = urlsplit(origin)
            if parsed.path or parsed.query or parsed.fragment:
                return ""
        else:
            referer = request.headers.get("referer")
            if not referer:
                return None
            parsed = urlsplit(referer)
    except ValueError:
        return ""
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username
        or parsed.password
    ):
        return ""
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def _is_allowed_origin(request: Request) -> bool:
    request_origin = _request_origin(request)
    if request_origin is None:
        return False
    allowed_origins = {
        origin.strip().rstrip("/").lower()
        for origin in settings.cors_origins.split(",")
        if origin.strip()
    }
    return request_origin in allowed_origins


def _is_rate_limited(request: Request, now: float) -> tuple[bool, int]:
    policy = _RATE_LIMITS.get(request.url.path)
    if policy is None:
        return False, 0

    limit, window_seconds = policy
    client_host = request.client.host if request.client else "unknown"
    key = (client_host, request.url.path)
    with _rate_limit_lock:
        if len(_rate_limit_entries) >= 8192:
            expired_before = now - max(window for _, window in _RATE_LIMITS.values())
            for stored_key, (window_start, _) in list(_rate_limit_entries.items()):
                if window_start <= expired_before:
                    del _rate_limit_entries[stored_key]
            while len(_rate_limit_entries) >= 8192:
                _rate_limit_entries.popitem(last=False)

        window_start, count = _rate_limit_entries.get(key, (now, 0))
        if now - window_start >= window_seconds:
            window_start, count = now, 0
        count += 1
        _rate_limit_entries[key] = (window_start, count)
        _rate_limit_entries.move_to_end(key)
        if count > limit:
            return True, max(1, int(window_seconds - (now - window_start)))
    return False, 0

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _add_security_headers(response: Response, is_api_response: bool) -> Response:
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if is_api_response:
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
        )
    if settings.secure_cookies:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


@app.middleware("http")
async def harden_api_requests(request: Request, call_next):
    response = None
    if request.url.path.startswith("/api/") and request.method not in {"GET", "HEAD", "OPTIONS"}:
        if request.headers.get("origin") or request.headers.get("referer"):
            if not _is_allowed_origin(request):
                response = JSONResponse(
                    status_code=403,
                    content={"detail": "Request origin is not allowed"},
                )
        elif request.cookies.get("medicare_session"):
            response = JSONResponse(
                status_code=403,
                content={"detail": "Origin or Referer header is required"},
            )

        if response is None:
            limited, retry_after = _is_rate_limited(request, monotonic())
            if limited:
                response = JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests; please try again later."},
                    headers={"Retry-After": str(retry_after)},
                )

    if response is None:
        response = await call_next(request)
    return _add_security_headers(response, request.url.path.startswith("/api/"))


app.include_router(auth_router)
app.include_router(account_router)
app.include_router(documents_router)
app.include_router(lifestyle_router)
app.include_router(knowledge_router)


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
