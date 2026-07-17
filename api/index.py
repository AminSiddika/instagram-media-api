"""FastAPI application entry point for Vercel serverless deployment."""

import logging
import secrets
import time
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.auth import (
    AuthError,
    ExpiredKeyError,
    InvalidKeyError,
    issue_api_key,
    validate_api_key,
)
from api.config import get_settings
from api.extractor import ExtractionError, extract_instagram_post
from api.models import (
    ErrorResponse,
    HealthResponse,
    InstagramPostResponse,
    IssueKeyRequest,
    IssueKeyResponse,
    VerifyKeyResponse,
)
from api.security import (
    check_rate_limit,
    is_private_ip,
    log_request,
    record_failed_auth,
    validate_and_maybe_rotate,
)

# Configure logging
settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Validate critical configuration at startup
if not settings.aes_key:
    logger.warning("AES_KEY is not set. Auth endpoints will fail until it is configured.")
if not settings.master_api_key:
    logger.warning("MASTER_API_KEY is not set. Master-only endpoints will be unreachable.")

app = FastAPI(
    title=settings.app_name,
    description=settings.app_description,
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

bearer_scheme = HTTPBearer(auto_error=False)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add request ID and security headers to every response."""
    request_id = request.headers.get("x-request-id") or secrets.token_hex(8)
    start = time.time()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # Remove server header if present
    if "server" in response.headers:
        del response.headers["server"]
    return response


async def get_api_key(
    request: Request,
    authorization: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> Optional[str]:
    """Extract the API key from Authorization header or X-API-Key header."""
    if authorization:
        return authorization.credentials
    if x_api_key:
        return x_api_key
    # Fallback to query param for easy browser testing (not recommended in production)
    return request.query_params.get("api_key")


async def require_api_key(
    request: Request,
    response: Response,
    api_key: Optional[str] = Depends(get_api_key),
) -> dict:
    """Dependency that validates the API key, enforces rate limits, rotates single-use keys, and returns payload."""
    try:
        return validate_and_maybe_rotate(api_key, request, response, settings)
    except ExpiredKeyError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except InvalidKeyError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except AuthError as exc:
        logger.error("Auth configuration error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


async def require_master_key(
    request: Request,
    api_key: Optional[str] = Depends(get_api_key),
) -> dict:
    """Dependency that requires the static master key."""
    check_rate_limit(api_key, request, settings)
    if not api_key:
        record_failed_auth(api_key, request, settings)
        raise HTTPException(status_code=401, detail="API key is missing")
    if not settings.master_api_key or api_key != settings.master_api_key:
        record_failed_auth(api_key, request, settings)
        raise HTTPException(status_code=403, detail="Master key required")
    log_request(request, api_key, status="master_authenticated")
    return {
        "kid": "master",
        "role": "admin",
        "exp": None,
        "type": "master",
    }


@app.exception_handler(ExtractionError)
async def extraction_error_handler(_: Any, exc: ExtractionError) -> JSONResponse:
    """Return a clean 400 response for extraction failures."""
    logger.warning("Extraction error: %s", exc)
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)},
    )


@app.exception_handler(AuthError)
async def auth_error_handler(_: Any, exc: AuthError) -> JSONResponse:
    """Return a clean 500 response for auth configuration failures."""
    logger.error("Auth error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)},
    )


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root() -> HTMLResponse:
    """Serve a friendly landing page."""
    return HTMLResponse(
        content=f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{settings.app_name}</title>
    <style>
        :root {{
            --bg: #0f0c19;
            --text: #f3f0ff;
            --muted: #8f8aa3;
            --accent: #e6683c;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background: var(--bg);
            color: var(--text);
            font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            text-align: center;
            padding: 2rem;
        }}
        .container {{ max-width: 520px; }}
        h1 {{ font-size: 2.5rem; margin-bottom: 1rem; }}
        p {{ color: var(--muted); line-height: 1.6; margin-bottom: 1.5rem; }}
        .links {{ display: flex; gap: 0.75rem; justify-content: center; flex-wrap: wrap; }}
        a {{
            color: var(--text);
            text-decoration: none;
            border: 1px solid rgba(255,255,255,0.12);
            padding: 0.6rem 1.2rem;
            border-radius: 999px;
            transition: all 0.2s ease;
        }}
        a:hover {{ background: white; color: var(--bg); border-color: white; }}
        .version {{ color: var(--accent); font-weight: 600; font-size: 0.85rem; letter-spacing: 0.1em; text-transform: uppercase; margin-top: 2rem; display: block; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{settings.app_name}</h1>
        <p>{settings.app_description}</p>
        <div class="links">
            <a href="/docs">Swagger UI</a>
            <a href="/redoc">ReDoc</a>
            <a href="/api/health">Health</a>
        </div>
        <span class="version">v{settings.app_version}</span>
    </div>
</body>
</html>"""
    )


@app.get(
    "/api/health",
    response_model=HealthResponse,
    summary="Health check",
    tags=["Monitoring"],
)
async def health_check(request: Request) -> HealthResponse:
    """Return API health status."""
    log_request(request, status="health")
    return HealthResponse(status="ok", version=settings.app_version)


@app.post(
    "/api/auth/issue-key",
    response_model=IssueKeyResponse,
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
    summary="Issue a new encrypted API key",
    tags=["Authentication"],
)
async def issue_key(
    request: Request,
    body: IssueKeyRequest,
    _: dict = Depends(require_master_key),
) -> IssueKeyResponse:
    """Generate an AES-encrypted API key with expiry (master key required)."""
    try:
        token = issue_api_key(
            settings,
            role=body.role,
            ttl_hours=body.ttl_hours,
            key_id=body.key_id,
            single_use=body.single_use,
        )
        # Decode to extract metadata for the response
        payload = validate_api_key(token, settings)
        return IssueKeyResponse(
            api_key=token,
            expires_at=payload["exp"],
            role=payload["role"],
            key_id=payload["kid"],
            single_use=payload.get("single_use", True),
        )
    except AuthError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get(
    "/api/auth/verify-key",
    response_model=VerifyKeyResponse,
    responses={401: {"model": ErrorResponse}},
    summary="Verify an API key",
    tags=["Authentication"],
)
async def verify_key(
    request: Request,
    response: Response,
    api_key: Optional[str] = Depends(get_api_key),
) -> VerifyKeyResponse:
    """Check whether the provided API key is valid and not expired.

    Single-use keys are rotated automatically and the new key is returned in
    the X-New-API-Key response header.
    """
    try:
        payload = validate_and_maybe_rotate(api_key, request, response, settings)
        return VerifyKeyResponse(
            valid=True,
            key_id=payload["kid"],
            role=payload["role"],
            expires_at=payload.get("exp"),
            type=payload.get("type", "issued"),
            single_use=payload.get("single_use", True),
        )
    except ExpiredKeyError:
        return VerifyKeyResponse(
            valid=False,
            key_id="",
            role="",
            expires_at=None,
            type="expired",
            single_use=None,
        )
    except InvalidKeyError:
        return VerifyKeyResponse(
            valid=False,
            key_id="",
            role="",
            expires_at=None,
            type="invalid",
            single_use=None,
        )


@app.get(
    "/api/fetch",
    response_model=InstagramPostResponse,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    summary="Extract Instagram media",
    tags=["Extraction"],
)
async def fetch_media(
    request: Request,
    url: str = Query(
        ...,
        description="Public Instagram post, Reel, or IGTV URL",
        examples=["https://www.instagram.com/p/ABC123xyz/"],
    ),
) -> InstagramPostResponse:
    """Fetch media URLs and metadata for a public Instagram post."""
    log_request(request, status="fetch_start")
    try:
        result = extract_instagram_post(url, settings)
        log_request(request, status="fetch_ok")
        return result
    except ExtractionError:
        raise
    except Exception as exc:
        logger.exception("Unexpected error during extraction")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while processing the request.",
        ) from exc


@app.get(
    "/api/proxy",
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    summary="Proxy a media file",
    tags=["Extraction"],
)
async def proxy_media(
    request: Request,
    url: str = Query(
        ...,
        description="Direct URL of the media file to proxy",
    ),
) -> Response:
    """Proxy an Instagram media file to avoid CORS and referer issues."""
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Invalid URL scheme.")

    try:
        from curl_cffi import requests as cf

        response = cf.get(
            url,
            headers={"User-Agent": "Mozilla/5.0"},
            impersonate=settings.impersonate_browser,
            timeout=settings.proxy_timeout,
        )
    except Exception as exc:
        logger.exception("Proxy request failed")
        raise HTTPException(
            status_code=500, detail="Failed to proxy media."
        ) from exc

    content_type = response.headers.get("content-type", "application/octet-stream")
    return Response(
        content=response.content,
        media_type=content_type,
        headers={
            "Cache-Control": "public, max-age=86400",
            "Access-Control-Allow-Origin": "*",
        },
    )
